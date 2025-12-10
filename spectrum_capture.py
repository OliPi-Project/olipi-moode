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

    def stop(self):
        self.running=False
        try: self.rec.close()
        except: pass

    def get_channel_peaks(self, return_db=True, volume_state=None, mixer_type=None, volume_mpd_max=100.0):
        # --- init accumulators ---
        if not hasattr(self, "_rms_accum_hw"):
            self._rms_accum_hw = []
            self._rms_accum_sw = []
            self._peak_max_hw = 0.0
            self._peak_max_sw = 0.0

        # --- read stored normalized values ---
        lp = float(getattr(self, "peak_left", 0.0))
        rp = float(getattr(self, "peak_right", 0.0))
        lr = float(getattr(self, "rms_left", 0.0))
        rr = float(getattr(self, "rms_right", 0.0))

        # --- determine nominal full-scale ---
        fn = str(getattr(self, "format_name","")).upper()
        if "FLOAT" in fn: nominal_full_scale = 1.0
        elif "S24" in fn: nominal_full_scale = 2**23
        elif "S32" in fn: nominal_full_scale = 2**31
        elif "S16" in fn: nominal_full_scale = 32768.0
        else: nominal_full_scale = 2**23

        used_full_scale = getattr(self, "_full_scale", nominal_full_scale)

        # --- reconstruct sample-estimate ---
        lp_sample = lp * used_full_scale
        rp_sample = rp * used_full_scale
        lr_sample = lr * used_full_scale
        rr_sample = rr * used_full_scale

        # --- normalize ---
        lp_norm = lp_sample / nominal_full_scale
        rp_norm = rp_sample / nominal_full_scale
        lr_norm = lr_sample / nominal_full_scale
        rr_norm = rr_sample / nominal_full_scale

        # --- parse volume ---
        vol_lin = None
        try:
            if isinstance(volume_state, str):
                vol_lin = 0.0 if volume_state.lower()=="mute" else float(volume_state)/volume_mpd_max
            elif volume_state is not None:
                vol_lin = float(volume_state)/volume_mpd_max
        except Exception:
            vol_lin = None

        # --- reconstruct pre-volume for software ---
        EPS_GAIN = 1e-9
        if mixer_type and str(mixer_type).lower()=="software" and vol_lin not in (None,0.0):
            gain = 1.0 / max(vol_lin, EPS_GAIN)
            CORRECTION_FACTOR = 10.0
            lp_norm = min(lp_norm * gain * CORRECTION_FACTOR, 1.0)
            rp_norm = min(rp_norm * gain * CORRECTION_FACTOR, 1.0)
            lr_norm = min(lr_norm * gain * CORRECTION_FACTOR, 1.0)
            rr_norm = min(rr_norm * gain * CORRECTION_FACTOR, 1.0)

        # --- update accumulators ---
        rms_avg = (lr_norm + rr_norm) / 2.0
        peak_avg = max(lp_norm, rp_norm)

        if mixer_type and str(mixer_type).lower()=="hardware":
            self._rms_accum_hw.append(rms_avg)
            self._peak_max_hw = max(self._peak_max_hw, peak_avg)
        elif mixer_type and str(mixer_type).lower()=="software":
            self._rms_accum_sw.append(rms_avg)
            self._peak_max_sw = max(self._peak_max_sw, peak_avg)

        # --- linear -> dB ---
        def lin2db(x): return -999.0 if x<=0 else 20*np.log10(x)

        out = {
            "left_peak":lp_norm, "right_peak":rp_norm,
            "left_rms":lr_norm, "right_rms":rr_norm,
        }

        if return_db:
            out.update({
                "left_peak_db":lin2db(lp_norm),
                "right_peak_db":lin2db(rp_norm),
                "left_rms_db":lin2db(lr_norm),
                "right_rms_db":lin2db(rr_norm),
            })

        # --- debug prints ---
        if getattr(self, "debug", False):
            print(f"[PEAK] mixer={mixer_type!s} vol_state={volume_state!s} raw_norm=True used_full_scale={used_full_scale!s}")
            print(f"raw lp={lp_norm:.6f} rp={rp_norm:.6f}")
            print(f"display lp_db={out.get('left_peak_db'):.1f} rp_db={out.get('right_peak_db'):.1f}")

            # --- print average RMS and peak so far ---
            if self._rms_accum_hw:
                avg_hw_db = lin2db(np.mean(self._rms_accum_hw))
                print(f"Avg RMS HW: {avg_hw_db:.2f} dB, Peak HW: {lin2db(self._peak_max_hw):.2f} dB")
            if self._rms_accum_sw:
                avg_sw_db = lin2db(np.mean(self._rms_accum_sw))
                print(f"Avg RMS SW: {avg_sw_db:.2f} dB, Peak SW: {lin2db(self._peak_max_sw):.2f} dB")

        return out

    def get_levels(self):
        if not self.available:
            return np.zeros(self.n_bars,dtype=np.float32)
        return self.levels.copy()

    def run(self):
        if not self.available:
            return

        self.stream_buf = np.zeros(0, dtype=np.float32)

        while self.running:
            try:
                n, data = self.rec.read()
            except Exception:
                time.sleep(0.02)
                continue

            # avoid corner-case
            if n <= 0 or not data:
                self.levels *= 0.92
                time.sleep(0.01)
                continue

            # compute bytes per sample reliably using number of frames returned by ALSA
            try:
                bytes_per_sample = max(1, len(data) // (max(1, n) * max(1, self.channels)))
            except Exception:
                bytes_per_sample = None

            fn = str(getattr(self, "format_name", "")).upper()

            # helper debug header once per format switch
            if getattr(self, "_last_debug_fmt", None) != (fn, self.channels, bytes_per_sample):
                self._last_debug_fmt = (fn, self.channels, bytes_per_sample)
                print(f"[SPECTRO DBG] format_name={fn!r} channels={self.channels} bytes={len(data)} frames={n} bytes_per_sample={bytes_per_sample}")

            # decode raw bytes into numeric arrays (float32 for further processing)
            if bytes_per_sample == 4:
                # could be int32 or float32; prefer float if format_name mentions FLOAT
                if "FLOAT" in fn:
                    samples = np.frombuffer(data, dtype=np.float32)
                    full_scale = 1.0
                else:
                    # read as int32
                    samples = np.frombuffer(data, dtype=np.int32).astype(np.float32)
                    # Heuristic: if the values fit in 24 bits -> it's probably S24_LE
                    # (right-justified in lower 24 bits) -> full_scale = 2**23
                    # otherwise -> probably 32-bit container left-justified -> full_scale = 2**31
                    absmax = float(np.max(np.abs(samples))) if samples.size else 0.0
                    if absmax < (1 << 24):
                        # samples are in 24-bit range -> normalize on 2**23
                        full_scale = float(2 ** 23)
                    else:
                        # likely full 32-bit values (or left-justified 24->32) -> normalize on 2**31
                        full_scale = float(2 ** 31)
            elif bytes_per_sample == 3:
                # packed 24-bit little-endian: decode to int32 with sign extension
                b = np.frombuffer(data, dtype=np.uint8)
                if b.size % 3 != 0:
                    # trim tail if misaligned
                    b = b[: (b.size // 3) * 3]
                b = b.reshape(-1, 3)
                vals = (b[:, 0].astype(np.int32)
                        | (b[:, 1].astype(np.int32) << 8)
                        | (b[:, 2].astype(np.int32) << 16))
                # sign-extend 24->32
                mask = 0x800000
                vals = vals & 0xFFFFFF
                vals = np.where(vals & mask, vals - 0x1000000, vals).astype(np.int32)
                samples = vals.astype(np.float32)
                full_scale = float(2 ** 23)
            elif bytes_per_sample == 2:
                samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
                full_scale = 32768.0
            else:
                # fallback: try float32 first, else int16
                try:
                    samples = np.frombuffer(data, dtype=np.float32)
                    full_scale = 1.0
                except Exception:
                    samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
                    full_scale = 32768.0

            self._full_scale = full_scale

            # ensure we have whole frames: trim if necessary
            if self.channels and samples.size % self.channels != 0:
                valid = (samples.size // self.channels) * self.channels
                samples = samples[:valid]

            # reshape to stereo (or duplicate mono)
            if self.channels == 2:
                if samples.size == 0:
                    continue
                stereo = samples.reshape(-1, 2)
            else:
                stereo = np.column_stack((samples, samples))

            left = stereo[:, 0]
            right = stereo[:, 1]

            # compute peak and RMS normalized to 0..1 using chosen full_scale
            EPS_local = 1e-12
            peak_left = float(np.max(np.abs(left))) / (full_scale + EPS_local)
            peak_right = float(np.max(np.abs(right))) / (full_scale + EPS_local)
            rms_left = float(np.sqrt(np.mean(left.astype(np.float32) ** 2))) / (full_scale + EPS_local)
            rms_right = float(np.sqrt(np.mean(right.astype(np.float32) ** 2))) / (full_scale + EPS_local)

            # clamp & store
            self.peak_left = min(1.0, peak_left)
            self.peak_right = min(1.0, peak_right)
            self.rms_left = min(1.0, rms_left)
            self.rms_right = min(1.0, rms_right)

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
                    self.baseline = 0.997 * self.baseline + 0.003 * band_energy

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
                    self.levels = 0.82 * self.levels + 0.18 * rel

                # advance buffer by hop_s
                self.stream_buf = self.stream_buf[self.hop_s:]

                # safety: if buffer grew huge, keep only tail
                if self.stream_buf.size > self.win_s * 8:
                    self.stream_buf = self.stream_buf[-self.win_s:]

            time.sleep(0.002)
