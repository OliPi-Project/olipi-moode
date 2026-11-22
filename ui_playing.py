#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2025 OliPi Project
# Copyright Sizenko Alexander for Digital-7 Font

import os
import sys
import subprocess
import socket
import re
import time
import datetime
import threading
import requests
import math
import random
import html
import http.server
import sqlite3
import json
import queue
import tempfile
import unicodedata
from pathlib import Path
from urllib.parse import urlparse
from mpd import MPDClient

OLIPIMOODE_DIR = Path(__file__).resolve().parent
os.environ.setdefault("OLIPI_DIR", str(OLIPIMOODE_DIR))

from olipi_core import core_common as core
from olipi_core.input_manager import start_inputs, press_data, process_key
from media_key_actions import load_shortcuts, is_key_reserved, is_key_used, handle_audio_keys, handle_custom_key, USED_MEDIA_KEYS, set_hooks as set_custom_hooks

DB_PATH = "/var/local/www/db/moode-sqlite3.db"
BTMeta_Path = "/var/local/www/btmeta.json"

show_icons = core.get_config("nowplaying", "show_icons", fallback=False, type=bool)
show_one_line = core.get_config("nowplaying", "show_one_line", fallback=False, type=bool)
show_extra_infos = core.get_config("nowplaying", "show_extra_infos", fallback=False, type=bool)
show_progress_barre = core.get_config("nowplaying", "show_progress_barre", fallback=False, type=bool)
show_cover_bg = core.get_config("nowplaying", "show_cover_bg", fallback="off", type=str)
show_vol_bar = core.get_config("nowplaying", "show_vol_bar", fallback=True, type=bool)
show_clock = core.get_config("nowplaying", "show_clock", fallback=True, type=bool)
show_spectrum = core.get_config("nowplaying", "show_spectrum", fallback=False, type=bool)
show_peak_vu = core.get_config("nowplaying", "show_peak_vu", fallback="off", type=str)
peak_vu_style = core.get_config("nowplaying", "peak_vu_style", fallback="horizontal_inline", type=str)
show_meters_alt = core.get_config("nowplaying", "show_meters_alt", fallback=False, type=bool)
show_scale_labels = core.get_config("nowplaying", "show_scale_labels", fallback=False, type=bool)
peak_correct = core.get_config("spectrum","peak_soft_correct", fallback=False, type=bool)

# --- Fonts ui_playing ---
if core.height < 64 and core.diag_inch >= 2.0:
    if show_one_line:
        font_artist = core.get_font("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", core.get_config("nowplaying", "font_size_artist", fallback=14, type=int))
    else:
        font_artist = core.get_font("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", core.get_config("nowplaying", "font_size_artist", fallback=10, type=int))
    font_vol_clock = core.get_font("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", core.get_config("nowplaying", "font_size_vol_clock", fallback=7, type=int))
    font_stop_clock = core.get_font("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", core.get_config("nowplaying", "font_size_stop_clock", fallback=20, type=int))
    font_extra_info = core.get_font("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", core.get_config("nowplaying", "font_size_extra_info", fallback=6, type=int))
    font_meters_label = core.get_font("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", core.get_config("nowplaying", "font_meters_label", fallback=6, type=int))
else:
    font_artist = core.get_font("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", core.get_config("nowplaying", "font_size_artist", fallback=14, type=int))
    font_vol_clock = core.get_font("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", core.get_config("nowplaying", "font_size_artist", fallback=10, type=int))
    font_stop_clock = core.get_font("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", core.get_config("nowplaying", "font_size_vol_clock", fallback=24, type=int))
    font_extra_info = core.get_font("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", core.get_config("nowplaying", "font_size_extra_info", fallback=9, type=int))
    font_meters_label = core.get_font("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", core.get_config("nowplaying", "font_meters_label", fallback=7, type=int))

core.load_translations(Path(__file__).stem)

render_lock = threading.Lock()
now_playing_mode = False

cover_lock = threading.Lock()
cover_event = threading.Event()
cover_request_id = 0
cover_pending = None

idle_timer = time.time()
last_wake_time = 0
screen_on = True
is_sleeping = False
blocking_render = False
previous_blocking_render = False

SCROLL_SPEED_NOWPLAYING = 0.05

menu_active = False
menu_options = [
    {"id": "remove_queue", "label": core.t("menu_remove_queue")},
    {"id": "playback_modes", "label": core.t("menu_playback_modes")},
    {"id": "power", "label": core.t("menu_power")}
]
menu_add_fav_option = [{"id": "add_fav", "label": core.t("menu_add_fav")}]
menu_remove_fav_option = [{"id": "remove_fav", "label": core.t("menu_remove_fav")}]
menu_add_songlog_option = [{"id": "add_songlog", "label": core.t("menu_add_songlog")}]
menu_search_artist_option = [{"id": "search_artist", "label": core.t("menu_search_artist")}]
menu_options_contextuel = []
menu_selection = 0
menu_context_flag = ""

playback_modes_menu_active = False
playback_modes_selection = 0
playback_modes_options = [
    {"id": "random", "label": core.t("menu_random")},
    {"id": "repeat", "label": core.t("menu_repeat")},
    {"id": "single", "label": core.t("menu_single")},
    {"id": "consume", "label": core.t("menu_consume")}
]
power_menu_active = False
power_menu_selection = 0
power_menu_options = [
    {"id": "poweroff", "label": core.t("menu_poweroff")},
    {"id": "reboot", "label": core.t("menu_reboot")},
    {"id": "reload_screen", "label": core.t("menu_reload_screen")},
    {"id": "restart_mpd", "label": core.t("menu_restart_mpd")}
]
confirm_box_active = False
confirm_box_selection = 0
confirm_box_title = core.t("title_confirm")
confirm_box_callback = None
confirm_box_options = [
    {"id": "confirm_yes", "label": core.t("menu_yes")},
    {"id": "confirm_no", "label": core.t("menu_no")}
]

tool_menu_active = False
tool_menu_selection = 0
tool_menu_options = [
    {"id": "renderers", "label": core.t("menu_renderers")},
    {"id": "equalizers", "label": core.t("menu_equalizers")},
    {"id": "show_songlog", "label": core.t("menu_show_songlog")},
    {"id": "hardware_info", "label": core.t("menu_hardware_info")},
    {"id": "configuration", "label": core.t("menu_configuration")}
]

eq_menu_active = False
eq_menu_selection = 0
eq_menu_options = [
    {"id": "graphic", "label": core.t("menu_graphic_eq")},
    {"id": "parametric", "label": core.t("menu_parametric_eq")}
]

eq_preset_active = False
eq_preset_selection = 0
eq_preset_options = []

songlog_active = False
songlog_lines = []
songlog_meta = []
songlog_selection = 0

songlog_action_active = False
songlog_action_selection = 0
songlog_action_options = [
    {"id": "play_yt_songlog", "label": core.t("menu_play_yt_songlog")},
    {"id": "queue_yt_songlog", "label": core.t("menu_queue_yt_songlog")},
    {"id": "show_info_songlog", "label": core.t("menu_show_info_songlog")},
    {"id": "delete_entry_songlog", "label": core.t("menu_delete_entry_songlog")},
    {"id": "delete_all_songlog", "label": core.t("menu_delete_all_songlog")}
]

yt_cache_path = OLIPIMOODE_DIR / "yt_cache.json"
yt_cache_lock = threading.Lock()

config_menu_active = False
config_menu_selection = 0
config_menu_options = [
    {"id": "language", "label": core.t("menu_language")},
    {"id": "ui", "label": core.t("menu_ui")},
    {"id": "screensaver", "label": core.t("menu_screensaver")},
    {"id": "debug", "label": core.t("menu_debug")}
]
if core.display_format != "MONO":
    config_menu_options.insert(1, {"id": "theme", "label": core.t("menu_theme")})

language_menu_active = False
language_menu_selection = 0
language_menu_options = [
    {"id": "en", "label": core.t("English")},
    {"id": "fr", "label": core.t("French")}
]
theme_menu_active = False
theme_menu_selection = 0
theme_menu_options = core.get_theme_menu()

ui_menu_active = False
ui_menu_selection = 0
ui_menu_options = [
    {"id": "icons", "label": core.t("menu_icons")},
    {"id": "oneline", "label": core.t("menu_oneline")},
    {"id": "extra", "label": core.t("menu_extra_infos")},
    {"id": "progress", "label": core.t("menu_progress_bare")},
    {"id": "cover_bg", "label": None},
    {"id": "spectrum", "label": core.t("menu_spectrum")},
    {"id": "peak_vu", "label": None},
    {"id": "peak_vu_style", "label": None},
    {"id": "meters_alt", "label": core.t("menu_meters_alt")},
    {"id": "scale_label", "label": core.t("menu_scale_label")},
    {"id": "vol_bar", "label": core.t("menu_vol_bar")},
    {"id": "clock_elapse", "label": core.t("menu_clock")},
    {"id": "apply", "label": core.t("menu_apply")}
]
cover_bg_options = ["off", "background", "resized"]
cover_bg_labels = {
    "off": core.t("menu_cover_off"),
    "background": core.t("menu_cover_bg"),
    "resized": core.t("menu_cover_alt"),
}
peak_vu_options = ["off", "peak", "vu", "both"]
peak_vu_labels = {
    "off": core.t("menu_peak_vu_off"),
    "peak": core.t("menu_peak_vu_peak"),
    "vu": core.t("menu_peak_vu_vu"),
    "both": core.t("menu_peak_vu_both"),
}
peak_vu_style_options = ["horizontal_inline", "horizontal_separate", "vertical"]
peak_vu_style_labels = {
    "horizontal_inline": core.t("menu_peak_vu_style_inline"),
    "horizontal_separate": core.t("menu_peak_vu_style_separate"),
    "vertical": core.t("menu_peak_vu_style_vertical"),
}
screensaver_menu_active = False
screensaver_menu_selection = 0
screensaver_menu_options = [
    {"id": "sleep", "label": None},
    {"id": "select", "label": core.t("menu_select")},
    {"id": "blank", "label": core.t("mode_blank")},
    {"id": "clock", "label": core.t("mode_clock")},
    {"id": "covers", "label": core.t("mode_covers")},
    {"id": "spectrum", "label": core.t("mode_spectrum")}
]
if core.display_format != "MONO":
    screensaver_menu_options.insert(6, {"id": "orbital", "label": core.t("mode_orbital")})
sleep_timeout_options = [0, 15, 30, 60, 300, 600]
sleep_timeout_labels = {0: "Off", 15: "15s", 30: "30s", 60: "1m", 300: "5m", 600: "10m"}

hardware_info_active = False
hardware_info_selection = 0
hardware_info_lines = []

renderers_menu_active = False
renderers_menu_selection = 0
renderers_menu_options = [
    {"id": "bluetooth", "label": core.t("menu_renderer_bluetooth")},
    {"id": "airplay", "label": core.t("menu_renderer_airplay")},
    {"id": "upnp", "label": core.t("menu_renderer_upnp")}
]
bluetooth_menu_active = False
bluetooth_menu_selection = 0
bluetooth_menu_options = [
    {"id": "bt_toggle", "label": core.t("menu_bt_toggle")},
    {"id": "bt_scan", "label": core.t("menu_bt_scan")},
    {"id": "bt_paired", "label": core.t("menu_bt_paired")},
    {"id": "bt_audio_output", "label": core.t("menu_bt_audio_output")},
    {"id": "bt_disconnect_all", "label": core.t("menu_bt_disconnect_all")}
]
bluetooth_scan_menu_active = False
bluetooth_scan_menu_selection = 0
bluetooth_scan_menu_options = []

bluetooth_paired_menu_active = False
bluetooth_paired_menu_selection = 0
bluetooth_paired_menu_options = []

bluetooth_audioout_menu_active = False
bluetooth_audioout_menu_selection = 0
bluetooth_audioout_menu_options = [
    {"id": "audioout_local", "label": core.t("menu_audioout_local")},
    {"id": "audioout_bt", "label": core.t("menu_audioout_bt")}
]
bluetooth_device_actions_menu_active = False
bluetooth_device_actions_menu_selection = 0
bluetooth_device_actions_menu_options = []

selected_bt_mac = None
wifi_extra_info = ""
eth_extra_info = ""

help_active = False
help_lines = []
help_selection = 0

learning_mode = False
learning_callback = None

# ---- ICON PATHS (keep as file paths) ----
ICON_PATHS = {
    "play": OLIPIMOODE_DIR / "assets/icons/play.png",
    "pause": OLIPIMOODE_DIR / "assets/icons/pause.png",
    "stop": OLIPIMOODE_DIR / "assets/icons/stop.png",
    "random_on": OLIPIMOODE_DIR / "assets/icons/random.png",
    "repeat_on": OLIPIMOODE_DIR / "assets/icons/repeat.png",
    "repeat1_on": OLIPIMOODE_DIR / "assets/icons/repeat1.png",
    "single_on": OLIPIMOODE_DIR / "assets/icons/single.png",
    "consume_on": OLIPIMOODE_DIR / "assets/icons/consume.png",
    "favorite": OLIPIMOODE_DIR / "assets/icons/favorite.png",
    "bluetooth": OLIPIMOODE_DIR / "assets/icons/bluetooth.png",
    "empty": OLIPIMOODE_DIR / "assets/icons/empty.png",
}

show_peak = show_peak_vu != "off"
show_cover = show_cover_bg != "off"
show_cover_alt = show_cover_bg == "resized"

screensaver_mode = core.get_config("settings", "screensaver_mode", fallback="blank", type=str)
if screensaver_mode == "covers" or show_cover:
    from io import BytesIO
    if core.display_format == "MONO":
        from PIL import ImageEnhance, ImageOps, ImageFilter
DYNAMIC_SS = ("orbital", "spectrum")

# runtime cache of loaded (and possibly tinted) icons
icons = {}
icon_width = 16

def _tint_icon(img, color):
    """
    Tint a white-on-transparent RGBA icon with the RGB color tuple.
    Only modifies non-transparent pixels; preserves alpha and background.
    """
    img = img.convert("RGBA")
    r_t, g_t, b_t = color
    pixels = img.load()
    for y in range(img.height):
        for x in range(img.width):
            pr, pg, pb, pa = pixels[x, y]
            if pa == 0:
                continue
            alpha_ratio = pa / 255.0
            new_r = int(r_t * alpha_ratio)
            new_g = int(g_t * alpha_ratio)
            new_b = int(b_t * alpha_ratio)
            pixels[x, y] = (new_r, new_g, new_b, pa)
    return img

def _resize_icon(img, base_size=16):
    """
    Resize icon depending on screen PPI.
    - Keep base_size if PPI <= 150
    - Scale progressively above
    """
    if img is None:
        return None
    if core.height <= 64:
        return img.resize((15, 15), core.Image.Resampling.LANCZOS)
    if core.ppi <= 150:
        return img
    scale = min(core.ppi / core.BASE_PPI, 1.6)
    size = int(base_size * scale)
    return img.resize((size, size), core.Image.Resampling.LANCZOS)

def load_icons_from_theme():
    """
    Load icons from ICON_PATHS and tint them once according to core.COLOR_ICONS.
    Do nothing (just load raw icons) for MONO displays or if COLOR_ICONS is missing.
    """
    global icons, icon_width
    icons.clear()
    is_mono = (core.display_format == "MONO")
    color = getattr(core, "COLOR_ICONS", None)
    for key, path in ICON_PATHS.items():
        try:
            if is_mono:
                im = core.Image.open(path).convert("1")
            else:
                im = core.Image.open(path).convert("RGBA")
        except Exception:
            im = core.Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        im = _resize_icon(im, base_size=16)
        if (not is_mono) and isinstance(color, tuple) and len(color) == 3 and color != (255, 255, 255):
            icons[key] = _tint_icon(im, color)
        else:
            icons[key] = im
    if "play" in icons and icons["play"] is not None:
        icon_width = icons["play"].width
    else:
        icon_width = 16
load_icons_from_theme()

def draw_mask(box, background, radius=3):
    x0, y0, x1, y1 = map(int, box)
    x0 = max(0, x0)
    y0 = max(0, y0)
    x1 = min(core.width, x1)
    y1 = min(core.height, y1)
    if x1 <= x0 or y1 <= y0:
        return
    # Solid background or monochrome screen
    if len(background) == 3 or core.display_format == "MONO":
        color = background[:3] if len(background) == 3 else core.COLOR_BG
        core.draw.rounded_rectangle(
            (x0, y0, x1, y1),
            radius=radius,
            fill=color
        )
        return
    # Composition limited to the mask area
    box = (x0, y0, x1, y1)
    base = core.image.crop(box).convert("RGBA")
    overlay = core.Image.new("RGBA", base.size, (0, 0, 0, 0))
    overlay_draw = core.screen.ImageDraw.Draw(overlay)
    overlay_draw.rounded_rectangle(
        (0, 0, base.width - 1, base.height - 1),
        radius=radius,
        fill=background
    )
    result = core.Image.alpha_composite(base, overlay)
    core.image.paste(result.convert(core.image.mode), (x0, y0))

def draw_icon_with_mask(icon, position, background=None, padding=0, radius=0):
    if icon is None:
        return
    x, y = position
    w, h = icon.size
    # Do not draw a mask for a fully transparent icon
    if icon.mode == "RGBA" and icon.getbbox() is None:
        return
    if background is not None:
        draw_mask(
            (x - padding, y - padding, x + w + padding, y + h + padding),
            background,
            radius
        )
    if icon.mode == "RGBA":
        core.image.paste(icon, (x, y), icon)
    else:
        core.image.paste(icon, (x, y))

def draw_text_with_mask(position, text, font, fill, background=None, padding=2, radius=2):
    if background is not None:
        bbox = core.draw.textbbox(position, text, font=font)
        ref_bbox = font.getbbox(text)
        height = ref_bbox[3] - ref_bbox[1]
        top = position[1] + ref_bbox[1]
        draw_mask(
            (
                bbox[0] - padding,
                top - padding,
                bbox[2] + padding,
                top + height + padding
            ),
            background,
            radius
        )
    core.draw.text(position, text, font=font, fill=fill)

spectrum = None
PALETTE_SPECTRUM = []

def load_spectrum_palette(theme_name="default"):
    themes = core.load_theme_file()
    theme = themes.get(theme_name, themes.get("default", {}))
    if "spectrum" in theme:
        global PALETTE_SPECTRUM
        PALETTE_SPECTRUM = [(float(val), core.get_color(tuple(col))) for val, col in theme["spectrum"]]
load_spectrum_palette(core.THEME_NAME)

last_title_seen = ""
last_artist_seen = ""
last_radio_path = None
last_radio_title = None
ignore_next_radio_title = False

query = ""
stream_url = ""
title_yt = ""
artist_yt = ""
album_yt = ""
final_title_yt = ""

favorites_cache = []
favorites_last_mtime = 0
favorites_last_check = 0

core.poweron_safe()

def run_active_loop():
    if not blocking_render and not is_sleeping:
        render_screen()

last_displayed_cover = None
def show_screensaver_cover():
    global last_displayed_cover
    cover = global_state.get("cover_img")
    if cover is None:
        cover = get_fallback_image("Screensaver Cover")
        if cover is not None:
            global_state["cover_img"] = cover
    if cover and cover is not last_displayed_cover:
        core.draw.rectangle((0, 0, core.width, core.height), fill=core.COLOR_BG)
        img = cover.copy()

        margin = int(min(core.width, core.height) * 0.05)
        if core.height <= 64:
            margin = 0
        img.thumbnail(
            (core.width - margin * 2, core.height - margin * 2),
            core.Image.LANCZOS
        )
        x = (core.width - img.width) // 2
        y = (core.height - img.height) // 2

        core.image.paste(img, (x, y))
        core.refresh()
        last_displayed_cover = cover
    elif not cover and last_displayed_cover != "no_cover":
        if core.DEBUG:
            print("NO COVER")
        last_displayed_cover = "no_cover"
        core.clear_display()

def run_sleep_loop():
    global is_sleeping, screen_on, last_displayed_cover
    if is_sleeping:
        return
    is_sleeping = True
    screen_on = False
    last_state = None
    if screensaver_mode == "covers":
        while is_sleeping:
            state = global_state.get("state", "unknown")
            # --- state change detection ---
            if state != last_state:
                last_state = state
                if state == "stop": # MPD case
                    core.clear_display()
                    core.poweroff_safe()
                    last_displayed_cover = None
                elif state == "play":
                    core.poweron_safe()
                    last_displayed_cover = None  # force refresh
            if state == "play":
                show_screensaver_cover()
            time.sleep(0.3)

    elif screensaver_mode == "orbital":
        from screensavers.screensaver_orbital import SaverOrbital
        saver = SaverOrbital(core, palette=PALETTE_SPECTRUM)
        while is_sleeping:
            levels = spectrum.get_levels() if spectrum else None
            saver.update(levels)
            saver.draw()
            core.refresh()
            time.sleep(core.REFRESH_INTERVAL)

    elif screensaver_mode == "spectrum":
        ratio = core.width / core.height
        # base relative
        base_h = core.height * 0.45
        # ratio normalization (square -> compact, wide -> taller)
        ratio_norm = min(1.0, max(0.0, (ratio - 1.0) / 1.0))
        height_factor = 0.65 + 0.35 * ratio_norm
        spectrum_h = int(base_h * height_factor)
        # safety clamps
        spectrum_h = max(24, spectrum_h)
        spectrum_h = min(int(core.height * 0.55), spectrum_h)

        #spectrum_h = max(25, min(80, (core.height // 2) - (core.height // 10)))
        y_spectrum_top = core.height - spectrum_h
        while is_sleeping:
            if spectrum:
                core.draw.rectangle((0, 0, core.width, core.height), fill=core.COLOR_BG)
                levels = spectrum.get_levels()
                draw_spectrum(y_top=y_spectrum_top, height=spectrum_h, levels=levels)
                core.refresh()
            time.sleep(core.REFRESH_INTERVAL)

    elif screensaver_mode == "clock":
        margin = int(min(core.width, core.height) * 0.14)
        font_path = OLIPIMOODE_DIR / "assets/fonts/digital_7/digital-7.ttf"
        test_text = "88:88"
        max_w = core.width - margin * 2
        max_h = core.height - margin * 2
        size = core.height
        while size > 5:
            font = core.get_font(font_path, size)
            bbox = font.getbbox(test_text)
            w = bbox[2] - bbox[0]
            h_txt = bbox[3] - bbox[1]
            if w <= max_w and h_txt <= max_h:
                break
            size -= 2
        font = core.get_font(font_path, size)
        space_px = int(size * 0.06)
        colon_visible = True
        while is_sleeping:
            core.draw.rectangle((0, 0, core.width, core.height), fill=core.COLOR_BG)
            h = time.strftime("%H")
            m = time.strftime("%M")
            w_h = font.getlength(h)
            w_col = font.getlength(":")
            w_m = font.getlength(m)
            total_w = w_h + space_px + w_col + space_px + w_m
            x = (core.width - total_w) // 2
            y = (core.height - h_txt) // 2 - bbox[1]
            pos = x
            # ---- "HH" ----
            core.draw.text((pos, y), h, font=font, fill=core.COLOR_SCREENSAVER_CLOCK)
            pos += w_h + space_px
            # ---- ":" ----
            color = core.COLOR_SCREENSAVER_CLOCK if colon_visible else core.COLOR_BG
            core.draw.text((pos, y), ":", font=font, fill=color)
            pos += w_col + space_px
            # ---- "MM" ----
            core.draw.text((pos, y), m, font=font, fill=core.COLOR_SCREENSAVER_CLOCK)
            core.refresh()
            colon_visible = not colon_visible
            time.sleep(1)

    elif screensaver_mode == "blank":
        core.clear_display()
        core.poweroff_safe()

