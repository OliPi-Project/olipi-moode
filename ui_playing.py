#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2025 OliPi Project
import faulthandler
faulthandler.enable()
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
import html
import http.server
import sqlite3
import json
import queue
from pathlib import Path
from mpd import MPDClient

OLIPIMOODE_DIR = Path(__file__).resolve().parent
os.environ.setdefault("OLIPI_DIR", str(OLIPIMOODE_DIR))

from olipi_core import core_common as core
from olipi_core.input_manager import start_inputs, debounce_data, process_key
from media_key_actions import handle_audio_keys, handle_custom_key, USED_MEDIA_KEYS, set_hooks as set_custom_hooks

yt_cache_path = OLIPIMOODE_DIR / "yt_cache.json"

PLS_PATH = "/var/lib/mpd/music/RADIO/Local Stream.pls"
LOGO_PATH = "/var/local/www/imagesw/radio-logos/Local Stream.jpg"
THUMB_PATH = "/var/local/www/imagesw/radio-logos/thumbs/Local Stream.jpg"
THUMB_SM_PATH = "/var/local/www/imagesw/radio-logos/thumbs/Local Stream_sm.jpg"
DB_PATH = "/var/local/www/db/moode-sqlite3.db"
LOCAL_STREAM_URL = "http://localhost:8080/stream.mp3"

# --- Fonts ui_playing ---
font_artist = core.get_font(OLIPIMOODE_DIR / 'Verdana.ttf', 15)
font_vol_clock = core.get_font(OLIPIMOODE_DIR / 'Verdana.ttf', 13)
font_stop_clock = core.get_font(OLIPIMOODE_DIR / 'Verdana.ttf', 24)
font_extra_info = core.get_font("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 9)

core.load_translations(Path(__file__).stem)

render_lock = threading.Lock()
now_playing_mode = False

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
menu_show_stream_queue_option = [{"id": "show_stream_queue", "label": core.t("menu_show_stream_queue")}]
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
    {"id": "show_songlog", "label": core.t("menu_show_songlog")},
    {"id": "hardware_info", "label": core.t("menu_hardware_info")},
    {"id": "configuration", "label": core.t("menu_configuration")}
]
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

stream_queue_active = False
stream_queue_lines = []
stream_queue_selection = 0

stream_queue = []
stream_queue_pos = 0
preload_queue = queue.Queue()
preload_queue_worker_started = False
yt_cache_lock = threading.Lock()

stream_queue_action_active = False
stream_queue_action_selection = 0
stream_queue_action_options = [
    {"id": "play_stream_queue_pos", "label": core.t("menu_play_stream_queue_pos")}
]

stream_manual_stop = False
stream_manual_skip = False
stream_transition_in_progress = False
current_ffmpeg = None
current_server = None
error_type = None

config_menu_active = False
config_menu_selection = 0
config_menu_options = [
    {"id": "sleep", "label": None},
    {"id": "language", "label": core.t("menu_language")},
    {"id": "debug", "label": core.t("menu_debug")}
]
if core.display_format != "MONO":
    config_menu_options.insert(2, {"id": "theme", "label": core.t("menu_theme")})
if core.height >= 128:
    config_menu_options.insert(3, {"id": "spectrum", "label": core.t("menu_spectrum")})
sleep_timeout_options = [0, 15, 30, 60, 300, 600]
sleep_timeout_labels = {0: "Off", 15: "15s", 30: "30s", 60: "1m", 300: "5m", 600: "10m"}

language_menu_active = False
language_menu_selection = 0
language_menu_options = [
    {"id": "en", "label": core.t("English")},
    {"id": "fr", "label": core.t("French")}
]
theme_menu_active = False
theme_menu_selection = 0
theme_menu_options = [
    {"id": "ocean",  "label": core.t("theme_ocean")},
    {"id": "autumn",  "label": core.t("theme_autumn")},
    {"id": "rasta",  "label": core.t("theme_rasta")},
    {"id": "unicorn",  "label": core.t("theme_unicorn")},
    {"id": "user",  "label": core.t("theme_user")},
    {"id": "default", "label": core.t("theme_default")}
]
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

# ---- ICON PATHS (keep as file paths) ----
ICON_PATHS = {
    "play": OLIPIMOODE_DIR / "icons/play.png",
    "pause": OLIPIMOODE_DIR / "icons/pause.png",
    "stop": OLIPIMOODE_DIR / "icons/stop.png",
    "random_on": OLIPIMOODE_DIR / "icons/random.png",
    "repeat_on": OLIPIMOODE_DIR / "icons/repeat.png",
    "repeat1_on": OLIPIMOODE_DIR / "icons/repeat1.png",
    "single_on": OLIPIMOODE_DIR / "icons/single.png",
    "consume_on": OLIPIMOODE_DIR / "icons/consume.png",
    "favorite": OLIPIMOODE_DIR / "icons/favorite.png",
    "bluetooth": OLIPIMOODE_DIR / "icons/bluetooth.png",
    "empty": OLIPIMOODE_DIR / "icons/empty.png",
}

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

show_clock = core.get_config("nowplaying", "show_clock", fallback=True, type=bool)

spectrum = None
PALETTE_SPECTRUM = []
show_spectrum = core.get_config("nowplaying", "show_spectrum", fallback=False, type=bool)

def load_spectrum_palette(theme_name="default"):
    themes = core.load_theme_file()
    theme = themes.get(theme_name, themes.get("default", {}))
    if "spectrum" in theme:
        global PALETTE_SPECTRUM
        PALETTE_SPECTRUM = [(float(val), core.get_color(tuple(col))) for val, col in theme["spectrum"]]

if core.height > 64:
    show_extra_infos = core.get_config("nowplaying", "show_extra_infos", fallback=False, type=bool)
    show_progress_barre = core.get_config("nowplaying", "show_progress_barre", fallback=False, type=bool)

if core.height >= 128 and show_spectrum:
    load_spectrum_palette(core.THEME_NAME)

last_title_seen = ""
last_artist_seen = ""

query = ""
stream_url = ""
title_yt = ""
artist_yt = ""
album_yt = ""
final_title_yt = ""

favorites_cache = []
favorites_last_mtime = 0
favorites_last_check = 0

def run_active_loop():
    if not blocking_render and not is_sleeping:
        render_screen()

def run_sleep_loop():
    global is_sleeping, screen_on
    if is_sleeping:
        return
    core.clear_display()
    core.poweroff_safe()
    screen_on = False
    is_sleeping = True

def has_internet_connection(timeout=2):
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=timeout)
        return True
    except OSError:
        return False

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
    "audioout": "Local"
}

def is_renderer_active():
    return (
        global_state.get("btsvc") == "1"
        and global_state.get("audioout") == "Local"
        and global_state.get("btactive") == "1"
    ) or any(
        global_state.get(flag) == "1"
        for flag in (
            "aplactive", "spotactive", "slactive", "rbactive",
            "paactive", "deezactive"
        )
    )

RENDERER_PARAMS = [
    "btsvc", "btactive", "airplaysvc", "aplactive", "spotifysvc", "spotactive",
    "slsvc", "slactive", "rbsvc", "rbactive", "pasvc", "paactive","deezersvc", "deezactive",
    "inpactive", "rxactive", "upnpsvc", "audioout"
]

def load_renderer_states_from_db():
    try:
        db_path = "/var/local/www/db/moode-sqlite3.db"
        conn = sqlite3.connect(db_path)
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

RADIO_MAP = {}
def build_radio_map(pls_directory="/var/lib/mpd/music/RADIO"):
    global RADIO_MAP
    radio_map = {}
    for filename in os.listdir(pls_directory):
        if filename.lower().endswith(".pls"):
            full_path = os.path.join(pls_directory, filename)
            try:
                url = ""
                title = ""
                with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if line.startswith("File1="):
                            url = line.split("=", 1)[1].strip()
                        elif line.startswith("Title1="):
                            title = line.split("=", 1)[1].strip()
                if url and title:
                    radio_map[url] = title
            except Exception as e:
                if core.DEBUG:
                    print(f"Error reading {filename}: {e}")
    RADIO_MAP = radio_map
build_radio_map()

