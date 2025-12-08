#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2025 OliPi Project

# spectrum_capture.py

import threading, time
from typing import List, Tuple, Optional
import numpy as np
import alsaaudio
from scipy.fft import rfft, rfftfreq

EPS = 1e-12

def hann(n):
    return 0.5-0.5*np.cos(2*np.pi*np.arange(n)/n)

def build_mel_filterbank(n_fft, sr, n_mels, fmin=20.0, fmax=None, bias=None):
    if fmax is None:
        fmax = sr / 2.0
    # --- automatic bias ---
    if bias is None:
        if n_mels <= 14:
            bias = 2.3
        elif n_mels <= 21:
            bias = 2.2
        elif n_mels <= 31:
            bias = 1.9
        elif n_mels <= 34:
            bias = 1.85
        elif n_mels <= 36:
            bias = 1.83
        elif n_mels <= 38:
            bias = 1.80
        elif n_mels <= 41:
            bias = 1.76
        else:
            bias = 1.6
    def hz_to_mel(f):
        return 2595.0 * np.log10(1.0 + f / 700.0)
    def mel_to_hz(m):
        return 700.0 * (10.0 ** (m / 2595.0) - 1.0)
    n_fft_bins = n_fft // 2 + 1
    freqs = np.linspace(0.0, sr / 2.0, n_fft_bins)
    mel_min = hz_to_mel(fmin)
    mel_max = hz_to_mel(fmax)
    frac = np.linspace(0.0, 1.0, n_mels + 2)
    if bias != 1.0:
        frac = frac ** bias
    mels = mel_min + (mel_max - mel_min) * frac
    hz_points = mel_to_hz(mels)
    bin_pos = np.interp(hz_points, freqs, np.arange(n_fft_bins).astype(np.float32))
    fb = np.zeros((n_mels, n_fft_bins), dtype=np.float32)
    for i in range(n_mels):
        left = bin_pos[i]
        center = bin_pos[i + 1]
        right = bin_pos[i + 2]
        if center <= left or right <= center:
            ic = int(round(center))
            if 0 <= ic < n_fft_bins:
                fb[i, ic] = 1.0
            continue
        # rising slope
        start = max(0, int(np.floor(left)))
        end = min(n_fft_bins - 1, int(np.ceil(center)))
        for k in range(start, end + 1):
            fb[i, k] = max(fb[i, k], max(0.0, (k - left) / (center - left)))
        # falling slope
        start2 = max(0, int(np.floor(center)))
        end2 = min(n_fft_bins - 1, int(np.ceil(right)))
        for k in range(start2, end2 + 1):
            fb[i, k] = max(fb[i, k], max(0.0, (right - k) / (right - center)))
        # normalize
        s = fb[i].sum()
        if s > 0:
            fb[i] /= s
    return fb


