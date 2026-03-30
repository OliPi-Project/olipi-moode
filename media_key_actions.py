#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2025 OliPi Project

import subprocess
import time
import re
import dis

# --- Globals / injectable hooks ---
t = None
config = None
show_message = None
next_stream = None
previous_stream = None
set_stream_manual_stop = None

# --- Shortcuts loaded from .ini ---
shortcuts = {}

# ------------------------
# Hooks injection
# ------------------------
def set_hooks(trsl, cfg, show_fn, next_fn=None, prev_fn=None, stop_flag_fn=None):
    global t, config, show_message, next_stream, previous_stream, set_stream_manual_stop
    t = trsl
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
    for section in ("shortcuts", "other_shortcuts"):
        if config and config.has_section(section):
            for k, v in config[section].items():
                shortcuts[k.upper()] = v.strip()

RESERVED_KEYS = {
    "KEY_UP", "KEY_DOWN", "KEY_LEFT", "KEY_RIGHT",
    "KEY_OK", "KEY_BACK", "KEY_INFO",
    "KEY_CHANNELUP", "KEY_CHANNELDOWN", "KEY_PLAY",
    "KEY_STOP", "KEY_NEXT", "KEY_PREVIOUS",
    "KEY_FORWARD", "KEY_REWIND", "KEY_VOLUMEUP",
    "KEY_VOLUMEDOWN", "KEY_MUTE", "KEY_POWER"
}

def is_key_reserved(key):
    return key in RESERVED_KEYS

def is_key_used(key):
    return key in shortcuts

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
        time.sleep(0.5)
        subprocess.run(["mpc", "play"], check=False)
        show_message(f"▶ {value.split('/')[-1]}")
    elif typ in ("folder", "file"):
        subprocess.run(["mpc", "clear"], check=False)
        subprocess.run(["mpc", "add", value], check=False)
        time.sleep(0.5)
        subprocess.run(["mpc", "play"], check=False)
        show_message(f"▶ {value.split('/')[-1]}")
     
    elif typ in ("parametric", "graphic"):
        try:
            cmd = ["sudo", "/var/www/util/eqctl.php", typ, "set", value]
            subprocess.run(cmd, timeout=5)
            show_message(f"{value} applied")
        except Exception as e:
            show_message(f"EQ set error: {e}")
    
    elif typ == "playback":
        subprocess.run(["mpc", value], check=False)

    else:
        return False

    return True

# ------------------------
# Handle standard audio keys
# ------------------------
def handle_audio_keys(key, final_code, menu_context_flag=""):
    
    if key in ("KEY_PLAY", "KEY_PAUSE"):
        if final_code >= 10:
            show_message(t("info_reboot"))
            if menu_context_flag == "local_stream" and set_stream_manual_stop:
                set_stream_manual_stop(manual_stop=True)
            subprocess.run("sudo moodeutl --reboot", shell=True, check=True)
        else:
            subprocess.run(["mpc", "toggle"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True

    elif key == "KEY_STOP":
        if menu_context_flag == "local_stream" and set_stream_manual_stop:
            set_stream_manual_stop(manual_stop=True)
        if final_code >= 10:
            show_message(t("info_poweroff"))
            subprocess.run("sudo moodeutl --shutdown", shell=True, check=True)
        else:
            subprocess.run(["mpc", "stop"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True

    elif key == "KEY_NEXT":
        if menu_context_flag == "local_stream" and next_stream:
            next_stream(manual_skip=True)
            return True
        if final_code >= 8:
            subprocess.run(["mpc", "seek", "+00:00:30"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif final_code >= 4:
            subprocess.run(["mpc", "seek", "+00:00:10"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.run(["mpc", "next"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True

    elif key == "KEY_PREVIOUS":
        if menu_context_flag == "local_stream" and previous_stream:
            previous_stream(manual_skip=True)
            return True
        elif final_code >= 8:
            subprocess.run(["mpc", "seek", "-00:00:30"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif final_code >= 4:
            subprocess.run(["mpc", "seek", "-00:00:10"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.run(["mpc", "prev"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    
    elif key == "KEY_FORWARD":
        if final_code >= 8:
            subprocess.run(["mpc", "seek", "+00:01:00"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif final_code >= 4:
            subprocess.run(["mpc", "seek", "+00:00:30"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.run(["mpc", "seek", "+00:00:10"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    
    elif key == "KEY_REWIND":
        if final_code >= 8:
            subprocess.run(["mpc", "seek", "-00:01:00"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif final_code >= 4:
            subprocess.run(["mpc", "seek", "-00:00:30"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.run(["mpc", "seek", "-00:00:10"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True

    elif key == "KEY_VOLUMEUP":
        if final_code >= 6:
            subprocess.run(["/var/www/util/vol.sh", "-up", "5"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.run(["/var/www/util/vol.sh", "-up", "1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True

    elif key == "KEY_VOLUMEDOWN":
        if final_code >= 6:
            subprocess.run(["/var/www/util/vol.sh", "-dn", "5"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.run(["/var/www/util/vol.sh", "-dn", "1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True

    elif key == "KEY_MUTE":
        subprocess.run(["/var/www/util/vol.sh", "-mute"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    
    elif key == "KEY_POWER":
        if final_code >= 10:
            show_message(t("info_reboot"))
            subprocess.run(["sudo", "moodeutl", "--reboot"])
        else:
            show_message(t("info_poweroff"))
            subprocess.run(["sudo", "moodeutl", "--shutdown"])
        return True

    return False

# ------------------------
# Handle custom keys (shortcuts)
# ------------------------
def handle_custom_key(key, final_code, menu_context_flag=""):
    # --- Dynamic shortcuts ---
    if key in shortcuts:
        return execute_shortcut(shortcuts[key], menu_context_flag)

    # --- Hardcoded keys example ---
    if key == "KEY_TESTKEY":
        if menu_context_flag == "local_stream" and set_stream_manual_stop:
            set_stream_manual_stop(manual_stop=True)
        subprocess.run("mpc stop; mpc clear", shell=True)
        time.sleep(1)
        subprocess.run("mpc load Favorites; mpc play", shell=True)
        return True

    return False

# ------------------------
# Gather all recognized keys
# ------------------------
def extract_hardcoded_keys():
    keys = set()
    for func in (handle_audio_keys, handle_custom_key):
        for instr in dis.get_instructions(func):
            if instr.opname == "LOAD_CONST":
                val = instr.argval
                if isinstance(val, str) and re.match(r"^KEY_[A-Z0-9_]+$", val):
                    keys.add(val)
                elif isinstance(val, tuple):
                    for item in val:
                        if isinstance(item, str) and re.match(r"^KEY_[A-Z0-9_]+$", item):
                            keys.add(item)
    return keys

def get_used_keys():
    keys = set()
    keys.update(extract_hardcoded_keys())
    for section in ("shortcuts", "other_shortcuts"):
        if config and config.has_section(section):
            keys.update(k.upper() for k in config[section].keys())
    return keys

USED_MEDIA_KEYS = get_used_keys()