def wake_screen():
    global is_sleeping, screen_on, last_wake_time
    if not is_sleeping:
        return
    screen_on = True
    core.poweron_safe()
    core.reset_scroll("menu_title", "menu_item")
    is_sleeping = False
    last_wake_time = time.time()

def has_internet_connection(timeout=2):
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=timeout)
        return True
    except OSError:
        return False

def restart_service():
    subprocess.Popen(["sudo", "systemctl", "restart", "olipi-ui-playing.service"])
    sys.exit(0)

global_state = {
    "favorite": False,
    "state": "unknown",
    "volume": "N/A",
    "clock": time.strftime("%Hh%M"),
    "random": "0",
    "repeat": "0",
    "single": "0",
    "consume": "0",
    "elapsed": "0.0",
    "duration": "0.0",
    "bitrate": "",
    "audio": "",
    "title": "",
    "album": "",
    "artist": "",
    "artist_album": "",
    "path": "",
    "radio_track_covers": False,
    "cover_img": None,
    "btsvc": "0",
    "btactive": "0",
    "airplaysvc": "0",
    "aplactive": "0",
    "spotifysvc": "0",
    "spotactive": "0",
    "slsvc": "0",
    "slactive": "0",
    "rbsvc": "0",
    "rbactive": "0",
    "pasvc": "0",
    "paactive": "0",
    "deezersvc": "0",
    "deezactive": "0",
    "upnpsvc": "0",
    "audioout": "Local",
    "mpdmixer": "software"
}

RENDERER_PARAMS = [
    "btsvc", "btactive", "airplaysvc", "aplactive", "spotifysvc", "spotactive",
    "slsvc", "slactive", "rbsvc", "rbactive", "pasvc", "paactive","deezersvc", "deezactive",
    "inpactive", "rxactive", "upnpsvc", "audioout", "mpdmixer"
]

def load_renderer_states_from_db():
    try:
        conn = sqlite3.connect(DB_PATH, timeout=1)
        cursor = conn.cursor()
        placeholders = ",".join(["?"] * len(RENDERER_PARAMS))
        cursor.execute(f"SELECT param, value FROM cfg_system WHERE param IN ({placeholders})", RENDERER_PARAMS)
        rows = cursor.fetchall()
        conn.close()
        for param, value in rows:
            global_state[param] = value
    except Exception as e:
        core.show_message(core.t("error_db", error=e))
        if core.DEBUG:
            print("error db: ", e)
load_renderer_states_from_db()

def is_bt_local_active():
    return (
        global_state.get("btsvc") == "1"
        and global_state.get("audioout") == "Local"
        and global_state.get("btactive") == "1"
    )

def is_renderer_active():
    return is_bt_local_active() or any(
        global_state.get(flag) == "1"
        for flag in (
            "aplactive", "spotactive", "slactive", "rbactive",
            "paactive", "deezactive"
        )
    )

def get_radio_info(path):
    try:
        with sqlite3.connect(DB_PATH, timeout=1) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT name, bitrate, format
                FROM cfg_radio
                WHERE station = ?
                LIMIT 1
            """, (path,))
            row = cursor.fetchone()
            if row:
                return {
                    "name": row[0] or "Unknown Radio",
                    "bitrate": row[1] or "",
                    "format": row[2] or ""
                }
    except Exception as e:
        if core.DEBUG:
            print("Radio SQL error:", e)
    return {
        "name": "Unknown Radio",
        "bitrate": "",
        "format": ""
    }

def format_time(seconds: float) -> str:
    if seconds is None or seconds <= 0:
        return "0:00"
    h, m = divmod(int(seconds), 3600)
    m, s = divmod(m, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h and not (show_meters_alt or show_cover_alt) else f"{h:02d}h{m:02d}" if h and (show_meters_alt or show_cover_alt) else f"{m:02d}:{s:02d}"

def clean_metadata(text):
    if not text:
        return ""
    # Fix common errors caused by misinterpreted UTF-8 encoding
    if "Ã" in text or "Â" in text:
        try:
            text = text.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    # Remove control characters and invisible characters
    text = "".join(
        char for char in text
        if unicodedata.category(char) not in ("Cc", "Cf")
    )
    # Normalize spaces
    text = text.replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    # Delete the information in parentheses and square brackets
    text = re.sub(r"\([^)]*\)|\[[^]]*\]", "", text)
    # Remove irrelevant information
    junk_patterns = [
        r"\bofficial\s+(?:music\s+)?video\b",
        r"\bofficial\s+audio\b",
        r"\bofficial\s+visualizer\b",
        r"\bradio\s+edit\b",
        r"\bremastered\b",
        r"\bremix\b",
        r"\blive\b",
        r"\bversion\b",
        r"\bmono\b",
        r"\bstereo\b",
    ]
    for pattern in junk_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    # Standardize the separators between artists
    text = re.sub(r"\s*[;&]\s*", ", ", text)
    # Avoid duplicate commas and spaces
    text = re.sub(r"\s*,\s*", ", ", text)
    text = re.sub(r"(?:,\s*){2,}", ", ", text)
    # Remove spaces and residual punctuation
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*[.,;:!?]+\s*$", "", text)
    return text.strip(" \t\r\n-–—;,:|,")

def convert_img_for_display(img):
    img = img.copy()
    img.thumbnail((512, 512), core.Image.LANCZOS)
    if core.display_format != "MONO":
        return img.convert("RGB")
    # --- For tiny OLEDs resize to target_w & crop center height ---
    if core.height <= 64:
        target_w = core.width - 20   # keeps margins
        target_h = core.height
        w, h = img.size
        if w > target_w:
            new_h = int(h * (target_w / w))
            img = img.resize((target_w, new_h), core.Image.LANCZOS)
        if img.height > target_h:
            top = (img.height - target_h) // 2
            img = img.crop((0, top, img.width, top + target_h))
    # --- Sharpen & contrast first ---
    img = ImageEnhance.Sharpness(img).enhance(2.6)
    img = ImageEnhance.Contrast(img).enhance(1.5)
    img = ImageEnhance.Brightness(img).enhance(1.3)
    # --- Convert to grayscale ---
    gray = ImageOps.grayscale(img)
    # --- Adaptive Gaussian blur ---
    blur_strength = 0.9 if gray.height > 90 else 0.4
    gray = gray.filter(ImageFilter.GaussianBlur(blur_strength))
    # --- Increase contrast moderately ---
    gray = ImageEnhance.Contrast(gray).enhance(1.2)
    # --- Final dithering ---
    return gray.convert("1", dither=core.Image.FLOYDSTEINBERG)

def draw_cover_background(x0, x1, y_top, y_bottom):
    cover = global_state.get("cover_img")
    if cover is None:
        return
    x0 = int(x0)
    x1 = int(x1)
    y_top = int(y_top)
    y_bottom = int(y_bottom)
    target_w = x1 - x0
    target_h = y_bottom - y_top
    if target_w <= 0 or target_h <= 0:
        return
    # Cache of the resized image
    cache_key = (id(cover), target_w, target_h)
    if getattr(draw_cover_background, "cache_key", None) != cache_key:
        img = cover.copy()
        w, h = img.size
        # Resize to fill the entire area
        scale = max(target_w / w, target_h / h)
        new_w = max(target_w, int(w * scale))
        new_h = max(target_h, int(h * scale))
        img = img.resize((new_w, new_h), core.Image.LANCZOS)
        # Centered crop
        left = (new_w - target_w) // 2
        top = (new_h - target_h) // 2
        img = img.crop((left, top, left + target_w, top + target_h))
        draw_cover_background.cache = img
        draw_cover_background.cache_key = cache_key
    core.image.paste(draw_cover_background.cache, (x0, y_top))

def get_fallback_image(source):
    try:
        path = "/var/www/images/default-album-cover.jpg"
        img = core.Image.open(path)
        if core.DEBUG:
            print(f"No Cover found (source: {source}) => fallback to default cover ")
        return convert_img_for_display(img)
    except:
        print("error fallback cover")
        return None

def get_radio_logo(name):
    try:
        radio_path = f"/var/local/www/imagesw/radio-logos/{name}.jpg"
        img = core.Image.open(radio_path)
        if img and core.DEBUG:
            print(f"Fallback to radio cover logo => {radio_path}")
        return convert_img_for_display(img)
    except (OSError, ValueError) as e:
        if core.DEBUG:
            print("Radio logo error:", e)
    return get_fallback_image("get_radio_logo(name)")

def get_radio_track_covers_enabled():
    try:
        conn = sqlite3.connect(DB_PATH, timeout=1)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT value FROM cfg_system
            WHERE param='radio_covers'
        """)
        result = cursor.fetchone()
        conn.close()
        if result and result[0] == "Yes":
            global_state["radio_track_covers"] = "radiocover_plus"
        else:
            global_state["radio_track_covers"] = False
        return result and result[0] == "Yes"
    except Exception as e:
        if core.DEBUG:
            print("radio_track_covers read error:", e)
        return False
get_radio_track_covers_enabled()

def get_cached_cover_url(title):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT cover_url FROM cfg_rcucache WHERE title = ? LIMIT 1",
                (title,)
            )
            row = cursor.fetchone()
            return row[0] if row and row[0] else None
    except Exception as e:
        if core.DEBUG:
            print("error rcucache: ", e)
        return None

def download_cover_image(url):
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=3)
        resp.raise_for_status()
        img = core.Image.open(BytesIO(resp.content))
        img.load()
        return convert_img_for_display(img)
    except Exception as e:
        if core.DEBUG:
            print("cover download error:", e)
        return None

def search_radiocover_plus(title, artist_album=None):
    try:
        title = clean_metadata(title)
        if not title:
            return None
        # --- parse "Artist - Track" ---
        artist = ""
        track = title
        if " - " in title:
            parts = title.split(" - ", 1)
            artist = parts[0].strip()
            track = parts[1].strip()
        # --- validation ---
        def is_valid(text):
            return text and len(text) >= 3 and re.search(r"[a-zA-Z0-9]", text)
        # --- blacklist radio ---
        text_all = f"{artist} {track}".lower()
        blacklist = ["radio", "fm", "stream", "station", "webradio"]
        for word in blacklist:
            if word in text_all:
                return None
        # --- compare with radio name ---
        if artist_album:
            radio_name = artist_album.lower()
            if track.lower() == radio_name or artist.lower() == radio_name:
                return None
        # --- fallback logic radiocover+ ---
        station = (
            artist_album
            if artist_album and artist_album != "Unknown Radio"
            else '""'
        )
        args = ["sudo", "python3", "/var/www/util/radiocover_plus.py"]
        if is_valid(artist) and is_valid(track):
            title = f"{artist} - {track}"
            args += ["--title", title, "--station", station]
        elif is_valid(track):
            args += ["--title", track, "--station", station]
        else:
            return None
        if core.DEBUG:
            print(f"Search with Radio Covers + => title={title} | station={station}")
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=15
        )
        url = result.stdout.strip()
        if core.DEBUG:
            print(f"Cover url found with Radio Covers + => {url}")
        return url if url.startswith("http") else None
    except Exception as e:
        if core.DEBUG:
            print("Radio cover error:", e)
        return None

def request_cover(placeholder=None, **kwargs):
    global cover_request_id, cover_pending
    with cover_lock:
        cover_request_id += 1
        request_id = cover_request_id
        if placeholder is not None:
            global_state["cover_img"] = placeholder
        if kwargs:
            cover_pending = (request_id, kwargs)
            cover_event.set()
        else:
            cover_pending = None
            cover_event.clear()
        if core.DEBUG:
            print(
                f"[COVER REQUEST #{request_id}] "
                f"path={kwargs.get('path', '')} "
                f"title={kwargs.get('title', '')} "
                f"placeholder={placeholder is not None}"
            )

def cover_worker():
    global cover_pending
    if screensaver_mode == "covers" or show_cover:
        while True:
            cover_event.wait()
            with cover_lock:
                request = cover_pending
                cover_pending = None
                cover_event.clear()
            if not request:
                continue
            request_id, data = request
            if core.DEBUG:
                print(
                    f"[COVER WORKER #{request_id}] "
                    f"path={data.get('path', '')} "
                    f"title={data.get('title', '')}"
                )
            try:
                source = data["source"]
                path = data.get("path", "")
                title = data.get("title", "")
                artist = data.get("artist", "")
                artist_album = data.get("artist_album", "")
                album = data.get("album", "")
                cover_url_bt = data.get("cover_url", "")
                cover_img = None
                radio_covers = data.get("radio_covers", False)

                ### Library covers
                if source == "mpd" and path and not path.startswith("http"):
                    client = MPDClient()
                    client.timeout = 10
                    try:
                        client.connect("localhost", 6600)
                        pic = client.readpicture(path)
                        raw = pic.get("binary")

                        if raw:
                            img = core.Image.open(BytesIO(raw))
                            cover_img = convert_img_for_display(img)
                        if cover_img is None:
                            cover_img = get_fallback_image("MPD Library")
                    finally:
                        try:
                            client.disconnect()
                        except Exception:
                            pass

                ### HTTP covers
                elif source == "mpd" and path.startswith("http"):
                    is_yt = path.startswith(("https://rr", "https://manifest"))
                    if radio_covers:
                        # Wait for moOde to populate its SQL cache
                        cover_url = None
                        start_time = time.monotonic()
                        timeout = 10
                        while time.monotonic() - start_time < timeout:
                            # Stop waiting if a newer cover request is pending
                            with cover_lock:
                                if request_id != cover_request_id:
                                    break
                            cover_url = get_cached_cover_url(title)
                            if cover_url:
                                if core.DEBUG:
                                    print(f"Cover found in moOde cache after {time.monotonic() - start_time:.1f}s")
                                break
                            time.sleep(0.5)
                        if not cover_url:
                            if core.DEBUG:
                                print(f"Cover url NOT found in sql cache after {timeout}s")
                        # Only search if this request is still current
                        with cover_lock:
                            is_current = request_id == cover_request_id
                        if is_current and not cover_url:
                            cover_url = search_radiocover_plus(title, "" if is_yt else artist_album)
                        if is_current and cover_url:
                            cover_img = download_cover_image(cover_url)
                    # Radio station logo fallback
                    if not cover_img and not is_yt and album != "Unknown Radio":
                        cover_img = get_radio_logo(album)

                ### Bluetooth covers
                elif source == "bt":
                    if radio_covers:
                        artist_title = f"{artist} - {title}"
                        cover_url = (
                            cover_url_bt
                            if cover_url_bt and not cover_url_bt.endswith("images/default-album-cover.jpg")
                            else search_radiocover_plus(artist_title, "")
                        )
                        if cover_url:
                            cover_img = download_cover_image(cover_url)

                if cover_img is None:
                    cover_img = get_fallback_image("Cover Worker found nothing")
            except Exception as e:
                if core.DEBUG:
                    print("Cover worker error:", e)
                cover_img = get_fallback_image("Cover Worker Error")

            # Only update the display if this is still the latest request
            with cover_lock:
                if request_id == cover_request_id:
                    global_state["cover_img"] = cover_img

                    if core.DEBUG and cover_img:
                        print(
                            f"[COVER OK #{request_id}] "
                            f"title={title} size={cover_img.size}"
                        )
                elif core.DEBUG:
                    print(f"[COVER DISCARDED #{request_id}] title={title}")

def player_status_thread():
    global last_title_seen, last_artist_seen, menu_context_flag
    global last_radio_path, last_radio_title, ignore_next_radio_title
    client = MPDClient()
    client.timeout = 10
    while True:
        try:
            client.connect("localhost", 6600)
            break
        except Exception as e:
            if core.DEBUG:
                print("Player MPD connect error, retry in 5s:", e)
            time.sleep(5)
    first_run = True
    radio_changed = False
    ignore_cover = False
    while True:
        if (is_sleeping and screensaver_mode == "blank") or is_bt_local_active():
            time.sleep(1)
            continue
        now = time.time()
        try:
            if not first_run:
                events = client.idle("player")
            else:
                events = []
            if "player" in events or first_run:
                first_run = False
                ignore_cover = False
                radio_changed = False
                song_data = client.currentsong()
                status_extra = client.status()
                path = song_data.get("file", "")
                artist = song_data.get("artist", "")
                album = song_data.get("album", "")
                title = song_data.get("title", "")
                state = status_extra.get("state", "unknown")
                radio_name = song_data.get("name", "")

                if path.startswith("http"):
                    artist = "Radio station"
                    if path.startswith("https://rr") or path.startswith("https://manifest"):
                        menu_context_flag = "local_stream"
                        artist_album = f"YT Stream | [Album: {album_yt}]" if album_yt else "YT Stream"
                        title = clean_metadata(title)
                    else:
                        menu_context_flag = "radio"
                        if path != last_radio_path:
                            last_radio_path = path
                            last_radio_title = last_title_seen
                            ignore_next_radio_title = True
                            radio_changed = True
                        radio_info = get_radio_info(path)
                        album = radio_info["name"]
                        artist_album = radio_name if album == "Unknown Radio" else album # Radio name
                        artist = album
                        if ignore_next_radio_title:
                            if not title or title == last_radio_title:
                                ignore_cover = True
                            else:
                                ignore_next_radio_title = False
                else:
                    menu_context_flag = "library"
                    artist_album = f"{artist} - {album}"
                if title != last_title_seen:
                    core.reset_scroll("nowplaying_title")
                    last_title_seen = title
                if artist_album != last_artist_seen:
                    core.reset_scroll("nowplaying_artist")
                    last_artist_seen = artist_album
                global_state["title"] = title
                global_state["album"] = album
                global_state["artist"] = artist
                global_state["artist_album"] = artist_album
                global_state["path"] = path
                global_state["state"] = state
                global_state["duration"] = float(status_extra.get("duration", 0.0))

                audio_fmt = status_extra.get("audio", "")
                if audio_fmt:
                    try:
                        samplerate, bits, channels = audio_fmt.split(":")
                        samplerate = round(int(samplerate)/1000, 1)
                        if samplerate.is_integer():
                            samplerate = int(samplerate)
                        if bits == "f":
                            bits_label = "32b_F" if core.screen.width < 160 else "32-bit Float"
                        else:
                            bits_label = f"{bits}b" if core.screen.width < 160 else f"{bits}-bit"
                        if core.screen.width >= 160:
                            global_state["audio"] = f"{samplerate} kHz / {bits_label}"
                        else:
                            global_state["audio"] = f"{samplerate}k / {bits_label}"
                    except Exception:
                        global_state["audio"] = audio_fmt
                else:
                    global_state["audio"] = "No Info"

                if (screensaver_mode == "covers" and core.SCREEN_TIMEOUT > 0) or show_cover:
                    cover_data = {}
                    if not ignore_cover:
                        cover_data = {
                            "source": "mpd",
                            "path": path,
                            "title": title,
                            "artist_album": artist_album,
                            "album": album,
                            "radio_covers": bool(global_state.get("radio_track_covers"))
                        }
                    if radio_changed:
                        request_cover(placeholder=get_radio_logo(album), **cover_data)
                    elif cover_data:
                        request_cover(**cover_data)

        except Exception as e:
            if core.DEBUG:
                print("Player idle error:", e)
            first_run = True
            try:
                client.disconnect()
                client.connect("localhost", 6600)
            except Exception:
                time.sleep(5)
        time.sleep(0.1)

