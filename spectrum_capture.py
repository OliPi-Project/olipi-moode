#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2025 OliPi Project (Benoit Toufflet)

import threading, time
import numpy as np
import alsaaudio
import scipy.fft

EPS = 1e-12
manual_bands = None

def hz_to_mel(f):
    return 2595.0*np.log10(1.0+f/700.0)

def mel_to_hz(m):
    return 700.0*(10.0**(m/2595.0)-1.0)

def hann(n):
    return 0.5-0.5*np.cos(2*np.pi*np.arange(n)/n)

def build_mel_filterbank(n_fft, sr, n_mels, fmin, fmax):
    n_fft_bins = n_fft//2 + 1
    freqs = np.linspace(0, sr/2, n_fft_bins)
    mels = np.linspace(hz_to_mel(fmin), hz_to_mel(fmax), n_mels+2)
    hz = mel_to_hz(mels)
    bins = np.floor((n_fft+1)*hz/sr).astype(int)
    bins = np.clip(bins, 0, n_fft_bins-1)
    fb = np.zeros((n_mels, n_fft_bins), dtype=np.float32)
    for i in range(n_mels):
        left, center, right = bins[i], bins[i+1], bins[i+2]
        if center==left: center=min(center+1,n_fft_bins-1)
        if right==center: right=min(right+1,n_fft_bins-1)
        if center>left: fb[i,left:center]=(freqs[left:center]-freqs[left])/(freqs[center]-freqs[left]+EPS)
        if right>center: fb[i,center:right]=(freqs[right]-freqs[center:right])/(freqs[right]-freqs[center]+EPS)
    fb_sum = fb.sum(axis=1, keepdims=True)+EPS
    fb = fb/fb_sum
    return fb