class SpectrumCapture(threading.Thread):
    def __init__(self, n_bars=16):
        super().__init__(daemon=True)

        self.device="hw:Loopback,1,0"
        self.n_bars=int(n_bars)
        self.win_s=4096
        self.hop_s=1024
        self.fmin=10
        self.fmax=None
        self.debug=True

        self._warmup_frames = 16
        self._warmup_count = 0

        self.running=True
        self.available=False

        # AGC / reference smoothing
        self.last_rms_update_ts = time.time()
        self.rms_long_left = 1e-9
        self.rms_long_right = 1e-9
        self.rms_long_tau = 4.0   # seconds smoothing window (tunable)
        self.headroom_db = 12.0   # default headroom (tunable, 9..20)
        # safety min/max gain
        self.min_gain_db = -40.0  # don't boost quieter than -40 dB
        self.max_gain_db = 12.0   # limit max gain (prevent explosion)

        self._open_device()

    def _open_device(self):
        try:
            self.rec = alsaaudio.PCM(type=alsaaudio.PCM_CAPTURE, device=self.device)
            info = self.rec.info()
        except Exception as e:
            print("[Spectro] open fail:",e)
            self.available=False
            return

        self.available=True
        self.samplerate = info.get("rate", 44100)
        self.channels = info.get("channels", 2)
        self.format_name = info.get("format_name","S16_LE")

        self.effective_sr = self.samplerate
        while self.effective_sr >= 88200:
            self.effective_sr //= 2

        # compute window/hop respecting samplerate factor
        factor = float(self.effective_sr) / 44100.0
        self.win_s = int(max(64, int(self.win_s) * factor))
        self.hop_s = int(max(32, int(self.hop_s) * factor))

        try: self.rec.setperiodsize(self.hop_s)
        except:
            pass

        # Pre-compute window and FFT bins
        self.window = hann(self.win_s).astype(np.float32)
        self.n_fft_bins = self.win_s // 2 + 1
        self.freqs = np.fft.rfftfreq(self.win_s, d=1.0/self.effective_sr)

        # Build filters
        self.filters = build_mel_filterbank(self.win_s, self.effective_sr, self.n_bars, self.fmin, self.fmax)

        # avoid tiny baseline that explodes log1p(band/baseline)
        init_level = 3.0     # <-- arbitrary log-unit target (bars ~ medium)
        init_rel = np.expm1(init_level)  # inverse log1p

        noise_ref = (self.effective_sr * 1e-6)  # proportional ref floor (tunable)
        self.baseline = np.ones(self.n_bars, dtype=np.float32) * noise_ref
        self.levels = np.zeros(self.n_bars, dtype=np.float32)
        self.stream_buf = np.zeros(self.win_s, dtype=np.float32)

        if self.debug:
            self.debug_filterbank(show=self.n_bars)

    def debug_filterbank(self, show=12):
        print(f"samplerate: {self.samplerate} - Effective_sr: {self.effective_sr} - n_fft: {self.win_s} - n_fft_bins: {self.n_fft_bins} - hop_s: {self.hop_s}")
        print(f"first freqs by bin:", [f"{f:.1f}" for f in self.freqs[:show]])
        centers = []
        for i in range(self.filters.shape[0]):
            row = self.filters[i]
            s = row.sum()
            if s <= 0:
                centers.append(0.0)
            else:
                centers.append(float((row * self.freqs[:row.size]).sum() / s))
        print("%d filter center freqs: %s" % (min(show, len(centers)), [f"{c:.1f}" for c in centers[:show]]))
        for i in range(min(show, self.filters.shape[0])):
            idx = np.where(self.filters[i] > 0)[0]
            if idx.size:
                print(f"band {i}: {self.freqs[idx[0]]:.1f} -> {self.freqs[idx[-1]]:.1f} Hz (bins {idx[0]}..{idx[-1]})")

    def _format_to_dtype(self):
        if "24" in self.format_name: return np.int32
        return np.int16

    def stop(self):
        self.running=False
        try: self.rec.close()
        except: pass

    def get_channel_peaks(self, return_db=True, use_agc=True):
        """
        Returns a dict with:
        left_peak, right_peak, left_rms, right_rms (linear 0..1)
        left_peak_db, right_peak_db, left_rms_db (raw dBFS)
        left_peak_agc, right_peak_agc, left_peak_agc_db, right_peak_agc_db (after AGC/gain & compression)
        """
        if not self.available:
            return {
                "left_peak":0.0,"right_peak":0.0,"left_rms":0.0,"right_rms":0.0,
                "left_peak_db":-999.0,"right_peak_db":-999.0,"left_rms_db":-999.0,"right_rms_db":-999.0,
                "left_peak_agc":0.0,"right_peak_agc":0.0,"left_peak_agc_db":-999.0,"right_peak_agc_db":-999.0,
            }

        lp = float(getattr(self, "peak_left", 0.0))
        rp = float(getattr(self, "peak_right", 0.0))
        lr = float(getattr(self, "rms_left", 0.0))
        rr = float(getattr(self, "rms_right", 0.0))

        def lin_to_db(a):
            if a <= 0.0:
                return -999.0
            return float(20.0 * np.log10(a))

        out = {
            "left_peak": lp, "right_peak": rp,
            "left_rms": lr, "right_rms": rr,
            "left_peak_db": lin_to_db(lp), "right_peak_db": lin_to_db(rp),
            "left_rms_db": lin_to_db(lr), "right_rms_db": lin_to_db(rr),
        }

        # AGC: derive reference db from long RMS + headroom
        if use_agc:
            # pick channel-average long RMS (you can use max, mean, or any rule)
            rms_long = max(1e-12, 0.5 * (self.rms_long_left + self.rms_long_right))
            rms_long_db = lin_to_db(rms_long)
            ref_db = rms_long_db + float(getattr(self, "headroom_db", 12.0))

            # clamp ref_db so gain doesn't explode
            ref_db = max(self.min_gain_db, min(ref_db, self.max_gain_db))

            # linear gain to apply
            gain_lin = 10.0 ** (-ref_db / 20.0)

            # optional mild compression after gain to tame peaks (soft saturator)
            def compress_lin(x):
                # x >= 0
                # simple soft-knee compressor: out = x / (1 + x)
                return x / (1.0 + x)

            lp_agc = min(1.0, compress_lin(lp * gain_lin))
            rp_agc = min(1.0, compress_lin(rp * gain_lin))

            out.update({
                "left_peak_agc": float(lp_agc),
                "right_peak_agc": float(rp_agc),
                "left_peak_agc_db": lin_to_db(lp_agc),
                "right_peak_agc_db": lin_to_db(rp_agc),
                "ref_db": float(ref_db),
                "rms_long_db": float(rms_long_db),
            })
        else:
            # if not using AGC, copy raw to agc fields
            out.update({
                "left_peak_agc": lp, "right_peak_agc": rp,
                "left_peak_agc_db": lin_to_db(lp), "right_peak_agc_db": lin_to_db(rp),
                "ref_db": None, "rms_long_db": None,
            })

        return out

    def get_levels(self):
        if not self.available:
            return np.zeros(self.n_bars,dtype=np.float32)
        return self.levels.copy()

    def run(self):
        if not self.available:
            return

        dtype = self._format_to_dtype()
        # streaming buffer (float32)
        self.stream_buf = np.zeros(0, dtype=np.float32)

        while self.running:
            try:
                n, data = self.rec.read()
            except Exception:
                time.sleep(0.02)
                continue

            if n <= 0 or not data:
                # decay display levels gently
                self.levels *= 0.92
                time.sleep(0.01)
                continue

            # convert PCM to float32
            samples = np.frombuffer(data, dtype=dtype).astype(np.float32)

            # stereo -> mono
            if self.channels == 2 and samples.size % 2 == 0:
                stereo = samples.reshape(-1, 2)
            else:
                stereo = np.column_stack((samples, samples))

            left = stereo[:, 0]
            right = stereo[:, 1]

            # compute sample-peak and rms per channel (raw integer -> float)
            full_scale = 2 ** (8 * np.dtype(dtype).itemsize - 1)  # e.g. int16 -> 32768, int32->2**31
            # but better: if dtype == np.int16: full_scale=32768, if int32 and 24-bit: 2**23
            if dtype == np.int16:
                full_scale = 32768.0
            else:
                # approximate for int32 used for 24-bit capture
                full_scale = float(2 ** 23)

            # normalize to 0..1
            peak_left = float(np.max(np.abs(left))) / (full_scale + EPS)
            peak_right = float(np.max(np.abs(right))) / (full_scale + EPS)
            rms_left = float(np.sqrt(np.mean(left.astype(np.float32) ** 2))) / (full_scale + EPS)
            rms_right = float(np.sqrt(np.mean(right.astype(np.float32) ** 2))) / (full_scale + EPS)

            # store in the object for drawing
            self.peak_left = min(1.0, peak_left)
            self.peak_right = min(1.0, peak_right)
            self.rms_left = min(1.0, rms_left)
            self.rms_right = min(1.0, rms_right)

            # timestamp & alpha calc for exponential smoothing (time-aware)
            now_ts = time.time()
            dt = max(1e-6, now_ts - getattr(self, "last_rms_update_ts", now_ts))
            self.last_rms_update_ts = now_ts

            # compute alpha from tau: alpha = 1 - exp(-dt / tau)
            alpha = 1.0 - np.exp(-dt / max(1e-6, self.rms_long_tau))

            # update long-term RMS (per-channel)
            # use the current frame rms (rms_left/rms_right computed earlier)
            self.rms_long_left = (1.0 - alpha) * getattr(self, "rms_long_left", rms_left) + alpha * rms_left
            self.rms_long_right = (1.0 - alpha) * getattr(self, "rms_long_right", rms_right) + alpha * rms_right

            #################
            # Spectrum
            ##############
            # stereo > mono
            samples = np.sqrt((stereo[:,0]**2 + stereo[:,1]**2) * 0.5)

            sr = self.samplerate
            while sr >= 88200:
                samples = samples[::2]
                sr //= 2

            # append to stream buffer
            if self.stream_buf.size == 0:
                self.stream_buf = samples
            else:
                self.stream_buf = np.concatenate((self.stream_buf, samples))

            # process as many frames as possible (win_s window, hop_s step)
            while self.stream_buf.size >= self.win_s and self.running:
                frame = self.stream_buf[:self.win_s]

                # FFT & power
                spec = rfft(frame * self.window, self.win_s)
                power = (spec.real ** 2 + spec.imag ** 2).astype(np.float32)

                # band energies already computed
                band_energy = self.filters @ power

                # warmup baseline handling
                if self._warmup_count < self._warmup_frames:
                    self.baseline = 0.85 * self.baseline + 0.15 * (band_energy + EPS)
                    self._warmup_count += 1
                else:
                    self.baseline = 0.990 * self.baseline + 0.010 * band_energy

                # avoid insane ratios that create spikes
                ratio = band_energy / (self.baseline + EPS)
                # clamp upper ratio to avoid huge log1p results on weird inputs
                ratio = np.minimum(ratio, 1e3)   # tune 1e3 -> 1e4 if you want more headroom

                rel = np.log1p(ratio).astype(np.float32)

                # if first warmup frame(s) -> initialize visual levels more gently
                if self._warmup_count <= 2:
                    # give levels a head start from rel (not full), avoids instant full bars
                    self.levels = 0.5 * rel
                else:
                    # smoothing into levels
                    self.levels = 0.78 * self.levels + 0.22 * rel

                # advance buffer by hop_s
                self.stream_buf = self.stream_buf[self.hop_s:]

                # safety: if buffer grew huge, keep only tail
                if self.stream_buf.size > self.win_s * 8:
                    self.stream_buf = self.stream_buf[-self.win_s:]

            time.sleep(0.001)
