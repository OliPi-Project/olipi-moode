#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2025 OliPi Project (Benoit Toufflet)

import subprocess
import requests
import time
import dis
import re

# Injectable global dependencies (via set_hooks)
show_message = None
next_stream = None
previous_stream = None
set_stream_manual_stop = None

def set_hooks(show_fn, next_fn=None, prev_fn=None, stop_flag_fn=None):
    global show_message, next_stream, previous_stream, set_stream_manual_stop
    show_message = show_fn
    next_stream = next_fn
    previous_stream = prev_fn
    set_stream_manual_stop = stop_flag_fn


def handle_audio_keys(key, final_code, menu_context_flag=""):
    if key in ("KEY_PLAY", "KEY_PAUSE"):
        if final_code >= 8:
            show_message("info_poweroff")
            if menu_context_flag == "local_stream" and set_stream_manual_stop:
                set_stream_manual_stop(manual_stop=True)
            subprocess.run("mpc stop && sudo systemctl stop nginx && sudo poweroff", shell=True, check=True)
        else:
            subprocess.run(["mpc", "toggle"], check=True)
        return True
    elif key == "KEY_STOP":
        if menu_context_flag == "local_stream" and set_stream_manual_stop:
            set_stream_manual_stop(manual_stop=True)
        subprocess.run(["mpc", "stop"], check=True)
        return True
    elif key == "KEY_NEXT":
        if menu_context_flag == "local_stream" and next_stream:
            next_stream(manual_skip=True)
            return True
        if final_code >= 4:
            subprocess.run(["mpc", "seek", "+00:00:10"], check=True)
        else:
            subprocess.run(["mpc", "next"], check=True)
        return True
    elif key == "KEY_PREVIOUS":
        if menu_context_flag == "local_stream" and previous_stream:
            previous_stream(manual_skip=True)
            return True
        if final_code >= 4:
            subprocess.run(["mpc", "seek", "-00:00:10"], check=True)
        else:
            subprocess.run(["mpc", "prev"], check=True)
        return True
    elif key == "KEY_FORWARD":
        if menu_context_flag == "local_stream":
            return True
        subprocess.run(["mpc", "seek", "+00:00:10"], check=True)
        return True
    elif key == "KEY_REWIND":
        if menu_context_flag == "local_stream":
            return True
        subprocess.run(["mpc", "seek", "-00:00:10"], check=True)
        return True
    elif key == "KEY_VOLUMEUP":
        try:
            requests.get("http://127.0.0.1/command/?cmd=set_volume+up+2")
        except requests.RequestException:
            pass
        return True
    elif key == "KEY_VOLUMEDOWN":
        try:
            requests.get("http://127.0.0.1/command/?cmd=set_volume+dn+2")
        except requests.RequestException:
            pass
        return True
    elif key == "KEY_MUTE":
        try:
            requests.get("http://127.0.0.1/command/?cmd=set_volume+mute")
        except requests.RequestException:
            pass
        return True
    return False


def handle_custom_key(key, final_code, menu_context_flag=""):

    if final_code >= 4: #long press
        if key == "KEY_YOURKEYLONG1":
            #yourcommande.here
            #before mpc stop/clear use this lines bellow:
            #if menu_context_flag == "local_stream" and set_stream_manual_stop:
            #    set_stream_manual_stop(manual_stop=True)
            #show_message("Your Message") #you can delete this line if not needed
            return True
        if key == "KEY_YOURKEYLONG2":
            #yourcommande.here
            #before mpc stop/clear use this lines bellow:
            #if menu_context_flag == "local_stream" and set_stream_manual_stop:
            #    set_stream_manual_stop(manual_stop=True)
            #show_message("Your Message") #you can delete this line if not needed
            return True
        return False

    if key == "KEY_YOURKEYSHORT1": #short press from now
        #yourcommande.here
        #before mpc stop/clear use this lines bellow:
        #if menu_context_flag == "local_stream" and set_stream_manual_stop:
        #    set_stream_manual_stop(manual_stop=True)
        #show_message("Your Message") #you can delete this line if not needed
        return True
    elif key == "KEY_YOURKEYSHORT2":
        #yourcommande.here
        #before mpc stop/clear use this lines bellow:
        #if menu_context_flag == "local_stream" and set_stream_manual_stop:
        #    set_stream_manual_stop(manual_stop=True)
        #show_message("Your Message") #you can delete this line if not needed
        return True
    elif key == "KEY_RED":
        if menu_context_flag == "local_stream" and set_stream_manual_stop:
            set_stream_manual_stop(manual_stop=True)
        subprocess.run("mpc stop; mpc clear", shell=True, check=True)
        time.sleep(1)
        subprocess.run("mpc load Favorites; mpc play", shell=True, check=True)
        show_message("Reading Favorites")
        return True
    elif key == "KEY_BLUE":
        if menu_context_flag == "local_stream" and set_stream_manual_stop:
            set_stream_manual_stop(manual_stop=True)
        subprocess.run("mpc stop; mpc clear", shell=True, check=True)
        time.sleep(1)
        subprocess.run("mpc load 'Default Playlist'; mpc play", shell=True, check=True)
        show_message("Reading Default Playlist")
        return True
    return False

def extract_used_keys():
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

USED_MEDIA_KEYS = extract_used_keys()