def format_time(seconds: float) -> str:
    if seconds is None or seconds <= 0:
        return "0:00"
    h, m = divmod(int(seconds), 3600)
    m, s = divmod(m, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"

def player_status_thread():
    global last_title_seen, last_artist_seen, menu_context_flag
    client = MPDClient()
    client.timeout = 10
    while True:
        try:
            client.connect("localhost", 6600)
            break
        except Exception as e:
            print("Player MPD connect error, retry in 5s:", e)
            time.sleep(5)
    first_run = True
    while True:
        if is_sleeping:
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
                song_data = client.currentsong()
                status_extra = client.status()
                path = song_data.get("file", "")
                artist = song_data.get("artist", "")
                album = song_data.get("album", "")
                title = song_data.get("title", "")
                if path.startswith("http"):
                    artist = "Radio station"
                    if path == "http://localhost:8080/stream.mp3":
                        menu_context_flag = "local_stream"
                        if stream_queue:
                            position = stream_queue_pos + 1 if 0 <= stream_queue_pos < len(stream_queue) else "?"
                            artist_album = f"YT {core.t('show_stream_queue_number', count=len(stream_queue), position=position)}"
                            title = final_title_yt
                        else:
                            artist_album = f"YT Stream | [Album: {album_yt}]" if album_yt else "YT Stream"
                            title = final_title_yt
                        # global_state["duration"] defined in yt_search_track()
                    else:
                        menu_context_flag = "radio"
                        album = RADIO_MAP.get(path, "Unknown Radio")
                        artist_album = album
                        global_state["duration"] = float(status_extra.get("duration", 0.0))
                else:
                    menu_context_flag = "library"
                    artist_album = f"{artist} - {album}"
                    global_state["duration"] = float(status_extra.get("duration", 0.0))
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
                global_state["state"] = status_extra.get("state", "unknown")
                audio_fmt = status_extra.get("audio", "")
                if audio_fmt:
                    try:
                        samplerate, bits, channels = audio_fmt.split(":")
                        samplerate = round(int(samplerate)/1000, 1)
                        if samplerate.is_integer():
                            samplerate = int(samplerate)
                        if core.screen.width >= 160:
                            global_state["audio"] = f"{samplerate} kHz / {bits} bit"
                        else:
                            global_state["audio"] = f"{samplerate}k / {bits}b"
                    except Exception:
                        global_state["audio"] = audio_fmt
                else:
                    global_state["audio"] = "No Info"
        except Exception as e:
            print("Player idle error:", e)
            first_run = True
            try:
                client.disconnect()
                client.connect("localhost", 6600)
            except Exception:
                time.sleep(5)
        time.sleep(0.5)

def mixer_status_thread():
    client = MPDClient()
    client.timeout = 10
    while True:
        try:
            client.connect("localhost", 6600)
            break
        except Exception as e:
            print("Mixer MPD connect error, retry in 5s:", e)
            time.sleep(5)
    first_run = True
    while True:
        if is_sleeping:
            time.sleep(1)
            continue
        try:
            if not first_run:
                events = client.idle("mixer")
            else:
                events = []
            if "mixer" in events or first_run:
                first_run = False
                status_extra = client.status()
                volume_state = status_extra.get("volume", "N/A")
                if volume_state == "0":
                    global_state["volume"] = "Mute"
                else:
                    global_state["volume"] = volume_state
        except Exception as e:
            print("Mixer idle error:", e)
            first_run = True
            try:
                client.disconnect()
                client.connect("localhost", 6600)
            except Exception:
                time.sleep(5)
        time.sleep(0.5)

def options_status_thread():
    client = MPDClient()
    client.timeout = 10
    while True:
        try:
            client.connect("localhost", 6600)
            break
        except Exception as e:
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
            print("Options idle error:", e)
            first_run = True
            try:
                client.disconnect()
                client.connect("localhost", 6600)
            except Exception:
                time.sleep(5)
        time.sleep(0.5)

def non_idle_status_thread():
    last_fav_time = 0
    last_clock_time = 0
    last_renderer_check = 0
    last_elapsed_update = 0
    client = MPDClient()
    client.timeout = 10
    while True:
        try:
            client.connect("localhost", 6600)
            break
        except Exception as e:
            print("Player MPD connect error, retry in 5s:", e)
            time.sleep(5)
    while True:
        if is_sleeping:
            time.sleep(1)
            continue
        now = time.time()
        if now - last_elapsed_update > 1:
            last_elapsed_update = now
            try:
                status_extra = client.status()
                global_state["elapsed"] = float(status_extra.get("elapsed", 0.0))
                global_state["bitrate"] = status_extra.get("bitrate", "")
            except Exception as e:
                print("Non idle status error:", e)
                try:
                    client.disconnect()
                except Exception:
                    pass
                time.sleep(1)
                try:
                    client.connect("localhost", 6600)
                except Exception as e2:
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
    global stream_queue, stream_queue_pos
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

        # Check if this is the currently playing track
        if stream_queue and 0 <= stream_queue_pos < len(stream_queue):
            playing_index = stream_queue[stream_queue_pos]
            if 0 <= playing_index < len(songlog_lines):
                delete_current = {songlog_lines[playing_index]}
            if delete_current and stream_queue:
                if core.DEBUG:
                    print("♻️  Track in play was deleted – skipping to next")
                next_stream(manual_skip=True)

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

        # Update stream_queue: remove equal indices and adjust others
        new_queue = []
        for i in stream_queue:
            if i == idx_abs:
                continue
            new_queue.append(i - 1 if i > idx_abs else i)

        # Adjust the position in the queue
        removed_before_pos = len(stream_queue) - len(new_queue)
        if stream_queue_pos >= len(new_queue):
            stream_queue_pos = max(0, len(new_queue) - 1)
        elif removed_before_pos and stream_queue_pos > 0:
            stream_queue_pos = max(0, stream_queue_pos - removed_before_pos)
        stream_queue = new_queue

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

def ensure_local_stream():
    # Copy logo if present (optional)
    if os.path.exists(OLIPIMOODE_DIR / "local-stream.jpg") and not os.path.exists(LOGO_PATH):
        if core.DEBUG:
            print("Copying Local Stream logo...")
        subprocess.run(["sudo", "cp", OLIPIMOODE_DIR / "local-stream.jpg", LOGO_PATH])
        subprocess.run(["sudo", "chmod", "777", LOGO_PATH])
        subprocess.run(["sudo", "chown", "root:root", LOGO_PATH])

        # Create large thumbnail (same as original logo)
        if core.DEBUG:
            print("Creating thumbnails...")
        subprocess.run(["sudo", "cp", OLIPIMOODE_DIR / "local-stream.jpg", THUMB_PATH])
        subprocess.run(["sudo", "chmod", "777", THUMB_PATH])
        subprocess.run(["sudo", "chown", "root:root", THUMB_PATH])

        # Create small thumbnail (80x80)
        img = core.Image.open(OLIPIMOODE_DIR / "local-stream.jpg")
        img.thumbnail((80, 80))
        img = img.convert("RGB")  # Ensure JPEG format
        temp_thumb_sm = "/tmp/local-stream-thumb-sm.jpg"
        img.save(temp_thumb_sm, "JPEG")
        subprocess.run(["sudo", "cp", temp_thumb_sm, THUMB_SM_PATH])
        subprocess.run(["sudo", "chmod", "777", THUMB_SM_PATH])
        subprocess.run(["sudo", "chown", "root:root", THUMB_SM_PATH])

    # Check database entry
    result = subprocess.run(
        ["sqlite3", DB_PATH, f"SELECT COUNT(*) FROM cfg_radio WHERE station='{LOCAL_STREAM_URL}';"],
        capture_output=True,
        text=True
    )
    if result.stdout.strip() == "0":
        if core.DEBUG:
            print("Inserting Local Stream into database...")
        sql_insert = f"""
        INSERT INTO cfg_radio (
            station, name, type, logo, genre, broadcaster, language,
            country, region, bitrate, format, geo_fenced, home_page, monitor
        ) VALUES (
            '{LOCAL_STREAM_URL}',
            'Local Stream',
            'r',
            'local',
            '',
            '',
            '',
            '',
            '',
            '192',
            'MP3',
            'No',
            '',
            'No'
        );
        """
        subprocess.run(f"echo \"{sql_insert}\" | sudo sqlite3 {DB_PATH}", shell=True, check=True)

    # Create .pls file if missing
    if not os.path.exists(PLS_PATH):
        if core.DEBUG:
            print("Creating Local Stream .pls file...")
        pls_content = """[playlist]
File1=http://localhost:8080/stream.mp3
Title1=Local Stream
Length1=-1
NumberOfEntries=1
Version=2
"""
        subprocess.run(f"echo '{pls_content}' | sudo tee '{PLS_PATH}' > /dev/null", shell=True, check=True)
        subprocess.run(["sudo", "chmod", "777", PLS_PATH])
        subprocess.run(["sudo", "chown", "root:root", PLS_PATH])
        subprocess.run(f"sudo touch '{PLS_PATH}'", shell=True, check=True)
        subprocess.run(["sudo", "php", OLIPIMOODE_DIR / "update_local_stream.php", LOCAL_STREAM_URL, "Local Stream", "r", "", "MP3"])

    else:
        if core.DEBUG:
            print("Local Stream already exists in database.")

def preload_worker():
    while True:
        index = preload_queue.get()
        if core.DEBUG:
            print("-  -  -  -  -  -  -  -  -")
            print(f"⚪ Preloading track index {index}")
        try:
            yt_search_track(index, preload=True)
        except Exception as e:
            core.show_message(core.t("preload_yt", error=e))
            if core.DEBUG:
                print("error preload yt: ", e)
        time.sleep(2.0)
        preload_queue.task_done()

def play_all_songlog_from_queue():
    global stream_queue, stream_queue_pos, preload_queue_worker_started
    if not songlog_lines:
        core.show_message(core.t("info_empty_songlog"))
        return
    for i in range(len(songlog_lines)):
        stream_queue.append(i)
    core.show_message(core.t("info_stream_queue_full", count=len(stream_queue)))
    time.sleep(1.5)
    stream_queue_pos = 0
    yt_search_track(stream_queue[0])
    if not preload_queue_worker_started:
        threading.Thread(target=preload_worker, daemon=True).start()
        preload_queue_worker_started = True
    for i in stream_queue[1:]:
        preload_queue.put(i)

def next_stream(manual_skip=False):
    global stream_queue_pos, stream_manual_skip, stream_transition_in_progress
    if stream_transition_in_progress:
        if core.DEBUG:
            print("⚠️ next_stream ignored (stream already launching)")
        return
    stream_queue_pos += 1
    if stream_queue_pos < len(stream_queue):
        stream_transition_in_progress = True
        stream_manual_skip = manual_skip
        next_index = stream_queue[stream_queue_pos]
        core.show_message(core.t("info_next_stream", pos=stream_queue_pos + 1, total=len(stream_queue)))
        if core.DEBUG:
            print("-------------------------Next Stream----------------------------------")
            print(f"⏭️ Next stream from queue: {next_index}")
            print(f"[next_stream] manual_skip = {manual_skip}")
        yt_search_track(next_index, preload=False)
    else:
        core.show_message(core.t("info_end_queue"))
        if core.DEBUG:
            print("✅ End of stream queue")

def previous_stream(manual_skip=True):
    global stream_queue_pos, stream_manual_skip, stream_transition_in_progress
    if stream_transition_in_progress:
        if core.DEBUG:
            print("⚠️ previous_stream ignored (stream already launching)")
        return
    previous_index = stream_queue_pos - 1
    if previous_index >= 0:
        stream_transition_in_progress = True
        stream_manual_skip = manual_skip
        stream_queue_pos = previous_index
        core.show_message(core.t("info_prev_stream", pos=stream_queue_pos + 1, total=len(stream_queue)))
        if core.DEBUG:
            print("-------------------------Previous Stream----------------------------------")
            print(f"⏮️ Previous stream from queue: {previous_index}")
            print(f"[prev_stream] manual_skip = {manual_skip}")
        yt_search_track(previous_index, preload=False)
    else:
        core.show_message(core.t("info_top_queue"))
        if core.DEBUG:
            print("✅ Top of stream queue")

def set_stream_manual_stop(manual_stop=True):
    global stream_manual_stop
    stream_manual_stop = manual_stop

def yt_search_track(index, preload=False, _fallback_attempt=False, local_query=None):
    global stream_url, final_title_yt, album_yt, artist_yt, query, blocking_render, stream_transition_in_progress

    load_renderer_states_from_db()
    if is_renderer_active() and not preload:
        if core.DEBUG:
            print("Renderer active – aborting yt_search_track()")
        return

    if not preload:
        stop_current_stream()

    if local_query is None:
        if index >= len(songlog_lines):
            if not preload:
                core.show_message(core.t("info_invalid_index"))
            return
        local_query = songlog_lines[index].strip()

    if core.DEBUG:
        print(f"→ Search for: {local_query}")

    yt_cache = {}

    # Thread-safe loading of the cache
    with yt_cache_lock:
        try:
            with open(yt_cache_path, "r", encoding="utf-8") as f:
                yt_cache = json.load(f)
        except:
            yt_cache = {}

    cache_entry = yt_cache.get(local_query)
    url_expired = False

    if cache_entry and cache_entry.get("resolved") and cache_entry.get("url"):
        expire_ts = cache_entry.get("expire_ts")
        expire_str = cache_entry.get("expires", "?")
        now_ts = int(time.time())

        if expire_ts is None:
            url_expired = True
            if core.DEBUG:
                print("❓ No expire_ts in cache – assuming expired")
        elif now_ts >= expire_ts:
            url_expired = True
            if core.DEBUG:
                print(f"🟢 Cached URL expired\n   Expired at: {expire_str}\n   Now       : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            if core.DEBUG:
                print(f"✓ Cached URL still valid until {expire_str}")

        if not url_expired:
            if core.DEBUG:
                print(f"Using cached result for: {local_query}")
            if not preload:
                stream_url = cache_entry["url"]
                final_title_yt = cache_entry["title"]
                artist_yt = cache_entry["artist"]
                album_yt = cache_entry.get("album", "")
                global_state["duration"] = float(cache_entry.get("duration") or 0.0)
                load_renderer_states_from_db()
                if is_renderer_active():
                    if core.DEBUG:
                        print("Renderer active – aborting launch of stream_songlog_entry()")
                    return
                try:
                    stream_songlog_entry()
                finally:
                    stream_transition_in_progress = False
                    stream_manual_skip = False
            return
    else:
        if core.DEBUG:
            print("❓ No entry in cache")

    if not preload:
        core.message_text = core.t("info_search_yt", query=local_query)
        core.message_permanent = True
        blocking_render = True
        time.sleep(0.05)
        render_screen()

    from yt_dlp import YoutubeDL
    try:
        ydl_opts = {
            'quiet': True,
            'default_search': 'ytsearch3',
            'noplaylist': True,
            'format': "bestaudio[protocol!=m3u8]",
            'no_warnings': True
        }

        # Retry logic: attempt the same extraction up to attempts_total times before giving up / fallback.
        attempts_total = 2
        info = None
        last_exception = None
        for attempt in range(attempts_total):
            try:
                with YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(local_query, download=False)
                # success -> break out
                last_exception = None
                break
            except Exception as e:
                last_exception = e
                if core.DEBUG:
                    print(f"[yt-dlp] attempt {attempt+1}/{attempts_total} failed: {e}")
                # if not last attempt, wait a bit and retry (for temporary CDN/format glitches)
                if attempt < attempts_total - 1:
                    time.sleep(1.0)
                    continue
        if info is None:
            raise last_exception if last_exception is not None else Exception("yt-dlp failed without exception")

        if "_type" in info and "entries" in info:
            entries = [v for v in info["entries"] if v.get("duration", 0) and v["duration"] > 60]
            if not entries:
                entries = info["entries"]  # fallback si rien trouvé
            video = entries[0]
        else:
            video = info

        resolved_url = video['url']
        title_raw = video.get("track") or video.get("title") or "Unknown"
        album = video.get("album")
        duration = video.get("duration")
        webpage_url = video.get("webpage_url")

        artist_candidates = {
            "artist": video.get("artist"),
            "album_artist": video.get("album_artist"),
            "composer": video.get("composer"),
            "creator": video.get("creator"),
            "uploader": video.get("uploader"),
        }

        if " - " in local_query:
            artist_query, title_query = map(str.strip, local_query.split(" - ", 1))
        else:
            artist_query = local_query.strip()
            title_query = ""

        artist_match = next((v for v in artist_candidates.values() if v and artist_query.lower() in v.lower()), None)

        if artist_query.lower() in title_raw.lower():
            title_final = title_raw
            artist_final = artist_query
        elif artist_match:
            title_final = f"{artist_query} - {title_raw}"
            artist_final = artist_query
        else:
            title_final = f"{title_raw} - ({artist_query} ?)"
            artist_final = f"Unknown / maybe {artist_query}"

        expire_ts = None
        expire_str = None
        match = re.search(r"[?&]expire=(\d+)", resolved_url)
        if match:
            expire_ts = int(match.group(1))
            expire_str = datetime.datetime.fromtimestamp(expire_ts).strftime("%Y-%m-%d %H:%M:%S")

        if core.DEBUG:
            print(f"[yt-dlp] title: {title_raw}")
            print(f"[yt-dlp] album: {album}")
            print(f"[yt-dlp] final-title: {title_final}")
            print(f"[yt-dlp] duration: {duration}")
            print(f"[yt-dlp] expire at: {expire_str}")

        with yt_cache_lock:
            yt_cache[local_query] = {
                "title": title_final,
                "artist": artist_final,
                "album": album,
                "duration": duration,
                "acodec": video.get('acodec'),
                "abr": video.get('abr'),
                "ext": video.get('ext'),
                "format": video.get('format'),
                "webpage_url": webpage_url,
                "url": resolved_url,
                "resolved": True,
                "timestamp": datetime.datetime.now().isoformat(),
                "expires": expire_str,
                "expire_ts": expire_ts
            }

            with open(yt_cache_path, "w", encoding="utf-8") as f:
                json.dump(yt_cache, f, indent=2)

        if not preload:
            stream_url = resolved_url
            final_title_yt = title_final
            artist_yt = artist_final
            album_yt = album
            global_state["duration"] = float((cache_entry.get("duration") if cache_entry else duration) or 0.0)
            load_renderer_states_from_db()
            if is_renderer_active():
                if core.DEBUG:
                    print("Renderer active – aborting launch of stream_songlog_entry()")
                core.message_permanent = False
                core.message_text = None
                blocking_render = False
                return
            try:
                stream_songlog_entry()
            finally:
                stream_transition_in_progress = False
                stream_manual_skip = False

    except Exception as e:
        if not preload:
            core.message_permanent = False
            core.message_text = None
            stream_manual_skip = False
            stream_transition_in_progress = False
            blocking_render = False

        if preload:
            if core.DEBUG:
                print(f"[yt-dlp] preload failed for '{local_query}': {e}")
            return

        if not _fallback_attempt:
            parts = local_query.split(" - ")
            if len(parts) == 2:
                fallback_query = parts[1].strip()
            else:
                fallback_query = local_query

            if core.DEBUG:
                print(f"No results for query: {local_query}")
                print(f"Retrying with fallback query: {fallback_query}")

            return yt_search_track(index, preload=preload, _fallback_attempt=True, local_query=fallback_query)

        core.show_message(core.t("error_yt", error=e))
        if core.DEBUG:
            print("error yt: ", e)
        if not preload and not core.DEBUG:
            core.show_message(core.t("error_yt_simple"))
        return

    if not preload:
        core.message_permanent = False
        core.message_text = None
        blocking_render = False

def stop_current_stream():
    global current_ffmpeg, current_server

    if current_ffmpeg and current_ffmpeg.poll() is None:
        try:
            current_ffmpeg.terminate()
            current_ffmpeg.wait(timeout=4)
            if core.DEBUG:
                print("✓ ffmpeg terminated")
        except subprocess.TimeoutExpired:
            if core.DEBUG:
                print("⚠️ ffmpeg did not terminate in time, killing...")
            try:
                current_ffmpeg.kill()
                current_ffmpeg.wait(timeout=2)
                if core.DEBUG:
                    print("✓ ffmpeg killed")
            except Exception as e:
                core.show_message(core.t("error_kill_ffmpeg", error=e))
                if core.DEBUG:
                    print("error kill ffmpeg: ", e)
        except Exception as e:
            core.show_message(core.t("error_stop_ffmpeg", error=e))
            if core.DEBUG:
                print("error stop ffmpeg: ", e)
    current_ffmpeg = None

    if current_server:
        try:
            current_server.shutdown()
            current_server.server_close()
            if core.DEBUG:
                print("✓ HTTP server stopped")
        except Exception as e:
            core.show_message(core.t("error_http_server", error=e))
            if core.DEBUG:
                print("error http server: ", e)
    current_server = None

    # Wait max 4s for port 8080 to be released
    for i in range(20):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(("localhost", 8080)) != 0:
                    if core.DEBUG:
                        print("✓ Port 8080 libre")
                    break
        except Exception as e:
            core.show_message(core.t("error_socket_check", error=e))
            if core.DEBUG:
                print("error socket check: ", e)
            break
        time.sleep(0.2)
    else:
        if core.DEBUG:
            print("⚠️ Port 8080 encore occupé après timeout")

def stream_songlog_entry():
    global current_ffmpeg, current_server, blocking_render, stream_manual_skip, stream_transition_in_progress, error_type
    stream_manual_skip = False

    load_renderer_states_from_db()
    if is_renderer_active():
        if core.DEBUG:
            print("Renderer active – aborting stream_songlog_entry()")
        return

    if core.DEBUG:
        print(f"⇨ Start Local Stream")

    core.message_text = core.t("info_streaming", title=final_title_yt)
    core.message_permanent = True
    blocking_render = True
    time.sleep(0.05)
    render_screen()

    class StreamHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            global current_ffmpeg, blocking_render, current_server, stream_manual_stop, stream_manual_skip, error_type
            if self.path != "/stream.mp3":
                self.send_error(404)
                return

            self.send_response(200)
            self.send_header("Content-Type", "audio/mpeg")
            self.end_headers()

            if core.DEBUG:
                print(f"→ Launching ffmpeg for: {final_title_yt}")

            cmd = [
                "ffmpeg", "-re",
                "-fflags", "+discardcorrupt",
                "-reconnect", "1",
                "-reconnect_streamed", "1",
                "-reconnect_delay_max", "2",
                "-i", stream_url,
                "-vn",
                "-c:a", "libmp3lame",
                "-b:a", "192k",
                "-metadata", f"title={final_title_yt}",
                "-f", "mp3", "-"
            ]

            try:
                # Launch ffmpeg with stderr piped so we can read errors without blocking ffmpeg.
                current_ffmpeg = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )

                # Sanity check
                if not current_ffmpeg or not current_ffmpeg.stdout:
                    if core.DEBUG:
                        print("⚠️ ffmpeg not ready, aborting stream")
                    return

                # Thread: read stderr continuously to avoid blocking ffmpeg.
                # decode with 'replace' to avoid unicode decode errors on arbitrary binary output.
                def _read_stderr(proc):
                    global error_type
                    try:
                        for raw in iter(proc.stderr.readline, b""):
                            if not raw:
                                break
                            line = raw.decode("utf-8", errors="replace").rstrip()
                            if not line:
                                continue

                            #error_type = None
                            lower = line.lower()
                            if "http error 403" in lower:
                                error_type = "Server returned 403 Forbidden (access denied)"
                            elif "http error 404" in lower:
                                error_type = "HTTP 404 Not Found"
                            elif "invalid data found" in lower or "moov atom not found" in lower:
                                error_type = "Corrupt / unsupported media"
                            elif "connection refused" in lower:
                                error_type = "Network error"
                            elif "could not find codec" in lower:
                                error_type = "Codec error"

                            if error_type:
                                if core.DEBUG:
                                    print(f" +++ {line} +++ ")

                    except Exception as e:
                        if core.DEBUG:
                            print(f"[ffmpeg stderr reader] {e}")
                    finally:
                        try:
                            if proc.stderr:
                                proc.stderr.close()
                        except Exception:
                            pass

                threading.Thread(target=_read_stderr, args=(current_ffmpeg,), daemon=True).start()

                # Read stdout and pipe to client
                empty_reads = 0
                while True:
                    chunk = current_ffmpeg.stdout.read(4096)
                    if not chunk:
                        empty_reads += 1
                        if empty_reads >= 20:
                            if core.DEBUG:
                                print("2s of empty chunk – aborting stream loop")
                            break
                        time.sleep(0.1)
                        continue

                    empty_reads = 0
                    try:
                        self.wfile.write(chunk)
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError) as e:
                        if core.DEBUG:
                            print(f"⚠️ Client disconnected: {e}")
                        break

            except Exception as e:
                # keep your previous special-case for the NoneType stdout on ffmpeg stop
                if "NoneType" in str(e) and "stdout" in str(e):
                    if core.DEBUG:
                        print(f"Ignored stream error on ffmpeg stop: {e}")
                else:
                    core.show_message(core.t("error_stream", error=e))
                    if core.DEBUG:
                        print("error stream: ", e)
            finally:
                try:
                    client = MPDClient()
                    client.connect("localhost", 6600)
                    client.stop()
                    client.close()
                    client.disconnect()
                except Exception as e:
                    core.show_message(core.t("error_mpd", error=e))
                    if core.DEBUG:
                        print("error mpd: ", e)
                    if not core.DEBUG:
                        core.show_message(core.t("error_generic"))

                if current_ffmpeg and current_ffmpeg.poll() is None:
                    try:
                        current_ffmpeg.terminate()
                        current_ffmpeg.wait(timeout=4)
                        if core.DEBUG:
                            print("✓ ffmpeg terminated cleanly")
                    except subprocess.TimeoutExpired:
                        if core.DEBUG:
                            print("⚠️ ffmpeg timeout, forcing kill")
                        try:
                            current_ffmpeg.kill()
                            current_ffmpeg.wait(timeout=2)
                            if core.DEBUG:
                                print("✓ ffmpeg killed")
                        except Exception as e:
                            core.show_message(core.t("error_ffmpeg", error=e))
                            if core.DEBUG:
                                print("error ffmpeg: ", e)
                current_ffmpeg = None
                if core.DEBUG:
                    print("----------------End of Stream---------------------")
                    print(f"[StreamHandler] stream_manual_skip = {stream_manual_skip}")
                    print(f"[StreamHandler] stream_manual_stop = {stream_manual_stop}")
                load_renderer_states_from_db()
                if error_type:
                    show_ffmpeg_error(error_type)
                    time.sleep(2)
                    error_type = None
                if not stream_manual_skip and not stream_manual_stop and not is_renderer_active():
                    threading.Thread(target=next_stream, daemon=True).start()
                stream_manual_stop = False
                stream_manual_skip = False

    def run_server():
        global current_server
        current_server = http.server.HTTPServer(("0.0.0.0", 8080), StreamHandler)
        current_server.serve_forever()

    threading.Thread(target=run_server, daemon=True).start()

    try:
        client = MPDClient()
        client.timeout = 10
        client.connect("localhost", 6600)
        client.clear()
        client.load("RADIO/Local Stream.pls")

        for _ in range(20):
            try:
                with socket.create_connection(("localhost", 8080), timeout=0.5):
                    break
            except OSError:
                time.sleep(0.25)

        client.play()

        start_time = time.time()
        while time.time() - start_time < 20:  # timeout max 20s
            status = client.status()
            if status.get("state") == "play":
                song = client.currentsong()
                title = song.get("title", "")
                # on considère que la lecture est "vraie" si un titre est présent
                if title != "Local Stream":
                    break
            # petit délai pour ne pas poller le CPU
            time.sleep(0.3)

        client.close()
        client.disconnect()

        core.message_permanent = False
        core.message_text = None
        if core.DEBUG:
            print(f"✅ Streaming ready: {final_title_yt}")

    except Exception as e:
        core.message_permanent = False
        core.message_text = None
        stream_transition_in_progress = False
        blocking_render = False
        core.show_message(core.t("error_mpd", error=e))
        if core.DEBUG:
            print("error mpd: ", e)
        else:
            core.show_message(core.t("error_generic"))

    stream_transition_in_progress = False
    blocking_render = False