def non_idle_status_thread():
    last_fav_time = 0
    last_clock_time = 0
    last_renderer_check = 0
    last_elapsed_update = 0
    last_bt_meta = 0
    client = MPDClient()
    client.timeout = 10
    while True:
        try:
            client.connect("localhost", 6600)
            break
        except Exception as e:
            if core.DEBUG:
                print("Player MPD connect error, retry in 5s:", e)
            time.sleep(5)
    while True:
        if is_sleeping and screensaver_mode not in ("covers", "spectrum"):
            time.sleep(1)
            continue
        now = time.time()

        if is_bt_local_active() and now - last_bt_meta > 1:
            global last_title_seen, last_artist_seen
            last_bt_meta = now
            if os.path.isfile(BTMeta_Path):
                if os.path.getsize(BTMeta_Path) > 10:
                    try:
                        with open(BTMeta_Path, "r", encoding="utf-8") as f:
                            BTMeta = json.load(f)
                        if BTMeta and BTMeta.get("title") and BTMeta.get("artist"):
                            artist_bt = BTMeta.get("artist", "")
                            title_bt = BTMeta.get("title", "")
                            album_bt = BTMeta.get("album", "")
                            duration_bt = float(BTMeta.get("duration", 0.0))
                            sformat_bt = BTMeta.get("sformat", "")
                            playstate_bt = BTMeta.get("playstate", "").lower()
                            artist_album_bt = f"{artist_bt} - {album_bt}" if BTMeta.get("album") else f"{artist_bt}"
                            global_state["artist"] = artist_bt
                            global_state["title"] = title_bt
                            global_state["album"] = album_bt
                            global_state["artist_album"] = artist_album_bt
                            global_state["duration"] = duration_bt
                            global_state["audio"] = sformat_bt
                            if playstate_bt in ("resume", "playing", "play"):
                                global_state["state"] = "play"
                            elif playstate_bt in ("pause", "paused"):
                                global_state["state"] = "pause"
                            else:
                                global_state["state"] = "unknown"
                            cover_url_bt = BTMeta.get("cover_url", "")
                            if title_bt != last_title_seen or artist_album_bt != last_artist_seen:
                                core.reset_scroll("nowplaying_title")
                                core.reset_scroll("nowplaying_artist")
                                last_title_seen = title_bt
                                last_artist_seen = artist_album_bt
                                if (screensaver_mode == "covers" and core.SCREEN_TIMEOUT > 0) or show_cover:
                                    request_cover(
                                        source="bt",
                                        artist=artist_bt,
                                        title=title_bt,
                                        cover_url=cover_url_bt,
                                        radio_covers=bool(global_state.get("radio_track_covers"))
                                    )
                    except Exception as e:
                        if core.DEBUG: print("error help BTMeta: ", e)
                else:
                    global_state["artist"] = ""
                    global_state["title"] = core.t("show_bt_input")
                    global_state["album"] = ""
                    global_state["artist_album"] = ""
                    global_state["audio"] = "No Info"
                    global_state["state"] = "unknown"
                    #global_state["cover_img"] = None
                    if core.DEBUG: print("No info: file '/var/local/www/btmeta.json' empty")
            else:
                if core.DEBUG: print("error '/var/local/www/btmeta.json' file not found!")

        if now - last_elapsed_update > 1:
            last_elapsed_update = now
            try:
                status_extra = client.status()
                global_state["elapsed"] = float(status_extra.get("elapsed", 0.0))
                global_state["bitrate"] = status_extra.get("bitrate", "")
            except Exception as e:
                if core.DEBUG:
                    print("Non_idle_status error:", e)
                try:
                    client.disconnect()
                except Exception:
                    pass
                time.sleep(1)
                try:
                    client.connect("localhost", 6600)
                except Exception as e2:
                    if core.DEBUG:
                        print("MPD reconnect failed:", e2)
                    time.sleep(2)
        if now - last_renderer_check > 1.5:
            last_renderer_check = now
            load_renderer_states_from_db()
        if now - last_fav_time > 1.5:
            last_fav_time = now
            global_state["favorite"] = is_current_song_favorite(global_state.get("path", ""))
        if now - last_clock_time > 10:
            last_clock_time = now
            global_state["clock"] = time.strftime("%Hh%M")
        time.sleep(0.5)

