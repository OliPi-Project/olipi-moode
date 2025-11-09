#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2025 OliPi Project

import os
import sys
import time
import re
import subprocess
import configparser
import threading
import random
import string
from datetime import datetime, timedelta, timezone
from mpd import MPDClient
from pathlib import Path

OLIPIMOODE_DIR = Path(__file__).resolve().parent
os.environ.setdefault("OLIPI_DIR", str(OLIPIMOODE_DIR))

from olipi_core import core_common as core
from olipi_core.input_manager import start_inputs, debounce_data, process_key

font_title = core.get_font("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 10)
font_item = core.get_font("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 11)
font_rename_input = core.get_font("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 12)
font_rename_info = core.get_font("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 10)
font_date = core.screen.ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
font_count = core.screen.ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)

core.load_translations(Path(__file__).stem)

idle_timer = time.time()
last_wake_time = 0
screen_on = True
is_sleeping = False
blocking_render = False
previous_blocking_render = False

SCROLL_SPEED_QUEUE = 0.05
SCROLL_SPEED_TITLE_QUEUE = 0.05
SCROLL_TITLE_QUEUE_PADDING_END = 20

queue_items = []
queue_selection = 0
current_playing = 0
refreshing_queue = False

m3u_path = None

menu_active = False
menu_selection = 0
menu_options = [
    {"id": "add_track_playlist", "label": core.t("menu_add_track_playlist")},
    {"id": "remove_from_queue", "label": core.t("menu_remove_from_queue")},
    {"id": "save_queue_playlist", "label": core.t("menu_save_queue_playlist")},
    {"id": "clear_queue", "label": core.t("menu_clear_queue")},
]

playlist_mode = False
playlist_selection = 0
playlist_list = []

playlist_view_mode = False
playlist_view_selection = 0
playlist_contents = []

track_count = int(core.get_config("settings", "random_track_count", fallback="20", type=str))
radio_count = int(core.get_config("settings", "random_radio_count", fallback="1", type=str))
custom_days = int(core.get_config("settings", "random_recent_album_custom_days", fallback="30", type=str))
empty_queue_menu_active = False
empty_queue_menu_selection = 0
empty_queue_menu_options = [
    {"id": "random_tracks", "label": core.t("menu_random_tracks", tracks_count=track_count)},
    {"id": "random_recent", "label": core.t("menu_random_recent")},
    {"id": "random_album", "label": core.t("menu_random_album")},
    {"id": "random_playlist", "label": core.t("menu_random_playlist")},
    {"id": "random_radios", "label": core.t("menu_random_radios", radios_count=radio_count)},
    {"id": "browse_library", "label": core.t("menu_browse_library")},
]

recent_albums_menu_active = False
recent_albums_menu_selection = 0
recent_albums_options = [
    {"id": "3d", "label": core.t("menu_recent_3d")},
    {"id": "7d", "label": core.t("menu_recent_7d")},
    {"id": "15d", "label": core.t("menu_recent_15d")},
    {"id": "custom", "label": core.t("menu_recent_album_custom", days=custom_days)},
]

genre_menu_active = False
genre_menu_selection = 0
genre_selected = []
genre_options = [g.strip() for g in core.get_config("manual", "genres", fallback="Varied,Relax,Rhythmic,Nocturne,Instru", type=str).split(",")]

rename_prompt_active = False
rename_prompt_selection = 0
rename_prompt_options = [
    {"id": "yes", "label": core.t("menu_rename_yes")},
    {"id": "no", "label": core.t("menu_rename_no")},
]

rename_mode = False
rename_input = ""
rename_cursor = 0
rename_original_name = ""
valid_chars = string.ascii_lowercase + string.digits + '-'

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

def monitor_mpd_status(interval=2):
    global current_playing
    prev_songid = -1

    while True:
        try:
            client = MPDClient()
            client.timeout = 5
            client.connect("localhost", 6600)
            status = client.status()
            songid = int(status.get("songid", -1))
            client.close()
            client.disconnect()

            if songid != prev_songid:
                prev_songid = songid
                if core.DEBUG:
                    print(f"[MPD] Song changed (songid={songid})")
                fetch_queue()

        except Exception as e:
            if core.DEBUG:
                print(f"[MPD Monitor Error] {e}")
        time.sleep(interval)

def format_localized_date(dt):
    months = [core.t(f"month_{i}") for i in range(1, 13)]
    return f"{dt.day} {months[dt.month - 1]} {dt.year}"

def build_radio_url_to_title1_map(pls_directory="/var/lib/mpd/music/RADIO"):
    url_to_title = {}
    for filename in os.listdir(pls_directory):
        if filename.lower().endswith(".pls"):
            full_path = os.path.join(pls_directory, filename)
            config_pl = configparser.ConfigParser()
            try:
                config_pl.read(full_path)
                url = config_pl.get("playlist", "File1", fallback="").strip()
                title = config_pl.get("playlist", "Title1", fallback="").strip()
                if url and title:
                    url_to_title[url] = title
            except Exception as e:
                if core.DEBUG:
                    print(f"Reading error {filename} : {e}")
    return url_to_title

def is_blacklisted_audio(filepath):
    raw = core.get_config("manual", "blacklist_audio_paths", fallback="", type=str)
    blacklist = [p.strip().rstrip("/") for p in raw.split(",") if p.strip()]
    filepath = filepath.replace("\\", "/")

    for entry in blacklist:
        if filepath.endswith(entry) or f"/{entry}/" in filepath:
            if core.DEBUG:
                print(f"[BL] Skipped blacklisted: {filepath}")
            return True
    return False

def play_random_album():
    try:
        client = MPDClient()
        client.timeout = 10
        client.connect("localhost", 6600)
        albums = [a["album"] for a in client.list("album") if a.get("album")]
        if not albums:
            return core.show_message(core.t("info_no_albums"))
        while albums:
            selected_album = random.choice(albums)
            songs = client.find("album", selected_album)
            valid_songs = [s for s in songs if "file" in s and not is_blacklisted_audio(s["file"])]
            if valid_songs:
                client.clear()
                for song in valid_songs:
                    client.add(song["file"])
                client.play()
                core.show_message(core.t("info_random_album_started"))
                return
            else:
                albums.remove(selected_album)
        core.show_message(core.t("info_no_albums"))
    except Exception as e:
        core.show_message(core.t("error_album_load"))
        if core.DEBUG:
            print(f"play_random_album() error: {e}")
    finally:
        try:
            client.close()
            client.disconnect()
        except:
            pass

def play_random_tracks(track_count=20):
    try:
        client = MPDClient()
        client.timeout = 10
        client.connect("localhost", 6600)
        core.show_message(core.t("info_loading_random_tracks"))
        songs = client.search("file", "")
        songs = [s for s in songs if "file" in s and not is_blacklisted_audio(s["file"])]
        if not songs:
            return core.show_message(core.t("info_no_music"))
        selected = random.sample(songs, min(track_count, len(songs)))
        client.clear()
        for song in selected:
            client.add(song["file"])
        client.play()
        core.show_message(core.t("info_random_tracks_played", track_count=track_count))
    except Exception as e:
        core.show_message(core.t("error_track_load"))
        if core.DEBUG:
            print(f"play_random_tracks() error: {e}")
    finally:
        try:
            client.close()
            client.disconnect()
        except:
            pass

def play_random_playlist():
    try:
        client = MPDClient()
        client.timeout = 10
        client.connect("localhost", 6600)
        playlists = [pl["playlist"] for pl in client.listplaylists()]
        if not playlists:
            return core.show_message(core.t("info_no_playlists"))
        selected = random.choice(playlists)
        client.clear()
        client.load(selected)
        client.play()
        core.show_message(core.t("info_random_playlist_loaded", playlist=selected))
    except Exception as e:
        core.show_message(core.t("error_playlist_load"))
        if core.DEBUG:
            print(f"play_random_playlist() error: {e}")
    finally:
        try:
            client.close()
            client.disconnect()
        except:
            pass

def play_random_radios(count=1):
    try:
        client = MPDClient()
        client.timeout = 10
        client.connect("localhost", 6600)
        radio_dir = "/var/lib/mpd/music/RADIO"
        radios = [f for f in os.listdir(radio_dir) if f.endswith(".pls")]
        if not radios:
            return core.show_message(core.t("info_no_radios"))
        selected = random.sample(radios, min(count, len(radios)))
        client.clear()
        for radio in selected:
            client.load(f"RADIO/{radio}")
        client.play()
        core.show_message(core.t("info_random_radios_added"))
    except Exception as e:
        core.show_message(core.t("error_radios_load"))
        if core.DEBUG:
            print(f"play_random_radios() error: {e}")
    finally:
        try:
            client.close()
            client.disconnect()
        except:
            pass

def play_recent_random_albums_by_artist_mpd(since_days=7):
    global recent_albums_menu_active
    client = MPDClient()
    try:
        client.timeout = 10
        client.connect("localhost", 6600)
        core.show_message(core.t("info_loading_generic"), permanent=True)
        since_date = (datetime.now(timezone.utc) - timedelta(days=since_days)).replace(microsecond=0).isoformat()
        #results = client.search(f"(modified-since '{since_date}')")
        results = client.search(f"(added-since '{since_date}')")
        artist_album_map = {}
        for entry in results:
            artist = entry.get("albumartist") or entry.get("artist")
            album = entry.get("album")
            track = entry.get("file")
            if artist and album and track and not is_blacklisted_audio(track):
                artist_album_map.setdefault(artist, {}).setdefault(album, []).append(track)
        if not artist_album_map:
            recent_albums_menu_active = True
            return core.show_message(core.t("info_no_recent_albums"))
        selected_albums = []
        for artist, albums in artist_album_map.items():
            album, tracks = random.choice(list(albums.items()))
            selected_albums.append((artist, album, tracks))
        client.clear()
        for artist, album, tracks in selected_albums:
            for track in sorted(tracks):
                client.add(track)
        client.play()
        album_count = len(selected_albums)
        core.show_message(core.t("info_recent_albums_loaded", count=album_count))
    except Exception as e:
        core.show_message(core.t("error_albums_load"))
        if core.DEBUG:
            print(f"[ERROR] play_recent_random_albums_by_artist_mpd: {e}")
    finally:
        try:
            client.close()
            client.disconnect()
        except:
            pass

def get_playlists():
    try:
        client = MPDClient()
        client.timeout = 10
        client.connect("localhost", 6600)
        playlists = client.listplaylists()
        client.close()
        client.disconnect()

        date_named = []
        normal_named = []
        lowercase_named = []

        for pl in playlists:
            name = pl.get("playlist", "")
            if name:
                if name[:10].count("-") == 2 and "_" in name:
                    date_named.append(name)
                elif name[0].islower():
                    lowercase_named.append(name)
                else:
                    normal_named.append(name)

        date_named.sort(reverse=True)
        lowercase_named.sort(key=str.lower)
        normal_named.sort(key=str.lower)

        return [core.t("show_create_new_playlist")] + date_named + lowercase_named + normal_named

    except Exception as e:
        if core.DEBUG:
            print(f"Error playlists: {e}")
        return [core.t("show_create_new_playlist")]

def fetch_queue():
    global queue_items, queue_selection, current_playing, refreshing_queue
    refreshing_queue = True
    queue_items = []
    try:
        client = MPDClient()
        client.timeout = 10
        client.connect("localhost", 6600)
        queue = client.playlistinfo()
        status = client.status()
        current_playing = int(status.get("song", 0))
        radio_titles = build_radio_url_to_title1_map()
        client.close()
        client.disconnect()

    except Exception as e:
        queue_items = [("F", core.t("error_fetch_queue") + f": {e}")]
        current_playing = 0
        refreshing_queue = False
        core.show_message(core.t("error_fetch_queue"))
        if core.DEBUG:
            print(f"Error queue: {e}")
        return

    for item in queue:
        file_str = item.get("file", "").strip()
        if file_str.lower().startswith("http"):
            station = radio_titles.get(file_str, "")
            title = item.get("title", "").strip()
            if station and title:
                display = f"{station} : {title}"
            elif station:
                display = station
            elif title:
                display = title
            else:
                display = file_str
        else:
            artist = item.get("artist", "").strip()
            title = item.get("title", "").strip()
            if artist and title:
                display = f"{title} - {artist}"
            else:
                display = title or os.path.basename(file_str)
        queue_items.append(("F", display))

    queue_selection = current_playing if 0 <= current_playing < len(queue_items) else 0
    refreshing_queue = False
    core.reset_scroll("queue_item")

def fetch_playlist_content(name):
    global playlist_contents, playlist_view_selection
    playlist_contents = []

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
                    display = f"{title} - {artist}"
                else:
                    display = title or os.path.basename(file_str)

            if display.strip() and display != ";":
                playlist_contents.append(display)

    except Exception as e:
        playlist_contents = [core.t("error_fetch_playlist")]
        playlist_view_selection = 0
        core.show_message(core.t("error_fetch_playlist"))
        if core.DEBUG:
            print(f"Error fetching playlist content: {e}")

def get_selected_genres():
    return ", ".join(genre_selected)

def render_screen():
    if core.message_text:
        core.draw_message()
    elif help_active:
        draw_help_screen()
    elif rename_mode:
        draw_rename_screen()
    elif rename_prompt_active:
        draw_rename_prompt()
    elif genre_menu_active:
        draw_genre_menu()
    elif playlist_view_mode:
        draw_playlist_view()
    elif playlist_mode:
        draw_playlists()
    elif recent_albums_menu_active:
        draw_recent_albums_menu()
    elif empty_queue_menu_active:
        draw_empty_queue_menu()
    elif menu_active:
        draw_menu()
    else:
        draw_queue()

    core.refresh()

def draw_menu():
    core.draw_custom_menu([item["label"] for item in menu_options], menu_selection, title=core.t("title_menu"))

def draw_playlists():
    core.draw_custom_menu(playlist_list, playlist_selection, title=core.t("title_choose_playlist"))

def draw_playlist_view():
    core.draw_custom_menu(playlist_contents, playlist_view_selection, title=core.t("title_playlist_content"))

def draw_empty_queue_menu():
    labels = []
    for item in empty_queue_menu_options:
        if item["id"] == "random_tracks":
            label = core.t("menu_random_tracks", tracks_count=track_count)
        elif item["id"] == "random_radios":
            label = core.t("menu_random_radios", radios_count=radio_count)
        else:
            label = item["label"]
        labels.append(label)
    core.draw_custom_menu(labels, empty_queue_menu_selection, title=core.t("title_random_playback"))

def draw_recent_albums_menu():
    labels = []
    for item in recent_albums_options:
        if item["id"] == "custom":
            label = core.t("menu_recent_album_custom", days=custom_days)
        else:
            label = item["label"]
        labels.append(label)
    core.draw_custom_menu(labels, recent_albums_menu_selection, title=core.t("title_recent_albums"))

def draw_genre_menu():
    core.draw_custom_menu(genre_options, genre_menu_selection, title=core.t("title_select_genres"), multi=genre_selected)

def draw_rename_prompt():
    core.draw_custom_menu([item["label"] for item in rename_prompt_options], rename_prompt_selection, title=core.t("title_rename_playlist"))

def draw_help_screen():
    core.draw_custom_menu(help_lines, help_selection, core.t("title_contextual_help"))

def draw_rename_screen():
    core.draw.rectangle((0, 0, core.width, core.height), fill=core.COLOR_BG)

    padding_x = max(1, int(core.width * 0.02))

    # --- Title → items spacing based on screen height ---
    if core.height <= 64:
        spacing_title_items = 2
        padding_y = 1
    else:
        spacing_title_items = 10
        padding_y = 6

    # ─── Title ───
    title = core.t("title_rename_playlist")
    title_width = core.draw.textlength(title, font=font_title)
    x_title = (core.width - title_width) // 2
    y_title = padding_y
    core.draw.text((x_title, y_title), title, font=font_title, fill=core.COLOR_TITLE)

    # ─── Input area ───
    input_y = padding_y + font_title.getbbox("Ay")[3] + spacing_title_items
    input_padding_x = 4
    input_padding_y = 3
    input_h = font_rename_input.getbbox("Ay")[3] - font_rename_input.getbbox("Ay")[1] + 2 * input_padding_y
    input_bottom = input_y + input_h
    core.draw.rectangle((0, input_y, core.width, input_bottom), fill=core.COLOR_INPUT_BG)

    # ─── Scroll horizontal ───
    text_before_cursor = rename_input[:rename_cursor]
    text_width_before_cursor = core.draw.textlength(text_before_cursor.replace(" ", "_"), font=font_rename_input)
    full_text_width = core.draw.textlength(rename_input.replace(" ", "_"), font=font_rename_input)

    # Automatic scroll if cursor exceeds the visible display
    visible_width = core.width - 2 * input_padding_x
    scroll_offset = 0
    if text_width_before_cursor > visible_width:
        scroll_offset = text_width_before_cursor - visible_width + 10  # petit padding

    display_text = rename_input.replace(" ", "_")
    core.draw.text((input_padding_x - scroll_offset, input_y + input_padding_y), display_text, font=font_rename_input, fill=core.COLOR_INPUT_TEXT)

    # Visual cursor: actual position
    cursor_x = core.draw.textlength(rename_input[:rename_cursor].replace(" ", "_"), font=font_rename_input) - scroll_offset + input_padding_x
    cursor_y = input_y + input_padding_y
    core.draw.line((cursor_x, cursor_y, cursor_x, cursor_y + font_rename_input.getbbox("A")[3]), fill=core.COLOR_INPUT_CURSOR)

    # ─── Multiline genre display ───
    if genre_selected:
        genre_text = core.t("show_label_genres") + " " + ", ".join(genre_selected)
        lines = []
        current_line = ""
        for word in genre_text.split(", "):
            test_line = current_line + (", " if current_line else "") + word
            if core.draw.textlength(test_line, font=font_rename_info) > core.width - 6:
                if current_line:
                    lines.append(current_line)
                current_line = word
            else:
                current_line = test_line
        if current_line:
            lines.append(current_line)

        max_lines = 3
        for i, line in enumerate(lines[:max_lines]):
            core.draw.text((padding_x, core.height - (max_lines - i) * 10), line, font=font_rename_info, fill=core.COLOR_INPUT_INFO)

def draw_queue():
    """
    Queue view: header at top, adaptive layout, improved selected-item scrolling.
    """
    now = time.time()

    # Background
    core.draw.rectangle((0, 0, core.width, core.height), fill=core.COLOR_BG)

    # If queue is being refreshed show a centered message and bail out
    if refreshing_queue:
        msg = core.t("show_refreshing_queue")
        text_w = core.draw.textlength(msg, font=font_item)
        core.draw.text(((core.width - text_w) // 2, core.height // 2 - 6),
                       msg, font=font_item, fill=core.COLOR_TEXT)
        return

    # 1) Choose header
    if not queue_items:
        header = core.t("title_empty_queue")
    else:
        header = core.t("title_now_playing")

    # 2) Dynamic paddings
    padding_x = max(1, int(core.width * 0.02))
    padding_y = max(1, int(core.height * 0.01))

    # 3) Title linear scroll (keep original behavior but safe-guard keys)
    state_t = core.scroll_state.setdefault("queue_title", {"offset": 0, "last_update": now})
    title_w = core.draw.textlength(header, font=font_title)
    bbox_title = font_title.getbbox("Ay")
    title_h = bbox_title[3] - bbox_title[1]

    inner_width_guess = core.width - 2 * padding_x
    if title_w > inner_width_guess and now - state_t.get("last_update", 0) > SCROLL_SPEED_TITLE_QUEUE:
        scroll_w = title_w + SCROLL_TITLE_QUEUE_PADDING_END
        state_t["offset"] = (state_t.get("offset", 0) + 1) % scroll_w
        state_t["last_update"] = now
    else:
        state_t["offset"] = 0

    # 4) Draw title at top (centered or scrolling)
    if title_w <= core.width:
        xh = (core.width - title_w) // 2
        core.draw.text((xh, 0), header, font=font_title, fill=core.COLOR_TITLE)
    else:
        off = state_t.get("offset", 0)
        core.draw.text((-off, 0), header, font=font_title, fill=core.COLOR_TITLE)
        core.draw.text((title_w + SCROLL_TITLE_QUEUE_PADDING_END - off, 0),
                       header, font=font_title, fill=core.COLOR_TITLE)

    # 5) Title -> items spacing depending on screen height
    if core.height <= 64:
        spacing_title_items = 5
        padding_item = 2
    elif core.height < 128:
        spacing_title_items = 5
        padding_item = 2
    else:
        spacing_title_items = 6
        padding_item = 2

    # 6) Fixed metrics for items (based on "Ay")
    item_bbox = font_item.getbbox("Ay")
    item_h = item_bbox[3] - item_bbox[1]
    line_h = item_h + padding_item

    # 7) Compute available lines (reserve top area for title + padding_y)
    start_y = title_h + spacing_title_items
    max_lines = max(1, (core.height - start_y - padding_y) // line_h)
    visible_lines = min(len(queue_items), max_lines)

    # 8) Handle empty queue with two centered notices (keep original texts)
    if not queue_items:
        notice = core.t("show_queue_empty_notice_1")
        b = core.draw.textbbox((0, 0), notice, font=font_item)
        x_notice = (core.width - (b[2] - b[0])) // 2
        core.draw.text((x_notice, start_y + 8), notice, font=font_item, fill=core.COLOR_TEXT)

        notice2 = core.t("show_queue_empty_notice_2")
        b2 = core.draw.textbbox((0, 0), notice2, font=font_rename_info)
        x_notice2 = (core.width - (b2[2] - b2[0])) // 2
        core.draw.text((x_notice2, start_y + 10 + line_h), notice2, font=font_rename_info, fill=core.COLOR_TEXT)
        return

    # 9) Compute window of items centered on selection
    start_idx = max(0, queue_selection - visible_lines // 2)
    if start_idx + visible_lines > len(queue_items):
        start_idx = max(0, len(queue_items) - visible_lines)

    # 10) Draw items
    for i in range(visible_lines):
        idx = start_idx + i
        if idx >= len(queue_items):
            break

        _, base_title = queue_items[idx]
        y_item = start_y + i * line_h

        prefix = " ⇨ " if idx == current_playing else ""
        full_text = prefix + base_title

        text_w = core.draw.textlength(full_text, font=font_item)
        text_y = y_item + (line_h - item_h) // 2 - item_bbox[1]
        x_text_base = padding_x

        if idx == queue_selection:
            # selection rectangle (full width, but vertical aligned to text bbox)
            sel_top = text_y + item_bbox[1] - 3
            sel_bot = text_y + item_bbox[3]
            core.draw.rectangle((0, sel_top, core.width - 1, sel_bot), outline=core.COLOR_MENU_OUTLINE, fill=core.COLOR_MENU_SELECTED_BG)

            # selected-item scroll: use phase-based state (pause_start -> scrolling -> pause_end)
            state_i = core.scroll_state.setdefault(
                "queue_item",
                {"offset": 0, "last_update": time.time(), "phase": "pause_start", "pause_start_time": time.time()}
            )
            avail = core.width - (padding_x + 2)

            if text_w > avail:
                # adaptive timing
                BASE_INTERVAL = SCROLL_SPEED_QUEUE
                MIN_INTERVAL = 0.03
                MAX_INTERVAL = 0.14
                PAUSE_DURATION = 0.6
                BLANK_DURATION = 0.12

                ratio = text_w / float(avail)
                interval = BASE_INTERVAL / max(0.001, ratio)
                scroll_speed = max(MIN_INTERVAL, min(MAX_INTERVAL, interval))

                phase = state_i.get("phase", "pause_start")

                if phase == "pause_start":
                    state_i["offset"] = 0
                    if now - state_i.get("pause_start_time", 0) > PAUSE_DURATION:
                        state_i["phase"] = "scrolling"
                        state_i["last_update"] = now

                elif phase == "scrolling":
                    if now - state_i.get("last_update", 0) > scroll_speed:
                        state_i["offset"] += 1
                        state_i["last_update"] = now
                        if state_i["offset"] >= (text_w - avail):
                            # reached end => enter pause_end
                            state_i["phase"] = "pause_end"
                            state_i["pause_start_time"] = now

                elif phase == "pause_end":
                    elapsed = now - state_i.get("pause_start_time", 0)
                    if elapsed >= PAUSE_DURATION:
                        # full pause finished: reset
                        state_i["offset"] = 0
                        state_i["phase"] = "pause_start"
                        state_i["pause_start_time"] = now

                # compute x once
                off = state_i.get("offset", 0)
                x_text = x_text_base - off if text_w > avail else x_text_base

                # very short blank near the end of the pause_end
                draw_text = True
                if state_i.get("phase") == "pause_end":
                    elapsed = now - state_i.get("pause_start_time", 0)
                    if elapsed >= (PAUSE_DURATION - BLANK_DURATION) and elapsed < PAUSE_DURATION:
                        draw_text = False

                if draw_text:
                    core.draw.text((x_text, text_y), full_text, font=font_item, fill=core.COLOR_MENU_SELECTED_TEXT)
                # else: skip drawing text during brief blank
            else:
                # text fits: reset state and draw normally
                state_i["offset"] = 0
                state_i["phase"] = "pause_start"
                state_i["pause_start_time"] = now
                core.draw.text((x_text_base, text_y), full_text, font=font_item, fill=core.COLOR_MENU_SELECTED_TEXT)
        else:
            # non-selected item
            core.draw.text((x_text_base, text_y), full_text, font=font_item, fill=core.COLOR_TEXT)

def add_default_cover(playlist_name):
    src =  OLIPIMOODE_DIR / "NewPlaylist.jpg"
    src_tmp =  OLIPIMOODE_DIR / "NewPlaylist-tmp.jpg"
    dest_dir = "/var/local/www/imagesw/playlist-covers"
    dest = os.path.join(dest_dir, f"{playlist_name}.jpg")

    try:
        img = core.Image.open(src).convert("RGB")
        draw = core.screen.ImageDraw.Draw(img)

        date_str = format_localized_date(datetime.now())
        bbox_date = draw.textbbox((0, 0), date_str, font=font_date)
        x_date = (img.width - (bbox_date[2] - bbox_date[0])) // 2
        draw.text((x_date, 8), date_str, fill=core.COLOR_TEXT, font=font_date)

        client = MPDClient()
        client.timeout = 10
        client.connect("localhost", 6600)
        playlist = client.listplaylist(playlist_name)
        client.close()
        client.disconnect()

        track_count = len(playlist)
        track_label = core.t("show_track_cover")
        if track_count == 1:
            count_str = f"1 {track_label}"
        else:
            count_str = f"{track_count} {track_label}s"

        bbox_count = draw.textbbox((0, 0), count_str, font=font_count)
        x_count = (img.width - (bbox_count[2] - bbox_count[0])) // 2
        draw.text((x_count, img.height - bbox_count[3] - 8), count_str, fill=core.COLOR_TEXT, font=font_count)

        img.save(src_tmp, "JPEG")
        subprocess.call(["sudo", "cp", src_tmp, dest])
        if core.DEBUG:
            print(f"Custom cover image saved to: {dest}")
        subprocess.call(["rm", src_tmp])

    except Exception as e:
        if core.DEBUG:
            print(f"Cover creation error: {e}")

def playlist_rename():
    global rename_mode, rename_input, rename_original_name

    if not all(c in valid_chars for c in rename_input):
        core.show_message(core.t("error_invalid_char"))
        rename_mode = False
        return

    try:
        client = MPDClient()
        client.timeout = 10
        client.connect("localhost", 6600)

        existing_playlists = [pl["playlist"] for pl in client.listplaylists()]
        if rename_input in existing_playlists:
            core.show_message(core.t("error_name_in_use"))
            client.close()
            client.disconnect()
            rename_mode = False
            return

        client.rename(rename_original_name, rename_input)
        client.close()
        client.disconnect()

        old_cover = f"/var/local/www/imagesw/playlist-covers/{rename_original_name}.jpg"
        new_cover = f"/var/local/www/imagesw/playlist-covers/{rename_input}.jpg"
        if os.path.exists(old_cover):
            try:
                subprocess.call(["sudo", "mv", old_cover, new_cover])
                if core.DEBUG:
                    print(f"Cover renamed to: {new_cover}")
            except Exception as e:
                if core.DEBUG:
                    print(f"Cover rename error (sudo mv): {e}")

        core.show_message(core.t("info_playlist_renamed_to", name=rename_input))

    except Exception as e:
        core.show_message(core.t("error_rename_playlist"))
        if core.DEBUG:
            print(f"Playlist renaming error: {e}")

    rename_mode = False

def confirm_playlist_choice(menu_option_id):
    global playlist_mode, menu_active, genre_menu_active, genre_menu_selection, genre_selected, m3u_path

    name = playlist_list[playlist_selection]

    try:
        client = MPDClient()
        client.timeout = 10
        client.connect("localhost", 6600)

        if menu_option_id == "add_track_playlist":
            if playlist_selection == 0:  # "<create new playlist>"
                timestamp = time.strftime("%Y-%m-%d_%Hh%M")
                new_name = f"{timestamp}"
                song = client.playlistinfo()[queue_selection]
                uri = song.get("file")
                if uri:
                    client.playlistadd(new_name, uri)
                    m3u_path = f"/var/lib/mpd/playlists/{new_name}.m3u"
                    try:
                        subprocess.call(["sudo", "chown", "root:root", m3u_path])
                        subprocess.call(["sudo", "chmod", "777", m3u_path])
                        if core.DEBUG:
                            print(f"Corrected permissions for {m3u_path}")
                    except Exception as e:
                        if core.DEBUG:
                            print(f"Error permission playlist: {e}")
                    genre_selected.clear()
                    genre_menu_selection = 0
                    genre_menu_active = True
                    draw_queue()
                    add_default_cover(new_name)
                    core.show_message(core.t("info_playlist_track_added", name=new_name))
            else:
                song = client.playlistinfo()[queue_selection]
                uri = song.get("file")
                if uri:
                    client.playlistadd(name, uri)
                if re.match(r'^[a-z].*$', name) or re.match(r'^\d{4}-\d{2}-\d{2}_\d{1,2}h\d{2}$', name):  # Format YYYY-MM-DD_HHhMM
                    add_default_cover(name)
                else:
                    print(f"Cover not replaced for default playlists: {name}")
                core.show_message(core.t("info_playlist_track_added", name=name))

        elif menu_option_id == "save_queue_playlist":
            if playlist_selection == 0:  # "<create new playlist>"
                timestamp = time.strftime("%Y-%m-%d_%Hh%M")
                new_name = f"{timestamp}"
                client.save(new_name, "create")
                m3u_path = f"/var/lib/mpd/playlists/{new_name}.m3u"
                try:
                    subprocess.call(["sudo", "chown", "root:root", m3u_path])
                    subprocess.call(["sudo", "chmod", "777", m3u_path])
                    if core.DEBUG:
                        print(f"Corrected permissions for {m3u_path}")
                except Exception as e:
                    if core.DEBUG:
                        print(f"Error permission playlist: {e}")
                genre_selected.clear()
                genre_menu_selection = 0
                genre_menu_active = True
                draw_queue()
                add_default_cover(new_name)
                core.show_message(core.t("info_queue_saved_as", name=new_name))

            else:
                client.save(name, "replace")
                if re.match(r'^[a-z].*$', name) or re.match(r'^\d{4}-\d{2}-\d{2}_\d{1,2}h\d{2}$', name):  # Format YYYY-MM-DD_HHhMM
                    add_default_cover(name)
                else:
                    print(f"Cover not replaced for default playlists: {name}")
                m3u_path = f"/var/lib/mpd/playlists/{name}.m3u"
                try:
                    subprocess.call(["sudo", "chown", "root:root", m3u_path])
                    subprocess.call(["sudo", "chmod", "777", m3u_path])
                    if core.DEBUG:
                        print(f"Corrected permissions for {m3u_path}")
                except Exception as e:
                    if core.DEBUG:
                        print(f"Error permission playlist: {e}")
                genre_selected.clear()
                genre_menu_selection = 0
                genre_menu_active = True
                core.show_message(core.t("info_playlist_replaced", name=name))

        client.close()
        client.disconnect()

    except Exception as e:
        if core.DEBUG:
            print(f"Playlist saving error: {e}")

    playlist_mode = False
    menu_active = False

def remove_track():
    global queue_selection, current_playing, menu_active, queue_items
    removed_index = queue_selection
    try:
        client = MPDClient()
        client.timeout = 10
        client.connect("localhost", 6600)
        client.delete(removed_index)
        core.show_message(core.t("info_track_removed", index=removed_index))
    except Exception as e:
        core.show_message(core.t("error_remove_track"))
        if core.DEBUG:
            print(f"Track removal error: {e}")
    finally:
        try:
            client.close()
            client.disconnect()
        except:
            pass
    menu_active = False
    if removed_index == current_playing:
        fetch_queue()
        return
    if 0 <= removed_index < len(queue_items):
        queue_items.pop(removed_index)
    if removed_index >= len(queue_items):
        queue_selection = max(0, len(queue_items) - 1)
    else:
        queue_selection = removed_index

def clear_queue():
    global menu_active, playlist_mode
    try:
        client = MPDClient()
        client.timeout = 10
        client.connect("localhost", 6600)
        client.clear()
        core.show_message(core.t("info_queue_cleared"))
        client.close()
        client.disconnect()
        menu_active = False
        playlist_mode = False
        fetch_queue()

    except Exception as e:
        if core.DEBUG:
            print(f"Error: {e}")

def nav_up():
    global menu_selection, queue_selection
    if menu_active:
        if menu_selection > 0:
            menu_selection -= 1
    else:
        if queue_selection > 0:
            queue_selection -= 1

def nav_down():
    global menu_selection, queue_selection
    if menu_active:
        if menu_selection < len(menu_options) - 1:
            menu_selection += 1
    else:
        if queue_selection < len(queue_items) - 1:
            queue_selection += 1

def nav_ok():
    global menu_active, menu_selection
    global empty_queue_menu_active, empty_queue_menu_selection
    if len(queue_items) == 0:
        empty_queue_menu_active = True
        empty_queue_menu_selection = 0
    else:
        menu_active = True
        menu_selection = 0

def nav_left_short():
    global queue_selection, current_playing
    queue_selection = current_playing

def nav_left_long():
    global menu_active, empty_queue_menu_active, recent_albums_menu_active, playlist_mode, playlist_view_mode, genre_menu_active, rename_prompt_active, rename_mode

    if rename_mode or rename_prompt_active:
        core.show_message(core.t("info_rename_cancelled"))
    elif genre_menu_active:
        core.show_message(core.t("info_genre_unmodified"))
    elif menu_active or empty_queue_menu_active or recent_albums_menu_active or playlist_mode or playlist_view_mode:
        core.show_message(core.t("info_back_to_queue"))

    menu_active = False
    empty_queue_menu_active = False
    recent_albums_menu_active = False
    playlist_mode = False
    playlist_view_mode = False
    genre_menu_active = False
    rename_prompt_active = False
    rename_mode = False
    fetch_queue()

def nav_right_short():
    print("Not implemented")

def nav_right_long():
    global current_playing, queue_selection
    try:
        client = MPDClient()
        client.timeout = 10
        client.connect("localhost", 6600)
        client.play(queue_selection)
        client.close()
        client.disconnect()
        current_playing = queue_selection
    except Exception as e:
        core.show_message(core.t("error_play_song"))
        if core.DEBUG:
            print(f"Reading error: {e}")

def nav_info():
    global help_active, help_lines, help_selection
    help_base_path = OLIPIMOODE_DIR / f"help_texts/help_ui_queue_{core.LANGUAGE}.txt"
    if not help_base_path.exists():
        help_base_path = OLIPIMOODE_DIR / "help_texts/help_ui_queue_en.txt"
    context = "queue"

    if playlist_view_mode:
        context = "playlist_view"
    elif playlist_mode:
        context = "playlist"
    elif playlist_mode:
        context = "playlist"
    elif genre_menu_active:
        context = "genres"
    elif rename_mode:
        context = "rename_screen"
    elif empty_queue_menu_active or recent_albums_menu_active:
        context = "random_menu"
    elif menu_active or recent_albums_menu_active or empty_queue_menu_active or rename_prompt_active:
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
        core.show_message(core.t("error_load_help", err=str(e)))
        if core.DEBUG:
            print(f"Error loading help: {e}")

def nav_back():
    core.show_message(core.t("info_back_nowplaying"))
    time.sleep(1)
    subprocess.call(["sudo", "systemctl", "start", "olipi-ui-playing.service"])
    subprocess.call(["sudo", "systemctl", "stop", "olipi-ui-queue.service"])
    sys.exit(0)

def nav_back_long():
    core.show_message(core.t("info_go_library_screen"))
    time.sleep(1)
    subprocess.call(["sudo", "systemctl", "start", "olipi-ui-browser.service"])
    subprocess.call(["sudo", "systemctl", "stop", "olipi-ui-queue.service"])
    sys.exit(0)

def trigger_menu(index):
    global playlist_mode, playlist_selection, playlist_list
    option_id = menu_options[index]["id"]
    if option_id in ("add_track_playlist", "save_queue_playlist"):
        playlist_mode = True
        playlist_selection = 0
        playlist_list = get_playlists()
        if not playlist_list:
            core.show_message(core.t("info_show_no_playlist"))
            return
    elif option_id == "remove_from_queue":
        remove_track()
    elif option_id == "clear_queue":
        clear_queue()

def finish_press(key):
    global menu_active, menu_selection, empty_queue_menu_active, empty_queue_menu_selection, genre_menu_active, genre_menu_selection, genre_selected
    global playlist_mode, playlist_selection, playlist_view_mode, playlist_view_selection
    global rename_prompt_active, rename_prompt_selection, rename_mode, rename_cursor, rename_input, rename_original_name, m3u_path, current_playlist_name
    global recent_albums_menu_active, recent_albums_menu_selection, recent_albums_options, help_active, help_selection
    global screen_on, idle_timer, is_sleeping, last_wake_time, custom_days, track_count, radio_count

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
        core.reset_scroll("queue_item", "menu_title", "menu_item")
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

    if playlist_view_mode:
        if key == "KEY_UP" and playlist_view_selection > 0:
            playlist_view_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and playlist_view_selection < len(playlist_contents) - 1:
            playlist_view_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            playlist_view_mode = False
            playlist_mode = True
            core.reset_scroll("menu_item")
        return

    if playlist_mode:
        if key == "KEY_UP" and playlist_selection > 0:
            playlist_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and playlist_selection < len(playlist_list) - 1:
            playlist_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_RIGHT":
            name = playlist_list[playlist_selection]
            fetch_playlist_content(name)
            playlist_view_selection = 0
            playlist_mode = False
            playlist_view_mode = True
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            playlist_mode = False
            core.reset_scroll("menu_item")
        elif key == "KEY_OK":
            confirm_playlist_choice(menu_options[menu_selection]["id"])
        return

    if menu_active:
        if key == "KEY_UP" and menu_selection > 0:
            menu_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and menu_selection < len(menu_options) - 1:
            menu_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            menu_active = False
            core.reset_scroll("queue_item", "menu_item")
        elif key == "KEY_OK":
            menu_active = False
            trigger_menu(menu_selection)
        return

    if empty_queue_menu_active:
        if key == "KEY_UP" and empty_queue_menu_selection > 0:
            empty_queue_menu_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and empty_queue_menu_selection < len(empty_queue_menu_options) - 1:
            empty_queue_menu_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            empty_queue_menu_active = False
            core.reset_scroll("queue_item", "menu_item")
        elif key == "KEY_CHANNELUP":
            selected_id = empty_queue_menu_options[empty_queue_menu_selection]["id"]
            if selected_id == "random_tracks" and track_count < 100:
                track_count += 1
            elif selected_id == "random_radios" and radio_count < 10:
                radio_count += 1
        elif key == "KEY_CHANNELDOWN":
            selected_id = empty_queue_menu_options[empty_queue_menu_selection]["id"]
            if selected_id == "random_tracks" and track_count > 1:
                track_count -= 1
            elif selected_id == "random_radios" and radio_count > 1:
                radio_count -= 1
        elif key == "KEY_OK":
            selected_id = empty_queue_menu_options[empty_queue_menu_selection]["id"]
            empty_queue_menu_active = False
            if selected_id == "random_album":
                play_random_album()
            elif selected_id == "random_tracks":
                core.save_config("random_track_count", track_count, section="settings")
                play_random_tracks(track_count=track_count)
            elif selected_id == "random_playlist":
                play_random_playlist()
            elif selected_id == "random_radios":
                core.save_config("random_radio_count", radio_count, section="settings")
                play_random_radios(count=radio_count)
            elif selected_id == "random_recent":
                recent_albums_menu_active = True
                recent_albums_menu_selection = 0
            elif selected_id == "browse_library":
                core.show_message(core.t("info_go_library_screen"))
                render_screen()
                time.sleep(1)
                subprocess.call(["sudo", "systemctl", "start", "olipi-ui-browser.service"])
                subprocess.call(["sudo", "systemctl", "stop", "olipi-ui-queue.service"])
                sys.exit(0)
        return

    if recent_albums_menu_active:
        if key == "KEY_UP" and recent_albums_menu_selection > 0:
            recent_albums_menu_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and recent_albums_menu_selection < len(recent_albums_options) - 1:
            recent_albums_menu_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            recent_albums_menu_active = False
            empty_queue_menu_active = True
            core.reset_scroll("menu_item")
        elif key == "KEY_CHANNELUP":
            if recent_albums_options[recent_albums_menu_selection]["id"] == "custom":
                if custom_days < 180:
                    custom_days += 1
        elif key == "KEY_CHANNELDOWN":
            if recent_albums_options[recent_albums_menu_selection]["id"] == "custom":
                if custom_days > 1:
                    custom_days -= 1
        elif key == "KEY_OK":
            recent_albums_menu_active = False
            selected_id = recent_albums_options[recent_albums_menu_selection]["id"]
            days_map = {"3d": 3, "7d": 7, "15d": 15, "custom": custom_days}
            selected_days = days_map.get(selected_id, 7)
            core.save_config("random_recent_album_custom_days", custom_days, section="settings")
            play_recent_random_albums_by_artist_mpd(since_days=selected_days)
        return

    if genre_menu_active:
        if key == "KEY_UP" and genre_menu_selection > 0:
            genre_menu_selection -= 1
            core.reset_scroll("menu_item")
        elif key == "KEY_DOWN" and genre_menu_selection < len(genre_options) - 1:
            genre_menu_selection += 1
            core.reset_scroll("menu_item")
        elif key == "KEY_LEFT":
            genre_menu_active = False
            subprocess.call(["python3",  OLIPIMOODE_DIR / "playlist_tags.py", "--file", m3u_path, "--set-genre", get_selected_genres(), "--add-img"])
            current_playlist_name = os.path.splitext(os.path.basename(m3u_path))[0]
            if re.match(r'^[a-z].*$', current_playlist_name) or re.match(r'^\d{4}-\d{2}-\d{2}_\d{1,2}h\d{2}$', current_playlist_name):
                rename_prompt_active = True
                rename_prompt_selection = 0
                return
            else:
                core.show_message(core.t("info_added_genre"))
            core.reset_scroll("menu_item")
        elif key == "KEY_OK":
            core.reset_scroll("menu_item")
            genre = genre_options[genre_menu_selection]
            if genre in genre_selected:
                genre_selected.remove(genre)
            else:
                genre_selected.append(genre)
        return

    if rename_prompt_active:
        if key == "KEY_UP" and rename_prompt_selection > 0:
            rename_prompt_selection -= 1
        elif key == "KEY_DOWN" and rename_prompt_selection < 1:
            rename_prompt_selection += 1
        elif key == "KEY_LEFT":
            rename_prompt_active = False
            core.show_message(core.t("info_added_genre"))
        elif key == "KEY_OK":
            rename_prompt_active = False
            if rename_prompt_options[rename_prompt_selection]["id"] == "yes":
                rename_mode = True
                rename_original_name = current_playlist_name
                rename_input = "new"
                rename_cursor = 0
            else:
                core.show_message(core.t("info_added_genre"))
        return

    if rename_mode:
        if key == "KEY_LEFT" and rename_cursor > 0:
            rename_cursor -= 1
        elif key == "KEY_RIGHT":
            if rename_cursor < len(rename_input) - 1:
                rename_cursor += 1
            elif rename_cursor < len(rename_input):
                rename_cursor += 1
                new_char = "a"
                rename_input += new_char
        elif key == "KEY_UP":
            ch = rename_input[rename_cursor]
            if ch in valid_chars:
                new_index = (valid_chars.index(ch) - 1) % len(valid_chars)
                new_ch = valid_chars[new_index]
                rename_input = rename_input[:rename_cursor] + new_ch + rename_input[rename_cursor + 1:]
        elif key == "KEY_DOWN":
            ch = rename_input[rename_cursor]
            if ch in valid_chars:
                new_index = (valid_chars.index(ch) + 1) % len(valid_chars)
                new_ch = valid_chars[new_index]
                rename_input = rename_input[:rename_cursor] + new_ch + rename_input[rename_cursor + 1:]
        elif key == "KEY_OK":
            playlist_rename()
            return

    else:
        if key == "KEY_OK":
            nav_ok()
        elif key == "KEY_LEFT":
            nav_left_short()
            core.reset_scroll("queue_item", "menu_item", "menu_title")
        elif key == "KEY_RIGHT":
            nav_right_short()
            core.reset_scroll("queue_item", "menu_item", "menu_title")
        elif key == "KEY_UP":
            nav_up()
            core.reset_scroll("queue_item", "menu_item")
        elif key == "KEY_DOWN":
            nav_down()
            core.reset_scroll("queue_item", "menu_item")
        elif key == "KEY_POWER":
            core.show_message(core.t("info_reboot"))
            subprocess.run(["mpc", "stop"])
            subprocess.run(["sudo", "systemctl", "stop", "nginx"])
            subprocess.run(["sudo", "reboot"])
        else:
            if core.DEBUG:
                print(f"key {key} not used in this script")

    debounce_data.pop(key, None)

core.start_message_updater()
start_inputs(core.config, finish_press, msg_hook=core.show_message)

def main():
    global previous_blocking_render, idle_timer

    fetch_queue()
    threading.Thread(target=monitor_mpd_status, daemon=True).start()

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