def show_ffmpeg_error(msg):
    core.show_message(msg)

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

    run_bluetooth_action("-S")
    update_trusted_devices_menu()

    time.sleep(0.5)
    core.message_permanent = False
    core.message_text = None
    core.show_message(core.t("info_bt_scan_ok"))
    blocking_render = False
    bluetooth_scan_menu_active = True

def update_trusted_devices_menu():
    global bluetooth_scan_menu_options
    output = run_bluetooth_action("-l")
    paired = run_bluetooth_action("-p").splitlines()
    paired_set = set(
        line[3:].strip().split(" ", 1)[0]
        for i, line in enumerate(paired)
        if i >= 2 and line.startswith("** ")
    )
    connected = run_bluetooth_action("-c").splitlines()
    connected_set = set(
        line[3:].strip().split(" ", 1)[0]
        for i, line in enumerate(connected)
        if i >= 2 and line.startswith("** ")
    )
    bluetooth_scan_menu_options = []
    for i, line in enumerate(output.splitlines()):
        if i < 2:
            continue
        if not line.startswith("** "):
            continue
        line = line[3:].strip()
        parts = line.split(" ", 1)
        if len(parts) == 2:
            mac, name = parts
            is_paired = mac in paired_set
            is_connected = mac in connected_set
            if is_connected:
                icon = "✓⚪ "
            elif is_paired and not is_connected:
                icon = "⚪ "
            else:
                icon = ""
            bluetooth_scan_menu_options.append({"id": f"bt_trusted_{mac}", "label": f"{icon}{name}", "mac": mac, "paired": is_paired, "connected": is_connected})

