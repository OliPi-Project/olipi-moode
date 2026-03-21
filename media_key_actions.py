#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2025 OliPi Project

import subprocess
import time
import re

# --- Globals / injectable hooks ---
config = None
show_message = None
next_stream = None
previous_stream = None
set_stream_manual_stop = None

# --- Volume memory ---
_last_volume = None

# --- Shortcuts loaded from .ini ---
shortcuts = {}

# ------------------------
# Hooks injection
# ------------------------
def set_hooks(cfg, show_fn, next_fn=None, prev_fn=None, stop_flag_fn=None):
    global config, show_message, next_stream, previous_stream, set_stream_manual_stop
    config = cfg
    show_message = show_fn
    next_stream = next_fn
    previous_stream = prev_fn
    set_stream_manual_stop = stop_flag_fn
    load_shortcuts()

# ------------------------
# Load shortcuts from config
# ------------------------
def load_shortcuts():
    global shortcuts
    shortcuts = {}
    if config and config.has_section("library_shortcuts"):
        shortcuts = dict(config["library_shortcuts"])

def execute_shortcut(action, menu_context_flag=""):
    try:
        typ, value = action.split(":", 1)
    except ValueError:
        return False

    if menu_context_flag == "local_stream" and set_stream_manual_stop:
        set_stream_manual_stop(manual_stop=True)

    if typ == "playlist":
        subprocess.run(["mpc", "clear"], check=False)
        subprocess.run(["mpc", "load", value], check=False)
        subprocess.run(["mpc", "play"], check=False)
    elif typ in ("folder", "file"):
        subprocess.run(["mpc", "clear"], check=False)
        subprocess.run(["mpc", "add", value], check=False)
        subprocess.run(["mpc", "play"], check=False)
    else:
        return False

    if show_message:
        # affiche juste le nom du fichier ou dossier sans le chemin complet
        show_message(f"▶ {value.split('/')[-1]}")
    return True

# ------------------------
# Handle standard audio keys
# ------------------------
def handle_audio_keys(key, final_code, menu_context_flag=""):
    global _last_volume

    if key in ("KEY_PLAY", "KEY_PAUSE"):
        if final_code >= 8:
            if show_message: show_message("Shutting down...")
            if menu_context_flag == "local_stream" and set_stream_manual_stop:
                set_stream_manual_stop(manual_stop=True)
            subprocess.run("mpc stop && sudo systemctl stop nginx && sudo poweroff", shell=True, check=True)
        else:
            subprocess.run(["mpc", "toggle"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True

    elif key == "KEY_STOP":
        if menu_context_flag == "local_stream" and set_stream_manual_stop:
            set_stream_manual_stop(manual_stop=True)
        subprocess.run(["mpc", "stop"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True

    elif key == "KEY_NEXT":
        if menu_context_flag == "local_stream" and next_stream:
            next_stream(manual_skip=True)
            return True
        if final_code >= 4:
            subprocess.run(["mpc", "seek", "+00:00:10"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.run(["mpc", "next"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True

    elif key == "KEY_PREVIOUS":
        if menu_context_flag == "local_stream" and previous_stream:
            previous_stream(manual_skip=True)
            return True
        if final_code >= 4:
            subprocess.run(["mpc", "seek", "-00:00:10"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.run(["mpc", "prev"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True

    elif key == "KEY_VOLUMEUP":
        subprocess.run(["mpc", "volume", "+1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True

    elif key == "KEY_VOLUMEDOWN":
        subprocess.run(["mpc", "volume", "-1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True

    elif key == "KEY_MUTE":
        result = subprocess.run(["mpc", "status"], capture_output=True, text=True)
        m = re.search(r"volume:\s*(\d+)%", result.stdout)
        if m:
            current_vol = int(m.group(1))
            if current_vol > 0:
                _last_volume = current_vol
                subprocess.run(["mpc", "volume", "0"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                restore_vol = _last_volume if _last_volume is not None else 3
                subprocess.run(["mpc", "volume", str(restore_vol)])
        else:
            subprocess.run(["mpc", "volume", "1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True

    return False

# ------------------------
# Handle custom keys (shortcuts)
# ------------------------
def handle_custom_key(key, final_code, menu_context_flag=""):
    # --- Dynamic shortcuts first ---
    if key in shortcuts:
        return execute_shortcut(shortcuts[key], menu_context_flag)

    # --- Hardcoded keys example ---
    if key == "KEY_TESTKEY":
        if menu_context_flag == "local_stream" and set_stream_manual_stop:
            set_stream_manual_stop(manual_stop=True)
        subprocess.run("mpc stop; mpc clear", shell=True)
        time.sleep(1)
        subprocess.run("mpc load Favorites; mpc play", shell=True)
        if show_message: show_message("Reading Favorites")
        return True

    return False

# ------------------------
# Gather all recognized keys
# ------------------------
def get_used_keys():
    keys = set()
    if config and config.has_section("library_shortcuts"):
        keys.update(config["library_shortcuts"].keys())
    return keys

USED_MEDIA_KEYS = get_used_keys()
