#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2025 OliPi Project

import os
import sys
import time
import re
import subprocess
import configparser
import string
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from mpd import MPDClient
from pathlib import Path

OLIPIMOODE_DIR = Path(__file__).resolve().parent
os.environ.setdefault("OLIPI_DIR", str(OLIPIMOODE_DIR))

from olipi_core import core_common as core
from olipi_core.input_manager import start_inputs, debounce_data, process_key

font_title = core.get_font("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 10)
font_item = core.get_font("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 11)
font_search_input = core.get_font("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 12)
font_search_info = core.get_font("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 10)

core.load_translations(Path(__file__).stem)

idle_timer = time.time()
last_wake_time = 0
screen_on = True
is_sleeping = False
blocking_render = False
previous_blocking_render = False

launch_from_artist_override = False

SCROLL_SPEED_LIBRARY = 0.03
SCROLL_SPEED_TITLE_LIBRARY = 0.05
SCROLL_TITLE_LIB_PADDING_END = 20

library_items = []
library_selection = 0
nav_stack = []
current_path = "/"

selected_items = []
multi_selection = False

menu_active = False
menu_selection = 0
menu_options = [
    {"id": "add_queue", "label": core.t("menu_add_queue")},
    {"id": "add_play", "label": core.t("menu_add_play")},
    {"id": "clear_play", "label": core.t("menu_clear_play")},
    {"id": "copy_to", "label": core.t("menu_copy_to")},
    {"id": "delete", "label": core.t("menu_delete")}
]
menu_multi_selection_options = [
    {"id": "add_queue", "label": core.t("menu_add_queue")},
    {"id": "add_play", "label": core.t("menu_add_play")},
    {"id": "clear_play", "label": core.t("menu_clear_play")},
    {"id": "deselect_all", "label": core.t("menu_deselect_all")},
    {"id": "copy_to", "label": core.t("menu_copy_selected_to")}
]

copy_mode_active = False
copy_source_items = []

copy_action_menu_active = False
copy_action_menu_selection = 0
copy_confirm_target = ""
copy_action_menu_options = [
    {"id": "copy", "label": core.t("menu_action_copy")},
    {"id": "move", "label": core.t("menu_action_move")},
    {"id": "cancel", "label": core.t("menu_action_cancel")}
]

FORBIDDEN_TARGET_FOLDERS = ("USB", "RADIO", "Playlists")

confirm_Box_active = False
confirm_Box_active_selection = 0
confirm_Box_options = [
    {"id": "yes", "label": core.t("menu_confirm_yes")},
    {"id": "no", "label": core.t("menu_confirm_no")}
]
confirm_Box_title = "Confirm?"
confirm_Box_callback = None

tool_menu_active = False
tool_menu_selection = 0
tool_menu_all_options = [
    {"id": "sort", "label": core.t("menu_tool_sort_options")},
    {"id": "update", "label": core.t("menu_tool_update_library")},
    {"id": "rescan", "label": core.t("menu_tool_rescan_library")},
    {"id": "search", "label": core.t("menu_tool_search")}
]
tool_menu_copy_options = [
    {"id": "sort", "label": core.t("menu_tool_sort_options")},
    {"id": "update", "label": core.t("menu_tool_update_library")},
    {"id": "rescan", "label": core.t("menu_tool_rescan_library")}
]
tool_menu_base_options = [
    {"id": "update", "label": core.t("menu_tool_update_library")},
    {"id": "rescan", "label": core.t("menu_tool_rescan_library")},
    {"id": "search", "label": core.t("menu_tool_search")}
]
tool_menu_search_results_options = [
    {"id": "save", "label": core.t("menu_tool_save_search")},
    {"id": "modify_terms", "label": core.t("menu_tool_modify_search_terms")},
    {"id": "modify_by", "label": core.t("menu_tool_modify_search_by")},
    {"id": "previous", "label": core.t("menu_tool_previous_search")}
]

search_results_active = False

menu_search_screen_active = False
menu_search_screen_selection = 0
menu_search_screen_options = [
    {"id": "search_by", "label": core.t("menu_search_by")},
    {"id": "erase_search", "label": core.t("menu_erase_search")},
    {"id": "previous_search", "label": core.t("menu_previous_search")}
]

grouping_mode_from_tool_active = False
grouping_mode_active = False
grouping_mode_selection = 0
grouping_mode_options = [
    {"id": "Titles", "label": core.t("menu_group_titles")},
    {"id": "Albums", "label": core.t("menu_group_albums")},
    {"id": "Artists", "label": core.t("menu_group_artists")},
    {"id": "Genres", "label": core.t("menu_group_genres")}
]
selected_grouping_mode = "Titles"

previous_search_options = []
previous_search_menu_active = False
previous_search_menu_selection = 0

search_mode = False
search_input = ""
search_cursor = 0
valid_chars = string.ascii_lowercase + '-' + string.digits + " '"
accent_variants = {
    "a": ["a", "à", "â", "ä"],
    "e": ["e", "é", "è", "ê", "ë"],
    "i": ["i", "î", "ï"],
    "o": ["o", "ô", "ö"],
    "u": ["u", "ù", "û", "ü"],
    "c": ["c", "ç"],
}

mpd_results_cache = []
radio_results_cache = []
radio_virtual_folder = []
artist_virtual_folder = {}
album_virtual_folder = {}

search_input_last = None
grouping_mode_last = None

sort_menu_active = False
sort_menu_selection = 0
sort_mode = "name"
sort_menu_options = [
    {"id": "name", "label": core.t("menu_sort_by_name")},
    {"id": "date", "label": core.t("menu_sort_by_date")},
    {"id": "release", "label": core.t("menu_sort_by_release")}
]

release_year_labels = {}
display_labels = {}

help_active = False
help_lines = []
help_selection = 0

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

def build_radio_url_to_title1_map(pls_directory="/var/lib/mpd/music/RADIO"):
    url_to_title = {}
    for filename in os.listdir(pls_directory):
        if filename.lower().endswith(".pls"):
            full_path = os.path.join(pls_directory, filename)
            config = configparser.ConfigParser()
            try:
                config.read(full_path)
                url = config.get("playlist", "File1", fallback="").strip()
                title = config.get("playlist", "Title1", fallback="").strip()
                if url and title:
                    url_to_title[url] = title
            except Exception as e:
                if core.DEBUG:
                    print(f"Reading error {filename} : {e}")
    return url_to_title

def update_library(path="/"):
    global blocking_render

    blocking_render = True
    core.message_permanent = True

    try:
        client = MPDClient()
        client.timeout = 60
        client.connect("localhost", 6600)
        print(f"→ Triggering client.update() for path: {path}")
        client.update(path)

        frames = ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"]
        i = 0
        while True:
            status = client.status()
            if "updating_db" not in status:
                print("✅ Update completed")
                break
            core.message_text = f"{core.t('info_update_progress')} {frames[i % len(frames)]}"
            render_screen()
            time.sleep(0.3)
            i += 1

        core.message_permanent = False
        update_items(current_path)
        core.show_message(core.t("info_update_completed"))

    except Exception as e:
        core.message_permanent = False
        blocking_render = False
        core.show_message(core.t("info_update_failed"))
        if core.DEBUG:
            print(f"Error in update_library({path}): {e}")

    finally:
        try:
            client.close()
            client.disconnect()
        except:
            pass
        blocking_render = False
        print("→ End of update_library()")

def rescan_library():
    global blocking_render
    blocking_render = True
    core.message_permanent = True
    try:
        client = MPDClient()
        client.timeout = 60
        client.connect("localhost", 6600)
        print("→ Lancement client.rescan()")
        client.rescan()
        frames = ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"]
        i = 0
        while True:
            status = client.status()
            if "updating_db" not in status:
                print("✅ Rescan completed")
                break
            core.message_text = f"{core.t('info_rescan_progress')} {frames[i % len(frames)]}"
            render_screen()
            time.sleep(0.3)
            i += 1
        core.message_permanent = False
        update_items("/")
        core.show_message(core.t("info_rescan_completed"))
    except Exception as e:
        core.message_permanent = False
        blocking_render = False
        core.show_message(core.t("info_rescan_failed"))
        if core.DEBUG:
         print("Error rescan_library:", e)
    finally:
        client.close()
        client.disconnect()
        blocking_render = False
        print("→ End of rescan_library()")

def confirm_copy(destination_path, move=False):
    global copy_mode_active, copy_source_items, blocking_render

    def abs_src_path(rel):
        return os.path.join("/var/lib/mpd/music", rel)

    # ─── 1. Initial Destination Validation ──────────────────────
    if (
        destination_path in FORBIDDEN_TARGET_FOLDERS
        or "::" in destination_path
        or destination_path.startswith("Search:")
        or destination_path.startswith("Artist:")
        or ".." in destination_path
        or not destination_path.strip()
    ):
        core.show_message(core.t("info_invalid_destination"))
        time.sleep(1)
        render_screen()
        return

    dst_abs = os.path.join("/var/lib/mpd/music", destination_path)

    # ─── 2. Pre-validation of the elements to be copied ─────────────────────────
    candidates = []

    for typ, val in copy_source_items:
        if typ == "D" and "/" not in val:
            print(f"Blocked action on root-level folder: {val}")
            core.show_message(core.t("info_action_blocked_folder"))
            time.sleep(1)
            continue
        if (
            val == "Playlists" or val == "RADIO"
            or val.startswith("Playlists/")
            or val.startswith("RADIO/")
        ):
            print(f"Blocked: copy from protected or virtual folder: {val}")
            core.show_message(core.t("info_copy_blocked_folder"))
            time.sleep(1)
            continue
        src_abs = abs_src_path(val)
        if not src_abs or not os.path.exists(src_abs):
            print(f"Source not found or already moved: {src_abs}")
            core.show_message(core.t("info_source_not_found"))
            time.sleep(1)
            continue

        dst_final = os.path.join(dst_abs, os.path.basename(src_abs))

        try:
            real_src = os.path.realpath(src_abs)
            real_dst = os.path.realpath(dst_final)
            common = os.path.commonpath([real_src, real_dst])
            if common in (real_src, real_dst):
                print(f"Blocked: source and destination overlap → src: {real_src}, dst: {real_dst}")
                core.show_message(core.t("info_overlap_blocked"))
                time.sleep(1)
                continue
        except Exception as e:
            core.show_message(core.t("info_path_check_error"))
            if core.DEBUG:
                print(f"Error checking path overlap: {e}")
            time.sleep(1)
            continue

        candidates.append((typ, val, src_abs, dst_final))

    if not candidates:
        core.show_message(core.t("info_nothing_to_copy"))
        time.sleep(1)
        render_screen()
        return

    # ─── 3. Display banner "in progress" ────────────────────────────
    core.message_permanent = True
    blocking_render = True
    core.message_text = core.t("info_move_progress") if move else core.t("info_copy_progress")
    render_screen()

    action_done = False

    try:
        if not os.path.exists(dst_abs):
            subprocess.run(["sudo", "mkdir", "-p", dst_abs], check=True)

        for typ, val, src_abs, dst_final in candidates:
            cmd = ["sudo", "mv", src_abs, dst_final] if move else ["sudo", "cp"]
            if not move:
                if os.path.isdir(src_abs):
                    cmd += ["-r", src_abs, dst_final]
                else:
                    cmd += [src_abs, dst_final]

            print(f"[sudo {'mv' if move else 'cp'}] {src_abs} -> {dst_final}")
            subprocess.run(cmd, check=True)
            action_done = True

        # ─── 4. Ending Message ───────────────────────────────
        core.message_permanent = False
        blocking_render = False
        core.show_message(core.t("info_move_done") if move else core.t("info_copy_done"))
        time.sleep(1)

        # ─── 5. UPDATE MPD ────────────────────────────────────
        update_library(destination_path)
        if move:
            updated = set()
            for typ, val, _, _ in candidates:
                base = val.split("/", 1)[0]
                if base not in updated:
                    print(f"Updating MPD for source root: {base}")
                    update_library(base)
                    updated.add(base)

    except Exception as e:
        core.show_message(core.t("info_operation_failed"))
        if core.DEBUG:
            print(f"Error in confirm_copy(): {e}")

    finally:
        if action_done:
            copy_source_items.clear()
            copy_mode_active = False

def confirm_delete():
    global delete_pending_item, blocking_render

    if not delete_pending_item:
        core.show_message(core.t("info_nothing_to_delete"))
        return

    typ, val = delete_pending_item
    abs_path = os.path.join("/var/lib/mpd/music", val)

    # ─── 1. Initial Checks ─────────────────────────────────
    if current_path == "/" and typ == "D" and "/" not in val:
        print(f"Blocked deletion of root-level folder: {val}")
        core.show_message(core.t("info_delete_blocked_root").format(val=val))
        return
    if (
        val == "Playlists" or val == "RADIO"
        or val.startswith("Playlists/")
        or val.startswith("RADIO/")
    ):
        print(f"Blocked: deletion from protected or virtual folder: {val}")
        core.show_message(core.t("info_delete_blocked_root").format(val=val))
        return
    if not abs_path.startswith("/var/lib/mpd/music/"):
        print(f"Unauthorized path for deletion: {abs_path}")
        core.show_message(core.t("info_delete_blocked_folder"))
        return
    if not os.path.exists(abs_path):
        print(f"Path not found: {abs_path}")
        core.show_message(core.t("info_file_notfound"))
        update_items(current_path)
        return

    # ─── 2. Banner display during deletion ──────────────
    core.message_permanent = True
    blocking_render = True
    core.message_text = core.t("info_deleting")
    render_screen()

    action_done = False

    try:
        if os.path.isdir(abs_path):
            print(f"[sudo rm -r] {abs_path}")
            subprocess.run(["sudo", "rm", "-r", abs_path], check=True)
        else:
            print(f"[sudo rm] {abs_path}")
            subprocess.run(["sudo", "rm", abs_path], check=True)

        action_done = True

    except Exception as e:
        core.message_permanent = False
        blocking_render = False
        core.show_message(core.t("info_delete_failed"))
        delete_pending_item = None
        if core.DEBUG:
            print(f"Error deleting {abs_path}: {e}")
        return

    # ─── 3. Complete deletion successful + MPD update ──────────────
    if action_done:
        core.message_permanent = False
        blocking_render = False
        core.show_message(core.t("info_deleted"))
        time.sleep(1)

        base = val.split("/", 1)[0]
        print(f"Updating MPD for root: {base}")
        update_library(base)
        delete_pending_item = None

def parse_playlist_file(name):
    global display_labels
    items = []
    display_labels.clear()
    try:
        client = MPDClient()
        client.timeout = 10
        client.connect("localhost", 6600)
        songs = client.listplaylistinfo(name)
        radio_titles = build_radio_url_to_title1_map()
        client.close()
        client.disconnect()
        for item in songs:
            file_str = item.get("file", "").strip()
            artist = item.get("artist", "").strip()
            title = item.get("title", "").strip()
            if file_str.lower().startswith("http"):
                station = radio_titles.get(file_str, "").strip()
                display = station or file_str
            else:
                if artist and title:
                    display = f"{artist} - {title}"
                else:
                    display = title or os.path.basename(file_str)
            if display.strip() and display != ";":
                items.append(("F", file_str))
                display_labels[file_str] = display
    except Exception as e:
        items = [("F", "Error")]
        display_labels["Error"] = core.t("show_error_read_playlist")
        if core.DEBUG:
            print(f"Error read playlist : {e}")
    return items

def save_search_to_file():
    global search_input_last, grouping_mode_last
    if not search_input_last or not grouping_mode_last:
        core.show_message(core.t("info_no_search_to_save"))
        return
    new_entry = f"{grouping_mode_last}|{search_input_last}".strip()
    try:
        history_path = OLIPIMOODE_DIR / "search_history.txt"
        lines = []
        if os.path.exists(history_path):
            with open(history_path, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
        if lines and lines[-1] == new_entry:
            core.show_message(core.t("info_already_saved"))
            return
        with open(history_path, "a", encoding="utf-8") as f:
            f.write(new_entry + "\n")
        core.show_message(core.t("info_search_saved"))
    except Exception as e:
        core.show_message(core.t("error_save_search"))
        if core.DEBUG:
            print(f"Error saving search : {e}")

def delete_search_history_entry(index):
    filepath = OLIPIMOODE_DIR / "search_history.txt"
    try:
        with open(filepath, "r") as f:
            lines = f.read().splitlines()
        if 0 <= index < len(lines):
            del lines[index]
            with open(filepath, "w") as f:
                f.write("\n".join(lines) + "\n")
            core.show_message(core.t("info_search_removed"))
    except Exception as e:
        core.show_message(core.t("error_search_removed"))
        if core.DEBUG:
            print(f"Error deleting history: {e}")

def load_previous_searches():
    try:
        with open(OLIPIMOODE_DIR / "search_history.txt", "r", encoding="utf-8") as f:
            return [line.strip() for line in f if "|" in line]
    except Exception as e:
        core.show_message(core.t("error_read_saved_search"))
        if core.DEBUG:
            print(f"Error reading history: {e}")
        return []

def get_search_tag(grouping_mode):
    if grouping_mode == "Titles":
        return "title"
    elif grouping_mode == "Albums":
        return "album"
    elif grouping_mode == "Artists":
        return "artist"
    elif grouping_mode == "Genres":
        return "genre"
    else:
        return "any"

def format_track_label(song, context=None):
    path = song["file"]
    ext = os.path.splitext(path)[-1]
    artist = song.get("artist") or "Unknown Artist"
    title = song.get("title", "")
    album = song.get("album", "")
    track_raw = song.get("track", "")
    track_str = track_raw[0] if isinstance(track_raw, list) else track_raw
    track = str(track_str).split("/")[0].strip()
    if context == "album_folder":
        prefix = f"{track} " if track else ""
        return f"{prefix}{title}{ext}" if title else os.path.basename(path)
    elif context == "artist_folder":
        label = f"♩ {title}{ext}" if title else os.path.basename(path)
        if album:
            label += f" ({album})"
        return label
    else:
        if artist and title:
            label = f"♩ {title} - {artist}{ext}"
            if album:
                label += f" ({album})"
            return label
        else:
            return os.path.basename(path)

def group_search_results(mpdsongs, mode):
    global artist_virtual_folder, album_virtual_folder
    library = []
    display_labels.clear()
    artist_virtual_folder.clear()
    album_virtual_folder.clear()

    def normalize(value):
        if isinstance(value, list):
            return ", ".join(v for v in value if isinstance(v, str)).strip()
        return str(value).strip()

    if mode == "Titles":
        for song in mpdsongs:
            if "file" not in song:
                continue
            path = normalize(song.get("file"))
            display_labels[path] = format_track_label(song)
            library.append(("F", path))
        library.sort(key=lambda item: natural_key(display_labels.get(item[1], "")))

    elif mode in ("Albums", "Artists"):
        albums = defaultdict(list)
        singles = []

        for song in mpdsongs:
            if "file" not in song:
                continue
            path = normalize(song.get("file"))
            album = normalize(song.get("album"))
            albumartist = normalize(song.get("albumartist"))
            artist_field = normalize(song.get("artist"))
            if mode == "Artists":
                if albumartist.lower() == "various artists":
                    artist = artist_field or "Unknown Artist"
                else:
                    artist = albumartist or artist_field or "Unknown Artist"
            else:
                artist = albumartist or artist_field or "Unknown Artist"
            if album:
                key = (album, artist)
                albums[key].append(song)
            else:
                display_labels[path] = format_track_label(song)
                singles.append(("F", path))

        for (album, artist), songs in albums.items():
            if len(songs) == 1:
                song = songs[0]
                path = normalize(song.get("file"))
                display_labels[path] = format_track_label(song)
                singles.append(("F", path))
            else:
                virtual_album_path = f"Album::{album} - {artist}"
                display_labels[virtual_album_path] = f"{album} - {artist}"
                library.append(("D", virtual_album_path))
                album_virtual_folder[virtual_album_path] = []
                for s in sorted(songs, key=lambda s: natural_key(normalize(s.get("track", "")))):
                    path = normalize(s.get("file"))
                    display_labels[path] = format_track_label(s, context="album_folder")
                    album_virtual_folder[virtual_album_path].append(("F", path))

        singles.sort(key=lambda item: natural_key(display_labels.get(item[1], "")))
        library.extend(singles)

    elif mode == "Genres":
        groups = defaultdict(list)
        singles = []

        for song in mpdsongs:
            if "file" not in song:
                continue
            artist = normalize(song.get("albumartist")) or normalize(song.get("artist")) or "Unknown Artist"
            groups[artist].append(song)

        for artist_name, songs in groups.items():
            if len(songs) == 1:
                s = songs[0]
                path = normalize(s.get("file"))
                display_labels[path] = format_track_label(s)
                singles.append(("F", path))
            else:
                virtual_artist_path = f"Artist::{artist_name}"
                display_labels[virtual_artist_path] = artist_name
                library.append(("D", virtual_artist_path))
                artist_virtual_folder[virtual_artist_path] = []
                for s in sorted(songs, key=lambda s: natural_key(normalize(s.get("title", "")))):
                    path = normalize(s.get("file"))
                    display_labels[path] = format_track_label(s, context="artist_folder")
                    artist_virtual_folder[virtual_artist_path].append(("F", path))

        singles.sort(key=lambda item: natural_key(display_labels.get(item[1], "")))
        library.extend(singles)

    else:
        library.sort(key=lambda item: natural_key(display_labels.get(item[1], "")))
    return library

def search_radio_titles(query):
    results = []
    base_path = "/var/lib/mpd/music/RADIO"
    try:
        for fname in os.listdir(base_path):
            if not fname.lower().endswith(".pls"):
                continue
            if query.lower() in fname.lower():
                results.append(("P", f"RADIO/{fname}"))
    except Exception as e:
        core.show_message(core.t("error_read_radios"))
        if core.DEBUG:
            print(f"Radio reading error: {e}")
    return results

def run_mpd_search(input_text, grouping_mode):
    global mpd_results_cache, radio_results_cache, search_input_last, grouping_mode_last
    global radio_virtual_folder, display_labels
    global library_items, current_path, nav_stack, library_selection
    global search_input, selected_grouping_mode, search_results_active, search_mode, search_cursor

    try:
        client = MPDClient()
        client.timeout = 10
        client.connect("localhost", 6600)

        if input_text == search_input_last and grouping_mode == grouping_mode_last:
            results = mpd_results_cache
            radio_matches = radio_results_cache
        else:
            tag = get_search_tag(grouping_mode)
            results = client.search(tag, input_text)
            radio_matches = search_radio_titles(input_text)
            mpd_results_cache = results
            radio_results_cache = radio_matches
            search_input_last = input_text
            grouping_mode_last = grouping_mode

        client.close()
        client.disconnect()

        if not results and not radio_matches:
            search_mode = True
            search_results_active = False
            search_input = input_text
            selected_grouping_mode = grouping_mode
            search_cursor = max(0, len(search_input) - 1)
            core.show_message(core.t("info_no_match_found"))
            return False

        display_labels.clear()

        library_items = group_search_results(results, grouping_mode)

        if radio_matches:
            library_items.insert(0, ("D", "Radios"))
            radio_folder_content = []
            for typ, val in radio_matches:
                label = val.split("/")[-1].removesuffix(".pls")
                display_labels[val] = label
                radio_folder_content.append((typ, val))
            radio_virtual_folder = radio_folder_content
        else:
            radio_virtual_folder = []

        current_path = f"Search: {input_text} ({grouping_mode})"
        search_results_active = True
        nav_stack.clear()
        library_selection = 0
        return True

    except Exception as e:
        search_mode = True
        search_results_active = False
        search_input = input_text
        selected_grouping_mode = grouping_mode
        search_cursor = max(0, len(search_input) - 1)
        core.show_message(core.t('info_search_failed'))
        if core.DEBUG:
            print(f"Search error: {e}")
        return False

def natural_key(string):
    return [int(s) if s.isdigit() else s.lower() for s in re.split(r'(\d+)', string)]

def extract_release_year(entry):
    for tag in ("originalyear", "originaldate", "date"):
        value = entry.get(tag)
        if value:
            try:
                return int(value[:4])
            except ValueError:
                continue
    return 0

def get_moode_folders(path="/"):
    global sort_mode, release_year_labels, display_labels, sort_allowed
    client = MPDClient()
    client.timeout = 10
    client.idletimeout = None
    sort_allowed = True
    try:
        client.connect("localhost", 6600)

        if path == "/":
            sort_allowed = False
            info = client.lsinfo("/")
            items_ls = [("D", e["directory"]) for e in info if "directory" in e]
            items_ls += [("F", e["file"]) for e in info if "file" in e]
            items_ls = sorted(items_ls, key=lambda x: natural_key(x[1]))

            virtual = [("D", "Playlists")]
            existing_dirs = {val for (typ, val) in items_ls if typ == "D"}
            if "RADIO" not in existing_dirs and os.path.isdir("/var/lib/mpd/music/RADIO"):
                virtual.append(("D", "RADIO"))

            return virtual + items_ls

        elif path == "Playlists":
            sort_allowed = False
            pl_data = client.listplaylists()
            return sorted(
                [("P", pl["playlist"]) for pl in pl_data if "playlist" in pl],
                key=lambda x: x[1].lower()
            )

        elif path == "RADIO":
            sort_allowed = False
            base_path = os.path.join("/var/lib/mpd/music", path)
            items = []
            try:
                for entry in os.listdir(base_path):
                    if entry.lower().endswith(".pls"):
                        full_path = os.path.join(path, entry)
                        items.append(("P", full_path))
                return sorted(items, key=lambda x: x[1].lower())
            except Exception as e:
                core.show_message(core.t("error_read_folder_radio"))
                if core.DEBUG:
                    print(f"RADIO folder read error: {e}")
                return []

        else:
            sort_allowed = True
            info = client.lsinfo(path)
            out = []
            display_labels.clear()

            for entry in info:
                if "directory" in entry:
                    out.append(("D", entry["directory"]))
                elif "file" in entry:
                    out.append(("F", entry["file"]))
                elif "playlist" in entry:
                    out.append(("P", entry["playlist"]))

            if sort_mode == "name":
                return sorted(out, key=lambda x: natural_key(x[1]))

            elif sort_mode == "date":
                def get_mtime(item):
                    try:
                        rel_path = item[1]
                        return os.path.getmtime(f"/var/lib/mpd/music/{rel_path}")
                    except Exception:
                        return 0
                return sorted(out, key=get_mtime, reverse=True)

            elif sort_mode == "release":
                release_year_labels.clear()
                dated = []
                for typ, val in out:
                    if typ == "D":
                        try:
                            sub_info = client.lsinfo(val)
                            file_entry = next((e for e in sub_info if "file" in e), None)
                            if file_entry:
                                year = extract_release_year(file_entry)
                                release_year_labels[val] = year
                            else:
                                year = 0
                        except Exception as e:
                            core.show_message(core.t("error_reading_folder"))
                            if core.DEBUG:
                                print(f"Folder reading error {val}: {e}")
                            year = 0
                        dated.append(((year, val.lower()), (typ, val)))
                    else:
                        dated.append(((0, val.lower()), (typ, val)))
                return [item for _, item in sorted(dated, reverse=True)]

            else:
                return out

    except Exception as e:
        core.show_message(core.t("error_reading_folder"))
        if core.DEBUG:
            print("Error retrieving lsinfo:", e)
        return []
    finally:
        client.close()
        client.disconnect()

def update_items(path="/", sel=0):
    global current_path, library_items, library_selection
    current_path = path
    library_items = get_moode_folders(path)
    library_selection = sel

def render_screen():
    if core.message_text:
        core.draw_message()
    elif help_active:
        draw_help_screen()
    elif copy_action_menu_active:
        draw_copy_action_menu()
    elif confirm_Box_active:
        draw_confirm_Box()
    elif grouping_mode_active:
        draw_search_field_menu()
    elif previous_search_menu_active:
        draw_previous_search_menu()
    elif menu_search_screen_active:
        draw_menu_search_screen()
    elif search_mode:
        draw_search_screen()
    elif sort_menu_active:
        draw_sort_menu()
    elif tool_menu_active:
        draw_tool_menu()
    elif menu_active:
        draw_menu()
    else:
        draw_library()

    core.refresh()

def draw_menu():
    if multi_selection:
        core.draw_custom_menu([item["label"] for item in menu_multi_selection_options], menu_selection, title=core.t("title_play_selection"))
    else:
        core.draw_custom_menu([item["label"] for item in menu_options], menu_selection, title=core.t("title_play_item"))

def draw_tool_menu():
    core.draw_custom_menu([item["label"] for item in tool_menu_options], tool_menu_selection, title=core.t("title_menu_tool"))

def draw_menu_search_screen():
    core.draw_custom_menu([item["label"] for item in menu_search_screen_options], menu_search_screen_selection, title=core.t("title_search_options"))

def draw_search_field_menu():
    core.draw_custom_menu([item["label"] for item in grouping_mode_options], grouping_mode_selection, title=core.t("title_search_by"))

def draw_previous_search_menu():
    core.draw_custom_menu(previous_search_options, previous_search_menu_selection, title=core.t("title_previous_search"))

def draw_sort_menu():
    selected_label = next((entry["label"] for entry in sort_menu_options if entry["id"] == sort_mode), None)
    core.draw_custom_menu([item["label"] for item in sort_menu_options], sort_menu_selection, title=core.t("title_sort_options"), multi=[selected_label] if selected_label else None)

def draw_help_screen():
    core.draw_custom_menu(help_lines, help_selection, title=core.t("title_help"))

def draw_copy_action_menu():
    core.draw_custom_menu([item["label"] for item in copy_action_menu_options], copy_action_menu_selection, title=core.t("title_select_action"))

def draw_confirm_Box():
    core.draw_custom_menu([item["label"] for item in confirm_Box_options], confirm_Box_active_selection, title=confirm_Box_title)

def draw_search_screen():
    core.draw.rectangle((0, 0, core.width, core.height), fill=core.COLOR_BG)

    padding_x = max(1, int(core.width * 0.02))

    # --- Title → items spacing based on screen height ---
    if core.height <= 64:
        spacing_title_items = 2
        padding_y = 1
    else:
        spacing_title_items = 10
        padding_y = 6

    # ─── Title (Search) ─────
    title = core.t("title_search")
    title_width = core.draw.textlength(title, font=font_title)
    x_title = (core.width - title_width) // 2
    y_title = padding_y
    core.draw.text((x_title, y_title), title, font=font_title, fill=core.COLOR_TITLE)

    # ─── Input box ──────
    input_y = padding_y + font_title.getbbox("Ay")[3] + spacing_title_items
    input_padding_x = 4
    input_padding_y = 3
    input_h = font_search_input.getbbox("Ay")[3] - font_search_input.getbbox("Ay")[1] + 2 * input_padding_y
    input_bottom = input_y + input_h
    core.draw.rectangle((0, input_y, core.width, input_bottom), fill=core.COLOR_INPUT_BG)

    # ─── Calculation of horizontal scroll based on cursor position ──────
    text_before_cursor = search_input[:search_cursor]
    text_width_before_cursor = core.draw.textlength(text_before_cursor, font=font_search_input)
    full_text_width = core.draw.textlength(search_input, font=font_search_input)

    # Automatic scroll if cursor exceeds the visible display
    visible_width = core.width - 2 * input_padding_x
    scroll_offset = 0
    if text_width_before_cursor > visible_width:
        scroll_offset = text_width_before_cursor - visible_width + 10  # petit padding

    display_text = search_input
    core.draw.text((input_padding_x - scroll_offset, input_y + input_padding_y), display_text, font=font_search_input, fill=core.COLOR_INPUT_TEXT)

    # Visual cursor: actual position
    cursor_x = core.draw.textlength(search_input[:search_cursor], font=font_search_input) - scroll_offset + input_padding_x
    cursor_y = input_y + input_padding_y
    core.draw.line((cursor_x, cursor_y, cursor_x, cursor_y + font_search_input.getbbox("A")[3]), fill=core.COLOR_INPUT_CURSOR)

    # ─── Option info: field ────────────────
    info_centered = input_bottom + spacing_title_items
    info1 = f"{core.t('show_search_by')}: {selected_grouping_mode}"
    core.draw.text((padding_x, info_centered), info1, font=font_search_info, fill=core.COLOR_INPUT_INFO)

def draw_library():
    now = time.time()
    # -------------------------------
    # 1) Header string
    # -------------------------------
    if copy_mode_active:
        header = core.t("title_copy_mode")
    elif current_path == "/":
        header = core.t("title_library_root")
    else:
        header = current_path

    # -------------------------------
    # 2) Header cache (text only)
    # -------------------------------
    head_state = core.scroll_state.setdefault("library_header_cache", {})

    # compute width only once per change
    header_changed = head_state.get("text") != header
    if header_changed:
        head_state["text"] = header
        head_state["w"] = core.draw.textlength(header, font=font_title)
        head_state["bbox"] = font_title.getbbox("Ay")

    title_w = head_state["w"]
    title_h = head_state["bbox"][3] - head_state["bbox"][1]

    # -------------------------------
    # 3) Background full clear
    # -------------------------------
    core.draw.rectangle((0, 0, core.width, core.height), fill=core.COLOR_BG)

    # -------------------------------
    # 4) Header linear scroll (unchanged)
    # -------------------------------
    padding_x = max(1, int(core.width * 0.02))
    padding_y = max(1, int(core.height * 0.01))
    inner_w = core.width - 2 * padding_x

    state_t = core.scroll_state.setdefault("library_title", {"offset": 0, "last_update": now})

    if title_w > inner_w and now - state_t["last_update"] > SCROLL_SPEED_TITLE_LIBRARY:
        scroll_w = title_w + SCROLL_TITLE_LIB_PADDING_END
        state_t["offset"] = (state_t["offset"] + 1) % scroll_w
        state_t["last_update"] = now

    if title_w <= core.width:
        xh = (core.width - title_w) // 2
        core.draw.text((xh, 0), header, font=font_title, fill=core.COLOR_TITLE)
    else:
        off = state_t["offset"]
        core.draw.text((-off, 0), header, font=font_title, fill=core.COLOR_TITLE)
        core.draw.text((title_w + SCROLL_TITLE_LIB_PADDING_END - off, 0), header, font=font_title, fill=core.COLOR_TITLE)

    # -------------------------------
    # 5) Vertical layout
    # -------------------------------
    if core.height <= 64:
        spacing_title_items = 5
        padding_item = 1
    elif core.height < 128:
        spacing_title_items = 5
        padding_item = 1
    else:
        spacing_title_items = 6
        padding_item = 1

    item_bbox = font_item.getbbox("Aéy")
    item_h = item_bbox[3] - item_bbox[1]
    line_h = item_h + padding_item

    start_y = title_h + spacing_title_items
    max_lines = max(1, (core.height - start_y - padding_y) // line_h)
    visible_lines = min(len(library_items), max_lines)

    start_idx = max(0, library_selection - visible_lines // 2)
    if start_idx + visible_lines > len(library_items):
        start_idx = max(0, len(library_items) - visible_lines)

    # -------------------------------
    # 6) Item cache (BIG SPEEDUP)
    # -------------------------------
    item_cache = core.scroll_state.setdefault("library_item_cache", {})
    selected_scroll = core.scroll_state.setdefault(
        "library_selected_scroll",
        {"text": None, "offset": 0, "phase": "pause_start",
         "pause_start_time": now, "last_update": now}
    )

    for i in range(visible_lines):
        idx = start_idx + i
        y_item = start_y + i * line_h

        typ, val = library_items[idx]

        # label resolution
        if current_path == "RADIO":
            display = val.split("/")[-1].removesuffix(".pls")
        else:
            display = display_labels.get(val, val.split("/")[-1])

        if sort_mode == "release" and val in release_year_labels:
            display += f" – {release_year_labels[val]}"

        # Checkbox prefix
        is_selected = (typ, val) in selected_items
        prefix = "✓ " if is_selected else ""
        full_text = prefix + display

        # ---------------------------
        # Non-selected items -> CACHE
        # ---------------------------
        if idx != library_selection:
            cached = item_cache.get(full_text)

            if cached is None:
                # build cache image
                w = core.draw.textlength(full_text, font=font_item)
                img_w = max(1, int(w))
                img_h = item_h
                img_mode = "1" if core.display_format == "MONO" else "RGB"
                bg = core.COLOR_BG
                img = core.Image.new(img_mode, (img_w, img_h), bg)
                d = core.screen.ImageDraw.Draw(img)
                d.text((0, -item_bbox[1]), full_text, font=font_item, fill=core.COLOR_TEXT)
                cached = item_cache[full_text] = img

            # paste cached image
            core.screen.image.paste(cached, (padding_x, int(y_item)))

            continue

        # ---------------------------
        # Selected item -> SCROLLING
        # ---------------------------
        text_w = core.draw.textlength(full_text, font=font_item)
        avail = core.width - (padding_x + 2)

        # highlight line
        text_y = y_item + (line_h - item_h) // 2 - item_bbox[1]
        sel_top = text_y + item_bbox[1] - 2
        sel_bot = text_y + item_bbox[3]
        core.draw.rectangle((0, sel_top, core.width - 1, sel_bot), outline=core.COLOR_MENU_OUTLINE, fill=core.COLOR_MENU_SELECTED_BG)

        # scrolling logic
        st = selected_scroll
        if st["text"] != full_text:
            st["text"] = full_text
            st["offset"] = 0
            st["phase"] = "pause_start"
            st["pause_start_time"] = now

        if text_w > avail:
            BASE_INTERVAL = SCROLL_SPEED_LIBRARY
            MIN_INTERVAL, MAX_INTERVAL = 0.02, 0.14
            PAUSE_DURATION = 0.6
            BLANK_DURATION = 0.12

            ratio = text_w / float(avail)
            step = BASE_INTERVAL / max(0.001, ratio)
            speed = max(MIN_INTERVAL, min(MAX_INTERVAL, step))

            phase = st["phase"]

            if phase == "pause_start":
                st["offset"] = 0
                if now - st["pause_start_time"] > PAUSE_DURATION:
                    st["phase"] = "scrolling"
                    st["last_update"] = now

            elif phase == "scrolling":
                if now - st["last_update"] > speed:
                    st["offset"] += 1
                    st["last_update"] = now
                    if st["offset"] >= (text_w - avail):
                        st["phase"] = "pause_end"
                        st["pause_start_time"] = now

            elif phase == "pause_end":
                if now - st["pause_start_time"] >= PAUSE_DURATION:
                    st["offset"] = 0
                    st["phase"] = "pause_start"
                    st["pause_start_time"] = now

            off = st["offset"]
            x_text = padding_x - off
        else:
            st["offset"] = 0
            st["phase"] = "pause_start"
            x_text = padding_x

        core.draw.text((x_text, text_y), full_text, font=font_item, fill=core.COLOR_MENU_SELECTED_TEXT)

def handle_virtual_folder_action(index, val, client):
    if val == "Radios" and current_path.startswith("Search:"):
        for typ_r, val_r in radio_virtual_folder:
            if val_r.endswith(".pls"):
                if index in (0, 2):
                    client.load(val_r)
                elif index == 1:
                    client.load(val_r, "0:", 0)
        return True
    elif val in artist_virtual_folder:
        contents = artist_virtual_folder[val]
        if not contents:
            print(f"No content found for {val} in artist_virtual_folder")
            return True
        for typ_f, path in contents:
            if typ_f == "F":
                if index in (0, 2):
                    client.add(path)
                elif index == 1:
                    client.add(path, 0)
        return True
    elif val in album_virtual_folder:
        for typ_f, path in album_virtual_folder[val]:
            if typ_f == "F":
                if index in (0, 2):
                    client.add(path)
                elif index == 1:
                    client.add(path, 0)
        return True
    return False

def trigger_menu(index):
    global selected_items, multi_selection, copy_mode_active, copy_source_items
    global confirm_Box_active, confirm_Box_active_selection, delete_pending_item, confirm_Box_title, confirm_Box_callback
    if multi_selection and not selected_items:
        core.show_message(core.t("info_no_selection"))
        return
    items = selected_items if multi_selection else [library_items[library_selection]]
    client = MPDClient()
    client.timeout = 10
    try:
        client.connect("localhost", 6600)
        selected_id = (menu_multi_selection_options if multi_selection else menu_options)[index]["id"]

        if selected_id == "add_queue":
            for typ, val in items:
                if typ == "D" and handle_virtual_folder_action(index, val, client):
                    continue
                if typ == "D":
                    client.add(val)
                elif typ == "P":
                    client.load(val)
                elif typ == "F":
                    client.add(val)
            core.show_message(core.t("info_added_to_queue"))

        elif selected_id == "add_play":
            for typ, val in items:
                if typ == "D" and handle_virtual_folder_action(index, val, client):
                    continue
                if typ == "D":
                    client.add(val, 0)
                elif typ == "P":
                    client.load(val, "0:", 0)
                elif typ == "F":
                    client.add(val, 0)
            client.play(0)
            core.show_message(core.t("info_added_and_played"))

        elif selected_id == "clear_play":
            client.clear()
            for typ, val in items:
                if typ == "D" and handle_virtual_folder_action(index, val, client):
                    continue
                if typ == "D":
                    client.add(val)
                elif typ == "P":
                    client.load(val)
                elif typ == "F":
                    client.add(val)
            client.play()
            core.show_message(core.t("info_cleared_and_played"))

        elif selected_id == "deselect_all" and multi_selection:
            selected_items.clear()
            multi_selection = False
            core.show_message(core.t("info_selection_emptied"))

        elif selected_id == "copy_to":
            if multi_selection and not selected_items:
                core.show_message(core.t("info_no_selection"))
                return

            items = selected_items if multi_selection else [library_items[library_selection]]

            for typ, val in items:
                if typ == "D" and current_path == "/" and "/" not in val:
                    print(f"Blocked: copy from root-level folder: {val}")
                    core.show_message(core.t("info_copy_blocked_root").format(val=val))
                    return
                if current_path in ("Playlists", "RADIO"):
                    print(f"Blocked: attempted copy from virtual folder: {current_path}")
                    core.show_message(core.t("info_copy_blocked_folder"))
                    return
            copy_source_items = list(items)
            copy_mode_active = True
            core.show_message(core.t("info_copy_nav_target"))
            print(f"→ Trigger copy to folder : {len(items)} items")

        elif selected_id == "delete":
            if multi_selection:
                core.show_message(core.t("info_delete_blocked_multi"))
                return
            typ, val = library_items[library_selection]
            if typ == "D" and current_path == "/" and "/" not in val:
                print(f"Deletion not allowed for: {val}")
                core.show_message(core.t("info_delete_blocked_root").format(val=val))
                return
            if current_path == "Playlists" or current_path == "RADIO":
                print(f"Blocked: attempted delete in virtual folder: {current_path}/{val}")
                core.show_message(core.t("info_delete_blocked_folder"))
                return
            delete_pending_item = (typ, val)
            confirm_Box_title = f"Delete {os.path.basename(val)}?"
            confirm_Box_callback = confirm_delete
            confirm_Box_active = True
            confirm_Box_active_selection = 0
            return

    except Exception as e:
        core.show_message(core.t("info_action_error"))
        if core.DEBUG:
            print(f"Error MPD: {e}")
    finally:
        client.close()
        client.disconnect()
        if multi_selection and selected_id in ("add_queue", "add_play", "clear_play", "copy_to", "delete"):
            selected_items.clear()
            multi_selection = False

def nav_up():
    global menu_selection, library_selection
    if menu_active:
        if menu_selection > 0:
            menu_selection -= 1
    else:
        if library_selection > 0:
            library_selection -= 1

def nav_down():
    global menu_selection, library_selection
    if menu_active:
        if menu_selection < len(menu_options) - 1:
            menu_selection += 1
    else:
        if library_selection < len(library_items) - 1:
            library_selection += 1

def nav_ok():
    global menu_active, menu_selection
    if not library_items:
        return
    typ, val = library_items[library_selection]
    if typ == "D" and current_path == "/" and val in ("Playlists", "RADIO"):
            core.show_message(core.t("info_action_not_allowed_here"))
            return
    else:
        menu_active = True
        menu_selection = 0

def nav_ok_long():
    global tool_menu_active, tool_menu_selection, tool_menu_options
    global menu_search_screen_active, menu_search_screen_selection
    if any([menu_active, sort_menu_active, grouping_mode_active,
            confirm_Box_active, copy_action_menu_active, help_active]):
        return
    if search_mode:
        menu_search_screen_active = True
        menu_search_screen_selection = 0
    elif search_results_active:
        tool_menu_active = True
        tool_menu_selection = 0
        tool_menu_options = tool_menu_search_results_options
    elif copy_mode_active:
        tool_menu_active = True
        tool_menu_selection = 0
        tool_menu_options = tool_menu_copy_options
    else:
        tool_menu_active = True
        tool_menu_selection = 0
        tool_menu_options = tool_menu_all_options if sort_allowed else tool_menu_base_options

def nav_left_short():
    global current_path, library_items, library_selection, nav_stack
    global search_input_last, grouping_mode_last, search_mode, search_input, selected_grouping_mode, search_cursor, search_results_active
    global mpd_results_cache, radio_results_cache

    if not nav_stack:
        # Case: we are at the root of a search
        if search_results_active and current_path.startswith("Search:"):
            if multi_selection:
                core.show_message(core.t("error_cannot_modify_selection"))
                return
            search_mode = True
            search_input = search_input_last
            selected_grouping_mode = grouping_mode_last
            search_cursor = max(0, len(search_input) - 1)
            search_results_active = False
        return

    prev_path, prev_selection = nav_stack.pop()
    # If we return to a research context
    if prev_path.startswith("Search:"):
        if search_input_last and grouping_mode_last and mpd_results_cache:
            library_items = group_search_results(mpd_results_cache, grouping_mode_last)

            if radio_results_cache:
                library_items.insert(0, ("D", "Radios"))
                for typ, val in radio_results_cache:
                    label = val.split("/")[-1].removesuffix(".pls")
                    display_labels[val] = label

            current_path = prev_path
            library_selection = prev_selection
            search_results_active = True
            core.reset_scroll("library_items", "menu_title", "menu_item")
            return

    # If we return from a virtual folder Artist:: or Album::
    if prev_path.startswith("Artist::") or prev_path.startswith("Album::"):
        # virtual paths: we do not go through update_items()
        current_path = prev_path
        library_selection = prev_selection
        core.reset_scroll("library_items", "menu_title", "menu_item")
        return

    # Otherwise, real folder
    update_items(prev_path)
    current_path = prev_path
    library_selection = prev_selection
    search_results_active = False
    core.reset_scroll("library_items", "menu_title", "menu_item")

def nav_left_long():
    global menu_active, nav_stack, search_mode, search_results_active
    global copy_mode_active, copy_source_items, sort_menu_active, grouping_mode_active
    global menu_search_screen_active, confirm_Box_active, copy_action_menu_active
    global help_active, multi_selection, selected_items
    msg_shown = False
    if copy_mode_active or copy_action_menu_active:
        copy_mode_active = False
        copy_action_menu_active = False
        copy_source_items.clear()
        core.show_message(core.t("info_copy_cancelled"))
        msg_shown = True
        time.sleep(1)
    if confirm_Box_active:
        confirm_Box_active = False
        core.show_message(core.t("info_action_cancelled"))
        msg_shown = True
        time.sleep(1)
    nav_stack.clear()
    selected_items.clear()
    core.message_text = None
    menu_active = False
    search_mode = False
    search_results_active = False
    sort_menu_active = False
    grouping_mode_active = False
    menu_search_screen_active = False
    help_active = False
    multi_selection = False
    core.message_permanent = False
    if not msg_shown:
        core.show_message(core.t("info_back_home"))
        time.sleep(0.5)
    update_items("/")

def nav_right_short():
    global current_path, library_items, library_selection, nav_stack, display_labels
    if not library_items:
        return
    typ, val = library_items[library_selection]
    if search_results_active:
        if (typ, val) == ("D", "Radios"):
            nav_stack.append((current_path, library_selection))
            current_path = "Search: Radios"
            library_items = radio_virtual_folder
            library_selection = 0
            core.reset_scroll("library_items", "menu_title", "menu_item")
            return
        if typ == "D" and val in artist_virtual_folder:
            nav_stack.append((current_path, library_selection))
            current_path = val
            library_items = artist_virtual_folder[val]
            library_selection = 0
            core.reset_scroll("library_items", "menu_title", "menu_item")
            return
        if typ == "D" and val in album_virtual_folder:
            nav_stack.append((current_path, library_selection))
            current_path = val
            library_items = album_virtual_folder[val]
            library_selection = 0
            core.reset_scroll("library_items", "menu_title", "menu_item")
            return
        return

    if typ == "D":
        nav_stack.append((current_path, library_selection))
        update_items(val)
        current_path = val
        library_selection = 0
        core.reset_scroll("library_items", "menu_title", "menu_item")
        return

    if typ == "P":
        try:
            if current_path == "Playlists":
                new_items = parse_playlist_file(val)
            elif current_path == "RADIO":
                core.show_message(core.t("info_radio_no_content"))
                return
            else:
                new_items = []
            nav_stack.append((current_path, library_selection))
            library_items[:] = new_items
            library_selection = 0
        except Exception as e:
            core.show_message(core.t("error_reading_playlist_radio"))
            if core.DEBUG:
                print(f"Playlist/radio reading error: {e}")
        return

def nav_right_long():
    global search_input, search_cursor
    if search_mode:
        if 0 <= search_cursor < len(search_input):
            char = search_input[search_cursor].lower()
            for base, variants in accent_variants.items():
                if char in variants:
                    current_index = variants.index(char)
                    next_variant = variants[(current_index + 1) % len(variants)]
                    search_input = (
                        search_input[:search_cursor]
                        + next_variant
                        + search_input[search_cursor + 1:]
                    )
                    print(f"→ Accent switch: {char} -> {next_variant}")
                    break

def nav_channelup():
    global selected_items, library_selection, library_items, multi_selection, current_path
    if 0 <= library_selection < len(library_items):
        typ, val = library_items[library_selection]
        if typ == "D" and current_path == "/" and val in ("Playlists", "RADIO"):
            core.show_message(core.t("info_selection_not_allowed_here"))
            return
        if (typ, val) not in selected_items:
            selected_items.append((typ, val))
    multi_selection = len(selected_items) > 0

def nav_channeldown():
    global selected_items, library_selection, library_items, multi_selection
    if 0 <= library_selection < len(library_items):
        item = library_items[library_selection]
        if item in selected_items:
            selected_items.remove(item)
    multi_selection = len(selected_items) > 0

def nav_info():
    global help_active, help_lines, help_selection
    help_base_path = OLIPIMOODE_DIR / f"assets/help_texts/help_ui_browser_{core.LANGUAGE}.txt"
    if not help_base_path.exists():
        help_base_path = OLIPIMOODE_DIR / "assets/help_texts/help_ui_browser_en.txt"
    context = "library"

    if menu_active or tool_menu_active or sort_menu_active or grouping_mode_active or previous_search_menu_active or menu_search_screen_active or confirm_Box_active or copy_action_menu_active:
        context = "menu"
    elif search_results_active or current_path.startswith("Search:"):
        context = "search"
    elif search_mode:
        context = "search_screen"

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
            core.show_message(core.t("info_no_help_available"))

    except Exception as e:
        core.show_message(core.t("error_loading_help"))
        if core.DEBUG:
            print(f"Error loading help: {e}")

def nav_back():
    core.show_message(core.t("info_back_nowplaying"))
    time.sleep(1)
    subprocess.call(["sudo", "systemctl", "start", "olipi-ui-playing.service"])
    subprocess.call(["sudo", "systemctl", "stop", "olipi-ui-browser.service"])
    sys.exit(0)

def nav_back_long():
    core.show_message(core.t("info_back_queue"))
    time.sleep(1)
    subprocess.call(["sudo", "systemctl", "start", "olipi-ui-queue.service"])
    subprocess.call(["sudo", "systemctl", "stop", "olipi-ui-browser.service"])
    sys.exit(0)

def finish_press(key):
    global menu_active, menu_selection, library_items, library_selection, current_path
    global search_mode, search_cursor, search_input, search_input_last, menu_search_screen_active, menu_search_screen_selection
    global previous_search_menu_active, previous_search_menu_selection, previous_search_options
    global mpd_results_cache, radio_results_cache, grouping_mode_last, grouping_mode_active, grouping_mode_selection
    global selected_grouping_mode, grouping_mode_from_tool_active
    global tool_menu_options, tool_menu_selection, tool_menu_active, sort_menu_selection, sort_menu_active, sort_mode
    global help_active, help_selection, copy_mode_active, copy_source_items
    global confirm_Box_active, confirm_Box_active_selection, confirm_Box_callback
    global copy_action_menu_active, copy_action_menu_selection, copy_confirm_target
    global screen_on, idle_timer, is_sleeping, last_wake_time

    data = debounce_data.get(key)
    if data is None:
        return

    final_code = data.get("max_code", 0)
    if core.DEBUG:
        print(f"End pressure {key} with final code {final_code}.")

    idle_timer = time.time()

    if is_sleeping:
        screen_on = True
        core.poweron_safe()
        core.reset_scroll("menu_title", "menu_item")
        is_sleeping = False
        last_wake_time = time.time()
        if core.DEBUG:
            print(f"[DEBUG] Wake up on key '{key}' (action skipped)")
        return

    if time.time() - last_wake_time < 2:
        if core.DEBUG:
            print(f"[DEBUG] Input '{key}' ignored (within post-wake delay)")
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
        elif key == "KEY_POWER":
            core.show_message(core.t("info_poweroff"))
            subprocess.run(["mpc", "stop"])
            subprocess.run(["sudo", "systemctl", "stop", "nginx"])
            subprocess.run(["sudo", "poweroff"])
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

    if confirm_Box_active:
        if key == "KEY_UP" and confirm_Box_active_selection > 0:
            confirm_Box_active_selection -= 1
        elif key == "KEY_DOWN" and confirm_Box_active_selection < 1:
            confirm_Box_active_selection += 1
        elif key == "KEY_LEFT":
            confirm_Box_active = False
            core.show_message(core.t("info_action_cancel"))
        elif key == "KEY_OK":
            confirm_Box_active = False
            selected_id = confirm_Box_options[confirm_Box_active_selection]["id"]
            if selected_id == "yes" and confirm_Box_callback:
                confirm_Box_callback()
            else:
                core.show_message(core.t("info_action_cancel"))
        return

    if copy_action_menu_active:
        if key == "KEY_UP" and copy_action_menu_selection > 0:
            copy_action_menu_selection -= 1
        elif key == "KEY_DOWN" and copy_action_menu_selection < 2:
            copy_action_menu_selection += 1
        elif key == "KEY_LEFT":
            copy_action_menu_active = False
            core.show_message(core.t("info_action_cancel"))
        elif key == "KEY_OK":
            selected_id = copy_action_menu_options[copy_action_menu_selection]["id"]
            copy_action_menu_active = False
            if selected_id == "copy":
                confirm_copy(copy_confirm_target, move=False)
            elif selected_id == "move":
                confirm_copy(copy_confirm_target, move=True)
            else:
                core.show_message(core.t("info_action_cancel"))
        return

    if menu_active:
        active_menu = menu_multi_selection_options if multi_selection else menu_options
        if key == "KEY_UP" and menu_selection > 0:
            menu_selection -= 1
        elif key == "KEY_DOWN" and menu_selection < len(active_menu) - 1:
            menu_selection += 1
        elif key == "KEY_OK":
            trigger_menu(menu_selection)
            menu_active = False
        elif key == "KEY_LEFT":
            menu_active = False
        core.reset_scroll("menu_item")
        return

    if tool_menu_active:
        if key == "KEY_UP" and tool_menu_selection > 0:
            tool_menu_selection -= 1
        elif key == "KEY_DOWN" and tool_menu_selection < len(tool_menu_options) - 1:
            tool_menu_selection += 1
        elif key == "KEY_LEFT":
            tool_menu_active = False
        elif key == "KEY_OK":
            tool_menu_active = False
            selected_id = tool_menu_options[tool_menu_selection]["id"]
            if selected_id == "sort":
                sort_menu_active = True
                sort_menu_selection = 0
            elif selected_id == "update":
                update_library()
            elif selected_id == "rescan":
                rescan_library()
            elif selected_id == "search":
                search_mode = True
                search_cursor = 0
                search_input = ""
            elif selected_id == "save":
                save_search_to_file()
            elif selected_id == "modify_by":
                if multi_selection:
                    core.show_message(core.t("error_cannot_modify_selection"))
                    return
                grouping_mode_from_tool_active = True
                grouping_mode_active = True
                grouping_mode_selection = next((i for i, e in enumerate(grouping_mode_options) if e["id"] == (grouping_mode_last or "Titles")), 0)
            elif selected_id == "modify_terms":
                if multi_selection:
                    core.show_message(core.t("error_cannot_modify_selection"))
                    return
                search_input = search_input_last or ""
                selected_grouping_mode = grouping_mode_last or "Titles"
                search_cursor = max(0, len(search_input) - 1)
                search_mode = True
            elif selected_id == "previous":
                if multi_selection:
                    core.show_message(core.t("error_cannot_modify_selection"))
                    return
                previous_search_options[:] = load_previous_searches()
                if not previous_search_options:
                    core.show_message(core.t("info_no_previous_search"))
                else:
                    menu_search_screen_active = False
                    previous_search_menu_active = True
                    previous_search_menu_selection = 0
        core.reset_scroll("menu_item")
        return

    if menu_search_screen_active:
        if key == "KEY_UP" and menu_search_screen_selection > 0:
            menu_search_screen_selection -= 1
        elif key == "KEY_DOWN" and menu_search_screen_selection < len(menu_search_screen_options) - 1:
            menu_search_screen_selection += 1
        elif key == "KEY_LEFT":
            menu_search_screen_active = False
        elif key == "KEY_OK":
            selected_id = menu_search_screen_options[menu_search_screen_selection]["id"]
            menu_search_screen_active = False
            if selected_id == "search_by":
                grouping_mode_active = True
                grouping_mode_selection = next((i for i, e in enumerate(grouping_mode_options) if e["id"] == selected_grouping_mode), 0)
            elif selected_id == "erase_search":
                search_input = ""
                search_cursor = 0
            elif selected_id == "previous_search":
                previous_search_options[:] = load_previous_searches()
                if not previous_search_options:
                    core.show_message(core.t("info_no_previous_search"))
                else:
                    previous_search_menu_active = True
                    previous_search_menu_selection = 0
        core.reset_scroll("menu_item")
        return

    if previous_search_menu_active:
        if key == "KEY_UP" and previous_search_menu_selection > 0:
            previous_search_menu_selection -= 1
        elif key == "KEY_DOWN" and previous_search_menu_selection < len(previous_search_options) - 1:
            previous_search_menu_selection += 1
        elif key == "KEY_LEFT":
            previous_search_menu_active = False
        elif key == "KEY_CHANNELDOWN":
            delete_search_history_entry(previous_search_menu_selection)
            previous_search_options.pop(previous_search_menu_selection)
            if previous_search_menu_selection >= len(previous_search_options):
                previous_search_menu_selection = max(0, len(previous_search_options) - 1)
        elif key == "KEY_OK":
            selected = previous_search_options[previous_search_menu_selection]
            try:
                mode, value = selected.split("|", 1)
                success = run_mpd_search(value.strip(), mode.strip())
                previous_search_menu_active = False
                search_mode = not success
            except Exception as e:
                core.show_message(core.t("error_previous_search"))
                if core.DEBUG:
                    print(f"Error handling previous search: {e}")
                previous_search_menu_active = False
                search_mode = True
        core.reset_scroll("menu_item")
        return

    if grouping_mode_active:
        if key == "KEY_UP" and grouping_mode_selection > 0:
            grouping_mode_selection -= 1
        elif key == "KEY_DOWN" and grouping_mode_selection < len(grouping_mode_options) - 1:
            grouping_mode_selection += 1
        elif key == "KEY_LEFT":
            grouping_mode_active = False
        elif key == "KEY_OK":
            selected_grouping_mode = grouping_mode_options[grouping_mode_selection]["id"]
            grouping_mode_active = False
            if grouping_mode_from_tool_active:
                search_input = search_input_last or ""
                grouping_mode_from_tool_active = False
                run_mpd_search(search_input, selected_grouping_mode)
        core.reset_scroll("menu_item")
        return

    if sort_menu_active:
        if key == "KEY_UP" and sort_menu_selection > 0:
            sort_menu_selection -= 1
        elif key == "KEY_DOWN" and sort_menu_selection < len(sort_menu_options) - 1:
            sort_menu_selection += 1
        elif key == "KEY_LEFT":
            sort_menu_active = False
        elif key == "KEY_OK":
            selected_id = sort_menu_options[sort_menu_selection]["id"]
            sort_mode = selected_id
            core.show_message(core.t("info_sort_by_" + selected_id))
            sort_menu_active = False
            update_items(current_path, library_selection)
        core.reset_scroll("menu_item")
        return

    if search_mode:
        if key == "KEY_LEFT" and search_cursor > 0:
            search_cursor -= 1
        elif key == "KEY_RIGHT":
            if search_cursor < len(search_input) - 1:
                search_cursor += 1
            elif search_cursor == len(search_input) - 1:
                last_char = search_input[-1]
                if last_char == " ":
                    search_input += "a"
                else:
                    search_input += " "
                search_cursor += 1
        elif key == "KEY_UP":
            if not search_input:
                search_input = "1"
            elif search_input and 0 <= search_cursor < len(search_input):
                ch = search_input[search_cursor]
                if ch in valid_chars:
                    new_index = (valid_chars.index(ch) + 1) % len(valid_chars)
                    new_ch = valid_chars[new_index]
                    search_input = search_input[:search_cursor] + new_ch + search_input[search_cursor + 1:]
        elif key == "KEY_DOWN":
            if not search_input:
                search_input = "a"
            elif search_input and 0 <= search_cursor < len(search_input):
                ch = search_input[search_cursor]
                if ch in valid_chars:
                    new_index = (valid_chars.index(ch) - 1) % len(valid_chars)
                    new_ch = valid_chars[new_index]
                    search_input = search_input[:search_cursor] + new_ch + search_input[search_cursor + 1:]
        elif key == "KEY_CHANNELUP":
            search_input = search_input[:search_cursor] + " " + search_input[search_cursor:]
        elif key == "KEY_CHANNELDOWN":
            if 0 <= search_cursor < len(search_input):
                search_input = search_input[:search_cursor] + search_input[search_cursor + 1:]
            search_cursor = min(search_cursor, len(search_input) - 1 if search_input else 0)
        elif key == "KEY_OK":
            if run_mpd_search(search_input, selected_grouping_mode):
                search_mode = False
            return
        return

    else:
        if key == "KEY_OK":
            if copy_mode_active:
                typ, val = library_items[library_selection]
                if typ != "D":
                    core.show_message(core.t("info_invalid_destination_select_folder"))
                    return
                if current_path == "/" and val in FORBIDDEN_TARGET_FOLDERS:
                    core.show_message(core.t("info_copy_forbidden_root"))
                    return
                dst_abs = os.path.join("/var/lib/mpd/music", val)
                for _, src_rel in copy_source_items:
                    src_name = os.path.basename(src_rel)
                    dst_final = os.path.join(dst_abs, src_name)
                    if os.path.exists(dst_final):
                        print(f"Warning: destination already contains folder {dst_final}")
                        core.show_message(core.t("info_already_exists_in_dest", name=src_name))
                        break  # or continue all if you prefer multiple notices
                copy_action_menu_active = True
                copy_action_menu_selection = 0
                copy_confirm_target = val
                return
            else:
                nav_ok()
        elif key == "KEY_LEFT":
            nav_left_short()
            core.reset_scroll("library_items", "menu_item", "menu_title")
        elif key == "KEY_RIGHT":
            nav_right_short()
            core.reset_scroll("library_items", "menu_item", "menu_title")
        elif key == "KEY_UP":
            nav_up()
            core.reset_scroll("library_items", "menu_item")
        elif key == "KEY_DOWN":
            nav_down()
            core.reset_scroll("library_items", "menu_item")
        elif key == "KEY_CHANNELUP":
            nav_channelup()
            core.reset_scroll("library_items", "menu_item")
        elif key == "KEY_CHANNELDOWN":
            nav_channeldown()
            core.reset_scroll("library_items", "menu_item")
        elif key == "KEY_POWER":
            core.show_message(core.t("info_reboot"))
            subprocess.run(["mpc", "stop"])
            subprocess.run(["sudo", "systemctl", "stop", "nginx"])
            subprocess.run(["sudo", "reboot"])
        else:
            print(f"key {key} not used in this script")

    debounce_data.pop(key, None)

override_path = OLIPIMOODE_DIR / ".search_artist"
if os.path.exists(override_path):
    try:
        with open(override_path) as f:
            artist_override = f.read().strip()
        os.remove(override_path)

        if artist_override:
            launch_from_artist_override = True
            search_input = artist_override
            selected_grouping_mode = "Artists"
            if run_mpd_search(search_input, selected_grouping_mode):
                search_mode = False
    except Exception as e:
        core.show_message(core.t("error_loading_artist_override"))
        if core.DEBUG:
            print(f"Error loading artist override: {e}")

core.start_message_updater()
start_inputs(core.config, finish_press, msg_hook=core.show_message)

def main():
    global previous_blocking_render, idle_timer

    if not launch_from_artist_override:
        update_items("/")

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
            time.sleep(0.1 if is_sleeping else 0.05)
    except KeyboardInterrupt:
        if core.DEBUG:
            print("Closing")

if __name__ == '__main__':
    main()