def update_paired_devices_menu():
    global bluetooth_paired_menu_options
    paired = run_bluetooth_action("-p").splitlines()
    connected = run_bluetooth_action("-c").splitlines()
    connected_set = set(
        line[3:].strip().split(" ", 1)[0]
        for i, line in enumerate(connected)
        if i >= 2 and line.startswith("** ")
    )

    bluetooth_paired_menu_options = []
    for i, line in enumerate(paired):
        if i < 2:
            continue
        if not line.startswith("** "):
            continue
        line = line[3:].strip()
        parts = line.split(" ", 1)
        if len(parts) == 2:
            mac, name = parts
            is_connected = mac in connected_set
            icon = "✓ " if is_connected else ""
            bluetooth_paired_menu_options.append({"id": f"bt_dev_{mac}", "label": f"{icon} {name}", "mac": mac, "connected": is_connected})

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

def toggle_audio_output(mode):
    global blocking_render, bluetooth_menu_active

    core.message_text = core.t("info_working")
    core.message_permanent = True
    blocking_render = True
    time.sleep(0.05)
    render_screen()

    output = []

    def act_bluaudiout():
        try:
            result = subprocess.run(
                ["sudo", "php", str(OLIPIMOODE_DIR / "audioout-toggle.php"), mode],
                capture_output=True, text=True, check=False
            )
            output.append(result.stdout.strip())
        except Exception as e:
            core.show_message(core.t("error_audioout", error=e))
            if core.DEBUG:
                print("error audioout: ", e)
            output.append("[ERROR]")

    thread = threading.Thread(target=act_bluaudiout)
    thread.start()
    thread.join()

    load_renderer_states_from_db()
    time.sleep(0.5)
    core.message_permanent = False
    core.message_text = None

    result_line = output[0] if output else "[ERROR]"

    if result_line.startswith("[AUDIOOUT_CHANGED]"):
        core.show_message(core.t("info_audioout_changed", mode=mode))
    elif result_line.startswith("[AUDIOOUT_ALREADY_SET]"):
        core.show_message(core.t("info_audioout_already", mode=mode))
    elif result_line.startswith("[AUDIOOUT_NO_BT]"):
        core.show_message(core.t("error_audioout_bt_missing"))
    elif result_line.startswith("[AUDIOOUT_INVALID]"):
        core.show_message(core.t("error_audioout_invalid"))
    elif result_line.startswith("[AUDIOOUT_USAGE]"):
        core.show_message(core.t("error_audioout_usage"))
    else:
        core.show_message(result_line)
    blocking_render = False
    bluetooth_menu_active = True