def get_moode_volume():
    try:
        conn = sqlite3.connect(DB_PATH, timeout=1)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT param, value
            FROM cfg_system
            WHERE param IN ('volmute', 'volknob')
        """)
        data = dict(cursor.fetchall())
        conn.close()
        level = int(data.get("volknob", 0))
        mute = data.get("volmute", "0") == "1"
        return "Mute" if mute else str(level)
    except Exception as e:
        if core.DEBUG:
            print("get_moode_volume error:", e)
        return 0

def mixer_status_thread():
    client = MPDClient()
    client.timeout = 10
    while True:
        try:
            client.connect("localhost", 6600)
            break
        except Exception as e:
            if core.DEBUG:
                print("Mixer MPD connect error, retry in 5s:", e)
            time.sleep(5)
    first_run = True
    while True:
        if is_sleeping and screensaver_mode != "spectrum":
            time.sleep(1)
            continue
        try:
            if not first_run:
                events = client.idle("mixer")
            else:
                events = []
            if "mixer" in events or first_run:
                first_run = False
                volume_state = get_moode_volume()
                global_state["volume"] = volume_state
        except Exception as e:
            if core.DEBUG:
                print("Mixer idle error:", e)
            first_run = True
            try:
                client.disconnect()
                client.connect("localhost", 6600)
            except Exception:
                time.sleep(5)
        time.sleep(0.4)

def options_status_thread():
    client = MPDClient()
    client.timeout = 10
    while True:
        try:
            client.connect("localhost", 6600)
            break
        except Exception as e:
            if core.DEBUG:
                print("Options MPD connect error, retry in 5s:", e)
            time.sleep(5)
    first_run = True
    while True:
        if is_sleeping:
            time.sleep(1)
            continue
        try:
            if not first_run:
                events = client.idle("options")
            else:
                events = []
            if "options" in events or first_run:
                first_run = False
                status_extra = client.status()
                global_state["repeat"] = status_extra.get("repeat", "0")
                global_state["random"] = status_extra.get("random", "0")
                global_state["single"] = status_extra.get("single", "0")
                global_state["consume"] = status_extra.get("consume", "0")
        except Exception as e:
            if core.DEBUG:
                print("Options idle error:", e)
            first_run = True
            try:
                client.disconnect()
                client.connect("localhost", 6600)
            except Exception:
                time.sleep(5)
        time.sleep(0.5)

def update_hardware_info():
    global hardware_info_lines

    last_temp_time = 0
    last_cpu_time = 0
    last_mem_time = 0
    last_wifi_time = 0
    last_disk_time = 0
    last_eth_time = 0

    def get_cpu_percent_avg():
        def read_stat():
            with open("/proc/stat") as f:
                for line in f:
                    if line.startswith("cpu "):
                        return list(map(int, line.strip().split()[1:]))
        s1 = read_stat()
        time.sleep(1.0)
        s2 = read_stat()
        idle1 = s1[3] + s1[4]
        idle2 = s2[3] + s2[4]
        total1 = sum(s1)
        total2 = sum(s2)
        total_diff = total2 - total1
        idle_diff = idle2 - idle1
        if total_diff == 0:
            return "Cpu: N/A"
        usage = 100.0 * (total_diff - idle_diff) / total_diff
        return f"Cpu: {usage:.0f}%"

    while hardware_info_active:
        now = time.time()

        if now - last_temp_time > 5:
            last_temp_time = now
            try:
                with open("/sys/class/thermal/thermal_zone0/temp") as f:
                    temp_val = int(f.read()) / 1000
                temp = f"Temp: {temp_val:.1f}°C"
            except Exception as e:
                if core.DEBUG: print(f"error temp: {e}")
                temp = "Temp: N/A"

        if now - last_cpu_time > 1:
            last_cpu_time = now
            try:
                cpu = get_cpu_percent_avg()
            except Exception as e:
                if core.DEBUG: print(f"error Cpu: {e}")
                cpu = "Cpu: N/A"

        if now - last_mem_time > 3:
            last_mem_time = now
            zram_line = "Zram: N/A"
            swap_line = "Swap: None"
            try:
                with os.popen("free -m") as f:
                    lines = f.readlines()
                if len(lines) > 1:
                    ram_line = lines[1].split()
                    total = int(ram_line[1])
                    used = int(ram_line[2])
                    mem = f"Mem: {used}/{total} MB"
                else:
                    mem = "Mem: N/A"
            except Exception as e:
                if core.DEBUG: print(f"error Mem: {e}")
                mem = "Mem: N/A"
            try:
                with os.popen("zramctl") as f:
                    lines = f.readlines()
                for line in lines:
                    if line.startswith("/dev/zram"):
                        parts = line.split()
                        if len(parts) >= 5:
                            disksize = parts[2]
                            data = parts[3]
                            comp = parts[4]
                            zram_line = f"Zram: {data} / {disksize} (cmp: {comp})"
                        break
            except Exception as e:
                if core.DEBUG: print(f"error Zram: {e}")
                zram_line = "Zram: N/A"
            try:
                with open("/proc/swaps", "r") as f:
                    lines = f.readlines()
                if len(lines) > 1:
                    for line in lines[1:]:
                        if "zram" not in line:
                            parts = line.split()
                            if len(parts) >= 4:
                                total = int(parts[2]) // 1024
                                used = int(parts[3]) // 1024
                                swap_line = f"Swap: {used}/{total} MB"
                            break
            except Exception as e:
                if core.DEBUG: print(f"error Swap: {e}")
                swap_line = "Swap: N/A"

        if now - last_wifi_time > 2:
            global wifi_extra_info
            last_wifi_time = now
            wifi = "WiFi: N/A"
            wifi_extra_info = ""
            ap_mode = False
            ssid = None
            ip_addr = None
            try:
                iw_info = os.popen("iw dev wlan0 info 2>/dev/null").read()
                if "type AP" in iw_info:
                    ap_mode = True
                    for line in iw_info.splitlines():
                        if "ssid" in line.lower():
                            ssid = line.strip().split()[-1]
                            break
                    wifi = "Access Point"
                else:
                    with os.popen("iwconfig wlan0 2>/dev/null") as f:
                        for line in f:
                            if "Link Quality" in line:
                                parts = line.strip().split("Link Quality=")
                                if len(parts) > 1:
                                    quality = parts[1].split()[0]
                                    if "/" in quality:
                                        val, max_ = map(int, quality.split("/"))
                                        if max_ != 0:
                                            wifi = f"WiFi: {round(100 * val / max_)}%"
                    with os.popen("iwgetid -r") as f:
                        ssid = f.read().strip()
                with os.popen("ip addr show dev wlan0") as f:
                    for line in f:
                        if "inet " in line:
                            ip_addr = line.strip().split()[1].split("/")[0]
                            break
                if ap_mode:
                    wifi_extra_info = core.t("info_wifi_ap", ssid=ssid or "AP", ip=ip_addr or "N/A")
                    if has_internet_connection():
                        wifi_extra_info += f" | {core.t('info_internet_ok')}"
                    else:
                        wifi_extra_info += f" | {core.t('info_no_internet')}"
                elif ssid:
                    wifi_extra_info = core.t("info_wifi_connected", ssid=ssid, ip=ip_addr or "N/A")
                    if has_internet_connection():
                        wifi_extra_info += f" | {core.t('info_internet_ok')}"
                    else:
                        wifi_extra_info += f" | {core.t('info_no_internet')}"
                else:
                    wifi_extra_info = core.t("info_wifi_disconnected")
            except Exception as e:
                wifi = "Wifi: N/A"
                wifi_extra_info = ""
                core.show_message(core.t("error_wifi_status", error=e))
                if core.DEBUG:
                    print("error wifi status: ", e)

        if now - last_eth_time > 2:
            global eth_extra_info
            last_eth_time = now
            eth = None
            eth_extra_info = ""
            try:
                if os.path.exists("/sys/class/net/eth0"):
                    with os.popen("ip addr show eth0") as f:
                        output = f.read()
                    if "inet " in output:
                        ip_line = [line for line in output.splitlines() if "inet " in line][0]
                        ip = ip_line.strip().split()[1].split("/")[0]
                        eth = f"Eth: {ip}"
                        if has_internet_connection():
                            eth_extra_info = core.t("info_internet_ok")
                        else:
                            eth_extra_info = core.t("info_no_internet")
                    else:
                        eth = core.t("menu_eth_disconnected")
            except Exception as e:
                eth = None
                core.show_message(core.t("error_eth_status", error=e))
                if core.DEBUG:
                    print("error eth status: ", e)

        if now - last_disk_time > 30:
            last_disk_time = now
            try:
                with os.popen("df -h /") as f:
                    lines = f.readlines()
                if len(lines) > 1:
                    parts = lines[1].split()
                    used, total, avail = parts[2], parts[1], parts[3]
                    disk = f"Root: {used}/{total} (free: {avail})"
                else:
                    disk = "Root: N/A"
            except Exception as e:
                if core.DEBUG: print(f"error Disk: {e}")
                disk = "Root: N/A"
            try:
                mpd_mounts = []
                with os.popen("df -h -x tmpfs -x devtmpfs") as f:
                    lines = f.readlines()[1:]
                for line in lines:
                    parts = line.split()
                    if len(parts) < 6:
                        continue
                    mount_point = parts[5]
                    if not (mount_point.startswith("/media/") or mount_point.startswith("/mnt/")):
                        continue
                    used, total, avail = parts[2], parts[1], parts[3]
                    name = os.path.basename(mount_point)
                    mpd_mounts.append(f"{name}: {used}/{total} (free: {avail})")
                def is_usb_mount(name, mount_point):
                    lower = name.lower()
                    return (
                        mount_point.startswith("/media/") or
                        "usb" in lower or
                        "sda" in lower or
                        "flash" in lower or
                        "stick" in lower
                    )
                mpd_mounts.sort(key=lambda line: (
                    is_usb_mount(line.split(":")[0], line),
                    line.lower()
                ))
            except Exception as e:
                if core.DEBUG: print(f"error Disk: {e}")
                mpd_mounts = ["Storage: N/A"]

        hardware_info_lines = [temp, cpu, wifi, mem, zram_line, swap_line, disk]
        if eth:
            hardware_info_lines.insert(3, eth)
        hardware_info_lines += mpd_mounts

def set_mpd_state(option, value):
    try:
        client = MPDClient()
        client.timeout = 2
        client.connect("localhost", 6600)
        if option == "random":
            client.random(value)
        elif option == "repeat":
            client.repeat(value)
        elif option == "single":
            client.single(value)
        elif option == "consume":
            client.consume(value)
        client.close()
        client.disconnect()
    except Exception as e:
        core.show_message(core.t("error_mpd", error=e))
        if core.DEBUG:
            print("error mpd: ", e)

def get_favorites_playlist_name():
    try:
        conn = sqlite3.connect("/var/local/www/db/moode-sqlite3.db")
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM cfg_system WHERE param = 'favorites_name'")
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else "Favorites"
    except Exception as e:
        core.show_message(core.t("error_db", error=e))
        if core.DEBUG:
            print("error db: ", e)
        return "Favorites"

global_state["favorites_playlist"] = get_favorites_playlist_name()

def is_current_song_favorite(path):
    global favorites_cache, favorites_last_mtime, favorites_last_check
    now = time.time()
    fav_name = global_state.get("favorites_playlist", "Favorites")
    fav_path = f"/var/lib/mpd/playlists/{fav_name}.m3u"
    if now - favorites_last_check < 3:
        return path in favorites_cache
    favorites_last_check = now
    try:
        mtime = os.path.getmtime(fav_path)
        if mtime != favorites_last_mtime:
            with open(fav_path, "r") as f:
                favorites_cache = set(f.read().splitlines())
            favorites_last_mtime = mtime
        return path in favorites_cache
    except Exception as e:
        core.show_message(core.t("error_favorite", error=e))
        if core.DEBUG:
            print("error favorite: ", e)
        return False

def toggle_favorite():
    global favorites_last_check
    fav_name = global_state.get("favorites_playlist", "Favorites")
    fav_path = f"/var/lib/mpd/playlists/{fav_name}.m3u"
    try:
        client = MPDClient()
        client.timeout = 2
        client.idletimeout = None
        client.connect("localhost", 6600)
        song = client.currentsong()
        file_path = song.get("file")
        if not file_path:
            core.show_message(core.t("info_no_track"))
            client.close()
            client.disconnect()
            return
        try:
            client.listplaylist(fav_name)
        except:
            if core.DEBUG: print("Favorite playlist not found, create new Favorites playlist.")
            client.save(fav_name)
            subprocess.run(["sudo", "chmod", "777", fav_path])
            subprocess.run(["sudo", "chown", "root:root", fav_path])
            subprocess.call(["python3",  OLIPIMOODE_DIR / "playlist_tags.py", "--file", fav_path, "--add-img"])
        playlist = client.listplaylist(fav_name)
        if file_path in playlist:
            client.command_list_ok_begin()
            client.playlistdelete(fav_name, playlist.index(file_path))
            client.command_list_end()
            subprocess.run(["sudo", "chmod", "777", fav_path])
            subprocess.run(["sudo", "chown", "root:root", fav_path])
            subprocess.call(["python3",  OLIPIMOODE_DIR / "playlist_tags.py", "--file", fav_path, "--add-img"])
            if core.DEBUG: print("✓ Removed from Favorites")
        else:
            client.playlistadd(fav_name, file_path)
            if core.DEBUG: print("✓ Added to Favorites")
        client.close()
        client.disconnect()
        favorites_last_check = 0

    except Exception as e:
        core.show_message(core.t("error_mpd", error=e))
        if core.DEBUG:
            print("error mpd: ", e)

def remove_from_queue():
    try:
        client = MPDClient()
        client.connect("localhost", 6600)
        song = client.currentsong()
        pos = song.get("pos")
        if pos is not None:
            client.delete(int(pos))
            core.show_message(core.t("info_removed_queue"))
        client.close()
        client.disconnect()
    except Exception as e:
        core.show_message(core.t("error_mpd", error=e))
        if core.DEBUG:
            print("error mpd: ", e)

def search_artist_from_now():
    artist = global_state.get("artist", "").strip()
    if not artist:
        core.show_message(core.t("error_search_artist_generic"))
        return
    artist_words = artist.split()
    if len(artist_words) > 2:
        artist = " ".join(artist_words[:2])
    artist = artist.lower()
    try:
        override_path = OLIPIMOODE_DIR / ".search_artist"
        with open(override_path, "w", encoding="utf-8") as f:
            f.write(artist)
        os.chmod(override_path, 0o664)
        os.chown(override_path, os.getuid(), os.getgid())
        core.show_message(core.t("info_search_artist", artist=artist))
        time.sleep(2)
        subprocess.call(["sudo", "systemctl", "start", "olipi-ui-browser.service"])
        subprocess.call(["sudo", "systemctl", "stop", "olipi-ui-playing.service"])
    except Exception as e:
        core.show_message(core.t("error_search_artist", error=e))
        if core.DEBUG:
            print("error search artist: ", e)
        if not core.DEBUG:
            core.show_message(core.t("error_generic"))

def ensure_songlog_file():
    try:
        path = OLIPIMOODE_DIR / "songlog.txt"
        if not path.exists():
            path.touch(mode=0o664, exist_ok=True)
            os.chown(path, os.getuid(), os.getgid())
    except Exception as e:
        core.show_message(core.t("error_create_songlog", error=e))
        if core.DEBUG:
            print("error create songlog: ", e)
        if not core.DEBUG:
            core.show_message(core.t("error_generic"))

def log_song():
    artist = global_state.get('artist', 'Unknown')
    title = global_state.get('title', 'Unknown')
    album = global_state.get('album', 'Unknown')
    now = datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    if artist == 'Radio station':
        main = f"{title}"
    else:
        main = f"{artist} - {title}"
    suffix = f"[{album} | {now}]"
    songlog_line = f"{main} {suffix}\n"
    ensure_songlog_file()
    with open(OLIPIMOODE_DIR / 'songlog.txt', 'a') as f:
        f.write(songlog_line)
    core.show_message(core.t("info_logged_title"))
    if core.DEBUG:
        print("Saved:", songlog_line.strip())

def show_songlog():
    global songlog_lines, songlog_meta
    try:
        ensure_songlog_file()
        path = OLIPIMOODE_DIR / "songlog.txt"
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        lines = [html.unescape(line.strip()) for line in lines if line.strip()]
        if not lines:
            core.show_message(core.t("info_empty_songlog"))
            songlog_lines = []
            songlog_meta = []
            prune_yt_cache_to_songlog
            return
        entries = lines[-50:][::-1]
        songlog_lines = []
        songlog_meta = []
        for line in entries:
            if "[" in line and "]" in line:
                text, meta = line.rsplit("[", 1)
                songlog_lines.append(text.strip())
                songlog_meta.append(meta.rstrip("] "))
            else:
                songlog_lines.append(line)
                songlog_meta.append("")
        prune_yt_cache_to_songlog()
    except Exception as e:
        core.show_message(core.t("error_rd_songlog", error=e))
        if core.DEBUG:
            print("error rd songlog: ", e)
        if not core.DEBUG:
            core.show_message(core.t("error_generic"))

def confirm_delete_all_songlog(cancel=False):
    if cancel:
        global songlog_active
        core.show_message(core.t("info_cancelled"))
        show_songlog()
        if not songlog_lines:
            tool_menu_active = True
        else:
            songlog_active = True
        core.reset_scroll("menu_item")
    else:
        delete_all_songlog()

def delete_all_songlog():
    global songlog_lines, songlog_selection, songlog_active
    try:
        ensure_songlog_file()
        path = OLIPIMOODE_DIR / "songlog.txt"
        with open(path, "w", encoding="utf-8") as f:
            f.write("")
        songlog_lines = []
        songlog_meta = []
        songlog_selection = 0
        core.show_message(core.t("info_all_deleted"))
        time.sleep(2)
        show_songlog()
    except Exception as e:
        core.show_message(core.t("error_rm_all_songlog", error=e))
        if core.DEBUG:
            print("error rm all songlog: ", e)
        if not core.DEBUG:
            core.show_message(core.t("error_generic"))

def delete_songlog_entry(index_from_display):
    global songlog_lines, songlog_selection
    try:
        path = OLIPIMOODE_DIR / "songlog.txt"
        with open(path, "r", encoding="utf-8") as f:
            all_lines = [ln.rstrip("\n") for ln in f if ln.strip()]
        if not all_lines or not songlog_lines:
            core.show_message(core.t("info_nothing_delete"))
            return
        # Retrieve the line to delete from songlog_lines
        target_line = songlog_lines[index_from_display]
        idx_abs = index_from_display
        new_all_lines = []
        for ln in all_lines:
            if ln.startswith(target_line):
                continue
            new_all_lines.append(ln)
        with open(path, "w", encoding="utf-8") as f:
            for ln in new_all_lines:
                f.write(ln + "\n")
        # Update songlog_lines: delete by index
        songlog_lines.pop(idx_abs)
        core.show_message(core.t("info_entry_deleted"))
        time.sleep(1)
        show_songlog()
        if songlog_selection >= len(songlog_lines):
            songlog_selection = max(0, len(songlog_lines) - 1)
    except Exception as e:
        core.show_message(core.t("error_rm_songlog", error=e))
        if core.DEBUG:
            print("error rm songlog: ", e)
        if not core.DEBUG:
            core.show_message(core.t("error_generic"))

def prune_yt_cache_to_songlog():
    cache_path = OLIPIMOODE_DIR / "yt_cache.json"
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            yt_cache = json.load(f)
    except:
        return
    valid_keys = set(line.strip() for line in songlog_lines)
    removed = 0
    for key in list(yt_cache.keys()):
        if key not in valid_keys:
            del yt_cache[key]
            removed += 1
    if removed:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(yt_cache, f, indent=2)
        if core.DEBUG:
            print(f"Pruned {removed} entries from yt_cache (not in songlog)")

def _load_yt_cache():
    with yt_cache_lock:
        try:
            with open(yt_cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}


def _save_yt_cache(yt_cache):
    with yt_cache_lock:
        with open(yt_cache_path, "w", encoding="utf-8") as f:
            json.dump(yt_cache, f, indent=2)


def _extract_ytdlp_videos(local_query):
    from yt_dlp import YoutubeDL
    ydl_opts = {
        "quiet": True,
        "default_search": "ytsearch2",
        "no-check-certificate": True,
        "noplaylist": True,
        "format": "bestaudio[protocol=m3u8_native]",
        "no_warnings": True,
        "ignoreerrors": True,
    }
    attempts_total = 2
    info = None
    last_exception = None

    for attempt in range(attempts_total):
        try:
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(local_query, download=False)
            last_exception = None
            break
        except Exception as e:
            last_exception = e
            if core.DEBUG:
                print(
                    f"[yt-dlp] attempt {attempt + 1}/"
                    f"{attempts_total} failed: {e}"
                )
            if attempt < attempts_total - 1:
                time.sleep(1.0)

    if info is None:
        raise last_exception or RuntimeError(
            "yt-dlp failed without exception"
        )

    if "_type" in info and "entries" in info:
        entries = [
            v for v in info.get("entries", [])
            if v and v.get("url")
        ]
        if not entries:
            raise RuntimeError(
                f"No yt-dlp entries found for: {local_query}"
            )
        # Prioritize long videos, preserving original order
        long_entries = [
            v for v in entries if (v.get("duration") or 0) > 60
        ]
        short_entries = [
            v for v in entries if (v.get("duration") or 0) <= 60
        ]
        videos = long_entries + short_entries

    else:
        if not info.get("url"):
            raise RuntimeError(
                f"No yt-dlp url found for: {local_query}"
            )
        videos = [info]

    if core.DEBUG:
        for i, video in enumerate(videos, 1):
            print(
                f"[yt-dlp] result {i}: "
                f"format={video.get('format_id')} "
                f"protocol={video.get('protocol')} "
                f"codec={video.get('acodec')} "
                f"abr={video.get('abr')} "
                f"ext={video.get('ext')}"
            )

    return videos

def resolve_stream_track(local_query):
    global final_title_yt, album_yt, artist_yt
    from difflib import SequenceMatcher

    def _norm(text):
        if not text:
            return ""
        text = text.lower().strip()
        # remove accents
        text = unicodedata.normalize("NFKD", text)
        text = "".join(c for c in text if not unicodedata.combining(c))
        # normalize separators
        text = text.replace("–", "-").replace("—", "-")
        # remove featuring blocks
        text = re.sub(
            r"\(?\b(feat\.?|ft\.?|featuring|with|w/)\b[^)\]]*\)?",
            "",
            text,
            flags=re.IGNORECASE
        )
        # normalize separators
        text = re.sub(r"[-_/|:~]+", " ", text)
        # remove junk chars
        text = re.sub(r"[^\w\s]", " ", text)
        # collapse spaces
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _tokenize(text):
        return [t for t in _norm(text).split() if len(t) > 1]

    def _similar(a, b):
        return SequenceMatcher(None, a, b).ratio()

    def _soft_match(query, target, min_ratio=0.6):
        q_tokens = _tokenize(query)
        t_tokens = _tokenize(target)
        if not q_tokens or not t_tokens:
            return False
        matched = 0
        for q in q_tokens:
            best = max((_similar(q, t) for t in t_tokens), default=0)
            # short words must match exactly
            threshold = 1.0 if len(q) <= 4 else 0.80
            if best >= threshold:
                matched += 1
        ratio = matched / len(q_tokens)
        return ratio >= min_ratio

    original_query = local_query.strip()

    local_query = (
        original_query
        .replace("–", "-")
        .replace("—", "-")
        .strip()
    )

    if core.DEBUG:
        print(f"→ Resolve stream track: {local_query}")

    if " - " not in local_query:
        if core.DEBUG:
            print(f"[yt] invalid query format: {local_query}")
        return None

    artist_query, title_query = map(
        str.strip,
        local_query.split(" - ", 1)
    )

    # canonical metadata
    artist_final = artist_query
    title_final = f"{artist_query} - {title_query}"

    # original cache key
    cache_key = original_query

    # ---------------------------------------------------------
    # cache lookup
    # ---------------------------------------------------------

    yt_cache = _load_yt_cache()
    cache_entry = yt_cache.get(cache_key)

    if cache_entry and cache_entry.get("resolved") and cache_entry.get("url"):

        expire_ts = cache_entry.get("expire_ts")
        expire_str = cache_entry.get("expires", "?")
        now_ts = int(time.time())

        url_expired = (
            expire_ts is None
            or now_ts >= int(expire_ts)
        )

        if not url_expired:

            if core.DEBUG:
                print(f"✓ Cached URL still valid until {expire_str}")
                print(f"Using cached result for: {local_query}")

            return {
                "query": local_query,
                "url": cache_entry["url"],
                "title": cache_entry.get("title") or title_final,
                "artist": cache_entry.get("artist") or artist_final,
                "album": cache_entry.get("album") or "",
                "duration": float(cache_entry.get("duration") or 0.0),
            }

    else:
        if core.DEBUG:
            print("❓ No entry in cache")

    # ---------------------------------------------------------
    # yt-dlp resolve
    # ---------------------------------------------------------

    search_queries = [local_query]

    cleaned_query = clean_metadata(local_query)
    if cleaned_query and cleaned_query != local_query:
        search_queries.append(cleaned_query)

    video = None
    resolved_url = None

    artist_match_query = clean_metadata(artist_query) or artist_query
    title_match_query = clean_metadata(title_query) or title_query

    for search_query in search_queries:

        if core.DEBUG:
            print(f"[yt] search: {search_query}")

        try:
            candidates = _extract_ytdlp_videos(search_query)

        except Exception as e:
            if core.DEBUG:
                print(f"[resolve] search failed: {e}")
            continue

        for candidate in candidates:

            if not candidate or not candidate.get("url"):
                continue

            candidate_artist = (
                candidate.get("artist")
                or candidate.get("album_artist")
                or candidate.get("creator")
                or ""
            )

            candidate_track = (
                candidate.get("track")
                or candidate.get("title")
                or ""
            )

            candidate_artist_clean = (
                clean_metadata(candidate_artist) or candidate_artist
            )

            candidate_track_clean = (
                clean_metadata(candidate_track) or candidate_track
            )

            artist_ok = (
                _soft_match(artist_match_query, candidate_artist_clean)
                or _soft_match(artist_match_query, candidate_track_clean)
            )

            title_ok = _soft_match(
                title_match_query,
                candidate_track_clean
            )

            if artist_ok and title_ok:
                video = candidate
                resolved_url = candidate["url"]
                break

            if core.DEBUG:
                print(
                    "[yt] rejected result\n"
                    f"   search query : {search_query}\n"
                    f"   query artist : {artist_query}\n"
                    f"   query title  : {title_query}\n"
                    f"   yt artist    : {candidate_artist}\n"
                    f"   yt track     : {candidate_track}"
                )

        if video:
            break

    if not video:
        if core.DEBUG:
            print(f"[resolve] no valid yt-dlp result: {local_query}")
        return None

    album = video.get("album")
    duration = video.get("duration")
    webpage_url = video.get("webpage_url")

    yt_track = video.get("track") or video.get("title") or ""

    expire_ts = None
    expire_str = None

    match = re.search(r"[?&]expire=(\d+)|/expire/(\d+)", resolved_url)

    if match:
        expire_ts = int(match.group(1) or match.group(2))

        expire_str = datetime.datetime.fromtimestamp(
            expire_ts
        ).strftime("%Y-%m-%d %H:%M:%S")

    if core.DEBUG:
        print(f"[yt-dlp] yt-track    : {yt_track}")
        print(f"[yt-dlp] final-title: {title_final}")
        print(f"[yt-dlp] album      : {album}")
        print(f"[yt-dlp] duration   : {duration}")
        print(f"[yt-dlp] expire at  : {expire_str}")

    yt_cache[cache_key] = {
        "title": title_final,
        "title_raw": yt_track,
        "artist": artist_final,
        "album": album,
        "duration": duration,
        "acodec": video.get("acodec"),
        "abr": video.get("abr"),
        "ext": video.get("ext"),
        "format": video.get("format"),
        "webpage_url": webpage_url,
        "url": resolved_url,
        "resolved": True,
        "timestamp": datetime.datetime.now().isoformat(),
        "expires": expire_str,
        "expire_ts": expire_ts,
    }

    _save_yt_cache(yt_cache)

    return {
        "query": local_query,
        "url": resolved_url,
        "title": title_final,
        "artist": artist_final,
        "album": album or "",
        "duration": float(duration or 0.0),
    }

def add_default_cover(playlist_name):
    src =  OLIPIMOODE_DIR / "assets/NewPlaylist.jpg"
    dest_dir = "/var/local/www/imagesw/playlist-covers"
    dest = os.path.join(dest_dir, f"{playlist_name}.jpg")
    subprocess.call(["sudo", "cp", src, dest])
    if core.DEBUG:
        print(f"Custom cover image saved to: {dest}")

def write_m3u_playlist(source_lines):
    total = len(source_lines)
    core.start_spinner(core.t("info_start_stream"))
    try:
        lines = [
            "#EXTM3U",
            "#EXTGENRE:YouTube",
            "#EXTIMG:local",
        ]
        resolved_tracks = []

        for idx, raw in enumerate(source_lines):
            query = raw.strip()
            #short_title = query[:48]
            core.update_spinner(text=core.t("info_search"), extra=f" [{idx+1}/{total}]:\n{query}\n")
            if not query:
                continue
            try:
                track = resolve_stream_track(query)
                if not track:
                    if core.DEBUG:
                        print(f"[resolve] rejected: {query}")
                    continue
            except Exception as e:
                if core.DEBUG:
                    print(f"[resolve] skip: {query}")
                    print(f"   reason: {e}")
                continue

            url = track.get("url")
            if not url:
                continue

            duration = int(track.get("duration") or -1)
            display = track["title"]

            lines.append(f"#EXTINF:{duration},{display}")
            lines.append(url)
            resolved_tracks.append(track)

        if len(resolved_tracks) == 0:
            print("⚠️ Playlist empty")
            return None

        content = "\n".join(lines) + "\n"

        tmp_path = "/tmp/YT-Stream.m3u"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(content)

        subprocess.run(["sudo", "cp", tmp_path, "/var/lib/mpd/playlists/YT-Stream.m3u"], check=True)
        subprocess.run(["sudo", "chmod", "777", "/var/lib/mpd/playlists/YT-Stream.m3u"], check=True)
        subprocess.run(["sudo", "chown", "root:root", "/var/lib/mpd/playlists/YT-Stream.m3u"], check=True)
        add_default_cover("YT-Stream")
        return resolved_tracks
    finally:
        core.stop_spinner()

def load_and_tag_playlist(resolved_tracks):
    client = MPDClient()
    client.timeout = 10
    client.connect("localhost", 6600)
    client.clear()
    client.load("YT-Stream")
    playlist = client.playlistinfo()

    for pos, song in enumerate(playlist):
        if pos >= len(resolved_tracks):
            break

        songid = song["id"]
        track = resolved_tracks[pos]

        client.addtagid(songid, "name", "YT Stream")
        client.addtagid(songid, "title", track["title"])

    client.play(0)
    client.close()
    client.disconnect()

def play_all_songlog_via_m3u(songlog_lines):
    global now_playing_mode
    if not songlog_lines:
        core.show_message(core.t("info_empty_songlog"))
        return
    try:
        resolved_tracks = write_m3u_playlist(songlog_lines)
        if not resolved_tracks:
            return
        load_and_tag_playlist(resolved_tracks)
    except Exception as e:
        core.show_message(core.t("error_mpd", error=e))
        if core.DEBUG:
            print("error play_all_songlog_via_m3u:", e)
    finally:
        core.stop_spinner()
        now_playing_mode = True

def play_songlog_index(index):
    global now_playing_mode
    if index >= len(songlog_lines):
        core.show_message(core.t("info_invalid_index"))
        return
    try:
        resolved_tracks = write_m3u_playlist([songlog_lines[index]])
        if not resolved_tracks:
            return
        load_and_tag_playlist(resolved_tracks)
    except Exception as e:
        core.show_message(core.t("error_mpd", error=e))
        if core.DEBUG:
            print("error play_songlog_index:", e)
    finally:
        core.stop_spinner()
        now_playing_mode = True

def run_bluetooth_action(*args):
    output = []

    def act_blucontrol():
        try:
            result = subprocess.run(["sudo", "/var/www/util/blu-control.sh"] + list(args), capture_output=True, text=True, timeout=30)
            output.append(result.stdout.strip())
        except Exception as e:
            core.show_message(core.t("error_bluetooth_action", error=e))
            if core.DEBUG:
                print("error bluetooth action: ", e)
            output.append("")

    thread = threading.Thread(target=act_blucontrol)
    thread.start()
    thread.join()
    return output[0] if output else ""

def perform_bluetooth_scan():
    global blocking_render, bluetooth_scan_menu_active
    core.message_text = core.t("inf_bt_scanning")
    core.message_permanent = True
    blocking_render = True
    time.sleep(0.05)
    render_screen()

    run_bluetooth_action("-s")
    update_trusted_devices_menu()

    time.sleep(0.5)
    core.message_permanent = False
    core.message_text = None
    core.show_message(core.t("info_bt_scan_ok"))
    blocking_render = False
    bluetooth_scan_menu_active = True

def get_bt_devices(flag):
    lines = run_bluetooth_action(flag).splitlines()
    devices = []

    for i, line in enumerate(lines):
        if i < 2:
            continue
        if not line.startswith("** "):
            continue

        line = line[3:].strip()
        parts = line.split(" ", 1)
        if len(parts) == 2:
            mac, name = parts
            devices.append({
                "mac": mac,
                "name": name
            })

    return devices

def get_bt_macs(flag):
    return {d["mac"] for d in get_bt_devices(flag)}

def get_connected_bt_mac():
    devices = get_bt_devices("-c")
    return devices[0]["mac"] if devices else None

def update_trusted_devices_menu():
    global bluetooth_scan_menu_options

    scanned = get_bt_devices("-l")
    paired_set = get_bt_macs("-p")
    connected_set = get_bt_macs("-c")

    bluetooth_scan_menu_options = []

    for d in scanned:
        mac = d["mac"]
        name = d["name"]

        is_paired = mac in paired_set
        is_connected = mac in connected_set

        if is_connected:
            icon = "✓⚪ "
        elif is_paired:
            icon = "⚪ "
        else:
            icon = ""

        bluetooth_scan_menu_options.append({
            "id": f"bt_trusted_{mac}",
            "label": f"{icon}{name}",
            "mac": mac,
            "paired": is_paired,
            "connected": is_connected
        })

def update_paired_devices_menu():
    global bluetooth_paired_menu_options

    paired_devices = get_bt_devices("-p")
    connected_set = get_bt_macs("-c")

    bluetooth_paired_menu_options = []

    for d in paired_devices:
        mac = d["mac"]
        name = d["name"]

        is_connected = mac in connected_set
        icon = "✓ " if is_connected else ""

        bluetooth_paired_menu_options.append({
            "id": f"bt_dev_{mac}",
            "label": f"{icon}{name}",
            "mac": mac,
            "connected": is_connected
        })

def open_device_actions_menu(mac, paired=False, connected=False):
    name = next((d['label'] for d in bluetooth_scan_menu_options + bluetooth_paired_menu_options if d['mac'] == mac), mac)
    global bluetooth_device_actions_menu_options, selected_bt_mac
    selected_bt_mac = mac
    options = []
    if not paired:
        options.append({"id": f"bt_pair_{mac}", "label": core.t("menu_bt_pair")})
        options.append({"id": f"bt_mac_{mac}", "label": mac})
    if paired and not connected:
        options.append({"id": f"bt_connect_{mac}", "label": core.t("menu_bt_connect")})
    if connected:
        options.append({"id": f"bt_disconnect_{mac}", "label": core.t("menu_bt_disconnect")})
    if paired:
        options.append({"id": f"bt_remove_{mac}", "label": core.t("menu_bt_remove")})
        options.append({"id": f"bt_mac_{mac}", "label": mac})
    bluetooth_device_actions_menu_options = options

def run_bt_action_and_msg(flag, mac, msg_key):
    global blocking_render, bluetooth_menu_active

    core.message_text = core.t("info_working")
    core.message_permanent = True
    blocking_render = True
    time.sleep(0.05)
    render_screen()

    run_bluetooth_action(flag, mac)

    time.sleep(0.5)
    core.message_permanent = False
    core.message_text = None
    core.show_message(core.t(msg_key, name=mac))
    blocking_render = False
    bluetooth_menu_active = True

def toggle_audio_output(mode, mac=None):
    global blocking_render, bluetooth_menu_active

    core.message_text = core.t("info_working")
    core.message_permanent = True
    blocking_render = True
    time.sleep(0.05)
    render_screen()

    output = []

    def act_bluaudiout():
        try:
            if mode == "Local":
                cmd = ["sudo", "/var/www/util/set-btaudio.php", "--local"]
            else:
                cmd = ["sudo", "/var/www/util/set-btaudio.php", "--btspeaker"]
                if mac:
                    cmd.append(mac)

            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            stdout = (result.stdout or "").strip()
            stderr = (result.stderr or "").strip()
            output.append(stdout if stdout else stderr)

        except Exception as e:
            core.show_message(core.t("error_audioout", error=e))
            if core.DEBUG:
                print("error audioout:", e)
            output.append("[ERROR]")

    thread = threading.Thread(target=act_bluaudiout)
    thread.start()
    thread.join()

    load_renderer_states_from_db()
    time.sleep(0.5)
    core.message_permanent = False
    core.message_text = None

    result_line = output[0] if output else "[ERROR]"

    if "Missing MAC address" in result_line:
        core.show_message(core.t("error_audioout_bt_missing"))
    elif result_line.startswith("Output is already"):
        core.show_message(core.t("info_audioout_already", mode=mode))
    else:
        core.show_message(core.t("info_audioout_changed", mode=mode))

    blocking_render = False
    bluetooth_menu_active = True

def update_eq_preset_menu(eq_type):
    global eq_preset_options, eq_preset_selection
    eq_preset_options = []
    try:
        cmd = ["sudo", "/var/www/util/eqctl.php", eq_type, "list"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        lines = result.stdout.strip().splitlines()
        for line in lines:
            parts = line.split("|")
            if len(parts) != 3:
                continue
            preset_id, name, active = parts
            label = name
            if active == "1":
                label = "✓ " + name
            eq_preset_options.append({
                "id": preset_id,
                "label": label,
                "name": name,
                "active": active == "1",
                "type": eq_type
            })
        eq_preset_selection = 0
    except Exception as e:
        core.show_message(f"EQ list error: {e}")

def render_screen():
    with render_lock:
        global now_playing_mode
        now_playing_mode = False
        if core.message_text:
            core.draw_message()
            idle_timer = time.time()
        elif help_active:
            draw_help_screen()
        elif confirm_box_active:
            draw_confirm_box()
        elif hardware_info_active:
            draw_hardware_info()
        elif screensaver_menu_active:
            draw_screensaver_menu()
        elif ui_menu_active:
            draw_ui_menu()
        elif theme_menu_active:
            draw_theme_menu()
        elif language_menu_active:
            draw_language_menu()
        elif config_menu_active:
            draw_config_menu()
        elif renderers_menu_active:
            draw_renderers_menu()
        elif bluetooth_device_actions_menu_active:
            draw_bluetooth_device_actions_menu()
        elif bluetooth_audioout_menu_active:
            draw_bluetooth_audioout_menu()
        elif bluetooth_scan_menu_active:
            draw_bluetooth_scan_menu()
        elif bluetooth_paired_menu_active:
            draw_bluetooth_paired_menu()
        elif bluetooth_menu_active:
            draw_bluetooth_menu()
        elif eq_preset_active:
            draw_eq_preset_menu()
        elif eq_menu_active:
            draw_eq_menu()
        elif tool_menu_active:
            draw_tool_menu()
        elif songlog_action_active:
            draw_songlog_action_menu()
        elif songlog_active:
            draw_songlog_menu()
        elif power_menu_active:
            draw_power_menu()
        elif playback_modes_menu_active:
            draw_playback_modes_menu()
        elif menu_active:
            draw_menu()
        else:
            now_playing_mode = True
            draw_nowplaying()
        core.refresh()

def draw_menu():
    global menu_options_contextuel

    if global_state.get("state", "unknown") == "stop":
        menu_options_contextuel = menu_options.copy()
    elif menu_context_flag == "library":
        menu_options_contextuel = (
            (menu_remove_fav_option.copy() if global_state.get("favorite") else menu_add_fav_option.copy())
            + menu_search_artist_option.copy()
            + menu_options.copy()
        )
    elif menu_context_flag == "radio":
        if global_state.get("state", "unknown") == "pause":
            menu_options_contextuel = menu_options.copy()
        else:
            menu_options_contextuel = menu_add_songlog_option.copy() + menu_options.copy()
    elif menu_context_flag == "local_stream":
        menu_options_contextuel = menu_options.copy()
    else:
        menu_options_contextuel = menu_options.copy()

    core.draw_custom_menu([item["label"] for item in menu_options_contextuel], menu_selection, title=core.t("title_menu"))

def draw_playback_modes_menu():
    active = []
    for item in playback_modes_options:
        key = item["id"]
        if global_state.get(key) == "1":
            active.append(item["label"])
    core.draw_custom_menu([item["label"] for item in playback_modes_options], playback_modes_selection, title=core.t("title_playback"), multi=active)

def draw_power_menu():
    core.draw_custom_menu([item["label"] for item in power_menu_options], power_menu_selection, title=core.t("title_power"))

def draw_songlog_menu():
    core.draw_custom_menu(songlog_lines, songlog_selection, title=core.t("title_songlog"))

def draw_songlog_action_menu():
    core.draw_custom_menu([item["label"] for item in songlog_action_options], songlog_action_selection, title=core.t("title_action_songlog"))

def draw_tool_menu():
    core.draw_custom_menu([item["label"] for item in tool_menu_options], tool_menu_selection, title=core.t("title_tools"))

def draw_eq_menu():
    core.draw_custom_menu([item["label"] for item in eq_menu_options], eq_menu_selection, title=core.t("title_equalizers"))

def draw_eq_preset_menu():
    core.draw_custom_menu([item["label"] for item in eq_preset_options], eq_preset_selection, title=core.t("title_eq_preset"))

def draw_renderers_menu():
    active = []
    for item in renderers_menu_options:
        key = item["id"] + "svc"
        if global_state.get(key) == "1":
            active.append(item["label"])
    core.draw_custom_menu([item["label"] for item in renderers_menu_options], renderers_menu_selection, title=core.t("title_renderers"), multi=active)

def draw_bluetooth_menu():
    for item in bluetooth_menu_options:
        if item["id"] == "bt_toggle":
            item["label"] = core.t("menu_bt_toggle") + " On" if global_state.get("btsvc") == "1" else core.t("menu_bt_toggle") + " Off"
    core.draw_custom_menu([item["label"] for item in bluetooth_menu_options], bluetooth_menu_selection, title=core.t("title_bluetooth"))

def draw_bluetooth_scan_menu():
    core.draw_custom_menu([item["label"] for item in bluetooth_scan_menu_options], bluetooth_scan_menu_selection, title=core.t("title_bt_scan_result"))

def draw_bluetooth_paired_menu():
    core.draw_custom_menu([item["label"] for item in bluetooth_paired_menu_options], bluetooth_paired_menu_selection, title=core.t("title_bt_paired_list"))

def draw_bluetooth_audioout_menu():
    selected = set()
    if global_state.get("audioout") == "Bluetooth":
        selected.add(core.t("menu_audioout_bt"))
    else:
        selected.add(core.t("menu_audioout_local"))
    core.draw_custom_menu([item["label"] for item in bluetooth_audioout_menu_options], bluetooth_audioout_menu_selection, title=core.t("title_bt_audio_output"), multi=selected)

def draw_bluetooth_device_actions_menu():
    core.draw_custom_menu([item["label"] for item in bluetooth_device_actions_menu_options], bluetooth_device_actions_menu_selection, title=core.t("title_bt_device_actions"))

def draw_hardware_info():
    core.draw_custom_menu(hardware_info_lines, hardware_info_selection, title=core.t("title_hardware_info"))

def draw_config_menu():
    config_flags = set()
    if core.DEBUG:
        config_flags.add(core.t("menu_debug"))
    core.draw_custom_menu([item["label"] for item in config_menu_options], config_menu_selection, title=core.t("title_config"), multi=config_flags)

def draw_language_menu():
    selected = {item["label"] for item in language_menu_options if item["id"] == core.LANGUAGE}
    core.draw_custom_menu([item["label"] for item in language_menu_options], language_menu_selection, title=core.t("title_language"), multi=selected)

def draw_theme_menu():
    selected = {item["label"] for item in theme_menu_options if item["id"] == core.THEME_NAME}
    core.draw_custom_menu([item["label"] for item in theme_menu_options], theme_menu_selection, title=core.t("title_theme"), multi=selected)

def draw_ui_menu():
    ui_flags = set()
    if show_icons:
        ui_flags.add(core.t("menu_icons"))
    if show_one_line:
        ui_flags.add(core.t("menu_oneline"))
    if show_extra_infos:
        ui_flags.add(core.t("menu_extra_infos"))
    if show_progress_barre:
        ui_flags.add(core.t("menu_progress_bare"))
    for item in ui_menu_options:
        if item["id"] == "cover_bg":
            item["label"] = (core.t("menu_cover") + f": {cover_bg_labels.get(show_cover_bg, cover_bg_labels['off'])}")
    if show_spectrum:
        ui_flags.add(core.t("menu_spectrum"))
    for item in ui_menu_options:
        if item["id"] == "peak_vu":
            item["label"] = (core.t("menu_peak_vu") + f": {peak_vu_labels.get(show_peak_vu, peak_vu_labels['off'])}")
        elif item["id"] == "peak_vu_style":
            item["label"] = (core.t("menu_peak_vu_style") + f": {peak_vu_style_labels.get(peak_vu_style, peak_vu_style_labels['horizontal_inline'])}")
    if show_meters_alt:
        ui_flags.add(core.t("menu_meters_alt"))
    if show_scale_labels:
        ui_flags.add(core.t("menu_scale_label"))
    if show_vol_bar:
        ui_flags.add(core.t("menu_vol_bar"))
    if show_clock:
        ui_flags.add(core.t("menu_clock"))
    core.draw_custom_menu([item["label"] for item in ui_menu_options], ui_menu_selection, title=core.t("title_ui"), multi=ui_flags)

def draw_screensaver_menu():
    for item in screensaver_menu_options:
        if item["id"] == "sleep":
            item["label"] = core.t("menu_sleep") + f": {sleep_timeout_labels.get(core.SCREEN_TIMEOUT, 'Off')}"
            break
    selected = {item["label"] for item in screensaver_menu_options if item["id"] == screensaver_mode}
    core.draw_custom_menu([item["label"] for item in screensaver_menu_options], screensaver_menu_selection, title=core.t("title_screensaver"), multi=selected)

def draw_confirm_box():
    core.draw_custom_menu([item["label"] for item in confirm_box_options], confirm_box_selection, title=confirm_box_title)

def draw_help_screen():
    core.draw_custom_menu(help_lines, help_selection, title=core.t("title_help"))

def is_spectrum_available():
    global spectrum
    if "spectrum" in globals() and spectrum and getattr(spectrum, "running", False):
        return True
    try:
        from spectrum_capture import SpectrumCapture
        test = SpectrumCapture()
        ok = getattr(test, "available", True)
        test.stop()
        return ok
    except Exception as e:
        if core.DEBUG:
            print(f"[Spectrum] Availability check failed: {e}")
        return False

def start_spectrum():
    with render_lock:
        global spectrum, show_spectrum
        from spectrum_capture import SpectrumCapture
        n_bars = core.get_config("spectrum", "num_bars", fallback=21, type=int)
        spectrum = SpectrumCapture(n_bars)
        spectrum.start()

def stop_spectrum(timeout=2.0):
    with render_lock:
        global spectrum
        if spectrum:
            try:
                spectrum.stop()
            except Exception:
                pass
            try:
                spectrum.join(timeout)
            except Exception:
                pass
            try:
                if hasattr(spectrum, "is_alive") and spectrum.is_alive():
                    if core.DEBUG:
                        print("Warning: spectrum thread still alive after join()")
            except Exception:
                pass
            spectrum = None

def monitor_bt_spectrum():
    last_bt_active = is_bt_local_active()
    while True:
        try:
            bt_active = is_bt_local_active()
            if bt_active != last_bt_active:
                if core.DEBUG:
                    print(
                        f"BT state change: "
                        f"{last_bt_active} -> {bt_active}"
                    )
                stop_spectrum()
                time.sleep(0.1)
                start_spectrum()
                last_bt_active = bt_active
            time.sleep(0.5)

        except Exception as e:
            if core.DEBUG:
                print(f"BT spectrum monitor error: {e}")
            time.sleep(2)

def monitor_mpd_spectrum():
    client = MPDClient()
    client.timeout = 10
    while True:
        while True:
            try:
                client.connect("localhost", 6600)
                last_path = client.currentsong().get("file", "")
                break
            except Exception as e:
                print("MPD monitor connect error, retry in 5s:", e)
                time.sleep(5)
        last_toggle = 0
        while True:
            try:
                events = client.idle()
                if 'player' not in events:
                    continue
                if menu_context_flag == "radio":
                    song_data = client.currentsong()
                    path = song_data.get("file", "")
                    path_changed = path != last_path
                    last_path = path
                    if not path_changed:
                        continue
                if time.time() - last_toggle < 0.4:
                    continue
                stop_spectrum()
                time.sleep(0.03)
                client.pause()
                time.sleep(0.02)
                client.pause()
                last_toggle = time.time()
                time.sleep(0.03)
                start_spectrum()
            except Exception as e:
                print("MPD monitor error:", e)
                try:
                    client.disconnect()
                except Exception:
                    pass
                time.sleep(2)
                break

def delayed_spectrum_start():
    if not is_spectrum_available():
        if core.DEBUG:
            print("[UI] Spectrum disabled: no loopback device")
        core.show_message(core.t("error_spectrum"))
    else:
        start_spectrum()
        threading.Thread(target=monitor_mpd_spectrum, daemon=True).start()
        threading.Thread(target=monitor_bt_spectrum, daemon=True).start()

def interpolate_palette(value, palette):
    """Interpolate between colors in a palette (value ∈ [0,1])."""
    value = max(0.0, min(1.0, value))
    for i in range(len(palette) - 1):
        v0, c0 = palette[i]
        v1, c1 = palette[i + 1]
        if v0 <= value <= v1:
            t = (value - v0) / (v1 - v0)
            r = int(c0[0] + t * (c1[0] - c0[0]))
            g = int(c0[1] + t * (c1[1] - c0[1]))
            b = int(c0[2] + t * (c1[2] - c0[2]))
            return (r, g, b)
    return palette[-1][1]

def get_spectrum_geometry(width_spec, num_bars):
    # layout: keep 1px spacing (pitch - 1)
    if num_bars <= 0:
        return 0, 0, 0, 0, 0
    total_width = int(width_spec)
    pitch = total_width // num_bars
    bar_width = max(1, pitch - 1)
    margin_left = (core.width - pitch * num_bars) // 2
    x0 = margin_left
    x1 = margin_left + (num_bars - 1) * pitch + bar_width
    return margin_left, pitch, bar_width, x0, x1

def draw_spectrum(y_top, height, levels, attack=0.9, release=0.80, width_spec=core.width):
    palette = PALETTE_SPECTRUM
    num_bars = len(levels)
    if num_bars <= 0:
        return

    # initialize persistent visual array (kept on function object)
    if not hasattr(draw_spectrum, "vis_levels") or len(draw_spectrum.vis_levels) != num_bars:
        draw_spectrum.vis_levels = [0.0] * num_bars
    # persistent visual peak (AGC visuel lent)
    if not hasattr(draw_spectrum, "vis_peak"):
        draw_spectrum.vis_peak = 1e-6
    vis = draw_spectrum.vis_levels
    # layout: keep 1px spacing (pitch - 1)
    margin_left, pitch, bar_width, x0, x1 = get_spectrum_geometry(width_spec, num_bars)
    draw_spectrum.bounds = (x0, x1)
    # Precompute gradient (top -> bottom)
    if height <= 1:
        global_gradient = [interpolate_palette(1.0, palette)]
    else:
        global_gradient = [
            interpolate_palette(1.0 - (yy / (height - 1)), palette)
            for yy in range(height)
        ]
    # Convert levels to a simple list of floats
    lv = [float(x) for x in levels]
    current_peak = max(lv)
    vp = draw_spectrum.vis_peak
    if current_peak > vp:
        vp = 0.6 * vp + 0.4 * current_peak
    else:
        vp = 0.995 * vp
    draw_spectrum.vis_peak = max(vp, 1e-6)
    peak = draw_spectrum.vis_peak
    norm_levels = [l / peak for l in lv]
    # Per-bar asymmetric smoothing
    for i, tgt in enumerate(norm_levels):
        prev = vis[i]
        if tgt >= prev:
            a = attack
            new = prev * (1.0 - a) + tgt * a
        else:
            r = release
            new = prev * (1.0 - r) + tgt * r
        vis[i] = min(max(new, 0.0), 1.0)
    # draw bars
    for i, v in enumerate(vis):
        bar_h = int(v * height)
        if bar_h <= 0:
            continue
        x0 = margin_left + i * pitch
        x1 = x0 + bar_width - 1
        y_start = y_top + height - bar_h
        for y in range(bar_h):
            idx = max(0, min((y_start + y - y_top), len(global_gradient) - 1))
            color = global_gradient[idx]
            core.draw.rectangle((x0, y_start + y, x1, y_start + y), fill=color)

METER_DB_MIN = -42.0
METER_DB_GAMMA = 1.4
METER_DB_STEPS = (3, 6, 8, 10, 12, 18)
marker_color = tuple(int(c * 0.65) for c in core.COLOR_ARTIST)

def get_meter_db_marks(length_px, font, min_label_gap=4, label_axis="x", start_padding=0,):
    if length_px <= 0:
        return (0.0,)
    def label_extent(db):
        label = f"{int(db):+d}" if db < 0 else " 0"
        bbox = font.getbbox(label)
        if label_axis == "y":
            return bbox[3] - bbox[1]
        return bbox[2] - bbox[0]
    for step in METER_DB_STEPS:
        marks = sorted(range(0, int(METER_DB_MIN), -step))
        # Remove markers that are too close to the edge
        while marks:
            first_pos = meter_db_to_ratio(marks[0]) * (length_px - 1)
            if first_pos >= start_padding:
                break
            marks.pop(0)
        if not marks:
            continue
        positions = [meter_db_to_ratio(db) * (length_px - 1) for db in marks]
        # Checking the Actual Spacing Between Labels
        spacing_ok = all(
            positions[i + 1] - positions[i]
            >= max(
                label_extent(marks[i]),
                label_extent(marks[i + 1])
            ) + min_label_gap
            for i in range(len(marks) - 1)
        )
        if spacing_ok:
            return tuple(marks)
    return (0.0,)

def meter_db_to_ratio(db):
    ratio = max(0.0, min(1.0, (db - METER_DB_MIN) / (0.0 - METER_DB_MIN)))
    return ratio ** METER_DB_GAMMA

def level_to_vis(value):
    if value <= 0:
        return 0.0
    db = 20.0 * math.log10(value)
    ratio = max(0.0, min(1.0, (db - METER_DB_MIN) / (0.0 - METER_DB_MIN)))
    return ratio ** METER_DB_GAMMA

def get_vis(s, kind, channel, value, attack=0.99, release=0.99):
    key = f"{kind}_{channel}_vis"
    previous = s.get(key, 0.0)
    target = level_to_vis(value)
    if kind == "peak":
        factor = attack if target >= previous else release
        current = previous * (1.0 - factor) + target * factor
    else:
        current = target
    s[key] = current
    return current

def get_gradient(length):
    palette = PALETTE_SPECTRUM
    if length <= 1:
        return [interpolate_palette(1.0, palette)]
    return [
        interpolate_palette(i / (length - 1), palette)
        for i in range(length)
    ]

def get_bar_color(i, gradient, over=False, over_start=0):
    normal_color = gradient[min(i, len(gradient) - 1)]
    if not over or i < over_start:
        return normal_color
    if core.display_format != "MONO":
        return (255, 0, 0)
    # Monochrome Hatching
    return core.COLOR_PROGRESS_BG if i % 2 == 0 else normal_color

def update_peak_hold(s, channel, vis, now, peak_hold_time=0.5):
    key = f"peak_{channel}"
    ts_key = f"{key}_ts"
    if vis > s.get(key, 0.0):
        s[key] = vis
        s[ts_key] = now
    elif now - s.get(ts_key, 0.0) > peak_hold_time:
        s[key] = max(0.0, s.get(key, 0.0) * 0.96)
    return s.get(key, 0.0)

def draw_meters_horizontal(y_top, bar_h, x0, x1, peak_info, mode="peak", layout="horizontal_inline", row_gap=2, scale_extra_h=0):
    if not hasattr(draw_meters_horizontal, "state"):
        draw_meters_horizontal.state = {}
    s = draw_meters_horizontal.state

    values = {
        "peak": {
            "left": max(0.0, peak_info.get("left_peak", 0.0)),
            "right": max(0.0, peak_info.get("right_peak", 0.0)),
        },
        "vu": {
            "left": max(0.0, peak_info.get("left_vu", 0.0)),
            "right": max(0.0, peak_info.get("right_vu", 0.0)),
        },
    }

    modes = ("peak", "vu") if mode == "both" else (mode,)
    channels = ("left", "right")

    def draw_bar(y, length, gradient, over=False):
        over_start = max(0, length - max(1, round(length * 0.05))) if over else length
        for i in range(length):
            color = get_bar_color(i, gradient, over, over_start)
            core.draw.line((x0 + i, y, x0 + i, y + bar_h - 1), fill=color)

    def draw_peak_hold(y, position):
        if x0 <= position < x1:
            core.draw.line((position, y, position, y + bar_h - 1), fill=core.COLOR_ARTIST)

    # Geometry
    width = max(0, x1 - x0)
    if width <= 0:
        return
    center_gap = min(4, max(2, width // 20))
    center = (x0 + x1) // 2

    # --- dBFS scale markers ---
    if scale_extra_h > 0:
        max_label_w = font_meters_label.getlength(str(METER_DB_MIN))
        if layout == "horizontal_separate":
            rows_count = 4 if mode == "both" else 2
            db_marks = get_meter_db_marks(width, font_meters_label, min_label_gap=4, label_axis="x", start_padding=round(max_label_w) + 2,)
        else:
            rows_count = 2 if mode == "both" else 1
            left_width = max(0, center - x0 - center_gap // 2)
            right_width = max(0, x1 - center - (center_gap - center_gap // 2))
            # Width of the largest label that can be merged
            merge_label = f"{int(METER_DB_MIN):+d}"
            bbox = font_meters_label.getbbox(merge_label)
            merge_label_w = bbox[2] - bbox[0]
            # Required space between the first two markers
            marker_gap = center_gap + 1
            merge_margin = 2
            start_padding = max(0, math.ceil((merge_label_w + 2 * merge_margin - marker_gap) / 2))
            db_marks = get_meter_db_marks(min(left_width, right_width), font_meters_label, min_label_gap=4, label_axis="x", start_padding=start_padding,)

        bars_height = (rows_count * bar_h + max(0, rows_count - 1) * row_gap)
        scale_y = y_top + bars_height
        for db in db_marks:
            ratio = meter_db_to_ratio(db)
            label = f"{int(db):+d}" if db < 0 else " 0"
            bbox = font_meters_label.getbbox(label)
            label_w = bbox[2] - bbox[0]
            if layout == "horizontal_separate":
                # Guides Spaced Across the Entire Width
                x = x0 + round(ratio * (width - 1))
                core.draw.line((x, y_top, x, scale_y + scale_extra_h), fill=marker_color)
                # Labels to the left of the markers
                core.draw.text((x - label_w - 2, scale_y + 2), label, font=font_meters_label, fill=core.COLOR_TRACK_TITLE)
            else:  # Horizontal Inline
                # Symmetric reference points around the center
                left_width = max(0, center - x0 - center_gap // 2)
                right_width = max(0, x1 - center - (center_gap - center_gap // 2))
                left_start = center - center_gap // 2 - 1
                right_start = center + (center_gap - center_gap // 2)
                left_x = left_start - round(ratio * (left_width - 1))
                right_x = right_start + round(ratio * (right_width - 1))
                # Vertical reference marks
                if left_width > 0:
                    core.draw.line((left_x, y_top, left_x, scale_y + scale_extra_h), fill=marker_color)
                if right_width > 0:
                    core.draw.line((right_x, y_top, right_x, scale_y + scale_extra_h), fill=marker_color)
                # Labels
                label = f"{int(db):+d}" if db < 0 else " 0"
                bbox = font_meters_label.getbbox(label)
                label_w = bbox[2] - bbox[0]
                left_label_x = left_x + 2
                right_label_x = right_x - label_w - 2
                # Check whether the two labels overlap
                merge_label = left_label_x + label_w > right_label_x
                if merge_label:
                    # Check that the merged label fits between the guides
                    available_width = right_x - left_x - 2 * 2
                    if available_width >= label_w:
                        label_x = (left_x + right_x - label_w) // 2
                        core.draw.text((label_x, scale_y + 2), label, font=font_meters_label, fill=core.COLOR_TRACK_TITLE)
                else:
                    core.draw.text((left_label_x, scale_y + 2), label, font=font_meters_label, fill=core.COLOR_TRACK_TITLE)
                    core.draw.text((right_label_x, scale_y + 2), label, font=font_meters_label, fill=core.COLOR_TRACK_TITLE)

    # Display order: Peak, then VU
    now = time.time()
    row = 0
    for kind in modes:
        levels = {}
        for channel in channels: levels[channel] = get_vis(s, kind, channel, values[kind][channel])
        if kind == "peak":
            holds = {channel: update_peak_hold(s, channel, levels[channel], now) for channel in channels}
        if layout == "horizontal_separate":
            gradient = get_gradient(width)
            for channel in channels:
                y = int(y_top + row * (bar_h + row_gap))
                # Background
                if not show_cover:
                    core.draw.rectangle((x0, y, x1 - 1, y + bar_h - 1), fill=core.COLOR_PROGRESS_BG)
                over = kind == "peak" and values[kind][channel] > 1.0
                filled = width if over else min(width, int(round(levels[channel] * width)))
                draw_bar(y, filled, gradient, over=over)
                if kind == "peak":
                    # Peak hold
                    hold_x = x0 + min(width - 1, int(round(holds[channel] * (width - 1))))
                    draw_peak_hold(y, hold_x)
                row += 1
        else:  # horizontal_inline
            y = int(y_top + row * (bar_h + row_gap))
            # Background
            if not show_cover:
                core.draw.rectangle((x0, y, center - center_gap, y + bar_h - 1), fill=core.COLOR_PROGRESS_BG)
                core.draw.rectangle((center + center_gap, y, x1 - 1, y + bar_h - 1), fill=core.COLOR_PROGRESS_BG)
            left_width = max(0, center - x0 - center_gap // 2)
            right_width = max(0, x1 - center - (center_gap - center_gap // 2))
            left_gradient = get_gradient(left_width)
            right_gradient = get_gradient(right_width)
            for channel, start, capacity, gradient, direction in (
                ("left", center - center_gap // 2 - 1,
                 left_width, left_gradient, -1),
                ("right", center + (center_gap - center_gap // 2),
                 right_width, right_gradient, 1),
            ):
                over = kind == "peak" and values[kind][channel] > 1.0
                filled = capacity if over else min(capacity, int(round(levels[channel] * capacity)))
                over_start = max(0, filled - max(1, round(filled * 0.05))) if over else filled
                for i in range(filled):
                    x = start + direction * i
                    color = get_bar_color(i, gradient, over, over_start)
                    core.draw.line((x, y, x, y + bar_h - 1), fill=color)
                if kind == "peak":
                    # Peak hold
                    if capacity:
                        hold_pos = int(round(holds[channel] * (capacity - 1)))
                        draw_peak_hold(y, start + direction * hold_pos)
            row += 1

def draw_meters_vertical(left_x0, left_x1, right_x0, right_x1, y0, y1, vbar_w, vbar_gap, peak_info, mode="peak", scale_extra_w=0):
    if not hasattr(draw_meters_vertical, "state"):
        draw_meters_vertical.state = {}
    s = draw_meters_vertical.state
    height = max(0, y1 - y0)
    if height <= 0:
        return

    values = {
        "peak": {
            "left": max(0.0, peak_info.get("left_peak", 0.0)),
            "right": max(0.0, peak_info.get("right_peak", 0.0)),
        },
        "vu": {
            "left": max(0.0, peak_info.get("left_vu", 0.0)),
            "right": max(0.0, peak_info.get("right_vu", 0.0)),
        },
    }

    modes = ("peak", "vu") if mode == "both" else (mode,)
    if mode not in ("peak", "vu", "both"):
        return
    # Single mode: double width compared to both mode
    bar_w = vbar_w if mode == "both" else vbar_w * 2
    gradient = get_gradient(height)

    def draw_bar(x0, x1, kind, level, hold=None, over=False):
        if x1 <= x0:
            return
        # Background
        if not show_cover or show_cover_alt:
            core.draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=core.COLOR_PROGRESS_BG)
        filled = min(height, int(round(level * height)))
        over_start = max(0, filled - max(1, round(filled * 0.05))) if over else filled
        # Bar grows from bottom to top
        for i in range(filled):
            color = get_bar_color(i, gradient, over, over_start)
            y = y1 - 1 - i
            core.draw.line((x0, y, x1 - 1, y), fill=color)
        if kind == "peak":
            # Peak hold
            if hold is not None:
                hold_pos = min(height - 1, int(round(hold * (height - 1))))
                hold_y = y1 - 1 - hold_pos
                core.draw.line((x0, hold_y, x1 - 1, hold_y), fill=core.COLOR_ARTIST)

    now = time.time()

    for channel, zone_x0, zone_x1 in (("left", left_x0, left_x1), ("right", right_x0, right_x1),):
        zone_width = zone_x1 - zone_x0
        if zone_width <= 0:
            continue
        # Space reserved for labels, outside the group
        if scale_extra_w > 0:
            if channel == "left":
                group_zone_x0 = zone_x0 + scale_extra_w
                group_zone_x1 = zone_x1
            else:
                group_zone_x0 = zone_x0
                group_zone_x1 = zone_x1 - scale_extra_w
        else:
            group_zone_x0 = zone_x0
            group_zone_x1 = zone_x1
        group_zone_width = group_zone_x1 - group_zone_x0
        if group_zone_width <= 0:
            continue

        if mode == "both":
            group_width = bar_w * 2 + vbar_gap
            group_x0 = (group_zone_x0 + group_zone_x1 - group_width) // 2
            if channel == "left":
                positions = {"peak": group_x0, "vu": group_x0 + bar_w + vbar_gap,}
            else:
                positions = {"vu": group_x0, "peak": group_x0 + bar_w + vbar_gap,}
        else:
            # Single mode: one centered, double-width bar
            group_width = bar_w
            center_x = (group_zone_x0 + group_zone_x1) // 2
            start_x = center_x - group_width // 2
            group_x0 = start_x
            positions = {mode: start_x}

        if group_width > group_zone_width:
            continue

        # dBFS Reference Points and Labels
        if scale_extra_w > 0:
            bbox = font_meters_label.getbbox(str(METER_DB_MIN))
            label_h = bbox[3] - bbox[1]
            db_marks = get_meter_db_marks(height, font_meters_label, min_label_gap=8, label_axis="y", start_padding=label_h + 4,)
            label_width = scale_extra_w - 2 - 2
            for db in db_marks:
                ratio = meter_db_to_ratio(db)
                y = y1 - 1 - int(round(ratio * (height - 1)))
                if channel == "left":
                    marker_x0 = group_x0 - scale_extra_w
                    marker_x1 = group_x0 + group_width - 1
                    label_x = marker_x0
                else:
                    marker_x0 = group_x0
                    marker_x1 = group_x0 + group_width + scale_extra_w - 1
                    label_x = marker_x1 - label_width + 1
                core.draw.line((marker_x0, y, marker_x1, y), fill=marker_color)

                label = f"{int(db):+d}" if db < 0 else f" {int(db)}"
                bbox = font_meters_label.getbbox(label)
                text_w = bbox[2] - bbox[0]
                text_h = bbox[3] - bbox[1]
                # Center the text within the allocated width
                text_x = label_x + (label_width - text_w) // 2
                text_y = y + 2
                core.draw.text((text_x, text_y), label, font=font_meters_label, fill=core.COLOR_TRACK_TITLE)

        for kind in modes:
            x0 = positions[kind]
            x1 = x0 + bar_w
            # Keep the bar inside its zone
            x0 = max(group_zone_x0, x0)
            x1 = min(group_zone_x1, x1)
            value = values[kind][channel]
            level = get_vis(s, kind, channel, value)
            hold = update_peak_hold(s, channel, level, now) if kind == "peak" else None
            over = kind == "peak" and value > 1.0

            draw_bar(x0, x1, kind, level, hold, over)

def draw_nowplaying():
    now = time.time()
    scroll_artist = core.scroll_state.setdefault(
        "nowplaying_artist",
        {"offset": 0, "last_update": time.time(), "phase": "pause_start", "pause_start_time": time.time()}
    )
    scroll_title = core.scroll_state.setdefault(
        "nowplaying_title",
        {"offset": 0, "last_update": time.time(), "phase": "pause_start", "pause_start_time": time.time()}
    )

    if is_renderer_active() and not is_bt_local_active():
        artist_album = core.t("show_renderer_active")
        title = core.t("show_renderer_hint")
    else:
        artist = global_state.get("artist", "")
        artist_album = global_state.get("artist_album", "")
        title = global_state.get("title", "")

    state = global_state.get("state", "unknown")
    volume = global_state.get("volume", "N/A")
    volume_display = "vol Bt" if is_bt_local_active() else f"vol {volume}"

    has_spectrum = show_spectrum and spectrum is not None
    vertical_meters = show_peak and peak_vu_style == "vertical"
    horizontal_meters = show_peak and peak_vu_style != "vertical"

    padding_x = max(2, int(round(core.width * 0.012))) if core.height > 64 else 0
    padding_y = max(2, int(round(core.height * 0.010))) if core.height > 64 else 0

    padding_mask = 2
    radius_mask = 2

    if core.height < 64:
        spacing = 1
        top_bar_h = icon_width + 2
    elif core.height <= 96:
        spacing = 2 if show_spectrum or show_peak or show_cover_alt else 4
        top_bar_h = icon_width + 3 if show_spectrum or show_peak else icon_width + 4
    elif core.height <= 128:
        spacing = 4 if show_spectrum or show_peak or show_cover_alt else 10
        top_bar_h = icon_width + 4 if show_spectrum or show_peak else icon_width + 10
    elif core.height <= 160:
        spacing = 6 if show_spectrum or show_peak or show_cover_alt else 16
        top_bar_h = icon_width + 8 if show_spectrum or show_peak else icon_width + 16
    elif core.height == 170:
        spacing = 4 if show_spectrum or show_peak or show_cover_alt else 8
        top_bar_h = icon_width + 5 if show_spectrum or show_peak else icon_width + 12
    else:
        spacing = 4 if show_cover_alt else 8 if show_spectrum or show_peak else 20
        top_bar_h = icon_width + 10 if show_spectrum or show_peak or show_cover_alt else icon_width + 22

    if not show_icons:
        top_bar_h = spacing if core.height > 64 else 0

    # Text background mask
    text_mask_bg = (0, 0, 0, 120) if show_cover and not show_cover_alt and state != "stop" else None

    # Background
    if text_mask_bg is not None:
        draw_cover_background(0, core.width, 0, core.height)
    else:
        core.draw.rectangle((0, 0, core.width, core.height), fill=core.COLOR_BG)

    # Top barre
    if show_icons:
        icon1 = icons["play"] if state == "play" else icons["pause"] if state == "pause" else icons["stop"] if state == "stop" else icons["empty"]
        icon2 = icons["random_on"] if global_state.get("random", "0") == "1" else icons["empty"]
        repeat = global_state.get("repeat", "0")
        single = global_state.get("single", "0")
        consume = global_state.get("consume", "0")

        if repeat == "1" and single == "1" and consume == "0":
            icon3 = icons["repeat1_on"]; icon4 = icons["empty"]
        elif consume == "1" and repeat == "1" and single == "1":
            icon3 = icons["empty"]; icon4 = icons["empty"]
        elif consume == "1" and single == "1" and repeat == "0":
            icon3 = icons["empty"]; icon4 = icons["single_on"]
        else:
            icon3 = icons["repeat_on"] if repeat == "1" else icons["empty"]
            icon4 = icons["single_on"] if single == "1" else icons["empty"]

        icon5 = icons["consume_on"] if consume == "1" else icons["empty"]
        icon6 = icons["favorite"] if global_state.get("favorite") else icons["empty"]
        icon7 = icons["bluetooth"] if global_state.get("audioout") == "Bluetooth" else icons["empty"]

        spacing_icon = 2
        draw_icon_with_mask(icon1, (0, 0), background=text_mask_bg)
        if not is_renderer_active():
            draw_icon_with_mask(icon2, (1 * (icon_width + spacing_icon), 0), background=text_mask_bg)
            draw_icon_with_mask(icon3, (2 * (icon_width + spacing_icon), 0), background=text_mask_bg)
            draw_icon_with_mask(icon4, (3 * (icon_width + spacing_icon), 0), background=text_mask_bg)
            draw_icon_with_mask(icon5, (4 * (icon_width + spacing_icon), 0), background=text_mask_bg)
            draw_icon_with_mask(icon6, (5 * (icon_width + spacing_icon), 0), background=text_mask_bg)

        icon7_x = core.width - icon_width - padding_x
        draw_icon_with_mask(icon7, (icon7_x, 0), background=text_mask_bg)

    # Stop state
    if state == "stop" and not is_renderer_active():
        clock_text = global_state["clock"]
        bbox = font_stop_clock.getbbox(clock_text)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = (core.width - text_w) // 2
        y = (core.height - text_h) // 2 - bbox[1]

        core.draw.text((x, y), clock_text, font=font_stop_clock, fill=core.COLOR_STOP_CLOCK)

        # Volume barre
        vol_bar_h = font_vol_clock.getbbox("vol 100")[3]
        y_vol_bar = core.height - vol_bar_h - padding_y

        core.draw.text((3, y_vol_bar), volume_display, font=font_vol_clock, fill=core.COLOR_VOL_CLOCK)
    else:
        # compute text height reliably from font bbox
        bbox = font_artist.getbbox("Aéy")
        text_h = max(1, int(bbox[3] - bbox[1]))
        def draw_scrolling(text, scroll_state, y, color):
            """
            Scroll rendering using a cached pre-rendered image of the text.
            Fixes float->int issues for Image.new by forcing integer sizes.
            """
            # measure text width (may be float) -> make it an int
            text_width_f = core.draw.textlength(text, font=font_artist)
            text_width = max(1, int(math.ceil(text_width_f)))

            # Normalize color to integer tuple (in case colors are floats)
            if isinstance(color, (tuple, list)):
                fill_color = tuple(int(round(c)) for c in color)
            else:
                fill_color = color

            # Re-render cached image only when the text changes
            if scroll_state.get("cached_text") != text or "render" not in scroll_state:
                # create image exactly sized to text; use bbox[1] as vertical baseline offset
                if core.display_format != "MONO":
                    img = core.Image.new("RGBA", (text_width, text_h), (0, 0, 0, 0))
                else:
                    img = core.Image.new("1", (text_width, text_h), core.COLOR_BG)
                d = core.screen.ImageDraw.Draw(img)
                # vertical offset to align baseline; using -bbox[1] positions text correctly
                d.text((0, -bbox[1]), text, font=font_artist, fill=fill_color)
                scroll_state["render"] = img
                scroll_state["cached_text"] = text
                # reset offset/phase when text changes
                scroll_state.setdefault("offset", 0)
                scroll_state.setdefault("phase", "pause_start")
                scroll_state.setdefault("pause_start_time", time.time())
                scroll_state.setdefault("last_update", time.time())

            render_img = scroll_state["render"]
            display_width = core.width
            now = time.time()

            # If the text is larger than display, do scrolling logic
            if text_width > display_width:
                phase = scroll_state.get("phase", "pause_start")
                PAUSE_DURATION = 1.5
                BLANK_DURATION = 0.12

                if phase == "pause_start":
                    scroll_state["offset"] = 0
                    if now - scroll_state.get("pause_start_time", 0) > PAUSE_DURATION:
                        scroll_state["phase"] = "scrolling"
                        scroll_state["last_update"] = now

                elif phase == "scrolling":
                    if now - scroll_state.get("last_update", 0) > SCROLL_SPEED_NOWPLAYING:
                        scroll_state["offset"] += 1
                        scroll_state["last_update"] = now
                        if scroll_state["offset"] >= (text_width - display_width):
                            scroll_state["phase"] = "pause_end"
                            scroll_state["pause_start_time"] = now

                elif phase == "pause_end":
                    elapsed = now - scroll_state.get("pause_start_time", 0)
                    if elapsed >= PAUSE_DURATION:
                        scroll_state["offset"] = 0
                        scroll_state["phase"] = "pause_start"
                        scroll_state["pause_start_time"] = now

                draw_text = True
                if scroll_state.get("phase") == "pause_end":
                    elapsed = now - scroll_state.get("pause_start_time", 0)
                    if elapsed >= (PAUSE_DURATION - BLANK_DURATION) and elapsed < PAUSE_DURATION:
                        draw_text = False

                if draw_text:
                    offset = int(scroll_state.get("offset", 0))

                    # Mask only if the cover is background
                    if text_mask_bg is not None:
                        draw_mask(
                            (0, y - 3, display_width, y + text_h + 3),
                            text_mask_bg,
                            radius=2
                        )

                    # Pre-rendered text with transparency
                    if render_img.mode == "RGBA":
                        core.image.paste(render_img, (-offset, y), render_img)
                    else:
                        core.image.paste(render_img, (-offset, y))

            else:
                # Text is short enough: center alignment
                x = (display_width - text_width) // 2

                if text_mask_bg is not None:
                    draw_mask(
                        (x - 3, y - 3, x + text_width + 3, y + text_h + 3),
                        text_mask_bg,
                        radius=2
                    )

                if render_img.mode == "RGBA":
                    core.image.paste(render_img, (x, y), render_img)
                else:
                    core.image.paste(render_img, (x, y))

        # --- Artist / Album / Title---
        if show_one_line:
            # --- Artist / Title oneline ---
            y_artist = top_bar_h
            artist_title = f"{artist} • {title}"
            draw_scrolling(artist_title, scroll_artist, y_artist, core.COLOR_ARTIST)
            y_extra_info = y_artist + text_h + spacing
        else:
            # --- Artist / Album ---
            y_artist = top_bar_h
            draw_scrolling(artist_album, scroll_artist, y_artist, core.COLOR_ARTIST)
            # --- Title ---
            y_title = y_artist + text_h + spacing
            draw_scrolling(title, scroll_title, y_title, core.COLOR_TRACK_TITLE)
            y_extra_info = y_title + text_h + spacing

        # --- Extra Infos ---
        if show_extra_infos:
            extra_info = global_state.get("audio", "")
            bitrate = global_state.get("bitrate", "")
            if bitrate:
                if extra_info:
                    extra_info += f" / {bitrate} kbps"
                else:
                    extra_info = f"{bitrate} kbps"
            if extra_info:
                bbox_info = font_extra_info.getbbox(extra_info)
                extra_info_h = bbox_info[3] - bbox_info[1]
                text_w = bbox_info[2] - bbox_info[0]
                x_extra_info = (core.width - text_w) // 2
                draw_text_with_mask(
                    (x_extra_info, y_extra_info),
                    extra_info,
                    font_extra_info,
                    core.COLOR_EXTRA_INFO,
                    background=text_mask_bg
                )
                y_progress = y_extra_info + extra_info_h + spacing + (padding_mask if text_mask_bg is not None else 0)
            else:
                y_progress = y_extra_info
        else:
            y_progress = y_extra_info

        # --- Progress Bar ---
        elapsed = float(global_state.get("elapsed", 0.0))
        duration = float(global_state.get("duration", 0.0))
        if show_progress_barre:
            progress_h = 2 if core.height > 160 else 1
            progress_w = int(core.width - (padding_x * 2))
            progress_x = (core.width - progress_w) // 2
            ratio = elapsed / duration if duration > 0 else 0
            fill_w = int(progress_w * ratio)
            if core.height <= 64 and fill_w > 0:
                core.draw.line((progress_x, y_progress, progress_x + fill_w, y_progress), fill=core.COLOR_PROGRESS, width=progress_h)
            else:
                # Background barre
                if not show_cover or show_cover_alt:
                    core.draw.line((progress_x, y_progress, progress_x + progress_w, y_progress), fill=core.COLOR_PROGRESS_BG, width=progress_h)
                # Progress fill
                if fill_w > 0:
                    core.draw.line((progress_x, y_progress, progress_x + fill_w, y_progress), fill=core.COLOR_PROGRESS, width=progress_h)
            y_spectrum = y_progress + progress_h + spacing + (2 if show_cover_alt else 0)
        else:
            y_spectrum = y_progress + (2 if show_cover_alt else 0)

        # Top vertical Meters
        y_meters_v = y_spectrum
        if not show_vol_bar and show_cover and (not show_cover_alt or show_meters_alt):
            pad_meters_v = padding_y
        elif not show_vol_bar and show_cover and (show_cover_alt or not show_meters_alt):
            pad_meters_v = 0
        else:
            pad_meters_v = spacing

        # Width vertical meters proportional to screen resolution
        vbar_w = max(2, min(8, core.width // 36))
        vbar_gap = max(1, min(4, core.width // 80))

        # define avaible space for meters
        if show_vol_bar:
            vol_bbox = font_vol_clock.getbbox(volume_display)
            vol_txt_h = vol_bbox[3] - vol_bbox[1] if text_mask_bg is not None else font_vol_clock.getbbox("vol 100")[3]
            vol_bar_h = vol_txt_h + padding_y + ((padding_mask * 2) if text_mask_bg is not None else 0)
            if show_clock:
                clock_text = global_state["clock"]
            else:
                elapsed_str = format_time(elapsed)
                duration_str = format_time(duration)
                remaining_str = format_time(max(0, duration - elapsed))
                if menu_context_flag == "radio":
                    clock_text = f"{elapsed_str}"
                else:
                    clock_text = f"{remaining_str}" if show_meters_alt or show_cover_alt else f"{elapsed_str}/{duration_str}"
            vol_w = core.draw.textlength("vol 100", font=font_vol_clock)
            clock_w = core.draw.textlength(clock_text, font=font_vol_clock)
            avaible_w = core.width - vol_w - clock_w - (padding_x * 4) - (padding_x * 2) - (padding_mask * 4 if text_mask_bg is not None else 0)
        else:
            vol_bar_h = 0
            avaible_w = core.width
        y_vol_bar = core.height - vol_bar_h

        # Reserve horizontal space for vertical meters
        scale_extra_w = 0
        if show_scale_labels and vertical_meters:
            bbox_scale = font_meters_label.getbbox("-36")
            scale_label_w = max(1, bbox_scale[2] - bbox_scale[0])
            scale_extra_w = 2 + scale_label_w + 2

        if vertical_meters and (not show_meters_alt or not show_vol_bar):
            if show_peak_vu == "both":
                vertical_group_w = vbar_w * 2 + vbar_gap
            else:
                vertical_group_w = vbar_w * 2

            avaible_w = core.width - 2 * (vertical_group_w + scale_extra_w) - (4 * padding_x) - (padding_mask * 4 if text_mask_bg is not None else 0)
            avaible_w = max(0, avaible_w)

        meters_w = core.width - padding_x * 4 if (not show_meters_alt and show_vol_bar and horizontal_meters) or (show_meters_alt and not show_vol_bar and show_cover_alt and horizontal_meters) else avaible_w

        # --- Cover / Meters bounds ---
        if has_spectrum:
            num_bars = len(spectrum.get_levels())
            if show_cover_alt:
                _, _, _, cover_x0, cover_x1 = get_spectrum_geometry(meters_w, num_bars)
        elif show_cover_alt or not show_vol_bar:
            cover_x0 = (core.width - int(meters_w)) // 2 + padding_x
            cover_x1 = (core.width + int(meters_w)) // 2 - padding_x

        # Horizontal meter dimensions
        meter_bar_h = (max(2, min(6, core.height // 36)) if show_meters_alt else max(2, min(8, core.height // 36)))
        padding_peak = (1 if core.height < 64 else 2 if core.height <= 96 or show_meters_alt else 4)
        meter_count = 1 if peak_vu_style == "horizontal_inline" else 2
        if show_peak_vu == "both":
            meter_count *= 2

        scale_extra_h = 0
        if show_scale_labels:
            bbox_scale = font_meters_label.getbbox("-36")
            scale_label_h = max(1, bbox_scale[3] - bbox_scale[1])
            scale_extra_h = 2 + scale_label_h + 2

        meter_height = (meter_count * meter_bar_h + scale_extra_h + max(0, meter_count - 1) * padding_peak)

        total_peak = meter_height + (padding_y if show_meters_alt else spacing) + (padding_mask * 2 if text_mask_bg is not None or show_cover_alt else 0)

        if show_cover_alt:
            if horizontal_meters:
                draw_cover_background(cover_x0, cover_x1, y_spectrum, (core.height - padding_y) if show_meters_alt else y_vol_bar - spacing)
            else:
                draw_cover_background(cover_x0, cover_x1, y_spectrum, (core.height - padding_y) if show_meters_alt else y_vol_bar - pad_meters_v)

        # --- Spectrum ---
        if has_spectrum:
            levels = spectrum.get_levels()
            if show_meters_alt:
                spectrum_bottom = (
                    (core.height - total_peak - padding_y)
                    if horizontal_meters
                    else core.height - (pad_meters_v if not show_vol_bar else padding_y)
                ) - (padding_mask if text_mask_bg is not None else 0)
            else:
                spectrum_bottom = (
                    y_vol_bar - (total_peak + padding_y)
                    if horizontal_meters
                    else y_vol_bar - pad_meters_v
                ) - (padding_mask if text_mask_bg is not None else 0)

            available_height = max(0, spectrum_bottom - y_spectrum)
            target_spectrum_h = int(meters_w * 0.25)
            spectrum_h = min(target_spectrum_h, available_height)
            y_spectrum = spectrum_bottom - spectrum_h

            if text_mask_bg is not None and hasattr(draw_spectrum, "bounds"):
                x0, x1 = draw_spectrum.bounds
                draw_mask(
                    (x0 - padding_mask, y_spectrum - padding_mask, x1 + padding_mask, y_spectrum + spectrum_h + padding_mask),
                    (0, 0, 0, 90),
                    radius=2
                )
            draw_spectrum(y_top=y_spectrum, height=spectrum_h, levels=levels, width_spec=meters_w)
            y_peak = y_spectrum + spectrum_h + spacing
        else:
            y_peak = y_spectrum + spacing * 2

        # --- Peak/VU Meters ---
        if show_peak and spectrum:
            pad_x = padding_x
            # Vertical Range of the VU Meters
            vertical_y0 = y_meters_v + pad_meters_v + (padding_mask if text_mask_bg is not None else 0)
            vertical_y1 = y_vol_bar - pad_meters_v - (padding_mask if text_mask_bg is not None else 0)

            if has_spectrum and hasattr(draw_spectrum, "bounds"):
                spectrum_x0, spectrum_x1 = draw_spectrum.bounds
            elif show_cover_alt:
                spectrum_x0 = cover_x0
                spectrum_x1 = cover_x1
            else:
                spectrum_x0 = (core.width - int(meters_w)) // 2 + padding_x
                spectrum_x1 = (core.width + int(meters_w)) // 2 - padding_x

            left_x0 = padding_x
            left_x1 = spectrum_x0 - padding_x

            right_x0 = spectrum_x1 + padding_x
            right_x1 = core.width - padding_x

            y_meter_h = (core.height - meter_height - padding_y if show_meters_alt else y_vol_bar - meter_height - spacing) - (padding_mask if text_mask_bg is not None or show_cover_alt else 0)

            peaks = spectrum.get_channel_peaks(
                volume_state=global_state.get("volume"),
                mixer_type=global_state.get("mpdmixer"),
                bt_active=is_bt_local_active(),
                soft_correct=peak_correct
            )

            if has_spectrum and hasattr(draw_spectrum, "bounds"):
                x0, x1 = draw_spectrum.bounds
            else:
                x0 = (core.width - int(meters_w)) // 2 + pad_x
                x1 = (core.width + int(meters_w)) // 2 - pad_x

            if text_mask_bg is not None or show_cover_alt:
                if horizontal_meters:
                    draw_mask(
                        (x0 - padding_mask, y_meter_h - padding_mask,
                        x1 + padding_mask, y_meter_h + meter_height + padding_mask),
                        (0, 0, 0, 90),
                        radius=2
                    )
                else:
                    # Width of the bar group
                    if show_peak_vu == "both":
                        group_w = vbar_w * 2 + vbar_gap
                    else:
                        group_w = vbar_w * 2

                    # Available zones after label reservations
                    left_group_zone_x0 = left_x0 + scale_extra_w
                    left_group_zone_x1 = left_x1
                    right_group_zone_x0 = right_x0
                    right_group_zone_x1 = right_x1 - scale_extra_w

                    # Alignment is the same as in draw_meters_vertical()
                    left_center = (left_group_zone_x0 + left_group_zone_x1) // 2
                    right_center = (right_group_zone_x0 + right_group_zone_x1) // 2
                    left_group_x0 = left_center - group_w // 2
                    right_group_x0 = right_center - group_w // 2

                    # Mask with labels and bars
                    left_mask_x0 = left_group_x0 - scale_extra_w - padding_mask
                    left_mask_x1 = left_group_x0 + group_w + padding_mask
                    right_mask_x0 = right_group_x0 - padding_mask
                    right_mask_x1 = right_group_x0 + group_w + scale_extra_w + padding_mask

                    draw_mask(
                        (
                            left_mask_x0,
                            vertical_y0 - padding_mask,
                            left_mask_x1,
                            vertical_y1 + padding_mask
                        ),
                        (0, 0, 0, 90),
                        radius=2
                    )

                    draw_mask(
                        (
                            right_mask_x0,
                            vertical_y0 - padding_mask,
                            right_mask_x1,
                            vertical_y1 + padding_mask
                        ),
                        (0, 0, 0, 90),
                        radius=2
                    )

            if vertical_meters:
                draw_meters_vertical(
                    left_x0, left_x1,
                    right_x0, right_x1,
                    vertical_y0, vertical_y1,
                    vbar_w, vbar_gap,
                    peaks,
                    mode=show_peak_vu,
                    scale_extra_w=scale_extra_w
                )
            else:
                draw_meters_horizontal(
                    y_meter_h,
                    meter_bar_h,
                    x0,
                    x1,
                    peaks,
                    mode=show_peak_vu,
                    layout=peak_vu_style,
                    row_gap=padding_peak,
                    scale_extra_h=scale_extra_h
                )

        # --- Bottom bar (Volume / Clock) ---
        if show_vol_bar:
            draw_text_with_mask(
                (padding_x, y_vol_bar),
                volume_display,
                font_vol_clock,
                core.COLOR_VOL_CLOCK,
                background=text_mask_bg,
                padding=padding_mask
            )

            draw_text_with_mask(
                (core.width - clock_w - padding_x, y_vol_bar),
                clock_text,
                font_vol_clock,
                core.COLOR_VOL_CLOCK,
                background=text_mask_bg,
                padding=padding_mask
            )

        #core.draw.line((0, core.height + 1, core.width, core.height + 1), fill=core.COLOR_PROGRESS, width=1)

def build_shortcut_action(typ, val):
    if typ == "parametric":
        return f"parametric:{val}"
    elif typ == "graphic":
        return f"graphic:{val}"
    elif typ == "playback":
        return f"playback:{val}"
    return None

def assign_shortcut_to_selected(selected):
    global learning_mode, learning_callback, blocking_render
    if eq_preset_active:
        typ = selected["type"]
        val = selected["name"]
    if playback_modes_menu_active:
        typ = "playback"
        val = selected["id"]
    action = build_shortcut_action(typ, val)
    if not action:
        core.show_message(core.t("info_invalid_item"))
        return
    core.message_permanent = True
    blocking_render = True
    core.message_text = core.t("info_press_key")
    render_screen()
    def on_key(key):
        global learning_mode, learning_callback, blocking_render
        core.message_permanent = False
        core.message_text = None
        blocking_render = False
        learning_mode = False
        learning_callback = None
        if is_key_reserved(key):
            core.show_message(core.t("info_key_reserved", key=key))
            return
        already_used = is_key_used(key)
        core.save_config(key, action, section="shortcuts", preserve_case=True)
        core.reload_config()
        load_shortcuts()
        if already_used:
            core.show_message(core.t("info_key_replaced", key=key))
        else:
            core.show_message(core.t("info_key_assigned", key=key))
    learning_mode = True
    learning_callback = on_key

def nav_left_short():
    if now_playing_mode:
        subprocess.run(["mpc", "prev"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

def nav_right_short():
    if now_playing_mode:
        subprocess.run(["mpc", "next"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

def nav_up():
    if now_playing_mode:
        subprocess.run(["/var/www/util/vol.sh", "-up", "1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

def nav_down():
    if now_playing_mode:
        subprocess.run(["/var/www/util/vol.sh", "-dn", "1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

def nav_right_long():
    if now_playing_mode:
        subprocess.run(["mpc", "seek", "+00:00:10"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

def nav_left_long():
    if now_playing_mode:
        subprocess.run(["mpc", "seek", "-00:00:10"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    else:
        core.show_message(core.t("info_back_home"))

        for var in [
            "menu_active", "confirm_box_active", "help_active",
            "songlog_active", "songlog_action_active",
            "tool_menu_active", "language_menu_active", "hardware_info_active", "config_menu_active",
            "screensaver_menu_active", "ui_menu_active","theme_menu_active",
            "power_menu_active", "renderers_menu_active", "bluetooth_menu_active",
            "bluetooth_scan_menu_active", "bluetooth_paired_menu_active",
            "bluetooth_audioout_menu_active", "bluetooth_device_actions_menu_active", "playback_modes_menu_active",
            "eq_menu_active", "eq_preset_active"
        ]:
            globals()[var] = False

        core.message_text = None
        core.message_permanent = False

def nav_ok():
    global menu_active, menu_selection, renderers_menu_active, renderers_menu_selection, bluetooth_menu_active, bluetooth_menu_selection
    if is_renderer_active():
        if (
            global_state.get("btsvc") == "1"
            and global_state.get("audioout") == "Local"
            and global_state.get("btactive") == "1"
        ):
            bluetooth_menu_active = True
            bluetooth_menu_selection = 0
        else:
            renderers_menu_active = True
            renderers_menu_selection = 0
        return
    elif now_playing_mode:
        menu_active = True
        menu_selection = 0

def nav_ok_long():
    global tool_menu_active, tool_menu_selection
    if now_playing_mode:
        tool_menu_active = True
        tool_menu_selection = 0
    elif eq_preset_active:
        selected = eq_preset_options[eq_preset_selection]
        assign_shortcut_to_selected(selected)
    elif playback_modes_menu_active:
        selected = playback_modes_options[playback_modes_selection]
        assign_shortcut_to_selected(selected)
    else:
        return

def nav_channelup():
    if menu_context_flag == "library":
        toggle_favorite()
    elif menu_context_flag == "radio":
        log_song()
    elif menu_context_flag == "local_stream":
        core.show_message(core.t("info_already_in_log"))
    else:
        core.show_message(core.t("info_unknown_fav"))

def nav_channeldown():
    remove_from_queue()

def nav_info():
    global help_active, help_lines, help_selection
    help_base_path = OLIPIMOODE_DIR / f"assets/help_texts/help_ui_playing_{core.LANGUAGE}.txt"
    if not help_base_path.exists():
        help_base_path = OLIPIMOODE_DIR / "assets/help_texts/help_ui_playing_en.txt"
    if now_playing_mode:
        context = "nowplaying_mode"
    elif playback_modes_menu_active or eq_preset_active:
        context = "menu_can_shortcut"
    else:
        context = "menu"
    try:
        with open(help_base_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        help_lines = []
        in_section = False
        for line in lines:
            line = line.strip()
            if line.startswith("# CONTEXT:"):
                in_section = (line == f"# CONTEXT:{context}")
                continue
            if in_section:
                help_lines.append(line)
        if help_lines:
            help_selection = 0
            help_active = True
        else:
            core.show_message(core.t("info_no_help"))
    except Exception as e:
        core.show_message(core.t("error_help", error=e))
        if core.DEBUG:
            print("error help: ", e)
        if not core.DEBUG:
            core.show_message(core.t("error_generic"))

def nav_info_long():
    print("not implemented")

def nav_back():
    core.show_message(core.t("info_go_library_screen"))
    time.sleep(0.3)
    subprocess.call(["sudo", "systemctl", "start", "olipi-ui-browser.service"])
    subprocess.call(["sudo", "systemctl", "stop", "olipi-ui-playing.service"])
    sys.exit(0)

def nav_back_long():
    core.show_message(core.t("info_go_playlist_screen"))
    time.sleep(0.3)
    subprocess.call(["sudo", "systemctl", "start", "olipi-ui-queue.service"])
    subprocess.call(["sudo", "systemctl", "stop", "olipi-ui-playing.service"])
    sys.exit(0)


def finish_press(key):
    global menu_active, menu_selection, songlog_active, songlog_selection, songlog_action_active, songlog_action_selection
    global power_menu_active, power_menu_selection, playback_modes_menu_active, playback_modes_selection
    global tool_menu_selection, tool_menu_active, config_menu_active, config_menu_selection
    global theme_menu_active, theme_menu_selection, ui_menu_active, ui_menu_selection, screensaver_menu_active, screensaver_menu_selection, sleep_timeout_options
    global help_active, help_selection, hardware_info_active, hardware_info_selection, language_menu_active, language_menu_selection
    global confirm_box_active, confirm_box_selection, confirm_box_callback, renderers_menu_active, renderers_menu_selection
    global bluetooth_menu_active, bluetooth_menu_selection, bluetooth_scan_menu_active, bluetooth_scan_menu_selection
    global bluetooth_audioout_menu_active, bluetooth_audioout_menu_selection
    global bluetooth_paired_menu_active, bluetooth_paired_menu_selection, bluetooth_device_actions_menu_active, bluetooth_device_actions_menu_selection
    global eq_menu_active, eq_menu_selection, eq_preset_active, eq_preset_selection
    global blocking_render, screen_on, idle_timer, is_sleeping, last_wake_time, learning_mode, learning_callback

    data = press_data.get(key)

    if data is None:
        return
    final_code = data.get("max_repeat_code", 0)
    if core.DEBUG:
        print(f"End pressure {key} with final code {final_code}.")

    idle_timer = time.time()

    if learning_mode:
        learning_mode = False
        if learning_callback:
            learning_callback(key)
        return

    if is_renderer_active():
        if key in ("KEY_LEFT", "KEY_RIGHT", "KEY_UP", "KEY_DOWN"):
            if now_playing_mode:
                core.show_message(core.t("info_action_blocked"))
                if core.DEBUG:
                    print(f"Renderer active → key '{key}' blocked (now_playing_mode)")
                return
        elif key in USED_MEDIA_KEYS:
            core.show_message(core.t("info_action_blocked"))
            if core.DEBUG:
                print(f"Renderer active → key '{key}' blocked")
            return

    if is_sleeping:
        if key in ("KEY_CHANNELUP", "KEY_CHANNELDOWN"):
            screen_on = True
            core.poweron_safe()
            core.reset_scroll("menu_title", "menu_item", "nowplaying_artist", "nowplaying_title")
            is_sleeping = False
            last_wake_time = time.time()
            if core.DEBUG:
                print(f"Wake up on key '{key}' (channel key)")
        elif key in ("KEY_LEFT", "KEY_RIGHT", "KEY_UP", "KEY_DOWN"):
            if now_playing_mode:
                if core.DEBUG:
                    print(f"Direction key '{key}' used in sleep mode (now_playing_mode)")
                pass
            else:
                if core.DEBUG:
                    print(f"Direction key '{key}' ignored in sleep mode (not now_playing_mode)")
                return
        elif key == "KEY_INFO" and final_code >= 4:
            if core.DEBUG:
                print(f"key '{key}' used in sleep mode")
            pass
        elif key in USED_MEDIA_KEYS and global_state.get("state", "unknown") != "stop":
            if core.DEBUG:
                print(f"Media key '{key}' ignored in sleep mode (no wake)")
            pass
        else:
            screen_on = True
            core.poweron_safe()
            core.reset_scroll("menu_title", "menu_item", "nowplaying_artist", "nowplaying_title")
            is_sleeping = False
            last_wake_time = time.time()
            if core.DEBUG:
                print(f"Wake up on key '{key}' (action skipped)")
            return

    if time.time() - last_wake_time < 1:
        if key in ("KEY_CHANNELUP", "KEY_CHANNELDOWN"):
            if core.DEBUG:
                print(f"Input '{key}' allowed (within post-wake delay)")
            pass
        else:
            if core.DEBUG:
                print(f"Input '{key}' ignored (within post-wake delay)")
            return

    if core.message_permanent:
        if final_code >= 4:
            if key == "KEY_LEFT":
                nav_left_long()
        return

    if core.message_text and not core.message_permanent:
        if key in ("KEY_LEFT", "KEY_OK"):
            core.message_text = None
        return

    if final_code >= 4:
        if key == "KEY_LEFT": nav_left_long()
        elif key == "KEY_OK": nav_ok_long()
        elif key == "KEY_BACK": nav_back_long()
        elif key == "KEY_RIGHT": nav_right_long()
        elif key == "KEY_INFO": nav_info_long()
        elif handle_audio_keys(key, final_code, menu_context_flag):
            return
        elif handle_custom_key(key, final_code, menu_context_flag):
            return
        return

    if key == "KEY_INFO":
        if help_active:
            help_active = False
        else:
            nav_info()
        return
    if key == "KEY_BACK":
        nav_back()
        return

    if help_active:
        if key in ("KEY_LEFT", "KEY_OK", "KEY_INFO"):
            help_active = False
            core.reset_scroll("menu_item")
            return
        if help_lines:
            if key == "KEY_DOWN":
                help_selection = (help_selection + 1) % len(help_lines)
                core.reset_scroll("menu_item")
            elif key == "KEY_UP":
                help_selection = (help_selection - 1) % len(help_lines)
                core.reset_scroll("menu_item")
        return

    if confirm_box_active:
        if key == "KEY_UP" and confirm_box_selection > 0:
            confirm_box_selection -= 1
        elif key == "KEY_DOWN" and confirm_box_selection < 1:
            confirm_box_selection += 1
        elif key == "KEY_LEFT":
            confirm_box_active = False
            if confirm_box_callback:
                confirm_box_callback(cancel=True)
            return
        elif key == "KEY_OK":
            option_id = confirm_box_options[confirm_box_selection]["id"]
            confirm_box_active = False
            if option_id == "confirm_yes":
                confirm_box_callback()
            else:
                core.show_message(core.t("info_cancelled"))
            core.reset_scroll("menu_item", "menu_title")
        return

    if menu_active:
        if key == "KEY_UP" and menu_selection > 0:
            menu_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and menu_selection < len(menu_options_contextuel) - 1:
            menu_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            menu_active = False
            core.reset_scroll("menu_item")
        elif key == "KEY_OK":
            item = menu_options_contextuel[menu_selection]
            option_id = item["id"]
            if option_id in ("add_fav", "remove_fav"):
                menu_active = False
                toggle_favorite()
            elif option_id == "search_artist":
                menu_active = False
                search_artist_from_now()
            elif option_id == "add_songlog":
                menu_active = False
                log_song()
            elif option_id == "remove_queue":
                menu_active = False
                remove_from_queue()
            elif option_id == "playback_modes":
                menu_active = False
                playback_modes_menu_active = True
                playback_modes_selection = 0
            elif option_id == "power":
                menu_active = False
                power_menu_active = True
                power_menu_selection = 0
            core.reset_scroll("menu_item", "menu_title")
        return

    if power_menu_active:
        if key == "KEY_UP" and power_menu_selection > 0:
            power_menu_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and power_menu_selection < len(power_menu_options) - 1:
            power_menu_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            power_menu_active = False
            menu_active = True
            core.reset_scroll("menu_item")
        elif key == "KEY_OK":
            option_id = power_menu_options[power_menu_selection]["id"]
            power_menu_active = False
            if option_id == "poweroff":
                core.show_message(core.t("info_poweroff"))
                subprocess.run(["sudo", "moodeutl", "--shutdown"])
            elif option_id == "reboot":
                core.show_message(core.t("info_reboot"))
                subprocess.run(["sudo", "moodeutl", "--reboot"])
            elif option_id == "reload_screen":
                core.show_message(core.t("info_reload_screen"))
                subprocess.call(["sudo", "systemctl", "restart", "olipi-ui-playing.service"])
                sys.exit(0)
            elif option_id == "restart_mpd":
                core.show_message(core.t("info_restart_mpd"))
                subprocess.call(["sudo", "systemctl", "restart", "mpd"])
            core.reset_scroll("menu_item", "menu_title")
        return

    if playback_modes_menu_active:
        if key == "KEY_UP" and playback_modes_selection > 0:
            playback_modes_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and playback_modes_selection < len(playback_modes_options) - 1:
            playback_modes_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            playback_modes_menu_active = False
            menu_active = True
            core.reset_scroll("menu_item", "menu_title")
        elif key == "KEY_OK":
            option = playback_modes_options[playback_modes_selection]
            state_key = option["id"]
            new_val = "0" if global_state[state_key] == "1" else "1"
            set_mpd_state(state_key, int(new_val))
            core.reset_scroll("menu_item", "menu_title")
        return

    if tool_menu_active:
        if key == "KEY_UP" and tool_menu_selection > 0:
            tool_menu_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and tool_menu_selection < len(tool_menu_options) - 1:
            tool_menu_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            tool_menu_active = False
            core.reset_scroll("menu_item", "menu_title")
        elif key == "KEY_OK":
            option_id = tool_menu_options[tool_menu_selection]["id"]
            #tool_menu_active = False
            if option_id == "renderers":
                tool_menu_active = False
                renderers_menu_active = True
                renderers_menu_selection = 0
            elif option_id == "equalizers":
                tool_menu_active = False
                eq_menu_active = True
                eq_menu_selection = 0
            elif option_id == "show_songlog":
                tool_menu_active = False
                show_songlog()
                if not songlog_lines:
                    tool_menu_active = True
                else:
                    songlog_active = True
                songlog_selection = 0
            elif option_id == "hardware_info":
                tool_menu_active = False
                hardware_info_active = True
                threading.Thread(target=update_hardware_info, daemon=True).start()
            elif option_id == "configuration":
                tool_menu_active = False
                config_menu_active = True
                config_menu_selection = 0
            core.reset_scroll("menu_item", "menu_title")
        return

    if eq_menu_active:
        if key == "KEY_UP" and eq_menu_selection > 0:
            eq_menu_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and eq_menu_selection < len(eq_menu_options) - 1:
            eq_menu_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            eq_menu_active = False
            tool_menu_active = True
            core.reset_scroll("menu_item", "menu_title")
        elif key == "KEY_OK":
            option_id = eq_menu_options[eq_menu_selection]["id"]
            if option_id == "graphic":
                update_eq_preset_menu("graphic")
            elif option_id == "parametric":
                update_eq_preset_menu("parametric")
            eq_menu_active = False
            eq_preset_active = True
            eq_preset_selection = 0
            core.reset_scroll("menu_item", "menu_title")
        return

    if eq_preset_active:
        if key == "KEY_UP" and eq_preset_selection > 0:
            eq_preset_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and eq_preset_selection < len(eq_preset_options) - 1:
            eq_preset_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            eq_preset_active = False
            eq_menu_active = True
            core.reset_scroll("menu_item", "menu_title")
        elif key == "KEY_OK":
            selected = eq_preset_options[eq_preset_selection]
            try:
                cmd = ["sudo", "/var/www/util/eqctl.php", selected["type"], "set",
                    "off" if selected["active"] else str(selected["id"])]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                msg = result.stdout.strip() or result.stderr.strip()
                if result.returncode == 0:
                    parts = msg.split("|")
                    if len(parts) == 3:
                        typ, _, name = parts
                        core.show_message(f"{typ} EQ set to {name}")
                    else:
                        core.show_message(msg)
                else:
                    core.show_message(msg.replace("ERR: ", ""))
            except Exception as e:
                core.show_message(f"EQ error: {e}")
            update_eq_preset_menu(selected["type"])
            core.reset_scroll("menu_item", "menu_title")

    if renderers_menu_active:
        if key == "KEY_UP" and renderers_menu_selection > 0:
            renderers_menu_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and renderers_menu_selection < len(renderers_menu_options) - 1:
            renderers_menu_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            renderers_menu_active = False
            if is_renderer_active():
                pass
            else:
                tool_menu_active = True
            core.reset_scroll("menu_item", "menu_title")
        elif key == "KEY_OK":
            renderer = renderers_menu_options[renderers_menu_selection]["id"]
            if renderer == "bluetooth":
                renderers_menu_active = False
                bluetooth_menu_active = True
                bluetooth_menu_selection = 0
            else:
                action = "off" if global_state.get(renderer + "svc") == "1" else "on"
                core.show_message(core.t("info_renderer_switched", name=renderer.capitalize(), status=action))
                subprocess.call(["moodeutl", "-Ro", str(f"--{renderer}"), action])
                load_renderer_states_from_db()
            core.reset_scroll("menu_item", "menu_title")
        return

    if bluetooth_menu_active:
        if key == "KEY_UP" and bluetooth_menu_selection > 0:
            bluetooth_menu_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and bluetooth_menu_selection < len(bluetooth_menu_options) - 1:
            bluetooth_menu_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            bluetooth_menu_active = False
            if is_renderer_active():
                pass
            else:
                renderers_menu_active = True
            core.reset_scroll("menu_item", "menu_title")
        elif key == "KEY_OK":
            item = bluetooth_menu_options[bluetooth_menu_selection]["id"]
            if item == "bt_toggle":
                action = "off" if global_state.get("btsvc") == "1" else "on"
                core.show_message(core.t("info_renderer_switched", name="Bluetooth", status=action))
                subprocess.call(["moodeutl", "-Ro", "--bluetooth", action])
                load_renderer_states_from_db()
            elif item == "bt_scan":
                bluetooth_menu_active = False
                perform_bluetooth_scan()
                bluetooth_scan_menu_selection = 0
            elif item == "bt_paired":
                bluetooth_menu_active = False
                update_paired_devices_menu()
                bluetooth_paired_menu_active = True
                bluetooth_paired_menu_selection = 0
            elif item == "bt_audio_output":
                bluetooth_menu_active = False
                load_renderer_states_from_db()
                bluetooth_audioout_menu_active = True
                bluetooth_audioout_menu_selection = 0
            elif item == "bt_disconnect_all":
                run_bluetooth_action("-D")
                core.show_message(core.t("info_bt_all_disconnected"))
            core.reset_scroll("menu_item", "menu_title")
        return

    if bluetooth_scan_menu_active:
        if key == "KEY_UP" and bluetooth_scan_menu_selection > 0:
            bluetooth_scan_menu_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and bluetooth_scan_menu_selection < len(bluetooth_scan_menu_options) - 1:
            bluetooth_scan_menu_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            bluetooth_scan_menu_active = False
            bluetooth_menu_active = True
            core.reset_scroll("menu_item", "menu_title")
        elif key == "KEY_OK":
            selected = bluetooth_scan_menu_options[bluetooth_scan_menu_selection]
            bluetooth_scan_menu_active = False
            open_device_actions_menu(selected["mac"], paired=selected.get("paired", False), connected=selected.get("connected", False))
            bluetooth_device_actions_menu_active = True
            bluetooth_device_actions_menu_selection = 0
            core.reset_scroll("menu_item", "menu_title")
        return

    if bluetooth_paired_menu_active:
        if key == "KEY_UP" and bluetooth_paired_menu_selection > 0:
            bluetooth_paired_menu_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and bluetooth_paired_menu_selection < len(bluetooth_paired_menu_options) - 1:
            bluetooth_paired_menu_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            bluetooth_paired_menu_active = False
            bluetooth_menu_active = True
            core.reset_scroll("menu_item", "menu_title")
        elif key == "KEY_OK":
            selected = bluetooth_paired_menu_options[bluetooth_paired_menu_selection]
            bluetooth_paired_menu_active = False
            open_device_actions_menu(selected["mac"], paired=True, connected=selected.get("connected", False))
            bluetooth_device_actions_menu_active = True
            bluetooth_device_actions_menu_selection = 0
            core.reset_scroll("menu_item", "menu_title")
        return

    if bluetooth_device_actions_menu_active:
        if key == "KEY_UP" and bluetooth_device_actions_menu_selection > 0:
            bluetooth_device_actions_menu_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and bluetooth_device_actions_menu_selection < len(bluetooth_device_actions_menu_options) - 1:
            bluetooth_device_actions_menu_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            bluetooth_device_actions_menu_active = False
            bluetooth_menu_active = True
            core.reset_scroll("menu_item", "menu_title")
        elif key == "KEY_OK":
            selected = bluetooth_device_actions_menu_options[bluetooth_device_actions_menu_selection]["id"]
            bluetooth_device_actions_menu_active = False
            if selected.startswith("bt_pair_"):
                run_bt_action_and_msg("-P", selected_bt_mac, "info_bt_paired_ok")
            elif selected.startswith("bt_connect_"):
                run_bt_action_and_msg("-C", selected_bt_mac, "info_bt_connect_ok")
            elif selected.startswith("bt_disconnect_"):
                run_bt_action_and_msg("-d", selected_bt_mac, "info_bt_disconnect_ok")
            elif selected.startswith("bt_remove_"):
                run_bt_action_and_msg("-r", selected_bt_mac, "info_bt_remove_ok")
            core.reset_scroll("menu_item", "menu_title")
        return

    if bluetooth_audioout_menu_active:
        if key == "KEY_UP" and bluetooth_audioout_menu_selection > 0:
            bluetooth_audioout_menu_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and bluetooth_audioout_menu_selection < len(bluetooth_audioout_menu_options) - 1:
            bluetooth_audioout_menu_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            bluetooth_audioout_menu_active = False
            bluetooth_menu_active = True
            core.reset_scroll("menu_item", "menu_title")
        elif key == "KEY_OK":
            selected = bluetooth_audioout_menu_options[bluetooth_audioout_menu_selection]["id"]
            bluetooth_audioout_menu_active = False
            if selected == "audioout_local":
                toggle_audio_output("Local")
            elif selected == "audioout_bt":
                mac = get_connected_bt_mac()
                toggle_audio_output("Bluetooth", mac)
            core.reset_scroll("menu_item", "menu_title")
        return

    if songlog_active:
        if key == "KEY_LEFT":
            songlog_active = False
            tool_menu_active = True
            core.reset_scroll("menu_item", "menu_title")
            return
        if songlog_lines:
            if key == "KEY_UP":
                songlog_selection = (songlog_selection - 1) % len(songlog_lines)
                core.reset_scroll("menu_item")
            elif key == "KEY_DOWN":
                songlog_selection = (songlog_selection + 1) % len(songlog_lines)
                core.reset_scroll("menu_item")
            elif key == "KEY_OK":
                songlog_active = False
                songlog_action_active = True
                songlog_action_selection = 0
                core.reset_scroll("menu_item", "menu_title")
        return

    if songlog_action_active:
        if key == "KEY_UP" and songlog_action_selection > 0:
            songlog_action_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and songlog_action_selection < len(songlog_action_options) - 1:
            songlog_action_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            songlog_action_active = False
            show_songlog()
            songlog_active = True
            core.reset_scroll("menu_item", "menu_title")
        elif key == "KEY_OK":
            option_id = songlog_action_options[songlog_action_selection]["id"]
            if option_id == "play_yt_songlog":
                songlog_action_active = False
                if not has_internet_connection():
                    core.show_message(core.t("info_no_internet"))
                    return
                play_songlog_index(songlog_selection)
            elif option_id == "queue_yt_songlog":
                songlog_action_active = False
                if not has_internet_connection():
                    core.show_message(core.t("info_no_internet"))
                    return
                play_all_songlog_via_m3u(songlog_lines)
            elif option_id == "show_info_songlog":
                info = songlog_meta[songlog_selection]
                if info:
                    core.show_message(info)
                else:
                    core.show_message(core.t("info_no_additional"))
            elif option_id == "delete_entry_songlog":
                songlog_action_active = False
                delete_songlog_entry(songlog_selection)
                if not songlog_lines:
                    tool_menu_active = True
                else:
                    songlog_active = True
            elif option_id == "delete_all_songlog":
                songlog_action_active = False
                confirm_box_active = True
                confirm_box_selection = 1
                confirm_box_callback = confirm_delete_all_songlog
            core.reset_scroll("menu_item", "menu_title")
        return

    if config_menu_active:
        if key == "KEY_UP" and config_menu_selection > 0:
            config_menu_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and config_menu_selection < len(config_menu_options) - 1:
            config_menu_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            config_menu_active = False
            tool_menu_active = True
            core.reset_scroll("menu_item")
        elif key == "KEY_OK":
            option_id = config_menu_options[config_menu_selection]["id"]
            if option_id == "language":
                config_menu_active = False
                language_menu_active = True
                language_menu_selection = 0
            elif option_id == "theme":
                config_menu_active = False
                theme_menu_active = True
                theme_menu_selection = 0
            elif option_id == "ui":
                config_menu_active = False
                ui_menu_active = True
                ui_menu_selection = 0
            elif option_id == "screensaver":
                config_menu_active = False
                screensaver_menu_active = True
                screensaver_menu_selection = 0
            elif option_id == "debug":
                config_menu_active = False
                new_debug = not core.DEBUG
                core.save_config("debug", new_debug, section="settings")
                core.show_message(core.t("info_debug_on") if new_debug else core.t("info_debug_off"))
                time.sleep(1)
                restart_service()
        return

    if language_menu_active:
        if key == "KEY_UP" and language_menu_selection > 0:
            language_menu_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and language_menu_selection < len(language_menu_options) - 1:
            language_menu_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            language_menu_active = False
            config_menu_active = True
            core.reset_scroll("menu_item")
        elif key == "KEY_OK":
            language_menu_active = False
            core.LANGUAGE = language_menu_options[language_menu_selection]["id"]
            core.save_config("language", core.LANGUAGE, section="settings")
            core.show_message(core.t("info_language_set", selected=language_menu_options[language_menu_selection]["label"]))
            time.sleep(1)
            restart_service()
        return

    if theme_menu_active:
        if key == "KEY_UP" and theme_menu_selection > 0:
            theme_menu_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and theme_menu_selection < len(theme_menu_options) - 1:
            theme_menu_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            theme_menu_active = False
            config_menu_active = True
            core.reset_scroll("menu_item")
        elif key == "KEY_OK":
            theme_menu_active = False
            core.THEME_NAME  = theme_menu_options[theme_menu_selection]["id"]
            core.save_config("color_theme", core.THEME_NAME , section="settings")
            core.show_message(core.t("info_theme_set", selected=theme_menu_options[theme_menu_selection]["label"]))
            time.sleep(1)
            restart_service()
        return

    if ui_menu_active:
        global show_icons, show_one_line, show_extra_infos, show_progress_barre, show_cover_bg, show_cover, show_cover_alt, show_vol_bar, show_clock
        global show_spectrum, show_peak_vu, show_peak, peak_vu_style, show_meters_alt, show_scale_labels
        if key == "KEY_UP" and ui_menu_selection > 0:
            ui_menu_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and ui_menu_selection < len(ui_menu_options) - 1:
            ui_menu_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            ui_menu_active = False
            config_menu_active = True
            core.reset_scroll("menu_item")
        elif key == "KEY_OK":
            option_id = ui_menu_options[ui_menu_selection]["id"]
            if option_id == "icons":
                new_icons = not show_icons
                core.save_config("show_icons", new_icons, section="nowplaying")
                show_icons = new_icons
            elif option_id == "oneline":
                new_oneline = not show_one_line
                core.save_config("show_one_line", new_oneline, section="nowplaying")
                show_one_line = new_oneline
            elif option_id == "extra":
                new_extra = not show_extra_infos
                core.save_config("show_extra_infos", new_extra, section="nowplaying")
                show_extra_infos = new_extra
            elif option_id == "progress":
                new_progress = not show_progress_barre
                core.save_config("show_progress_barre", new_progress, section="nowplaying")
                show_progress_barre = new_progress
            elif option_id == "cover_bg":
                idx = cover_bg_options.index(show_cover_bg)
                new_cover_bg = cover_bg_options[(idx + 1) % len(cover_bg_options)]
                show_cover_bg = new_cover_bg
                core.save_config("show_cover_bg", show_cover_bg, section="nowplaying")
                show_cover = show_cover_bg != "off"
                show_cover_alt = show_cover_bg == "resized"
                if new_cover_bg != "off":
                    global_state["cover_img"] = get_fallback_image("Cover turned ON")
            elif option_id == "spectrum":
                if not is_spectrum_available():
                    core.show_message(core.t("error_spectrum"))
                    time.sleep(1)
                    return
                new_spectrum = not show_spectrum
                core.save_config("show_spectrum", new_spectrum, section="nowplaying")
                show_spectrum = new_spectrum
            elif option_id == "peak_vu":
                idx = peak_vu_options.index(show_peak_vu)
                new_peak_vu = peak_vu_options[(idx + 1) % len(peak_vu_options)]
                if new_peak_vu != "off" and not is_spectrum_available():
                    core.show_message(core.t("error_spectrum"))
                    time.sleep(1)
                    return
                show_peak_vu = new_peak_vu
                core.save_config("show_peak_vu", show_peak_vu, section="nowplaying")
                show_peak = show_peak_vu != "off"
            elif option_id == "peak_vu_style":
                idx = peak_vu_style_options.index(peak_vu_style)
                idx = (idx + 1) % len(peak_vu_style_options)
                peak_vu_style = peak_vu_style_options[idx]
                core.save_config("peak_vu_style", peak_vu_style, section="nowplaying")
            elif option_id == "meters_alt":
                new_meters_alt = not show_meters_alt
                core.save_config("show_meters_alt",new_meters_alt, section="nowplaying")
                show_meters_alt = new_meters_alt
            elif option_id == "scale_label":
                new_scale_label = not show_scale_labels
                core.save_config("show_scale_labels",new_scale_label, section="nowplaying")
                show_scale_labels = new_scale_label
            elif option_id == "vol_bar":
                new_vol_bar = not show_vol_bar
                core.save_config("show_vol_bar", new_vol_bar, section="nowplaying")
                show_vol_bar = new_vol_bar
            elif option_id == "clock_elapse":
                new_clock = not show_clock
                core.save_config("show_clock", new_clock, section="nowplaying")
                show_clock = new_clock
            elif option_id == "apply":
                ui_menu_active = False
                core.show_message(core.t("info_reload_screen"))
                time.sleep(1)
                restart_service()
            core.reset_scroll("menu_item", "menu_title")
        return

    if screensaver_menu_active:
        if key == "KEY_UP" and screensaver_menu_selection > 0:
            screensaver_menu_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and screensaver_menu_selection < len(screensaver_menu_options) - 1:
            screensaver_menu_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            screensaver_menu_active = False
            config_menu_active = True
            core.reset_scroll("menu_item")
        elif key == "KEY_OK":
            option_id = screensaver_menu_options[screensaver_menu_selection]["id"]
            if option_id == "sleep":
                idx = sleep_timeout_options.index(core.SCREEN_TIMEOUT)
                idx = (idx + 1) % len(sleep_timeout_options)
                core.SCREEN_TIMEOUT = sleep_timeout_options[idx]
                core.save_config("screen_timeout", core.SCREEN_TIMEOUT, section="settings")
            elif option_id == "select":
                pass
            else:
                screensaver_menu_active = False
                screensaver_mode = screensaver_menu_options[screensaver_menu_selection]["id"]
                core.save_config("screensaver_mode", screensaver_mode , section="settings")
                core.show_message(core.t("info_screensaver_set", selected=screensaver_menu_options[screensaver_menu_selection]["label"]))
                time.sleep(1)
                restart_service()
            core.reset_scroll("menu_item", "menu_title")
        return

    if hardware_info_active:
        if key == "KEY_UP" and hardware_info_selection > 0:
            hardware_info_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and hardware_info_selection < len(hardware_info_lines) - 1:
            hardware_info_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            hardware_info_active = False
            tool_menu_active = True
            core.reset_scroll("menu_item")
        elif key == "KEY_OK":
            if wifi_extra_info:
                core.show_message(wifi_extra_info)
            else:
                core.show_message(core.t("info_wifi_disconnected"))
        return

    else:
        if key == "KEY_OK":
            nav_ok()
            core.reset_scroll("menu_item", "menu_title")
        elif key == "KEY_LEFT":
            nav_left_short()
        elif key == "KEY_RIGHT":
            nav_right_short()
        elif key == "KEY_UP":
            nav_up()
        elif key == "KEY_DOWN":
            nav_down()
        elif key == "KEY_CHANNELUP":
            nav_channelup()
        elif key == "KEY_CHANNELDOWN":
            nav_channeldown()
        elif handle_audio_keys(key, final_code, menu_context_flag):
            return
        elif handle_custom_key(key, final_code, menu_context_flag):
            return
        else:
            core.show_message(f"{key} unassigned")
            if core.DEBUG:
                print(f"key {key} not used in this script")

    press_data.pop(key, None)

core.start_message_updater()

start_inputs(core.config, finish_press, msg_hook=core.show_message)
set_custom_hooks(core.t, core.config, core.show_message)

def main():
    global previous_blocking_render, idle_timer
    threading.Thread(target=player_status_thread, daemon=True).start()
    threading.Thread(target=mixer_status_thread, daemon=True).start()
    threading.Thread(target=options_status_thread, daemon=True).start()
    threading.Thread(target=non_idle_status_thread, daemon=True).start()
    threading.Thread(target=cover_worker, daemon=True).start()
    if show_spectrum or show_peak or screensaver_mode in DYNAMIC_SS:
        threading.Thread(target=lambda: (time.sleep(0.5), delayed_spectrum_start()), daemon=True).start()
    try:
        while True:
            if previous_blocking_render != blocking_render:
                idle_timer = time.time()
            previous_blocking_render = blocking_render
            ui_busy = (
                blocking_render
                or core.message_permanent
                or core.message_text is not None
            )
            # --- wake if message appears ---
            if is_sleeping and ui_busy:
                wake_screen()
            # --- sleep handling ---
            if core.SCREEN_TIMEOUT > 0 and now_playing_mode:
                if time.time() - idle_timer > core.SCREEN_TIMEOUT:
                    if not is_sleeping and not ui_busy:
                        run_sleep_loop()
            # --- render ---
            if screen_on:
                run_active_loop()

            if is_sleeping and screensaver_mode not in DYNAMIC_SS:
                time.sleep(0.1)
            else:
                time.sleep(core.REFRESH_INTERVAL)
    except KeyboardInterrupt:
        if core.DEBUG:
            print("Closing")

if __name__ == '__main__':
    main()
