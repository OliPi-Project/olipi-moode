#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2025 OliPi Project

# screensaver_orbital.py

import math
import random
from typing import Optional, Iterable
import numpy as np

EPS = 1e-12

def _scale_color(color, factor):
    try:
        return (int(color[0] * factor), int(color[1] * factor), int(color[2] * factor))
    except Exception:
        return color

class SaverOrbital:
    DEFAULT_PARAMS = {
        "particle_count": None,
        "trail_len": None,
        "head_size": 1.6,
        "base_r_factor": 0.18,

        # speed mapping
        "speed_min": 1.6,
        "speed_max": 20.0,
        "speed_exp": 4.2,
        "peak_mult": 2.1,

        # smoothing
        "audio_alpha_up": 0.50,       # smooth < raw
        "audio_alpha_down": 0.40,     # smooth < raw

        "radius_smooth_alpha": 0.40,  # small/concentrate particle radius < larger particle radius

        "global_speed_alpha": 0.45,   # smoothing speed < raw speed
        "global_radius_alpha": 0.50,  # smooth growing radius speed < raw growing radius speed

        # center circle breathing & start ripples
        "center_smooth": 0.20,

        # bursts (treble fireworks)
        "burst_enabled": True,
        "burst_threshold": 0.15,
        "burst_particles": 5,
        "burst_per_hit": 5,
        "max_bursts": 300,
        "burst_speed": 3.3,
        "burst_life": 12,

        # normalization
        "level_percentile": 99,
        "max_norm_floor": 1e-6,

        # perf clamping
        "min_particles": 12,
        "max_particles": 120,
    }

    def __init__(self, core, params: Optional[dict] = None, palette: Optional[list] = None):
        self.core = core
        self.params = dict(self.DEFAULT_PARAMS)
        if params:
            self.params.update(params)
        self.palette = palette

        # geometry and particle counts
        area = core.width * core.height
        pcount = self.params["particle_count"]
        if pcount is None:
            auto = int(area // 1400)
            pcount = max(self.params["min_particles"], min(self.params["max_particles"], auto))
        self.pcount = int(pcount)

        trail_len = self.params["trail_len"]
        if trail_len is None:
            trail_len = 3 if min(core.width, core.height) <= 64 else 6
        self.trail_len = max(1, int(trail_len))

        self.cx = core.width // 2
        self.cy = core.height // 2
        self.base_r = int(min(core.width, core.height) * float(self.params["base_r_factor"]))

        rnd = random.Random(42)
        self.angles = [ (i / self.pcount) * 2 * math.pi + rnd.uniform(-0.4, 0.4) for i in range(self.pcount) ]
        self.rfacts = [ 0.5 + rnd.random() * 0.8 for _ in range(self.pcount) ]
        self.speeds = [ 0.005 + rnd.random() * 0.024 for _ in range(self.pcount) ]
        self.phases = [ rnd.random() * 2 * math.pi for _ in range(self.pcount) ]
        self.col_idx = [ i % max(1, len(self.palette or [1])) for i in range(self.pcount) ]
        self.trails = [ [(self.cx, self.cy)] * self.trail_len for _ in range(self.pcount) ]

        # visual state
        self.prev_energy = 0.0
        self.prev_speed_boost = 1.0
        self.prev_radius_boost = 1.0
        self.radius_smooth_alpha = float(self.params["radius_smooth_alpha"])
        self.global_speed_alpha = float(self.params["global_speed_alpha"])
        self.global_radius_alpha = float(self.params["global_radius_alpha"])
        self.max_radius_step = max(2, int(max(8, self.base_r * 0.15)))
        self.curr_r = [ int(self.base_r * rf) for rf in self.rfacts ]

        # peaks & jitter
        self.peak_timer = 0
        self.peak_frames = 4
        self.peak_scale = 1.8
        self.jitter_scale = 3.2

        self.sun_base_r = int(self.base_r * 0.14)

        # center breathing / ripples
        self.center_r = int(self.base_r * 0.16)
        self.center_smooth = float(self.params["center_smooth"])
        self.ripples = []
        self.bass_prev = 0.0

        # head visuals fixed
        self.head_size = max(1, int(round(self.params["head_size"])))
        self.color_brightness = 0.9

        # audio smoothing
        self.energy_smooth = 0.0
        self.audio_alpha_up = float(self.params["audio_alpha_up"])
        self.audio_alpha_down = float(self.params["audio_alpha_down"])

        # burst pool for fireworks (float positions)
        mb = int(self.params["max_bursts"])
        self.burst_x = [0.0] * mb
        self.burst_y = [0.0] * mb
        self.burst_vx = [0.0] * mb
        self.burst_vy = [0.0] * mb
        self.burst_life = [0] * mb
        self.burst_alpha = [0.0] * mb
        self._burst_pool_idx = 0
        self._burst_count = mb

    # ---------- public API ----------
    def update(self, levels: Optional[Iterable[float]] = None):
        """Update state from spectral `levels` (list / np.array)."""
        # prepare levels array
        if levels is None or len(levels) == 0:
            lv = np.zeros(1, dtype=np.float32)
        else:
            lv = np.asarray(levels, dtype=np.float32)

        # robust normalization (percentile)
        pct = self.params.get("level_percentile", 98)
        peak_est = float(np.percentile(lv, pct)) if lv.size else 1.0
        peak_est = max(peak_est, self.params.get("max_norm_floor", EPS))
        norm = lv / peak_est
        norm = np.clip(norm, 0.0, None)

        # compute bass/mid/treble
        L = norm.size
        if L <= 13:
            bass_count = 2
        elif L <= 18:
            bass_count = 3
        elif L <= 28:
            bass_count = 4
        elif L <= 35:
            bass_count = 5
        elif L <= 41:
            bass_count = 6
        else:
            bass_count = 7
        bass_count = min(bass_count, L)
        bass = float(norm[:bass_count].mean()) if bass_count > 0 else 0.0
        mid_start = bass_count
        mid_end = mid_start + (L - bass_count)//2
        mid = float(norm[mid_start:mid_end].mean()) if mid_end > mid_start else 0.0
        treble = float(norm[mid_end:].mean()) if mid_end < L else 0.0

        # energy metric
        energy_mean = float(norm.mean())
        energy_peak = float(norm.max())
        energy = 0.70 * energy_mean + 0.30 * energy_peak

        # asymmetrical smoothing of audio energy
        a = self.audio_alpha_up if energy > self.energy_smooth else self.audio_alpha_down
        self.energy_smooth = self.energy_smooth * (1.0 - a) + energy * a
        energy = self.energy_smooth

        # peak detection
        delta = energy - self.prev_energy
        if delta > 0.12:
            self.peak_timer = self.peak_frames
        if self.peak_timer > 0:
            peak_mul = self.peak_scale
            self.peak_timer -= 1
        else:
            peak_mul = 1.0
        self.prev_energy = energy

        # speed mapping
        e = max(0.0, min(1.0, energy))
        mapped = e ** float(self.params.get("speed_exp", 1.4))
        target_speed = float(self.params.get("speed_min", 0.6)) + (float(self.params.get("speed_max", 9.0)) - float(self.params.get("speed_min", 0.6))) * mapped
        if self.peak_timer > 0:
            target_speed *= float(self.params.get("peak_mult", 1.3))

        # radius mapping (mids control orbit size)
        target_radius = 1.0 + (mid ** 0.8) * 0.9

        # smooth global targets
        speed_boost = self.prev_speed_boost * (1.0 - self.global_speed_alpha) + target_speed * self.global_speed_alpha
        radius_boost = self.prev_radius_boost * (1.0 - self.global_radius_alpha) + target_radius * self.global_radius_alpha
        self.prev_speed_boost = speed_boost
        self.prev_radius_boost = radius_boost

        # base radius breathing (bass)
        breath = 1.0 + bass * 0.8
        target_base_r = int(self.base_r * breath)
        if not hasattr(self, "_curr_base_r"):
            self._curr_base_r = self.base_r
        self._curr_base_r = int(self._curr_base_r * 0.85 + target_base_r * 0.15)

        # center breathing/ripples (bass-driven)
        center_target = int(self.base_r * (0.16 + min(1.0, bass * 2.8) * 0.45))
        self.center_r = int(self.center_r * (1.0 - self.center_smooth) + center_target * self.center_smooth)

        bass_delta = (bass - getattr(self, "bass_prev", 0.0))
        self.bass_prev = bass
        if bass_delta > 0.12:
            # spawn a ripple
            self.ripples.append({"r": self.center_r + 2, "alpha": 0.9, "speed": 1.6 + bass * 2.6})

        # main particles update (angles, radii, trails)
        max_step = max(2, int(max(8, self.base_r * 0.15)))
        for i in range(self.pcount):
            a = self.angles[i] + self.speeds[i] * speed_boost * (1.0 + 0.25 * math.sin(self.phases[i] + energy * 5.0))
            self.angles[i] = a

            r_target = int(self._curr_base_r * self.rfacts[i] * radius_boost)
            prev_r = self.curr_r[i]
            delta_r = r_target - prev_r
            if delta_r > self.max_radius_step:
                delta_r = self.max_radius_step
            elif delta_r < -self.max_radius_step:
                delta_r = -self.max_radius_step

            r_new = prev_r + delta_r
            r_new = int(prev_r * (1.0 - self.radius_smooth_alpha) + r_new * self.radius_smooth_alpha)
            self.curr_r[i] = max(1, r_new)

            # jitter (treble-driven) modulated by bass for stability
            tval = treble
            j_scale = 1.0 - min(0.9, float(self.curr_r[i]) / float(max(1, int(self.base_r * 1.8))))
            jx = int(math.cos(a * 3.0 + self.phases[i]) * ((tval ** 1.1) * (1.0 + 0.6 * bass)) * self.jitter_scale * j_scale)
            jy = int(math.sin(a * 2.0 + self.phases[i]) * ((tval ** 1.1) * (1.0 + 0.6 * bass)) * self.jitter_scale * j_scale)

            x = int(self.cx + math.cos(a) * self.curr_r[i]) + jx
            y = int(self.cy + math.sin(a) * self.curr_r[i]) + jy

            t = self.trails[i]
            for k in range(self.trail_len - 1, 0, -1):
                t[k] = t[k - 1]
            t[0] = (x, y)

        # --- TREBLE FIREWORKS: spawn small explosions of MANY micro-particles around a head ---
        if self.params.get("burst_enabled", True):
            prev_t = getattr(self, "_prev_treble", 0.0)
            treble_delta = treble - prev_t
            self._prev_treble = treble

            if treble_delta > self.params.get("burst_threshold", 0.10):
                # number of explosions to trigger (can be 1..n)
                n_expl = max(1, int(self.params.get("burst_per_hit", 6) * (treble_delta * 4.0)))
                n_expl = min(n_expl, 6)  # clamp explosions per frame
                particles_per_expl = int(self.params.get("burst_particles", 10))

                for _ in range(n_expl):
                    # choose a head near which explosion originates
                    pi = int(random.random() * self.pcount)
                    hx, hy = self.trails[pi][0]

                    # spawn multiple micro-particles in 360° around (hx,hy)
                    for _p in range(particles_per_expl):
                        idx = self._burst_pool_idx
                        angle = random.random() * 2.0 * math.pi
                        base = float(self.params.get("burst_speed", 2.8))
                        speed = (0.6 + random.random() * 1.4) * base * (0.6 + treble * 1.4)
                        self.burst_x[idx] = float(hx)
                        self.burst_y[idx] = float(hy)
                        self.burst_vx[idx] = math.cos(angle) * speed
                        self.burst_vy[idx] = math.sin(angle) * speed
                        life = int(self.params.get("burst_life", 12) * (0.7 + random.random() * 0.8))
                        self.burst_life[idx] = max(1, min(255, life))
                        self.burst_alpha[idx] = 1.0
                        self._burst_pool_idx = (idx + 1) % self._burst_count


        # update bursts (motion + decay)
        mb = self._burst_count
        for i in range(mb):
            if self.burst_life[i] > 0:
                self.burst_x[i] += self.burst_vx[i]
                self.burst_y[i] += self.burst_vy[i]
                # apply small drag and fade
                self.burst_vx[i] *= 0.96
                self.burst_vy[i] *= 0.96
                self.burst_alpha[i] *= 0.86
                self.burst_life[i] -= 1


        # update ripples lifecycle (make them ephemeral)
        if self.ripples:
            alive = []
            maxdim = max(self.core.width, self.core.height) * 1.2
            for rp in self.ripples:
                rp["r"] += rp["speed"]
                rp["alpha"] *= 0.92
                if rp["alpha"] > 0.08 and rp["r"] < maxdim:
                    alive.append(rp)
            self.ripples = alive

    def draw(self):
        core = self.core
        core.draw.rectangle((0, 0, core.width, core.height), fill=core.COLOR_BG)

        # --- build reversed color ladder (highest -> lowest) ---
        if self.palette:
            # palette entries are like (pos, [r,g,b])
            pal = [p[1] for p in self.palette]
            col_ladder = pal[::-1]
        else:
            col_ladder = [core.COLOR_ARTIST]

        # safe accessor
        def pick(idx):
            if idx < len(col_ladder):
                return tuple(col_ladder[idx])
            return tuple(col_ladder[-1])

        # helper : blend color -> bg by t (0..1). t=1 -> color, t=0 -> bg
        def blend_to_bg(color, bg, t):
            return (int(color[0] * t + bg[0] * (1.0 - t)),
                    int(color[1] * t + bg[1] * (1.0 - t)),
                    int(color[2] * t + bg[2] * (1.0 - t)))

        bg = tuple(core.COLOR_BG)
        # pick colors from ladder: 0 = highest (top), 1 = next, 2 = next...
        sun_raw    = pick(0)
        center_raw = pick(1) if len(col_ladder) > 1 else pick(0)
        ripple_raw = pick(2) if len(col_ladder) > 2 else center_raw

        # luminosity scalers (tweak these to taste)
        sun_lum = 0.45 + 0.30 * min(1.0, self.prev_energy * 1.1)    # brighter when energy up
        center_lum = 0.25 + 0.20 * min(1.0, self.prev_energy * 1.1)

        # compute final colors (scale then blend a bit toward bg so ripples fade properly on inverted screens)
        sun_col = blend_to_bg(tuple(int(c) for c in sun_raw), bg, min(1.0, sun_lum))
        center_col = blend_to_bg(tuple(int(c) for c in center_raw), bg, min(1.0, center_lum))

        # -----------------------
        #  SUN (filled) - fixed size
        # -----------------------
        core.draw.ellipse(
            (self.cx - self.sun_base_r, self.cy - self.sun_base_r,
             self.cx + self.sun_base_r, self.cy + self.sun_base_r),
            fill=sun_col
        )

        # -----------------------
        #  BREATHING RING (outline) - same as before
        # -----------------------
        ring_col = center_col
        core.draw.ellipse(
            (self.cx - self.center_r, self.cy - self.center_r,
             self.cx + self.center_r, self.cy + self.center_r),
            outline=ring_col
        )

        # -----------------------
        #  RIPPLES (outline blended to bg by their alpha)
        # -----------------------
        for rp in self.ripples:
            if rp["alpha"] <= 0:
                continue
            lum = max(0.08, min(0.35, rp["alpha"]))   # clamp
            # blend ripple color towards background for fade effect (works on inverted displays)
            ripple_col = blend_to_bg(tuple(int(c) for c in ripple_raw), bg, lum)
            rr = int(rp["r"])
            if rr >= 2:
                core.draw.ellipse(
                    (self.cx - rr, self.cy - rr, self.cx + rr, self.cy + rr),
                    outline=ripple_col
                )

        # -----------------------
        #  TRAILS + HEADS
        # -----------------------
        for i in range(self.pcount):
            base_color = core.COLOR_ARTIST
            if self.palette:
                base_color = tuple(self.palette[self.col_idx[i] % len(self.palette)][1])
            t = self.trails[i]
            idx_factor = 0.6 + 0.4 * (0.5 + 0.5 * math.sin(self.phases[i]))
            head_c = _scale_color(base_color, self.color_brightness * idx_factor)
            x0, y0 = t[0]
            hs = self.head_size
            core.draw.rectangle((x0, y0, x0 + hs - 1, y0 + hs - 1), fill=head_c)
            if self.trail_len > 1:
                x1, y1 = t[1]
                dx = x1 - x0; dy = y1 - y0
                dist2 = dx*dx + dy*dy
                if dist2 <= (hs + 6) * (hs + 6):
                    core.draw.line((x0, y0, x1, y1), fill=head_c)
            for idx in range(1, self.trail_len):
                x, y = t[idx]
                factor = 0.25 + 0.75 * (1.0 - idx / float(self.trail_len))
                c = _scale_color(base_color, factor)
                core.draw.point((x, y), fill=c)

        # -----------------------
        #  BURSTS (micro particles): keep artist color but blend by alpha
        # -----------------------
        for i in range(self._burst_count):
            if self.burst_life[i] > 0:
                bx = int(self.burst_x[i])
                by = int(self.burst_y[i])
                a = max(0.06, min(1.0, self.burst_alpha[i]))
                col = blend_to_bg(tuple(core.COLOR_ARTIST), bg, a)
                # offer a slightly larger dot when stronger
                core.draw.point((bx, by), fill=col)