def render_screen():
    with render_lock:
        #t0 = time.perf_counter()
        global now_playing_mode
        now_playing_mode = False

        #t_s = time.perf_counter()
        if core.message_text:
            core.draw_message()
            idle_timer = time.time()
        elif help_active:
            draw_help_screen()
        elif confirm_box_active:
            draw_confirm_box()
        elif hardware_info_active:
            draw_hardware_info()
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
        elif stream_queue_action_active:
            draw_stream_queue_action_menu()
        elif stream_queue_active:
            draw_stream_queue_menu()
        elif menu_active:
            draw_menu()
        else:
            now_playing_mode = True
            draw_nowplaying()

        #t_draw = time.perf_counter() - t_s
        #t_b = time.perf_counter()
        core.refresh()
        #t_blit = time.perf_counter() - t_b
        #print(f"TIMING nowplaying draw {t_draw*1000:.1f} ms | blit {t_blit*1000:.1f} ms | total {(time.perf_counter()-t0)*1000:.1f} ms")

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
        filtered_options = [opt for opt in menu_options if opt.get("id") not in {"remove_queue", "playback_modes"}]
        if stream_queue:
            menu_options_contextuel = menu_show_stream_queue_option.copy() + filtered_options
        else:
            menu_options_contextuel = filtered_options
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
    selected = set()
    if stream_queue and 0 <= stream_queue_pos < len(stream_queue):
        playing_index = stream_queue[stream_queue_pos]
        if 0 <= playing_index < len(songlog_lines):
            selected = {songlog_lines[playing_index]}
    core.draw_custom_menu(songlog_lines, songlog_selection, title=core.t("title_songlog"), multi=selected, checkmark="▶ ")

