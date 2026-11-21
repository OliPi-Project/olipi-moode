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
            bias = 1.79
        elif n_mels <= 41:
            bias = 1.75
        else:
            bias = 1.7
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
    def __init__(self, n_bars=21):
        super().__init__(daemon=True)

        self.device="hw:Loopback,1,0"
        self.n_bars=int(n_bars)
        self.win_s=4096
        self.hop_s=1024
        self.fmin=20
        self.fmax=None
        self.debug=False

        self._warmup_frames = 16
        self._warmup_count = 0

        self.running=True
        self.available=False

        self._open_device()

    def _open_device(self):
        try:
            self.rec = alsaaudio.PCM(
                type=alsaaudio.PCM_CAPTURE,
                mode=alsaaudio.PCM_NONBLOCK,
                device=self.device
            )
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

        period_size = int(
            round(self.hop_s * self.samplerate / self.effective_sr)
        )

        try:
            self.rec.setperiodsize(period_size)
        except:
            pass

        # Pre-compute window and FFT bins
        self.window = hann(self.win_s).astype(np.float32)
        self.n_fft_bins = self.win_s // 2 + 1
        self.freqs = np.fft.rfftfreq(self.win_s, d=1.0/self.effective_sr)

        # Build filters
        self.filters = build_mel_filterbank(self.win_s, self.effective_sr, self.n_bars, self.fmin, self.fmax)

        self.baseline = np.ones(self.n_bars, dtype=np.float32)
        self.levels = np.zeros(self.n_bars, dtype=np.float32)
        self.stream_buf = np.zeros(self.win_s, dtype=np.float32)

        self.vu_left = 0.0
        self.vu_right = 0.0

        self.rms_window = 2048
        self.rms_ring = np.zeros((self.rms_window, 2), dtype=np.float32)
        self.rms_pos = 0
        self.rms_count = 0
        self.rms_sum_sq = np.zeros(2, dtype=np.float64)

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

    def get_channel_peaks(self, volume_state=None, mixer_type=None, bt_active=False, soft_correct=True):
        # --- linear -> dB ---
        def lin2db(x): return -999.0 if x<=0 else 20*np.log10(x)

        # --- read stored normalized values ---
        lp = float(getattr(self, "peak_left", 0.0))
        rp = float(getattr(self, "peak_right", 0.0))
        lr = float(getattr(self, "rms_left", 0.0))
        rr = float(getattr(self, "rms_right", 0.0))

        lv = float(getattr(self, "vu_left", 0.0))
        rv = float(getattr(self, "vu_right", 0.0))

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

        lv_norm = lv * used_full_scale / nominal_full_scale
        rv_norm = rv * used_full_scale / nominal_full_scale

        # --- parse volume ---
        vol_step = None
        try:
            if isinstance(volume_state, str):
                vol_step = 0.0 if volume_state.lower()=="mute" else int(volume_state)
            elif volume_state is not None:
                vol_step = int(volume_state)
        except Exception:
            vol_step = None

        SOFTVOL_CORRECTION = [
            (1, 1, 999.909799),
            (2, 2, 558.219624),
            (3, 3, 511.914522),
            (4, 4, 355.414138),
            (5, 5, 265.354404),
            (6, 6, 208.250714),
            (7, 7, 173.800711),
            (8, 8, 149.124380),
            (9, 9, 129.286090),
            (10, 10, 115.121330),
            (11, 11, 95.458883),
            (12, 12, 85.705590),
            (13, 13, 79.242250),
            (14, 14, 73.687233),
            (15, 15, 65.076015),
            (16, 16, 60.506955),
            (17, 17, 54.496762),
            (18, 18, 51.528156),
            (19, 19, 47.102732),
            (20, 20, 44.670586),
            (21, 21, 41.301498),
            (22, 22, 38.219333),
            (23, 23, 35.563328),
            (24, 24, 33.143819),
            (25, 25, 31.175925),
            (26, 26, 29.429196),
            (27, 27, 27.829631),
            (28, 28, 26.394838),
            (29, 29, 24.561416),
            (30, 30, 23.381531),
            (31, 31, 21.967000),
            (32, 32, 20.544366),
            (33, 33, 19.750346),
            (34, 34, 18.696665),
            (35, 35, 17.749156),
            (36, 36, 16.626118),
            (37, 37, 15.828345),
            (38, 38, 15.126329),
            (39, 39, 14.323843),
            (40, 40, 13.565392),
            (41, 41, 13.025002),
            (42, 42, 12.382804),
            (43, 43, 11.687966),
            (44, 44, 11.155196),
            (45, 45, 10.700838),
            (46, 46, 10.177031),
            (47, 47, 9.695480),
            (48, 48, 9.257221),
            (49, 49, 8.786778),
            (50, 50, 8.428378),
            (51, 51, 8.028800),
            (52, 52, 7.668093),
            (53, 53, 7.338640),
            (54, 54, 7.000161),
            (55, 55, 6.719589),
            (56, 56, 6.428450),
            (57, 57, 6.124998),
            (58, 58, 5.875261),
            (59, 59, 5.614328),
            (60, 60, 5.384208),
            (61, 61, 5.137784),
            (62, 62, 4.915911),
            (63, 63, 4.722107),
            (64, 64, 4.516482),
            (65, 65, 4.321119),
            (66, 66, 4.131190),
            (67, 67, 3.955420),
            (68, 68, 3.794251),
            (69, 69, 3.634073),
            (70, 70, 3.485519),
            (71, 71, 3.335419),
            (72, 72, 3.199926),
            (73, 73, 3.073037),
            (74, 74, 2.938745),
            (75, 75, 2.817323),
            (76, 76, 2.705647),
            (77, 77, 2.590654),
            (78, 78, 2.481311),
            (79, 79, 2.383054),
            (80, 80, 2.287859),
            (81, 81, 2.192396),
            (82, 82, 2.102845),
            (83, 83, 2.017906),
            (84, 84, 1.932556),
            (85, 85, 1.859233),
            (86, 86, 1.780365),
            (87, 87, 1.709011),
            (88, 88, 1.642460),
            (89, 89, 1.574732),
            (90, 90, 1.510430),
            (91, 91, 1.451799),
            (92, 92, 1.393113),
            (93, 93, 1.335759),
            (94, 94, 1.282317),
            (95, 95, 1.231484),
            (96, 96, 1.181872),
            (97, 97, 1.133704),
            (98, 98, 1.090321),
            (99, 99, 1.044869),
            (100, 100, 1.003091),
        ]

        SOFTVOL_MAP = {vmin: factor for vmin, _, factor in SOFTVOL_CORRECTION}

        def get_softvol_factor(volume):
            return SOFTVOL_MAP.get(volume, 1.0)

        raw_lp_norm = lp_norm
        raw_rp_norm = rp_norm
        factor = 1.0

        if (
            not bt_active
            and soft_correct == True
            and mixer_type == "software"
            and vol_step
            and vol_step > 0
        ):
            factor = get_softvol_factor(vol_step)
            lp_norm *= factor
            rp_norm *= factor
            lr_norm *= factor
            rr_norm *= factor

            lv_norm *= factor
            rv_norm *= factor

        if self.debug:
            now = time.monotonic()
            last = getattr(self, "_softvol_debug_ts", 0)

            if now - last >= 1.0:
                print(
                    f"[SOFTVOL] volume={vol_step} factor={factor:.3f} | "
                    f"raw L/R={raw_lp_norm:.4f}/{raw_rp_norm:.4f} | "
                    f"corrected L/R={lp_norm:.4f}/{rp_norm:.4f}"
                )
                self._softvol_debug_ts = now

        out = {
            "left_peak":lp_norm, "right_peak":rp_norm,
            "left_rms":lr_norm, "right_rms":rr_norm,
            "left_peak_db":lin2db(lp_norm), "right_peak_db":lin2db(rp_norm),
            "left_rms_db":lin2db(lr_norm), "right_rms_db":lin2db(rr_norm),
            "left_vu": lv_norm, "right_vu": rv_norm,
        }

        return out

    def get_levels(self):
        if not self.available:
            return np.zeros(self.n_bars,dtype=np.float32)
        return self.levels.copy()

    def update_vu(self, rms_left, rms_right, dt):
        # RMS level targets
        target_rms_left = rms_left
        target_rms_right = rms_right
        attack = 0.300
        release = 0.300
        # Left
        tau_left = attack if target_rms_left > self.vu_left else release
        alpha_left = 1.0 - np.exp(-dt / tau_left)
        self.vu_left += alpha_left * (target_rms_left - self.vu_left)
        # Right
        tau_right = attack if target_rms_right > self.vu_right else release
        alpha_right = 1.0 - np.exp(-dt / tau_right)
        self.vu_right += alpha_right * (target_rms_right - self.vu_right)

    def update_rms_window(self, stereo):
        n = stereo.shape[0]
        if n >= self.rms_window:
            # The block is at least as large as the window:
            # only the most recent samples are retained.
            stereo = stereo[-self.rms_window:]
            n = self.rms_window
            self.rms_ring[:] = stereo
            self.rms_sum_sq[:] = np.sum(
                stereo.astype(np.float64) ** 2,
                axis=0
            )
            self.rms_pos = 0
            self.rms_count = self.rms_window
        else:
            end = self.rms_pos + n
            if end <= self.rms_window:
                # No wrap
                old = self.rms_ring[self.rms_pos:end]
                self.rms_sum_sq -= np.sum(
                    old.astype(np.float64) ** 2,
                    axis=0
                )
                self.rms_ring[self.rms_pos:end] = stereo
                self.rms_sum_sq += np.sum(
                    stereo.astype(np.float64) ** 2,
                    axis=0
                )
            else:
                # Wrap around the ring
                first = self.rms_window - self.rms_pos
                second = n - first
                old1 = self.rms_ring[self.rms_pos:]
                old2 = self.rms_ring[:second]
                self.rms_sum_sq -= np.sum(
                    old1.astype(np.float64) ** 2,
                    axis=0
                )
                self.rms_sum_sq -= np.sum(
                    old2.astype(np.float64) ** 2,
                    axis=0
                )
                self.rms_ring[self.rms_pos:] = stereo[:first]
                self.rms_ring[:second] = stereo[first:]
                self.rms_sum_sq += np.sum(
                    stereo[:first].astype(np.float64) ** 2,
                    axis=0
                )
                self.rms_sum_sq += np.sum(
                    stereo[first:].astype(np.float64) ** 2,
                    axis=0
                )
            self.rms_pos = (self.rms_pos + n) % self.rms_window
            self.rms_count = min(
                self.rms_count + n,
                self.rms_window
            )
        count = max(1, self.rms_count)
        return (
            float(np.sqrt(self.rms_sum_sq[0] / count)),
            float(np.sqrt(self.rms_sum_sq[1] / count))
        )

    def run(self):
        if not self.available:
            return

        self.stream_buf = np.empty((0, 2), dtype=np.float32)

        while self.running:
            try:
                n, data = self.rec.read()
            except Exception:
                time.sleep(0.02)
                continue

            # avoid corner-case
            if n <= 0 or not data:
                self.levels *= 0.92
                self.update_vu(0.0, 0.0, 0.01)
                time.sleep(0.01)
                continue

            # compute bytes per sample reliably using number of frames returned by ALSA
            try:
                bytes_per_sample = max(1, len(data) // (max(1, n) * max(1, self.channels)))
            except Exception:
                bytes_per_sample = None

            fn = str(getattr(self, "format_name", "")).upper()

            # decode raw bytes into numeric arrays (float32 for further processing)
            """if bytes_per_sample == 4:
                # could be int32 or float32; prefer float if format_name mentions FLOAT
                if "FLOAT" in fn:
                    samples = np.frombuffer(data, dtype=np.float32)
                    full_scale = 1.0
                    scale_name = "full scale 1"
                else:
                    # read as int32
                    samples = np.frombuffer(data, dtype=np.int32).astype(np.float32)
                    # Heuristic: if the values fit in 24 bits -> it's probably S24_LE
                    # (right-justified in lower 24 bits) -> full_scale = 2**23
                    # otherwise -> probably 32-bit container left-justified -> full_scale = 2**31
                    absmax = float(np.max(np.abs(samples))) if samples.size else 0.0
                    if absmax < (1 << 24):
                        # samples are in 24-bit range
                        full_scale = float(2 ** 23)
                        scale_name = "2^23 (24-bit range)"
                    else:
                        # likely full 32-bit values
                        full_scale = float(2 ** 31)
                        scale_name = "2^31 (32-bit range)"""
            if bytes_per_sample == 4:
                if "FLOAT" in fn:
                    samples = np.frombuffer(data, dtype=np.float32)
                    full_scale = 1.0
                    scale_name = "full scale 1"
                elif "S24" in fn:
                    samples = np.frombuffer(data, dtype=np.int32).astype(np.float32)
                    full_scale = float(2 ** 23)
                    scale_name = "2^23 (24-bit range)"
                elif "S32" in fn:
                    samples = np.frombuffer(data, dtype=np.int32).astype(np.float32)
                    full_scale = float(2 ** 31)
                    scale_name = "2^31 (32-bit range)"
                else:
                    samples = np.frombuffer(data, dtype=np.int32).astype(np.float32)
                    full_scale = float(2 ** 31)
                    scale_name = "2^31 (32-bit fallback)"
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

            # helper debug header once per format switch
            if getattr(self, "_last_debug_fmt", None) != (fn, self.channels, bytes_per_sample, self.samplerate):
                self._last_debug_fmt = (fn, self.channels, bytes_per_sample, self.samplerate)

                if "FLOAT" in fn:
                    bits_info = "32-bit float"
                elif fn.startswith("S") and fn[1:3].isdigit():
                    bits_info = f"{fn[1:3]}-bit integer"
                else:
                    bits_info = "unknown"

                print(
                    f"[SPECTRO DBG] format={fn} "
                    f"rate={self.samplerate} Hz "
                    f"bits={bits_info} "
                    f"channels={self.channels} "
                    f"bytes_per_sample={bytes_per_sample} "
                    f"frames={n} bytes={len(data)}"
                )
                if bytes_per_sample == 4:
                    print(f"[SPECTRO DBG] scale= {scale_name}")

            # ensure we have whole frames: trim if necessary
            if self.channels and samples.size % self.channels != 0:
                valid = (samples.size // self.channels) * self.channels
                samples = samples[:valid]

            if samples.size == 0:
                self.levels *= 0.92
                time.sleep(0.001)
                continue

            # reshape to stereo (or duplicate mono)
            if self.channels == 2:
                stereo = samples.reshape(-1, 2)
            else:
                stereo = np.column_stack((samples, samples))

            left = stereo[:, 0]
            right = stereo[:, 1]

            # Compute peak and RMS
            peak_left = float(np.max(np.abs(left))) / full_scale
            peak_right = float(np.max(np.abs(right))) / full_scale

            #rms_left = float(np.sqrt(np.mean(left * left, dtype=np.float64))) / full_scale
            #rms_right = float(np.sqrt(np.mean(right * right, dtype=np.float64))) / full_scale
            rms_left, rms_right = self.update_rms_window(stereo)
            rms_left /= full_scale
            rms_right /= full_scale

            # Store raw measurements
            self.peak_left = peak_left
            self.peak_right = peak_right
            self.rms_left = rms_left
            self.rms_right = rms_right

            # Update smoothed RMS level
            dt = left.size / float(self.samplerate)
            self.update_vu(rms_left, rms_right, dt)

            #################
            # Spectrum
            ##############

            # stereo > mono

            #samples = np.sqrt((stereo[:,0]**2 + stereo[:,1]**2) * 0.5)
            #samples = (stereo[:, 0] + stereo[:, 1]) * 0.5

            # Keep left and right channels separate for spectrum analysis
            sr = self.samplerate
            while sr >= 88200:
                stereo = stereo[::2]
                sr //= 2

            # Append stereo data to stream buffer
            if self.stream_buf.size == 0:
                self.stream_buf = stereo
            else:
                self.stream_buf = np.concatenate((self.stream_buf, stereo), axis=0)

            # process as many frames as possible (win_s window, hop_s step)
            while self.stream_buf.shape[0] >= self.win_s and self.running:
                frame_left = self.stream_buf[:self.win_s, 0]
                frame_right = self.stream_buf[:self.win_s, 1]

                # FFT & average stereo power
                spec_left = rfft(frame_left * self.window, self.win_s)
                spec_right = rfft(frame_right * self.window, self.win_s)

                power_left = spec_left.real**2 + spec_left.imag**2
                power_right = spec_right.real**2 + spec_right.imag**2

                power = ((power_left + power_right) * 0.5).astype(np.float32)

                # band energies already computed
                band_energy = self.filters @ power

                # warmup baseline handling
                if self._warmup_count == 0:
                    self.baseline = np.maximum(band_energy, EPS)
                    self._warmup_count = 1

                elif self._warmup_count < self._warmup_frames:
                    self.baseline = 0.85 * self.baseline + 0.15 * (band_energy + EPS)
                    self._warmup_count += 1

                else:
                    self.baseline = 0.997 * self.baseline + 0.003 * band_energy

                # avoid insane ratios that create spikes
                ratio = band_energy / (self.baseline + EPS)
                # clamp upper ratio to avoid huge log1p results on weird inputs
                ratio = np.minimum(ratio, 1e3)   # tune 1e3 -> 1e4 if you want more headroom

                gate = 0.06 + 0.02 * (np.arange(self.n_bars) / self.n_bars)
                ratio = np.maximum(0.0, ratio - gate)

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
                if self.stream_buf.shape[0] > self.win_s * 8:
                    self.stream_buf = self.stream_buf[-self.win_s:]

            time.sleep(0.002)