class SpectrumCapture(threading.Thread):
    DEFAULT_PROFILE = {
        "win_s": 2048,
        "hop_s": 1024,
        "smoothing": 0.65,
        "attack": 0.55,
        "release": 0.75,
        "agc_alpha": 0.02,
        "noise_gate_db": -85
    }

    def __init__(self, device="hw:Loopback,1,0", profile=None,
                 num_bars=36, fmin=0, fmax=None, manual_bands=None):
        super().__init__(daemon=True)
        self.device = device
        self.profile = profile or self.DEFAULT_PROFILE
        self.num_bars = num_bars
        self.fmin = fmin
        self.fmax = fmax
        self.manual_bands = manual_bands
        self.running = True
        self.available = False

        try:
            self.recorder = alsaaudio.PCM(type=alsaaudio.PCM_CAPTURE, device=self.device)
            info = self.recorder.info()
            self.available = True
        except alsaaudio.ALSAAudioError as e:
            print(f"[Spectro] ALSA device {self.device} unavailable: {e}")
            self.recorder = None
            self.available = False
            return
        self.samplerate = info.get("rate", 44100)
        self.channels = info.get("channels", 2)
        self.format_name = info.get("format_name", "S16_LE")
        self.nominal_bits = info.get("nominal_bits", 16)
        #print(info)

        # Adapt win/hop according to samplerate
        factor = self.samplerate / 44100.0
        self.win_s = int(self.profile["win_s"] * factor)
        self.hop_s = int(self.profile["hop_s"] * factor)
        self.smoothing = self.profile["smoothing"]
        self.attack = self.profile["attack"]
        self.release = self.profile["release"]
        self.agc_alpha = self.profile["agc_alpha"]
        self.noise_gate_db = self.profile["noise_gate_db"]

        try:
            self.recorder.setperiodsize(self.hop_s)
        except Exception as e:
            print(f"[Spectro] Failed to set period size: {e}")
            self.available = False
            return

        # Pre-compute window and FFT
        self.window = hann(self.win_s).astype(np.float32)
        self.n_fft_bins = self.win_s // 2 + 1
        self.freqs = np.fft.rfftfreq(self.win_s, d=1.0/self.samplerate)

        # Mel or manual filtering
        if self.manual_bands:
            self.filters = self._build_manual_filters(self.manual_bands)
        else:
            self.filters = build_mel_filterbank(self.win_s, self.samplerate, self.num_bars,
                                                self.fmin, self.fmax or self.samplerate//2)

        self.levels = np.zeros(self.num_bars, dtype=np.float32)
        self.baseline = np.ones(self.num_bars, dtype=np.float32)

    def _build_manual_filters(self, bands):
        fb = np.zeros((self.num_bars, self.n_fft_bins), dtype=np.float32)
        for i, (lo, hi) in enumerate(bands):
            if i >= self.num_bars: break
            lo_hz = max(lo, self.fmin)
            hi_hz = min(hi, self.fmax or self.samplerate//2)
            idx = np.where((self.freqs >= lo_hz) & (self.freqs < hi_hz))[0]
            if idx.size == 0: continue
            fb[i, idx] = 1.0
        fb_sum = fb.sum(axis=1, keepdims=True) + EPS
        fb = fb / fb_sum
        return fb

    def _frame_dbfs(self, samples):
        rms = np.sqrt(np.mean(np.square(samples.astype(np.float32))) + EPS)
        return 20.0 * np.log10(rms / 32768.0 + EPS)

    def get_levels(self):
        if not self.available:
            return np.zeros(self.num_bars, dtype=np.float32)
        return self.levels.copy()

    def stop(self):
        self.running = False
        try:
            self.recorder.close()
        except Exception:
            pass

    def run(self):
        if not self.available or not self.recorder:
            return 
        buf = np.zeros(self.win_s, dtype=np.float32)
        while self.running:
            try:
                l, data = self.recorder.read()
                if l <= 0 or not data:
                    self.levels *= 0.9
                    time.sleep(0.005)
                    continue
            except alsaaudio.ALSAAudioError as e:
                msg = str(e).lower()
                if "bad file descriptor" in msg or "file descriptor in bad state" in msg:
                    break
                time.sleep(0.05)
                continue

            # PCM conversion according to actual format
            if "16" in self.format_name:
                dtype = np.int16
            elif "24" in self.format_name:
                dtype = np.int32
            else:
                dtype = np.int16
            samples = np.frombuffer(data, dtype=dtype).astype(np.float32)

            # Stereo mix if required
            if self.channels == 2 and samples.size % 2 == 0:
                samples = samples.reshape(-1, 2).mean(axis=1)

            # Prepare frame
            if samples.size >= self.win_s:
                frame = samples[:self.win_s]
            else:
                shift = self.win_s - samples.size
                buf[:shift] = buf[samples.size:]
                buf[shift:] = samples
                frame = buf

            # Noise gate
            dbfs = self._frame_dbfs(frame)
            if dbfs < self.noise_gate_db:
                self.levels *= 0.85
                continue

            rms_factor = min(max((dbfs - self.noise_gate_db)/40.0, 0.0), 1.0)

            # FFT and energy per band
            windowed = frame * self.window
            spec = scipy.fft.rfft(windowed, n=self.win_s)
            power = (spec.real**2 + spec.imag**2).astype(np.float32)
            band_energy = self.filters @ power

            # AGC baseline
            self.baseline = (1.0 - self.agc_alpha) * self.baseline + self.agc_alpha * (band_energy + EPS)
            rel = np.log1p(band_energy / (self.baseline + EPS)) * 0.9
            rel = np.clip(rel, 0.0, 1.0).astype(np.float32)
            rel *= rms_factor

            # Smooth attack/release
            new_levels = self.levels.copy()
            rising = rel > new_levels
            new_levels[rising] = (1.0 - self.attack) * new_levels[rising] + self.attack * rel[rising]
            new_levels[~rising] *= self.release
            self.levels = self.smoothing * self.levels + (1.0 - self.smoothing) * new_levels
            time.sleep(0.005)