def draw_stream_queue_menu():
    global stream_queue_lines
    stream_queue_lines = [songlog_lines[i] for i in stream_queue if 0 <= i < len(songlog_lines)]
    selected = {stream_queue_lines[stream_queue_pos]}
    core.draw_custom_menu(stream_queue_lines, stream_queue_selection, title=core.t("title_stream_queue"), multi=selected, checkmark="▶ ")

def draw_stream_queue_action_menu():
    core.draw_custom_menu([item["label"] for item in stream_queue_action_options], stream_queue_action_selection, title=core.t("title_action_stream_queue"))

def draw_songlog_action_menu():
    core.draw_custom_menu([item["label"] for item in songlog_action_options], songlog_action_selection, title=core.t("title_action_songlog"))

def draw_tool_menu():
    core.draw_custom_menu([item["label"] for item in tool_menu_options], tool_menu_selection, title=core.t("title_tools"))

def draw_theme_menu():
    # currently selected theme
    selected = {item["label"] for item in theme_menu_options if item["id"] == core.THEME_NAME}
    core.draw_custom_menu([item["label"] for item in theme_menu_options], theme_menu_selection, title=core.t("title_theme"), multi=selected)

def draw_language_menu():
    selected = {item["label"] for item in language_menu_options if item["id"] == core.LANGUAGE}
    core.draw_custom_menu([item["label"] for item in language_menu_options], language_menu_selection, title=core.t("title_language"), multi=selected)

def draw_config_menu():
    for item in config_menu_options:
        if item["id"] == "sleep":
            item["label"] = core.t("menu_sleep") + f": {sleep_timeout_labels.get(core.SCREEN_TIMEOUT, 'Off')}"
            break
    config_flags = set()
    if core.DEBUG:
        config_flags.add(core.t("menu_debug"))
    if show_spectrum:
        config_flags.add(core.t("menu_spectrum"))
    core.draw_custom_menu([item["label"] for item in config_menu_options], config_menu_selection, title=core.t("title_config"), multi=config_flags)

def draw_help_screen():
    core.draw_custom_menu(help_lines, help_selection, title=core.t("title_help"))

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

def draw_confirm_box():
    core.draw_custom_menu([item["label"] for item in confirm_box_options], confirm_box_selection, title=confirm_box_title)

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
        try:
            from spectrum_capture import SpectrumCapture
        except Exception as e:
            print(f"[Spectrum] Import failed: {e}")
            show_spectrum = False

        num_bars = core.get_config("spectrum", "num_bars", fallback=36, type=int)
        fmin = core.get_config("spectrum", "fmin", fallback=0, type=int)
        fmax = core.get_config("spectrum", "fmax", fallback=None, type=int)
        profile_str = core.get_config("spectrum", "spectrum_profile", fallback="", type=str)
        try:
            profile_dict = json.loads(profile_str) if profile_str else None
        except json.JSONDecodeError as e:
            print(f"Invalid JSON for spectrum_profile in ini: {e}")
            profile_dict = None
        spectrum = SpectrumCapture(
            num_bars=num_bars,
            fmin=fmin,
            fmax=fmax,
            profile=profile_dict
        )
        spectrum.start()
        if core.DEBUG:
            print(f"Samplerate: {spectrum.samplerate} Hz, Channels: {spectrum.channels}, Format: {spectrum.format_name}")

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

def monitor_spectrum():
    client = MPDClient()
    client.timeout = 10
    while True:
        # Try to connect until success
        while True:
            try:
                client.connect("localhost", 6600)
                break
            except Exception as e:
                print("MPD monitor connect error, retry in 5s:", e)
                time.sleep(5)
        last_toggle = 0
        while True:
            try:
                events = client.idle()
                if 'player' in events:
                    if time.time() - last_toggle < 0.2:
                        continue
                    stop_spectrum()
                    time.sleep(0.1)
                    client.pause()
                    time.sleep(0.05)
                    client.pause()
                    last_toggle = time.time()
                    time.sleep(0.1)
                    start_spectrum()
            except Exception as e:
                print("MPD monitor error:", e)
                try:
                    client.disconnect()
                except Exception:
                    pass
                time.sleep(2)
                break  # leave inner loop, go back to reconnect

def delayed_spectrum_start():
    if not is_spectrum_available():
        if core.DEBUG:
            print("[UI] Spectrum disabled: no loopback device")
        core.show_message(core.t("error_spectrum"))
    else:
        start_spectrum()
        threading.Thread(target=monitor_spectrum, daemon=True).start()

def interpolate_palette(value, palette):
    """Interpolate between colors in a palette (value ∈ [0,1])."""
    value = max(0.0, min(1.0, value))  # clamp
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

def draw_spectrum(y_top, height, levels):
    palette = PALETTE_SPECTRUM
    num_bars = len(levels)
    bar_width = (core.width - 4) // num_bars if num_bars > 0 else core.width - 4
    total_width = bar_width * num_bars
    margin_left = (core.width - total_width) // 2

    # Precompute global gradient if needed
    global_gradient = []
    if height <= 1:
        color = interpolate_palette(1.0, palette)
        global_gradient = [color]
    else:
        for yy in range(height):
            value = 1.0 - (yy / (height - 1))  # bottom → top
            global_gradient.append(interpolate_palette(value, palette))

    # Draw bars
    for i, level in enumerate(levels):
        bar_h = int(level * height)
        if bar_h <= 0:
            continue
        x0 = margin_left + i * bar_width
        y_start = y_top + height - bar_h
        for y in range(bar_h):
            idx = y_start + y - y_top
            idx = max(0, min(idx, len(global_gradient) - 1))
            color = global_gradient[idx]
            core.draw.rectangle((x0, y_start + y, x0 + bar_width - 1, y_start + y), fill=color)

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
    if is_renderer_active():
        if (
            global_state.get("btsvc") == "1"
            and global_state.get("audioout") == "Local"
            and global_state.get("btactive") == "1"
        ):
            artist_album = core.t("show_bt_input")
            title = core.t("show_bt_output_hint")
        else:
            artist_album = core.t("show_renderer_active")
            title = core.t("show_renderer_hint")
    else:
        artist_album = global_state.get("artist_album", "")
        title = global_state.get("title", "")

    text1_width = core.draw.textlength(artist_album, font=font_artist)
    text2_width = core.draw.textlength(title, font=font_artist)

    state = global_state.get("state", "unknown")
    volume = global_state.get("volume", "N/A")

    # Background
    core.draw.rectangle((0, 0, core.width, core.height), fill=core.COLOR_BG)

    padding_x = max(2, int(core.width * 0.02))
    padding_y = max(2, int(core.height * 0.01))

    # Top barre
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
    core.image.paste(icon1, (0 * icon_width, -0), mask=icon1)
    if menu_context_flag != "local_stream" and not is_renderer_active():
        core.image.paste(icon2, (1 * (icon_width + spacing_icon), -0), mask=icon2)
        core.image.paste(icon3, (2 * (icon_width + spacing_icon), -0), mask=icon3)
        core.image.paste(icon4, (3 * (icon_width + spacing_icon), -0), mask=icon4)
        core.image.paste(icon5, (4 * (icon_width + spacing_icon), -0), mask=icon5)
        core.image.paste(icon6, (5 * (icon_width + spacing_icon), -0), mask=icon6)
    icon7_x = core.width - icon_width - padding_x
    core.image.paste(icon7, (icon7_x, -0), mask=icon7)

    # Stop state
    if state == "stop" and not is_renderer_active():
        clock_text = global_state["clock"]
        bbox = font_stop_clock.getbbox(clock_text)  # (x0, y0, x1, y1)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = (core.width - text_w) // 2
        y = (core.height - text_h) // 2 - bbox[1]

        core.draw.text((x, y), clock_text, font=font_stop_clock, fill=core.COLOR_STOP_CLOCK)

        # Volume barre
        bottom_bar_h = font_vol_clock.getbbox("Vol: 100")[3] + 0  # height + padding
        y_bottom = core.height - bottom_bar_h - padding_y

        core.draw.text((3, y_bottom), f"Vol: {volume}", font=font_vol_clock, fill=core.COLOR_VOL_CLOCK)
    else:
        # compute text height reliably from font bbox
        bbox = font_artist.getbbox("Ay")  # (x0, y0, x1, y1)
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
                mode = "RGB" if core.display_format != "MONO" else "1"
                img = core.Image.new(mode, (text_width, text_h), core.COLOR_BG)
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

            # If the text is larger than display, do scrolling logic (unchanged)
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
                    # paste the pre-rendered image at the scrolled X position
                    core.image.paste(render_img, (-scroll_state["offset"], y))

            else:
                # fits: center it by pasting the cached image
                x = (display_width - text_width) // 2
                core.image.paste(render_img, (x, y))

        if core.height <= 96:
            spacing = 3
            top_bar_h = icon_width + 4
        elif core.height <= 128:
            spacing = 3 if show_spectrum else 10
            top_bar_h = icon_width + 4 if show_spectrum else icon_width + 10
        elif core.height <= 160:
            spacing = 8 if show_spectrum else 16
            top_bar_h = icon_width + 9 if show_spectrum else icon_width + 16
        elif core.height == 170 and core.width == 320:
            spacing = 4 if show_spectrum else 12
            top_bar_h = icon_width + 5 if show_spectrum else icon_width + 12
        else:
            spacing = 12 if show_spectrum else 24
            top_bar_h = icon_width + 13 if show_spectrum else icon_width + 24

        # --- Artist / Album ---
        y_artist = top_bar_h
        draw_scrolling(artist_album, scroll_artist, y_artist, core.COLOR_ARTIST)

        # --- Title ---
        y_title = y_artist + text_h + spacing
        draw_scrolling(title, scroll_title, y_title, core.COLOR_TRACK_TITLE)

        # --- Extra Infos ---
        y_extra_info = y_title + text_h + spacing
        if core.height > 64 and show_extra_infos:
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
                core.draw.text((x_extra_info, y_extra_info), extra_info, font=font_extra_info, fill=core.COLOR_EXTRA_INFO)
                y_progress = y_extra_info + extra_info_h + spacing
            else:
                y_progress = y_extra_info
        else:
            y_progress = y_extra_info

        elapsed = float(global_state.get("elapsed", 0.0))
        duration = float(global_state.get("duration", 0.0))
        # --- Progress Bar ---
        if core.height > 64 and show_progress_barre:
            progress_h = 2
            progress_w = int(core.width - (padding_x * 2))
            progress_x = (core.width - progress_w) // 2
            ratio = elapsed / duration if duration > 0 else 0
            fill_w = int(progress_w * ratio)
            # Background barre
            core.draw.rectangle((progress_x, y_progress + 2, progress_x + progress_w, y_progress + 2 + progress_h),
                                outline=core.COLOR_PROGRESS_BG, fill=core.COLOR_PROGRESS_BG)
            # Progress fill
            if fill_w > 0:
                core.draw.rectangle((progress_x, y_progress + 2, progress_x + fill_w, y_progress + 2 + progress_h),
                                    outline=core.COLOR_PROGRESS, fill=core.COLOR_PROGRESS)
            y_spectrum = y_progress + progress_h + spacing
        else:
            y_spectrum = y_progress

        # --- Bottom bar (Volume / Clock) ---
        bottom_bar_h = font_vol_clock.getbbox("Vol: 100")[3] + (padding_y if core.height > 64 else 0)
        y_bottom = core.height - bottom_bar_h - (padding_y if core.height > 64 else 0)

        # --- Spectre dynamique ---
        if core.height >= 128 and show_spectrum and spectrum:
            levels = spectrum.get_levels()
            available_height = max(0, y_bottom - y_spectrum - spacing)
            #spectrum_h = min(int(40 * core.scale), available_height)
            spectrum_h = available_height
            draw_spectrum(y_top=y_spectrum, height=spectrum_h, levels=levels)

        # --- Volume / Clock ---
        core.draw.text((padding_x, y_bottom), f"Vol: {volume}", font=font_vol_clock, fill=core.COLOR_VOL_CLOCK)
        if show_clock:
            clock_text = global_state["clock"]
        else:
            elapsed_str = format_time(elapsed)
            duration_str = format_time(duration)
            if menu_context_flag == "radio":
                clock_text = f"{elapsed_str}"
            else:
                clock_text = f"{elapsed_str}/{duration_str}"
        clock_w = core.draw.textlength(clock_text, font=font_vol_clock)
        core.draw.text((core.width - clock_w - padding_x, y_bottom), clock_text, font=font_vol_clock, fill=core.COLOR_VOL_CLOCK)

def nav_left_short():
    if menu_context_flag == "local_stream":
        previous_stream(manual_skip=True)
        return
    if now_playing_mode:
        subprocess.run(["mpc", "prev"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

def nav_right_short():
    if menu_context_flag == "local_stream":
        next_stream(manual_skip=True)
        return
    if now_playing_mode:
        subprocess.run(["mpc", "next"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

def nav_up():
    if now_playing_mode:
        subprocess.run(["mpc", "volume", "+1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

def nav_down():
    if now_playing_mode:
        subprocess.run(["mpc", "volume", "-1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

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
            "power_menu_active", "renderers_menu_active", "bluetooth_menu_active",
            "bluetooth_scan_menu_active", "bluetooth_paired_menu_active",
            "bluetooth_audioout_menu_active", "bluetooth_device_actions_menu_active", "playback_modes_menu_active"
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
    if menu_context_flag == "local_stream":
        return
    else:
        remove_from_queue()

def nav_info():
    global help_active, help_lines, help_selection
    help_base_path = OLIPIMOODE_DIR / f"help_texts/help_ui_playing_{core.LANGUAGE}.txt"
    if not help_base_path.exists():
        help_base_path = OLIPIMOODE_DIR / "help_texts/help_ui_playing_en.txt"
    context = "nowplaying_mode" if now_playing_mode else "menu"
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
    new_clock = not show_clock
    core.save_config("show_clock", new_clock, section="nowplaying")
    core.show_message(core.t("info_clock_on") if new_clock else core.t("info_clock_off"))
    time.sleep(1)
    os.execv(sys.executable, ['python3'] + sys.argv)

def nav_back():
    core.show_message(core.t("info_go_library_screen"))
    time.sleep(1)
    subprocess.call(["sudo", "systemctl", "start", "olipi-ui-browser.service"])
    subprocess.call(["sudo", "systemctl", "stop", "olipi-ui-playing.service"])
    sys.exit(0)

def nav_back_long():
    core.show_message(core.t("info_go_playlist_screen"))
    time.sleep(1)
    subprocess.call(["sudo", "systemctl", "start", "olipi-ui-queue.service"])
    subprocess.call(["sudo", "systemctl", "stop", "olipi-ui-playing.service"])
    sys.exit(0)


def finish_press(key):
    global menu_active, menu_selection, songlog_active, songlog_selection, songlog_action_active, songlog_action_selection
    global power_menu_active, power_menu_selection, playback_modes_menu_active, playback_modes_selection
    global stream_queue_active, stream_queue_selection, stream_queue_action_active, stream_queue_action_selection
    global stream_queue_pos, stream_manual_skip, stream_transition_in_progress
    global tool_menu_selection, tool_menu_active, config_menu_active, config_menu_selection, sleep_timeout_options, theme_menu_active, theme_menu_selection
    global help_active, help_selection, hardware_info_active, hardware_info_selection, language_menu_active, language_menu_selection
    global confirm_box_active, confirm_box_selection, confirm_box_callback, renderers_menu_active, renderers_menu_selection
    global bluetooth_menu_active, bluetooth_menu_selection, bluetooth_scan_menu_active, bluetooth_scan_menu_selection
    global bluetooth_audioout_menu_active, bluetooth_audioout_menu_selection
    global bluetooth_paired_menu_active, bluetooth_paired_menu_selection, bluetooth_device_actions_menu_active, bluetooth_device_actions_menu_selection
    global blocking_render, screen_on, idle_timer, is_sleeping, last_wake_time

    data = debounce_data.get(key)

    if data is None:
        return
    final_code = data.get("max_code", 0)
    if core.DEBUG:
        print(f"End pressure {key} with final code {final_code}.")

    idle_timer = time.time()

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
        elif key in USED_MEDIA_KEYS:
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

    if time.time() - last_wake_time < 2:
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
        if key == "KEY_LEFT":
            nav_left_long()
        elif key == "KEY_OK":
            nav_ok_long()
        elif key == "KEY_BACK":
            nav_back_long()
        elif key == "KEY_RIGHT":
            nav_right_long()
        elif key == "KEY_INFO":
            nav_info_long()
        elif key == "KEY_POWER":
            core.show_message(core.t("info_poweroff"))
            subprocess.run(["mpc", "stop"])
            subprocess.run(["sudo", "systemctl", "stop", "nginx"])
            subprocess.run(["sudo", "poweroff"])
        elif handle_audio_keys(key, final_code):
            return
        elif handle_custom_key(key, final_code):
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
            elif option_id == "show_stream_queue":
                menu_active = False
                stream_queue_active = True
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
                subprocess.call(["mpc", "stop"])
                subprocess.call(["sudo", "systemctl", "stop", "nginx"])
                subprocess.call(["sudo", "poweroff"])
            elif option_id == "reboot":
                core.show_message(core.t("info_reboot"))
                subprocess.call(["mpc", "stop"])
                subprocess.call(["sudo", "systemctl", "stop", "nginx"])
                subprocess.call(["sudo", "reboot"])
            elif option_id == "reload_screen":
                core.show_message(core.t("info_reload_screen"))
                subprocess.call(["sudo", "systemctl", "restart", "olipi-ui-playing.service"])
                sys.exit(0)
            elif option_id == "restart_mpd":
                core.show_message(core.t("info_restart_mpd"))
                subprocess.call(["sudo", "systemctl", "restart", "mpd"])
            core.reset_scroll("menu_item", "menu_title")
        return

    if stream_queue_active:
        if key == "KEY_UP":
            stream_queue_selection = (stream_queue_selection - 1) % len(stream_queue_lines)
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN":
            stream_queue_selection = (stream_queue_selection + 1) % len(stream_queue_lines)
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            stream_queue_active = False
            menu_active = True
            core.reset_scroll("menu_item", "menu_title")
        elif key == "KEY_OK":
            stream_queue_active = False
            stream_queue_action_active = True
            stream_queue_action_selection = 0
            core.reset_scroll("menu_item", "menu_title")
        return

    if stream_queue_action_active:
        if key == "KEY_UP":
            stream_queue_action_selection = (stream_queue_action_selection - 1) % len(stream_queue_action_options)
            core.reset_scroll("menu_item")
            return
        elif key == "KEY_DOWN":
            stream_queue_action_selection = (stream_queue_action_selection + 1) % len(stream_queue_action_options)
            core.reset_scroll("menu_item")
            return
        elif key == "KEY_LEFT":
            stream_queue_action_active = False
            stream_queue_active = True
            core.reset_scroll("menu_item", "menu_title")
            return
        elif key == "KEY_OK":
            selected_action = stream_queue_action_options[stream_queue_action_selection]["id"]
            if selected_action == "play_stream_queue_pos":
                stream_queue_action_active = False
                if core.DEBUG:
                    print(f"▶️ Play from queue at position {stream_queue_selection}")
                stream_manual_skip = True
                stream_transition_in_progress = True
                stream_queue_pos = stream_queue_selection
                yt_search_track(stream_queue_pos, preload=False)
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
                subprocess.call(["sudo", "php", str(OLIPIMOODE_DIR / f"renderer-toggle.php"), renderer, action])
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
                subprocess.call(["sudo", "php", str(OLIPIMOODE_DIR / "renderer-toggle.php"), "bluetooth", action])
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
                toggle_audio_output("Bluetooth")
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
                ensure_local_stream()
                if not has_internet_connection():
                    core.show_message(core.t("info_no_internet"))
                    return
                stream_queue.clear()
                yt_search_track(songlog_selection)
            elif option_id == "queue_yt_songlog":
                songlog_action_active = False
                ensure_local_stream()
                if not has_internet_connection():
                    core.show_message(core.t("info_no_internet"))
                    return
                stream_queue.clear()
                play_all_songlog_from_queue()
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
            if option_id == "sleep":
                idx = sleep_timeout_options.index(core.SCREEN_TIMEOUT)
                idx = (idx + 1) % len(sleep_timeout_options)
                core.SCREEN_TIMEOUT = sleep_timeout_options[idx]
                core.save_config("screen_timeout", core.SCREEN_TIMEOUT, section="settings")
            elif option_id == "language":
                config_menu_active = False
                language_menu_active = True
                language_menu_selection = 0
            elif option_id == "theme":
                config_menu_active = False
                theme_menu_active = True
                theme_menu_selection = 0
            elif option_id == "debug":
                config_menu_active = False
                new_debug = not core.DEBUG
                core.save_config("debug", new_debug, section="settings")
                core.show_message(core.t("info_debug_on") if new_debug else core.t("info_debug_off"))
                time.sleep(1)
                os.execv(sys.executable, ['python3'] + sys.argv)
            elif option_id == "spectrum":
                if not is_spectrum_available():
                    core.show_message(core.t("error_spectrum"))
                    time.sleep(1)
                    return
                config_menu_active = False
                new_spectrum = not show_spectrum
                core.save_config("show_spectrum", new_spectrum, section="nowplaying")
                core.show_message(core.t("info_spectrum_on") if new_spectrum else core.t("info_spectrum_off"))
                time.sleep(1)
                os.execv(sys.executable, ['python3'] + sys.argv)
            core.reset_scroll("menu_item", "menu_title")
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
            tool_menu_active = True
            core.reset_scroll("menu_item")
        elif key == "KEY_OK":
            language_menu_active = False
            core.LANGUAGE = language_menu_options[language_menu_selection]["id"]
            core.save_config("language", core.LANGUAGE, section="settings")
            core.show_message(core.t("info_language_set", selected=language_menu_options[language_menu_selection]["label"]))
            time.sleep(1)
            os.execv(sys.executable, ['python3'] + sys.argv)
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
            os.execv(sys.executable, ['python3'] + sys.argv)  # restart to apply theme
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
        elif key == "KEY_POWER":
            core.show_message(core.t("info_reboot"))
            subprocess.run(["mpc", "stop"])
            subprocess.run(["sudo", "systemctl", "stop", "nginx"])
            subprocess.run(["sudo", "reboot"])
        elif handle_audio_keys(key, final_code, menu_context_flag):
            return
        elif handle_custom_key(key, final_code, menu_context_flag):
            return
        else:
            if core.DEBUG:
                print(f"key {key} not used in this script")

    debounce_data.pop(key, None)

core.start_message_updater()

start_inputs(core.config, finish_press, msg_hook=core.show_message)
set_custom_hooks(core.show_message, next_stream, previous_stream, set_stream_manual_stop)

def main():
    global previous_blocking_render, idle_timer
    threading.Thread(target=player_status_thread, daemon=True).start()
    threading.Thread(target=mixer_status_thread, daemon=True).start()
    threading.Thread(target=options_status_thread, daemon=True).start()
    threading.Thread(target=non_idle_status_thread, daemon=True).start()
    if core.height >= 128 and show_spectrum:
        threading.Thread(target=lambda: (time.sleep(0.5), delayed_spectrum_start()), daemon=True).start()
    try:
        while True:
            if previous_blocking_render != blocking_render:
                idle_timer = time.time()
            previous_blocking_render = blocking_render
            if core.SCREEN_TIMEOUT > 0 and time.time() - idle_timer > core.SCREEN_TIMEOUT:
                if not is_sleeping and not blocking_render:
                    run_sleep_loop()
            elif screen_on:
                run_active_loop()
            time.sleep(0.1 if is_sleeping else core.REFRESH_INTERVAL)
    except KeyboardInterrupt:
        if core.DEBUG:
            print("Closing")

if __name__ == '__main__':
    main()
