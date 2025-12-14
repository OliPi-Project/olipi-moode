#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2025 OliPi Project

import os
import sys
import subprocess
import shutil
import time
import stat
import json
import traceback
import argparse
import tempfile
import urllib.request
import urllib.error
import re
import yaml
from copy import deepcopy
from pathlib import Path
from lang import SETUP

APT_DEPENDENCIES = [
    "git", "python3-pil", "python3-venv", "python3-pip", "python3-tk", "libasound2-dev",
    "libopenblas-dev", "libopenblas-pthread-dev", "libblas-dev", "liblapack-dev", "libgfortran5",
    "i2c-tools", "python3-rpi-lgpio", "python3-setuptools"
]

REQUIRED_MOODE_VERSION = "9.3.7"
OLIPI_CORE_REPO = "https://github.com/OliPi-Project/olipi-core.git"
OLIPI_MOODE_REPO = "https://github.com/OliPi-Project/olipi-moode.git"
OLIPI_MOODE_DEV_BRANCH = "dev"
OLIPI_CORE_DEV_BRANCH = "dev"

# path relative to local_dir e.g. ["config/user_key.ini, something.ini"]
PRESERVE_FILES = {
    "moode": ["songlog.txt", "search_history.txt", "theme_user.yaml"],
    "core": []
}

lang = "en"

INSTALL_DIR = os.path.dirname(os.path.abspath(__file__))  # directory containing this script
OLIPI_MOODE_DIR = os.path.dirname(INSTALL_DIR)  # parent → olipi-moode
OLIPI_CORE_DIR = os.path.join(OLIPI_MOODE_DIR, "olipi_core")
DEFAULT_VENV_PATH = os.path.expanduser("~/.olipi-moode-venv")
INSTALL_LIRC_REMOTE_PATH = os.path.join(INSTALL_DIR, "install_lirc_remote.py")
SETUP_SCRIPT_PATH = os.path.join(INSTALL_DIR, "install_olipi.py")
REEXEC_FLAG = Path(tempfile.gettempdir()) / f"olipi_reexec_{os.getuid()}.flag"
TMP_LOG_FILE = Path("/tmp/setup.log")
CONFIG_TXT = "/boot/firmware/config.txt"
THEME_PATH_MAIN = Path(OLIPI_MOODE_DIR) / "theme_colors.yaml"
THEME_PATH_USER = Path(OLIPI_MOODE_DIR) / "theme_user.yaml"

_LOG_INITIALIZED = False

def finalize_log(exit_code=0):
    try:
        if TMP_LOG_FILE.exists():
            status = "success" if exit_code == 0 else "aborted" if exit_code == 130 else "error"
            timestamp = time.strftime("%Y-%m-%d")
            dest = Path(INSTALL_DIR) / "logs" / f"setup_{timestamp}_{status}.log"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(TMP_LOG_FILE), dest)
            print(f"Setup log saved to {dest}")
    except Exception:
        pass

def safe_exit(code=1, error=None):
    try:
        if error is not None:
            with TMP_LOG_FILE.open("a", encoding="utf-8") as fh:
                fh.write(f"+++++++++\n[ERROR] {time.strftime('%Y-%m-%d %H:%M:%S')}: {repr(error)}\n")
                fh.write(traceback.format_exc())
    except Exception:
        pass
    finalize_log(exit_code=code)
    clean_reex_flag()
    sys.exit(code)

def log_line(msg=None, error=None, context=None):
    try:
        prefix = "INFO" if msg else "ERROR"
        log_text = msg if msg else error
        sep = "-" * 30
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        header = f"\n{sep}\n[-- {timestamp}] Logging {context}\n\n"
        TMP_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with TMP_LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(header)
            fh.write(f"[{prefix}] {log_text}\n")
    except Exception:
        pass

def run_command(cmd, log_out=True, show_output=False, check=False):
    global _LOG_INITIALIZED

    sep = "-" * 60
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    header = f"\n{sep}\n[--- {timestamp}] Running: {cmd}\n\n"

    TMP_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    mode = "w" if not _LOG_INITIALIZED else "a"
    with TMP_LOG_FILE.open(mode, encoding="utf-8") as fh:
        fh.write(header)
    _LOG_INITIALIZED = True

    process = subprocess.Popen(
        cmd, shell=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1
    )

    stdout_lines = []
    with TMP_LOG_FILE.open("a", encoding="utf-8") as logfh:
        for line in process.stdout:
            stdout_lines.append(line)
            if log_out:
                logfh.write(line)
            if show_output:
                print(line, end="")

    rc = process.wait()

    result = subprocess.CompletedProcess(
        args=cmd,
        returncode=rc,
        stdout="".join(stdout_lines),
        stderr=""
    )

    if check and result.returncode != 0:
        print(f"❌ Command failed (exit {result.returncode}): {cmd}")
        log_line(error=f"Command failed: {cmd} (rc={result.returncode})", context="run_command")
        safe_exit(1, error=f"Command failed (exit {result.returncode}): {result.stdout}")

    return result

def choose_language():
    global lang
    print(SETUP.get("choose_language", {}).get(lang, "Please choose your language:"))
    print(SETUP.get("language_options", {}).get(lang, "[1] English\n[2] Français"))
    choice = input(" > ").strip()
    if choice == "2":
        lang = "fr"
    elif choice != "1":
        print(SETUP.get("invalid_choice", {}).get(lang, "Invalid choice. Defaulting to English."))

def get_moode_version():
    res = run_command("moodeutl --mooderel", log_out=True, show_output=False, check=False)
    if res.returncode == 0 and res.stdout:
        return res.stdout.strip().split()[0]
    return None

def check_moode_version():
    current = get_moode_version()
    if not current:
        print(SETUP.get("moode_detect_fail", {}).get(lang, "❌ Could not detect Moode version."))
        safe_exit(1)
    if tuple(map(int, current.split("."))) < tuple(map(int, REQUIRED_MOODE_VERSION.split("."))):
        print(SETUP.get("moode_too_old", {}).get(lang, "Moode too old.").format(current))
        safe_exit(1)
    print(SETUP.get("moode_ok", {}).get(lang, "✅ Moode version {} detected — OK.").format(current))

def install_apt_dependencies():
    print(SETUP["install_apt"][lang])
    missing = []
    for pkg in APT_DEPENDENCIES:
        res = run_command(f"dpkg -s {pkg}", log_out=False, show_output=False, check=False)
        if res.returncode != 0:
            missing.append(pkg)

    if missing:
        print(SETUP["apt_missing"][lang].format(", ".join(missing)))
        run_command(f"sudo apt-get update", log_out=False, show_output=True, check=False)
        run_command(f"sudo apt-get install -y {' '.join(missing)}", log_out=True, show_output=True, check=True)

    print(SETUP["apt_ok"][lang])

def safe_read_file_as_lines(path, critical=True):
    try:
        res = run_command(f"cat {path}", log_out=True, show_output=False, check=False)
        # run_command returns stdout as string for non-interactive
        return res.stdout.splitlines()
    except Exception as e1:
        log_line(error=f"❌ Failed to read file with sudo: {e1}", context="safe_read_file_as_lines")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.readlines()
        except Exception as e2:
            log_line(error=f"❌ Direct read of {path} failed: {e2}", context="safe_read_file_as_lines")
            if critical:
                safe_exit(1, error=f"❌ Direct read of {path} failed: {e2}")
            else:
                print(f"⚠️ Could not read {path}, continuing anyway or ctrl+c to quit and check what wrong.")
                return []

def safe_write_file_as_root(path, lines, critical=True):
    try:
        with tempfile.NamedTemporaryFile('w', delete=False, encoding="utf-8") as tmp:
            if isinstance(lines, list):
                for line in lines:
                    tmp.write(line if line.endswith("\n") else line + "\n")
            else:
                tmp.write(lines if lines.endswith("\n") else lines + "\n")
            tmp_path = tmp.name
        run_command(f"sudo cp {tmp_path} {path}", log_out=False, show_output=False, check=True)
        run_command(f"sudo rm -f {tmp_path}", log_out=False, show_output=False, check=False)
    except Exception as e:
        log_line(error=f"❌ Write file as root of {path} failed: {e}", context="safe_write_file_as_root")
        if critical:
            safe_exit(1, error=f"❌ Write file as root of {path} failed: {e}")
        else:
            print(f"⚠️ Write file as root of {path} failed, continuing anyway or ctrl+c to quit and check what wrong.")
            pass

def create_backup(file_path, critical=True):
    moode_version = get_moode_version()
    if os.path.exists(file_path):
        backup_path = f"{file_path}.olipi-back-moode{moode_version}"
        if os.path.exists(backup_path):
            print(SETUP["backup_exist"][lang].format(backup_path))
            pass
        else:
            try:
                run_command(f"sudo cp -p {file_path} {backup_path}", log_out=True, show_output=True, check=True)
                print(SETUP["backup_created"][lang].format(backup_path))
            except Exception as e:
                log_line(error=f"⚠ Backup of {file_path} failed: {e}", context="create_backup")
                if critical:
                    safe_exit(1, error=f"❌ Direct read of {file_path} failed: {e}")
                else:
                    print(f"⚠ Backup of {file_path} failed, continuing anyway or ctrl+c to quit and check what wrong.")
                    pass

def update_olipi_section(lines, marker, new_lines=None, replace_prefixes=None, clear=False):
    section_start = "# --- Olipi-moode START ---"
    section_end = "# --- Olipi-moode END ---"
    marker_line = f"# @marker: {marker}"
    # Normalize input
    new_lines = new_lines or []
    # If requested, remove any lines matching replace_prefixes **anywhere** in the file.
    if replace_prefixes:
        # Build regexes that match optional leading whitespace, optional comment sign, then the prefix
        patterns = [re.compile(r'^\s*(?:#\s*)?' + re.escape(p)) for p in replace_prefixes]
        cleaned = []
        for ln in lines:
            stripped = ln.rstrip("\n")
            # never remove section markers
            if stripped.strip() in (section_start, section_end) or stripped.lstrip().lower().startswith("# @marker:"):
                cleaned.append(ln)
                continue
            # if any pattern matches the line (after lstrip), skip it
            if any(pat.match(stripped) for pat in patterns):
                # skip this line (do not include in cleaned)
                continue
            cleaned.append(ln)
        lines = cleaned
    # Locate section boundaries
    start_idx = None
    end_idx = None
    for i, line in enumerate(lines):
        if line.strip() == section_start:
            start_idx = i
        elif line.strip() == section_end and start_idx is not None:
            end_idx = i
            break
    # If section not found, create it at the end of file
    if start_idx is None or end_idx is None:
        if lines and lines[-1].strip() != "":
            lines.append("\n")
        lines.append(section_start + "\n")
        lines.append(section_end + "\n")
        start_idx = len(lines) - 2
        end_idx = len(lines) - 1
    # Extract block content between START and END (list of lines, with newlines preserved)
    block = lines[start_idx + 1:end_idx]
    # Find marker inside the block
    marker_idx = None
    for i, line in enumerate(block):
        if line.strip().lower() == marker_line.lower():
            marker_idx = i
            break
    # If clear=True → remove the whole block under this marker (only inside block)
    if marker_idx is not None and clear:
        end_m = marker_idx + 1
        while end_m < len(block) and not block[end_m].lstrip().startswith("# @marker:"):
            end_m += 1
        block[marker_idx+1:end_m] = []
        lines[start_idx + 1:end_idx] = block
        return lines
    # Update or add marker section
    if marker_idx is not None and not clear:
        # Find block end (next marker or end of section)
        end_m = marker_idx + 1
        while end_m < len(block) and not block[end_m].lstrip().startswith("# @marker:"):
            end_m += 1
        # Replace or append new_lines under marker. Keep existing non-matching lines.
        # We keep existing lines, then append new_lines (like your "filtered extend" behavior).
        existing = block[marker_idx+1:end_m]
        # strip trailing newlines, re-add newline to ensure consistent formatting
        filtered = [l.rstrip("\n") + "\n" for l in existing]
        if new_lines:
            filtered.extend([l.rstrip("\n") + "\n" for l in new_lines])
        block[marker_idx+1:end_m] = filtered
    else:
        # Marker not found → append marker inside section, then new_lines
        # ensure marker line ends with newline
        block.append(marker_line + "\n")
        if not clear and new_lines:
            block.extend([l.rstrip("\n") + "\n" for l in new_lines])
    # Write back updated block into lines
    lines[start_idx + 1:end_idx] = block
    return lines

def safe_cleanup(path: Path, preserve_files=None, base: Path = None):
    preserve_files = preserve_files or []
    base = base or path
    for item in path.iterdir():
        rel_path = str(item.relative_to(base))
        # Skip preserved files
        if rel_path in preserve_files:
            continue
        try:
            if item.is_dir():
                safe_cleanup(item, preserve_files=preserve_files, base=base)
                item.rmdir()
            else:
                item.unlink()
        except PermissionError:
            # Try to fix permissions and remove as root if possible
            try:
                # Reset permissions so current user can delete
                item.chmod(0o777)
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    item.unlink(missing_ok=True)
            except Exception as e:
                # Last resort: try sudo rm -rf for root-owned files
                os.system(f"sudo rm -rf '{item}'")
                log_line(error=f"Forced cleanup with sudo for {item}: {e}", context="install_repo_cleanup (safe_cleanup)")
        except OSError as e:
            log_line(error=f"Failed to remove {item}: {e}", context="install_repo_cleanup (safe_cleanup)")


def move_contents(src: Path, dst: Path, preserve_files=None, base: Path = None):
    preserve_files = preserve_files or []
    base = base or src

    for item in src.iterdir():
        rel_path = str(item.relative_to(base))
        target = dst / item.name
        if item.is_dir():
            target.mkdir(exist_ok=True)
            move_contents(item, target, preserve_files, base=base)
        else:
            if rel_path in preserve_files and target.exists():
                continue
            shutil.move(str(item), str(target))

def merge_ini_with_dist(user_file: Path, dist_file: Path):
    def parse_ini_with_comments(lines):
        """Parse ini preserving comments and blank lines per section."""
        sections = {}
        current_section = None
        buffer = []
        for line in lines:
            m = re.match(r'^\s*\[([^\]]+)\]\s*$', line)
            if m:
                if current_section:
                    sections[current_section] = buffer
                current_section = m.group(1)
                buffer = [line]
            else:
                buffer.append(line)

        if current_section:
            sections[current_section] = buffer
        return sections
    def extract_key_info(lines):
        """Extract info on each key: value and whether it was commented."""
        info = {}
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("###"):
                continue
            m = re.match(r'^([#\s]*)([^#;=\s]+)\s*=\s*(.*)$', line)
            if m:
                prefix, key, val = m.groups()
                info[key.strip()] = {
                    "value": val.strip(),
                    "commented": prefix.strip().startswith("#"),
                }
        return info
    # --- Load both files
    dist_lines = dist_file.read_text().splitlines()
    user_lines = user_file.read_text().splitlines()
    dist_sections = parse_ini_with_comments(dist_lines)
    user_sections = parse_ini_with_comments(user_lines)
    user_info = {s: extract_key_info(lines) for s, lines in user_sections.items()}
    merged_lines = []
    # --- Iterate through dist sections in order
    for section, dist_lines in dist_sections.items():
        merged_lines.append(f"[{section}]")
        dist_info = extract_key_info(dist_lines)
        user_vals = user_info.get(section, {})
        pending_comments = []
        for line in dist_lines[1:]:
            stripped = line.strip()
            # Blank line
            if not stripped:
                if pending_comments:
                    merged_lines.extend(pending_comments)
                    pending_comments = []
                merged_lines.append("")
                continue
            # Explanatory comment
            if stripped.startswith("###"):
                pending_comments.append(line)
                continue
            # Key (active or commented)
            m = re.match(r'^([#\s]*)([^#;=\s]+)\s*=\s*(.*)$', line)
            if m:
                prefix, key, val = m.groups()
                key = key.strip()
                val = val.strip()
                if pending_comments:
                    merged_lines.extend(pending_comments)
                    pending_comments = []
                if key in user_vals:
                    user_entry = user_vals[key]
                    # preserve comment state
                    prefix = "#" if user_entry["commented"] else ""
                    merged_lines.append(f"{prefix}{key} = {user_entry['value']}")
                else:
                    # keep dist line as is
                    merged_lines.append(line)
                continue
            # Other comment lines
            if stripped.startswith("#"):
                merged_lines.append(line)
                continue
            merged_lines.append(line)
        if pending_comments:
            merged_lines.extend(pending_comments)
        merged_lines.append("")
    # --- Append user-only sections
    for section in user_sections.keys():
        if section not in dist_sections:
            merged_lines.append(f"[{section}]")
            merged_lines.extend(user_sections[section][1:])
            merged_lines.append("")
    # Make a backup
    user = os.getenv("SUDO_USER") or os.getenv("USER") or "pi"
    home = Path("/home") / user
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_path = home / f"{user_file.name}.{timestamp}.bak"
    if user_file.exists():
        user_file.replace(backup_path)
    print(f"✅ backup file saved to {backup_path}")
    # Write new merged file
    user_file.write_text("\n".join(merged_lines) + "\n")

def sync_user_themes():
    themes_main = yaml.safe_load(THEME_PATH_MAIN.read_text(encoding="utf-8")) or {}
    default_theme = themes_main.get("default", {})
    theme_user = yaml.safe_load(THEME_PATH_USER.read_text(encoding="utf-8")) or {}
    changed = False
    def sync_dict(template: dict, user_dict: dict) -> dict:
        nonlocal changed
        res = {}
        for key, tval in template.items():
            if key in user_dict:
                uval = user_dict[key]
                if isinstance(tval, dict) and isinstance(uval, dict):
                    res[key] = sync_dict(tval, uval)
                else:
                    res[key] = deepcopy(uval)
            else:
                res[key] = deepcopy(tval)
                changed = True
        return res
    new_user = {}
    for theme_name, theme_val in theme_user.items():
        if not isinstance(theme_val, dict):
            new_user[theme_name] = deepcopy(default_theme)
            changed = True
        else:
            new_user[theme_name] = sync_dict(default_theme, theme_val)
    if changed:
        class FlowListDumper(yaml.SafeDumper):
            pass
        def _repr_list(dumper, data):
            if isinstance(data, list) and len(data) == 3 and all(isinstance(x, int) for x in data):
                return dumper.represent_sequence('tag:yaml.org,2002:seq', data, flow_style=True)
            if (
                isinstance(data, list)
                and len(data) == 2
                and (isinstance(data[0], (int, float)) or (isinstance(data[0], str) and re.match(r'^\d*\.?\d+$', data[0])))
                and isinstance(data[1], list)
                and len(data[1]) == 3
                and all(isinstance(x, int) for x in data[1])
            ):
                return dumper.represent_sequence('tag:yaml.org,2002:seq', data, flow_style=True)
            return dumper.represent_sequence('tag:yaml.org,2002:seq', data, flow_style=False)
        FlowListDumper.add_representer(list, _repr_list)
        backup = THEME_PATH_USER.with_suffix(".yaml.bak")
        THEME_PATH_USER.replace(backup)
        with THEME_PATH_USER.open("w", encoding="utf-8") as f:
            yaml.dump(new_user, f, Dumper=FlowListDumper, sort_keys=False, allow_unicode=True)
        print(SETUP.get("theme_user_updated", {}).get(lang, "🎨 User themes updated"))
    print(SETUP.get("theme_user_ok", {}).get(lang, "🎨 User themes already up to date"))

def copytree_safe(src, dst):
    def ignore_special_files(_, names):
        ignore = []
        for name in names:
            path = Path(src) / name
            # Ignore named pipes, sockets, block/char devices
            if path.is_fifo() or path.is_socket() or path.is_block_device() or path.is_char_device():
                ignore.append(name)
            # Ignore Python cache folders
            elif path.is_dir() and name == "__pycache__":
                ignore.append(name)
        return ignore
    shutil.copytree(src, dst, dirs_exist_ok=True, ignore=ignore_special_files)

def repo_url_to_slug(repo_url: str) -> str:
    # Accept either ssh or https
    if repo_url.startswith("git@github.com:"):
        slug = repo_url[len("git@github.com:"):].rstrip(".git")
    else:
        # strip https://github.com/
        slug = repo_url.replace("https://github.com/", "").replace("http://github.com/", "").rstrip(".git")
    return slug

def github_get_releases(slug: str):
    url = f"https://api.github.com/repos/{slug}/releases"
    headers = {"User-Agent": "OliPi-Setup-Script"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read().decode("utf-8")
            return json.loads(data)
    except urllib.error.HTTPError as e:
        log_line(error=f"GitHub API HTTPError: {e}", context="github_get_releases")
    except Exception as e:
        log_line(error=f"GitHub API error: {e}", context="github_get_releases")
    return []

def get_latest_release_tag(path_or_repo: str, branch: str = "main", include_prerelease: bool = True) -> str:
    # Local repo case
    if Path(path_or_repo).exists():
        rc = subprocess.run(
            f"git -C {path_or_repo} describe --tags --abbrev=0",
            shell=True, capture_output=True, text=True
        )
        if rc.returncode == 0:
            return rc.stdout.strip()
        return ""

    # Remote repo case -> use GitHub API
    slug = repo_url_to_slug(path_or_repo)
    releases = github_get_releases(slug)
    if not releases:
        return ""

    # iterate releases in API order (most recent first)
    for rel in releases:
        if rel.get("draft"):
            continue
        if not include_prerelease and rel.get("prerelease"):
            continue
        # If branch is not main, prefer releases that target that branch or whose tag contains branch
        target = rel.get("target_commitish", "") or ""
        tag = rel.get("tag_name", "") or ""
        if branch == "main":
            # accept the first suitable release
            return tag
        else:
            # prefer releases specifically targeting the branch or having branch in tag
            if target == branch or (branch in tag):
                return tag
    # fallback: return first non-draft (maybe prerelease) if nothing matched
    for rel in releases:
        if not rel.get("draft"):
            if not include_prerelease and rel.get("prerelease"):
                continue
            return rel.get("tag_name", "") or ""
    return ""

def parse_semver_prefix(tag: str):
    if not tag:
        return ()
    # match leading digits and dots
    m = re.match(r"v?(\d+(?:\.\d+)*)", tag)
    if not m:
        return ()
    parts = tuple(int(p) for p in m.group(1).split("."))
    return parts

def version_is_newer(local: str, remote: str) -> bool:
    try:
        lp = parse_semver_prefix(local)
        rp = parse_semver_prefix(remote)
        if not rp:
            return False
        if not lp:
            return True
        # compare lexicographically
        return rp > lp
    except Exception:
        return False

def compare_version(local, remote):
    if not local:
        local_version = "0.0.0"

    local_version = local.lstrip("v").split("-")[0]
    remote_version = remote.lstrip("v").split("-")[0]

    l_major, l_minor, l_patch = map(int, local_version.split("."))
    r_major, r_minor, r_patch = map(int, remote_version.split("."))

    if r_major == 0:
        # Mode "unstable": minor bump = breaking
        if r_minor > l_minor:
            return "major"
        elif r_minor == l_minor and r_patch > l_patch:
            return "minor"
    else:
        # Mode stable: SemVer strict
        if r_major > l_major:
            return "major"
        elif r_major == l_major and r_minor > l_minor:
            return "minor"
        elif r_major == l_major and r_minor == l_minor and r_patch > l_patch:
            return "patch"

    return "same"

def load_mergeable_files(repo_dir: Path):
    mergeable_file = Path(repo_dir) / ".mergeable_files.json"
    if not mergeable_file.exists():
        return [], []
    try:
        with mergeable_file.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            mergeable = data.get("mergeable", []) or []
            force_on_major = data.get("force_on_major", []) or []
            # normalize to list of strings
            mergeable = [str(x) for x in mergeable]
            force_on_major = [str(x) for x in force_on_major]
            return mergeable, force_on_major
        elif isinstance(data, list):
            # shorthand: list == mergeable
            return [str(x) for x in data], []
    except Exception as e:
        log_line(error=f"Failed to load mergeable files: {e}", context="load_mergeable_files")
    return [], []

def install_repo(repo_name: str, repo_url: str, local_dir: Path, branch: str, mode: str = "install") -> Path:

    print(SETUP.get(f"install_{repo_name.lower()}", {}).get(lang, f"Installing {repo_name}..."))

    local_dir = Path(local_dir)
    repo_exists = local_dir.exists() and (local_dir / ".git").exists()

    # determine remote and local tags
    remote_tag = "dev" if mode == "dev_mode" else get_latest_release_tag(repo_url, branch=branch) or ""
    local_tag = ""
    if repo_exists:
        local_tag = get_latest_release_tag(str(local_dir), branch=branch) or ""

    # clone into a temp dir
    temp_dir = local_dir.parent / (local_dir.name + "_tmp_clone")
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    run_command(f"git clone --branch {branch} {repo_url} {temp_dir}", log_out=True, show_output=True, check=True)
    print(SETUP.get(f"{repo_name.lower()}_cloned", {}).get(lang, f"✅ {repo_name} has been cloned to {temp_dir}").format(temp_dir))

    # checkout tag if not dev
    effective_remote_tag = "dev"
    if mode != "dev_mode" and remote_tag:
        run_command(f"git -C {temp_dir} fetch --tags origin", log_out=True, show_output=False, check=False)
        if remote_tag not in ("", "tag not found"):
            run_command(f"git -C {temp_dir} checkout {remote_tag}", log_out=True, show_output=False, check=False)
            effective_remote_tag = remote_tag

    # load mergeable files declared in repo we just cloned
    mergeable_files, repo_force_on_major = load_mergeable_files(temp_dir)
    if mergeable_files:
        print(SETUP.get("found_mergeable", {}).get(lang, "⚙️ Found mergeable files for {}: {}").format(repo_name, mergeable_files or "none"))
    log_line(msg=f"Mergeable files for {repo_name}: {mergeable_files} / force_on_major: {repo_force_on_major}", context="install_repo")

    # decide change_type (patch/minor/major) if we had a local repo
    change_type = "same"
    if repo_exists and effective_remote_tag and local_tag:
        try:
            change_type = compare_version(local_tag, effective_remote_tag)
        except Exception:
            change_type = "same"

    if mode == "dev_mode":
        print(f"\n⚙️ Dev mode detected for {repo_name}. Choose config handling:")
        print(" [1] Preserve all mergeable files (same as Patch Update)")
        print(" [2] Merge .dist into existing mergeable files (same as Minor Update)")
        print(" [3] Force-reset mergeable files (overwrite from .dist) (same as Major Update)")
        ans = input("Select [1-3] > ").strip()
        if ans not in ("1","2","3"):
            ans = "1"
        if ans == "1":
            change_type = "patch"
        elif ans == "2":
            change_type = "minor"
        elif ans == "3":
            change_type = "major"

    # Force-reset files = intersection of repo-declared force_on_major and mergeable files
    force_reset_files = []
    force_reset = False
    if change_type == "major":
        force_reset_files = [f for f in repo_force_on_major if f in mergeable_files]
        if force_reset_files:
            choice = input(SETUP.get("found_force_dist", {}).get(lang, "\n⚙️ Major update → Do you want to force a reset for OliPi-{}: {} ? [Y/n]").format(repo_name, force_reset_files or "none") + " > ").strip().lower()
            if choice in ["", "y", "o"]:
                force_reset = True
            else:
                force_reset = False

    # Update preserve files: mergeable files must be preserved during cleanup/move
    current_preserve = set(PRESERVE_FILES.get(repo_name.lower(), []) or [])
    current_preserve.update(mergeable_files)
    preserve_files = list(current_preserve)

    # ensure local dir exists then clean preserving listed files
    if local_dir.exists():
        print(SETUP.get("cleaning_local", {}).get(lang, "⚡ Cleaning up {} (preserve: {})").format(local_dir, preserve_files))
        log_line(msg=f"Cleaning up {local_dir} (preserve: {preserve_files})", context="install_repo")
        safe_cleanup(local_dir, preserve_files=preserve_files)
    else:
        local_dir.mkdir(parents=True, exist_ok=True)

    # move cloned files into place, keeping preserved files
    print(SETUP.get("moving_files", {}).get(lang, "📦 Moving cloned files from {} to {}").format(temp_dir, local_dir))
    move_contents(temp_dir, local_dir, preserve_files=preserve_files)
    shutil.rmtree(temp_dir)
    print(SETUP.get("clone_done", {}).get(lang, "✅ Done! {} deleted.").format(temp_dir))

    # Handle mergeable files: either reset on major (with backup) or merge .dist into user file or skip
    if change_type == "patch":
        print(SETUP["patch_skip_merge"][lang])
    else:
        for f in mergeable_files:
            user_file = local_dir / f
            dist_file = local_dir / f"{f}.dist"

            # if explicit force-reset for this file (only on major)
            if f in force_reset_files and force_reset:
                if user_file.exists():
                    user = os.getenv("SUDO_USER") or os.getenv("USER") or "pi"
                    home = Path("/home") / user
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    backup_path = home / f"{user_file.name}.{timestamp}.bak"
                    user_file.replace(backup_path)
                    print(SETUP["backup_file"][lang].format(user_file.name, backup_path))
                    log_line(msg=f"Back up file {user_file.name} → {backup_path}", context="install_repo")
                if dist_file.exists():
                    shutil.copy2(dist_file, user_file)
                    print(SETUP["forced_overwrite"][lang].format(user_file.name, dist_file.name))
                    log_line(msg=f"Force overwrite for {dist_file} → {user_file}", context="install_repo")
                continue

            if not user_file.exists() and dist_file.exists():
                shutil.copy2(dist_file, user_file)
                print(SETUP["create_file"][lang].format(user_file.name, dist_file.name))
                log_line(msg=f"{user_file.name} does not exist, create the file from {dist_file.name}", context="install_repo")

            # normal merge if .dist exists
            elif user_file.exists() and dist_file.exists():
                merge_ini_with_dist(user_file, dist_file)
                print(SETUP["merged_file"][lang].format(user_file.name, dist_file.name))
                log_line(msg=f"Merged file {user_file} with {dist_file}", context="install_repo")
            else:
                print(SETUP["no_dist"][lang].format(user_file.name))

    log_line(msg=f"{repo_name} installed/updated. branch:{branch}", context="install_repo")
    return local_dir

# --- thin wrappers for specific repos --------------------------------------
def install_olipi_core(mode="install"):
    return install_repo(
        repo_name="Core",
        repo_url=OLIPI_CORE_REPO,
        local_dir=Path(OLIPI_CORE_DIR),
        branch=(OLIPI_CORE_DEV_BRANCH if mode == "dev_mode" else "main"),
        mode=mode
    )

def install_olipi_moode(mode="install"):
    return install_repo(
        repo_name="Moode",
        repo_url=OLIPI_MOODE_REPO,
        local_dir=Path(OLIPI_MOODE_DIR),
        branch=(OLIPI_MOODE_DEV_BRANCH if mode == "dev_mode" else "main"),
        mode=mode
    )

def check_i2c(core_config):
    print(SETUP["i2c_check"][lang])
    lines = safe_read_file_as_lines(CONFIG_TXT, critical=True)
    lines = update_olipi_section(lines, "screen overlay", clear=True)
    # Ask raspi-config whether I2C is enabled
    result = run_command("sudo raspi-config nonint get_i2c", log_out=True, show_output=False, check=False)
    if result.returncode != 0 or result.stdout.strip() != "0":
        choice = input(SETUP["i2c_disabled"][lang] + " > ").strip().lower()
        if choice in ["", "y", "o"]:
            print(SETUP["i2c_enabling"][lang])
            # add commented dtparam in olipi section so that raspi-config doesn't add the overlay anywhere
            lines = update_olipi_section(lines, "screen overlay", ["#dtparam=i2c_arm=on"], replace_prefixes=["dtparam=i2c_arm=on"])
            safe_write_file_as_root(CONFIG_TXT, lines, critical=True)
            run_command("sudo raspi-config nonint do_i2c 0", log_out=True, show_output=False, check=True)
            print(SETUP["i2c_enabled"][lang])
            lines = safe_read_file_as_lines(CONFIG_TXT, critical=True)
        else:
            print(SETUP["i2c_enable_failed"][lang])
            return "CANCEL"
    lines = update_olipi_section(lines, "screen overlay", ["dtparam=i2c_baudrate=400000"], replace_prefixes=["dtparam=i2c_baudrate"])
    safe_write_file_as_root(CONFIG_TXT, lines, critical=True)
    # run i2cdetect (retry a few times)
    res = None
    for _ in range(10):
        res = run_command("i2cdetect -y 1", log_out=True, show_output=False, check=False)
        if res and res.stdout.strip():
            break
        time.sleep(1)
    detected_addresses = []
    if res and res.stdout:
        for line in res.stdout.splitlines():
            if ":" in line:
                parts = line.split(":")[1].split()
                for part in parts:
                    if part != "--":
                        detected_addresses.append(part.lower())
    if not detected_addresses:
        # no devices found -> offer options
        print(SETUP["i2c_no_devices"][lang])
        print(SETUP["i2c_check_wiring"][lang])
        # give user choices: retry / back / skip / cancel
        while True:
            ans = input(SETUP.get("i2c_no_dev_options", {}).get(lang,
                         "[0] Back to screens / [s] Skip config / [x] Cancel install > ")).strip().lower()
            if not ans:
                print(SETUP["prompt_invalid"][lang])
                continue
            if ans in ("0", "b", "r", "back"):
                return "BACK"
            if ans in ("s", "p", "skip"):
                return "SKIP"
            if ans in ("x", "q", "a", "cancel"):
                return "CANCEL"
            print(SETUP["prompt_invalid"][lang])
    # If we have addresses, show them and allow selection with navigation options
    print(SETUP["i2c_addresses_detected"][lang].format(", ".join(["0x" + addr for addr in detected_addresses])))
    if "3c" in detected_addresses or "3d" in detected_addresses:
        default_addr = "3c" if "3c" in detected_addresses else "3d"
        print(SETUP["i2c_display_ok"][lang].format("0x" + default_addr))
    print()
    print(SETUP.get("i2c_choose_detected", {}).get(lang, "Choose the I2C address from the list above:"))
    for i, addr in enumerate(detected_addresses, start=1):
        print(f"[{i}] 0x{addr}")
    print(SETUP.get("i2c_choose_actions", {}).get(lang, "[0] Back to screens / [s] Skip config / [x] Cancel install")) 
    while True:
        choice = input("> ").strip().lower()
        if not choice:
            print(SETUP["prompt_invalid"][lang])
            continue
        if choice in ("0", "b", "back"):
            return "BACK"
        if choice in ("s", "skip"):
            return "SKIP"
        if choice in ("x", "q", "cancel"):
            return "CANCEL"
        try:
            idx = int(choice) - 1
            if not (0 <= idx < len(detected_addresses)):
                raise IndexError()
        except Exception:
            print(SETUP["prompt_invalid"][lang])
            continue
        selected_addr = detected_addresses[idx]
        # Save in config.ini
        try:
            core_config.save_config("i2c_address", "0x" + selected_addr, section="screen", preserve_case=True)
            print(SETUP["i2c_saved"][lang].format("0x" + selected_addr))
            log_line(msg=f"Saved i2c_address = 0x{selected_addr} to config.ini", context="check_i2c")
        except Exception as e:
            print(SETUP.get("screen_save_fail", {}).get(lang, "❌ Failed to save to config.ini"))
            safe_exit(1, error=f"❌ Failed to save to config.ini {e}")
        return "OK"

def check_spi(core_config):
    print(SETUP["spi_check"][lang])
    lines = safe_read_file_as_lines(CONFIG_TXT, critical=True)
    lines = update_olipi_section(lines, "screen overlay", clear=True)
    # Ask raspi-config whether SPI is enabled (nonint getter)
    result = run_command("sudo raspi-config nonint get_spi", log_out=True, show_output=False, check=False)
    if result.returncode != 0 or result.stdout.strip() != "0":
        # SPI reported disabled -> offer to enable (requires reboot)
        choice = input(SETUP["spi_disabled"][lang] + " > ").strip().lower()
        if choice in ["", "y", "o"]:
            # dtparam=spi=on is absent by default on Moode audio, so we tell raspi-config where to write it:
            lines = update_olipi_section(lines, "screen overlay", ["#dtparam=spi=on"], replace_prefixes=["dtparam=spi=on"])
            safe_write_file_as_root(CONFIG_TXT, lines, critical=True)
            print(SETUP["spi_enabling"][lang])
            run_command("sudo raspi-config nonint do_spi 0", log_out=True, show_output=False, check=True)
            print(SETUP["spi_enabled"][lang])
        else:
            print(SETUP["spi_enable_failed"][lang])
            return "CANCEL"
    fb_active = ""
    res = run_command("dmesg | grep -i 'graphics fb.*spi'", log_out=True, show_output=False, check=False)
    fb_active_lines = res.stdout.strip().splitlines()
    if fb_active_lines:
        clean_lines = []
        for line in fb_active_lines:
            # retirer le timestamp initial entre crochets si présent
            clean_line = line
            if line.startswith("["):
                try:
                    clean_line = line.split("]", 1)[1].strip()
                except IndexError:
                    pass
            clean_lines.append(clean_line)
        display = "\n    ".join(clean_lines)
        print(SETUP["spi_fb_detected"][lang].format(display))
        log_line(msg=f"SPI framebuffer active:\n{display}", context="check_spi")
    devices = []
    for entry in Path("/sys/bus/spi/devices").iterdir():
        devices.append(entry.name)
    if devices:
        print(SETUP["spi_devices_detected"][lang].format(", ".join(devices)))
        log_line(msg=f"SPI devices found: {', '.join(devices)}", context="check_spi")
    return "OK"

def discover_screens_from_olipicore(olipi_core_dir):
    discovered = {}
    try:
        # ensure package is importable from OLIPI_MOODE_DIR
        if str(Path(OLIPI_MOODE_DIR)) not in sys.path:
            sys.path.insert(0, str(Path(OLIPI_MOODE_DIR)))
        # try to import the canonical registry if it exists inside olipi_core
        try:
            from olipi_core.screens import supported_screens as ss
            base = dict(getattr(ss, "SCREEN_METADATA", {}))
        except Exception as e:
            safe_exit(1, error=f"Screen discovery failed: {e}")
            base = {}
        for k, v in base.items():
            discovered.setdefault(k, v)
    except Exception as e:
        safe_exit(1, error=f"Screen discovery failed: {e}")
    log_line(msg=f"Discovered {len(discovered)} supported screens", context="discover_screens")
    return discovered

def configure_screen(olipi_moode_dir, olipi_core_dir):
    os.environ["OLIPI_DIR"] = str(Path(olipi_moode_dir))
    if str(Path(olipi_moode_dir)) not in sys.path:
        sys.path.insert(0, str(Path(olipi_moode_dir)))
    try:
        from olipi_core import core_config
    except Exception as e:
        print(SETUP.get("screen_discovery_fail", {}).get(lang, "❌ Could not import olipi_core.core_config; screen setup will be skipped."))
        safe_exit(1, error=f"❌ Could not import olipi_core.core_config; screen setup will be skipped. {e}")
        return False

    screens = discover_screens_from_olipicore(olipi_core_dir)
    if not screens:
        print(SETUP.get("screen_none_found", {}).get(lang, "No screen modules found."))
        safe_exit(1, error=f"❌ No screen found.")
        return False

    keys = sorted(screens.keys())

    while True:
        print(SETUP.get("screen_choose_list", {}).get(lang, "\nAvailable screens:"))
        for i, key in enumerate(keys, start=1):
            info = screens[key]
            print(f"  [{i}] {key} — {info.get('resolution')} — {info.get('type').upper()} — {info.get('color')}")
        
        print(SETUP.get("screen_skip_option", {}).get(lang, "\n  [0] Skip screen configuration"))
        print(SETUP.get("screen_cancel_option", {}).get(lang, "  [x] Cancel installation"))

        # ask user (no default)
        choice = input(SETUP.get("screen_choose_prompt", {}).get(lang, "\nChoose your screen by number > ")).strip().lower()
        if not choice:
            print(SETUP.get("screen_invalid_choice", {}).get(lang, "Invalid choice. Please enter a number, 0 to skip, or x to cancel."))
            continue

        if choice in ("0", "s", "skip"):
            # return True to continue install
            #core_config.save_config("current_screen", "NONE", section="screen", preserve_case=True)
            log_line(msg="User skipped screen configuration", context="configure_screen")
            print(SETUP.get("screen_skipped", {}).get(lang, "⏭ Screen configuration skipped."))
            return True

        if choice in ("x", "q", "cancel"):
            print(SETUP.get("interactive_abort", {}).get(lang))
            safe_exit(0)

        # numeric selection
        try:
            idx = int(choice)
            if not (1 <= idx <= len(keys)):
                raise ValueError("out of range")
        except Exception:
            print(SETUP.get("screen_invalid_choice", {}).get(lang, "Invalid choice. Please enter a valid number."))
            continue

        selected = keys[idx - 1]
        meta = screens[selected]
        selected_id = meta["id"]
        print(SETUP.get("screen_selected", {}).get(lang, "Selected: {}").format(selected))
        log_line(msg=f"User selected screen {selected} (type={meta.get('type')})", context="configure_screen")

        create_backup(CONFIG_TXT)

        # If I2C or SPI do their checks; check_i2c may ask to go BACK or SKIP
        if meta["type"] == "i2c":
            res = check_i2c(core_config)
            if res == "BACK":
                # loop again to rechoose a screen
                continue
            if res == "SKIP":
                # user asked to skip -> save NONE and return True
                try:
                    core_config.save_config("current_screen", "NONE", section="screen", preserve_case=True)
                    log_line(msg="Saved current_screen = NONE (user skipped during i2c)", context="configure_screen")
                except Exception:
                    pass
                print(SETUP.get("screen_skipped", {}).get(lang, "⏭ Screen configuration skipped."))
                return True
            if res == "CANCEL":
                safe_exit(130)
            # res == "OK" -> continue

        elif meta["type"] == "spi":
            res = check_spi(core_config)
            if res == "CANCEL":
                safe_exit(130)
            # res == "OK" -> continue

        try:
            core_config.save_config("current_screen", selected_id.upper(), section="screen", preserve_case=True)
            log_line(msg=f"Saved current_screen = {selected_id} to config.ini", context="configure_screen")
        except Exception as e:
            print(SETUP.get("screen_save_fail", {}).get(lang, "❌ Failed to save screen to config.ini"))
            safe_exit(1, error=f"❌ Failed to save screen to config.ini. {e}")
            return False

        # If SPI -> ask pins and save them
        if meta.get("type") == "spi":
            print(SETUP.get("screen_spi_info", {}).get(lang, "SPI screen selected — Enter the GPIO pin number (BCM)."))
            dc = input(SETUP.get("screen_dc_prompt", {}).get(lang, "DC pin (data/command) > "))
            rst = input(SETUP.get("screen_reset_prompt", {}).get(lang, "RESET pin > "))
            bl = input(SETUP.get("screen_bl_prompt", {}).get(lang, "BL pin (backlight) — leave empty if none) > "))

            selected_fbname = meta.get("fbname")
            speed = meta.get("speed", None)
            txbuflen = meta.get("txbuflen", None)

            lines = safe_read_file_as_lines(CONFIG_TXT, critical=True)
            overlay_line = f"dtoverlay=fbtft,spi0-0,{selected_fbname.lower()},reset_pin={rst},dc_pin={dc}"
            if bl:
                overlay_line += f",led_pin={bl}"
            if speed:
                overlay_line += f",speed={speed}"
            if txbuflen:
                overlay_line += f",txbuflen={txbuflen}"
            new_lines = [overlay_line]
            lines = update_olipi_section(lines, "screen overlay", new_lines, replace_prefixes=["dtoverlay=fbtft"])

            safe_write_file_as_root(CONFIG_TXT, lines, critical=True)

            core_config.reload_config()
            print(SETUP.get("screen_saved_ok", {}).get(lang, "Screen configuration saved."))
            return True

        # If I2C just reload config and finish
        core_config.reload_config()
        print(SETUP.get("screen_saved_ok", {}).get(lang, "Screen configuration saved."))
        return True

def check_ram():
    res = run_command("dpkg -s zram-tools >/dev/null 2>&1", log_out=False, show_output=False, check=False)
    zram_tools_installed = (res.returncode == 0)
    res = run_command("dpkg -s systemd-zram-generator >/dev/null 2>&1", log_out=False, show_output=False, check=False)
    zram_generator_installed = (res.returncode == 0)
    if zram_tools_installed:
        print(SETUP.get("zram_migrating", {}).get(lang, "Migrating to systemd-zram-generator..."))
        run_command("sudo systemctl stop olipi-ui-playing.service", log_out=True, show_output=False, check=False)
        run_command("sudo systemctl stop zramswap.service", log_out=True, show_output=False, check=False)
        run_command("sudo systemctl disable zramswap.service", log_out=True, show_output=False, check=False)
        run_command("sudo apt-get update", log_out=True, show_output=False, check=False)
        run_command("sudo apt-get purge -y zram-tools", log_out=True, show_output=True, check=False)
        run_command("sudo apt-get autoremove -y", log_out=True, show_output=False, check=False)
        run_command("sudo systemctl daemon-reload", log_out=True, show_output=False, check=False)
        if Path("/etc/default/zramswap.olipi-bak").exists():
            try:
                run_command("sudo rm -f /etc/default/zramswap.olipi-bak", log_out=True, show_output=False, check=False)
            except Exception:
                pass
        run_command("sudo apt-get update", log_out=True, show_output=False, check=False)
        res = run_command("sudo apt-get install -y systemd-zram-generator", log_out=True, show_output=True, check=False)
        if res.returncode == 0:
            print(SETUP.get("zram_done", {}).get(lang, "ZRAM configured, reboot required."))
            reboot = input(SETUP["reboot_prompt"][lang]).strip().lower()
            if reboot in ["", "o", "y"]:
                run_command("sudo reboot", log_out=True, show_output=True, check=False)
            else:
                print(SETUP["reboot_cancelled"][lang])
        else:
            print(SETUP.get("zram_failed", {}).get(lang, "❌ Failed to configure ZRAM."))
            safe_exit(1)
        return
    if not zram_generator_installed:
        print(SETUP.get("zram_installing", {}).get(lang, "Installing systemd-zram-generator..."))

        run_command("sudo apt-get update", log_out=True, show_output=False, check=False)
        res = run_command("sudo apt-get install -y systemd-zram-generator",
                          log_out=True, show_output=True, check=False)
        if res.returncode == 0:
            print(SETUP.get("zram_done", {}).get(lang, "ZRAM installed, reboot required."))
            reboot = input(SETUP["reboot_prompt"][lang]).strip().lower()
            if reboot in ["", "o", "y"]:
                run_command("sudo reboot", log_out=True, show_output=True, check=False)
            else:
                print(SETUP["reboot_cancelled"][lang])
        else:
            print(SETUP.get("zram_failed", {}).get(lang, "❌ Failed to install ZRAM."))
            safe_exit(1)

def check_virtualenv():
    if os.path.exists(DEFAULT_VENV_PATH):
        print(SETUP["venv_found"][lang].format(DEFAULT_VENV_PATH))
        print(SETUP["venv_reuse_choice"][lang])
        while True:
            choice = input(" > ").strip()
            if choice == "1":
                print(SETUP["venv_reuse_update"][lang].format(DEFAULT_VENV_PATH))
                log_line(msg="Reuse and update Virtual environment", context="setup_virtualenv")
                return True
            elif choice == "2":
                print(SETUP["venv_delete"][lang])
                log_line(msg="Virtual environment deleted", context="check_virtualenv")
                try:
                    shutil.rmtree(DEFAULT_VENV_PATH)
                except Exception as e:
                    print(f"❌ Failed to delete {DEFAULT_VENV_PATH}: {e}")
                    safe_exit(1, e)
                return True
            elif choice == "3":
                print(SETUP["venv_skipped"][lang])
                log_line(msg="venv configuration skipped by user", context="check_virtualenv")
                return False
            else:
                print(SETUP["prompt_invalid"][lang])
    return DEFAULT_VENV_PATH

def setup_virtualenv(venv_path):
    requirements_path = os.path.join(OLIPI_MOODE_DIR, "requirements.txt")
    if not os.path.exists(venv_path):
        print(SETUP["venv_install"][lang].format(venv_path))
        run_command(f"python3 -m venv --system-site-packages {venv_path}", log_out=True, show_output=True, check=True)
    pip_path = os.path.join(venv_path, "bin", "pip")
    if not os.path.isfile(pip_path):
        print(f"❌ pip not found in the virtual environment at {pip_path}.")
        log_line(error=f"❌ pip not found in the virtual environment at {pip_path}.", context="setup_virtualenv")
        safe_exit(1)
    print("⬆️ Upgrading pip ...")
    # ----- Free memory before heavy install -----
    # Stop services
    run_command("sudo systemctl stop olipi-ui-playing", log_out=True, show_output=False, check=False)
    run_command("mpc stop", log_out=True, show_output=False, check=False)
    run_command("sudo systemctl stop mpd", log_out=True, show_output=False, check=False)
    # Drop caches
    run_command("sudo sync", log_out=True, show_output=True, check=False)
    run_command("sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches'", log_out=True, show_output=True, check=False)
    # -------------------------------------------
    run_command(f"{pip_path} install --upgrade pip", log_out=True, show_output=True, check=True)
    print(SETUP["install_requirement"][lang])
    if not os.path.isfile(requirements_path):
        print(f"⚠️ requirements.txt not found at {requirements_path}, skipping dependency install.")
        log_line(error="❌ requirements.txt not found — Cancel install", context="setup_virtualenv")
        safe_exit(1)
    run_command(f"{pip_path} install --prefer-binary --no-cache-dir --upgrade --requirement {requirements_path}", log_out=True, show_output=True, check=True)
    # Restart MPD service after install
    run_command("sudo systemctl start mpd", log_out=True, show_output=True)
    log_line(msg="Virtual environment setup/update complete", context="setup_virtualenv")

def detect_user():
    user = os.getenv("SUDO_USER") or os.getenv("USER") or "pi"
    print(SETUP["user_detected"][lang].format(user))
    return user

SERVICES = {
    "olipi-ui-playing": """[Unit]
Description=OliPi MoOde Now-Playing Screen (ui_playing)
After=network.target sound.target
Wants=sound.target
StartLimitIntervalSec=200
StartLimitBurst=10

[Service]
Type=simple
ExecStart={venv}/bin/python3 {project}/ui_playing.py
WorkingDirectory={project}
User={user}
Group={user}
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
""",
    "olipi-ui-browser": """[Unit]
Description=OliPi MoOde Library Browser Screen (ui_browser)
After=network.target sound.target
Wants=sound.target
StartLimitIntervalSec=200
StartLimitBurst=10

[Service]
Type=simple
ExecStart={venv}/bin/python3 {project}/ui_browser.py
WorkingDirectory={project}
User={user}
Group={user}
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
""",
    "olipi-ui-queue": """[Unit]
Description=OliPi MoOde Queue Management Screen (ui_queue)
After=network.target sound.target
Wants=sound.target
StartLimitIntervalSec=200
StartLimitBurst=10

[Service]
Type=simple
ExecStart={venv}/bin/python3 {project}/ui_queue.py
WorkingDirectory={project}
User={user}
Group={user}
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
""",
    "olipi-starting-wait": """[Unit]
Description=OliPi UI playing Wait for Moode Audio to be ready
After=network.target sound.target
Wants=sound.target
StartLimitIntervalSec=200
StartLimitBurst=10

[Service]
Type=simple
ExecStart={venv}/bin/python3 {project}/ui_wait.py
WorkingDirectory={project}
User={user}
Group={user}
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
""",
    "olipi-ui-off": """[Unit]
Description=OliPi Screen Off (ui_off)

[Service]
Type=oneshot
RemainAfterExit=true
ExecStart=/bin/true
ExecStop={venv}/bin/python3 {project}/ui_off.py

[Install]
WantedBy=multi-user.target
"""
}

def write_service(name, content):
    tmp_path = f"/tmp/{name}.service"
    target_path = f"/etc/systemd/system/{name}.service"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        log_line(error=f"Failed to write temp service file {tmp_path}: {e}", context="write_service")
        raise

    run_command(f"sudo mv {tmp_path} {target_path}", log_out=True, show_output=True, check=True)
    run_command(f"sudo chown root:root {target_path}", log_out=True, show_output=False, check=True)
    run_command("sudo systemctl daemon-reload", log_out=True, show_output=False, check=True)
    print(SETUP["service_created"][lang].format(name))
    log_line(msg=f"Service {name} installed at {target_path}", context="write_service")

def run_install_services(venv, user):
    project_path = OLIPI_MOODE_DIR
    log_line(msg=f"install_services started (user={user}, venv={venv})", context="run_install_services")
    print(SETUP["install_services"][lang])
    auto_enable = {
        "olipi-starting-wait",
        "olipi-ui-off",
    }
    for name, template in SERVICES.items():
        while True:         
            service_content = template.format(venv=venv, project=project_path, user=user)
            try:
                write_service(name, service_content)
                if name in auto_enable:
                    run_command(f"sudo systemctl enable {name}", log_out=True, show_output=False, check=True)
                    print(SETUP["service_enabled"][lang].format(name))
            except PermissionError:
                print(SETUP["permission_denied"][lang])
                safe_exit(1, error="Permission denied while writing/enabling service")
            except Exception as e:
                log_line(error=f"Failed to install service {name}: {e}", context="run_install_services")
                print(SETUP.get("service_save_failed", {}).get(lang, "❌ Failed to install service."))
            break          
    log_line(msg="install_services finished", context="run_install_services")

def append_to_profile():
    profile_path = os.path.expanduser("~/.profile")
    block_start = "# --- OliPi Reminder Start ---"
    block_end = "# --- OliPi Reminder Finish ---"
    lines_to_add = [
        'echo ""',
        'echo "Moode debug => moodeutl -l"',
        'echo "Force Moode update => sudo /var/www/util/system-updater.sh moode9"',
        f'echo "Update or Reinstall OliPi Moode => python3 {SETUP_SCRIPT_PATH}"',
        f'echo "Configure IR remote => python3 {INSTALL_LIRC_REMOTE_PATH}"',
        'echo ""'
    ]
    prefixes = [line.split()[0] for line in lines_to_add]  # ici "echo"
    print(SETUP["profile_update"][lang])
    log_line(msg="Appending to ~/.profile", context="append_to_profile")
    try:
        if os.path.exists(profile_path):
            with open(profile_path, "r", encoding="utf-8") as f:
                content_lines = [line.rstrip("\n") for line in f.readlines()]
        else:
            content_lines = []
        filtered_lines = []
        inside_old_block = False
        for line in content_lines:
            stripped = line.strip()
            if stripped == block_start:
                inside_old_block = True
                continue
            if stripped == block_end:
                inside_old_block = False
                continue
            if inside_old_block:
                continue
            if stripped == 'echo ""':
                continue
            if any(stripped.startswith(p) for p in prefixes):
                continue
            filtered_lines.append(line)
        filtered_lines.append(block_start)
        filtered_lines.extend(lines_to_add)
        filtered_lines.append(block_end)
        with open(profile_path, "w", encoding="utf-8") as f:
            f.write("\n".join(filtered_lines) + "\n")
        print(SETUP["profile_updated"][lang])
    except Exception as e:
        log_line(error=f"Failed to update profile: {e}", context="append_to_profile")
        print(SETUP["profile_update_error"][lang].format(e))

def install_done():
    print(SETUP["install_done"][lang])
    lirc_script = os.path.join(INSTALL_DIR, "install_lirc_remote.py")
    print(SETUP["controle_explanation"][lang].format(lirc_script))
    print(SETUP["moode_reminder"][lang])
    with TMP_LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(f"+++++++++\n[SUCCESS] ✅ install_olipi.py finished successfully")
    finalize_log(0)
    clean_reex_flag()
    reboot = input(SETUP["reboot_prompt"][lang]).strip().lower()
    if reboot in ["", "o", "y"]:
        run_command("sudo reboot", log_out=True, show_output=True, check=False)
    else:
        print(SETUP["reboot_cancelled"][lang])

def clean_reex_flag():
    try:
        if REEXEC_FLAG.exists():
            REEXEC_FLAG.unlink()
    except Exception:
        pass

def main():
    parser = argparse.ArgumentParser(description="OliPi setup (install / update / develop)")
    parser.add_argument("--install", action="store_true", help="Perform a full install of OliPi")
    parser.add_argument("--update", action="store_true", help="Update existing OliPi installation")
    parser.add_argument("--dev", action="store_true", help="Developer mode: use branches/latest commits instead of releases")
    args = parser.parse_args()

    choose_language()

    reexecuted = REEXEC_FLAG.exists()
    clean_reex_flag()

    if not reexecuted:
        check_ram()
        check_moode_version()

    # check if repos are present
    moode_present = Path(OLIPI_MOODE_DIR).exists() and (Path(OLIPI_MOODE_DIR) / ".git").exists()
    core_present = Path(OLIPI_CORE_DIR).exists() and (Path(OLIPI_CORE_DIR) / ".git").exists()

    # interactive command selection if not passed
    cmd = None
    if args.dev:
        cmd = "dev_mode"
    elif args.install:
        cmd = "install"
    elif args.update:
        cmd = "update"
    else:
        moode_change = ""
        core_change = ""
        if moode_present:
            local_tag_moode = get_latest_release_tag(OLIPI_MOODE_DIR, branch="main") or ""
            remote_tag_moode = get_latest_release_tag(OLIPI_MOODE_REPO, branch="main") or ""
            moode_change = compare_version(local_tag_moode, remote_tag_moode)
            print(f"OliPi-Moode: local version: {local_tag_moode} Latest version: {remote_tag_moode}")
        else:
            print(SETUP.get("repo_not_git", {}).get(lang, "⚠️ Folder {} does not exist or is not a Git repository. First install?").format(OLIPI_MOODE_DIR))
            
        if core_present:
            local_tag_core = get_latest_release_tag(OLIPI_CORE_DIR, branch="main") or ""
            remote_tag_core = get_latest_release_tag(OLIPI_CORE_REPO, branch="main") or ""
            core_change = compare_version(local_tag_core, remote_tag_core) 
            print(f"OliPi-Core: local version: {local_tag_core} Latest version: {remote_tag_core}")
        else:
            print(SETUP.get("repo_not_git", {}).get(lang, "⚠️ Folder {} does not exist or is not a Git repository. First install?").format(OLIPI_CORE_DIR))
            

        if moode_present and core_present:
            if moode_change == "same" and core_change == "same":
                ans = input(SETUP.get("already_uptodate", {}).get(lang, "✅ Already up-to-date. Force update [U], configure screen [C], complete install (I), or abort (A)? [U/C/I/A] ")).strip().lower()
                if ans == "u":
                    cmd = "update"
                elif ans == "i":
                    cmd = "install"
                elif ans == "c":
                    cmd = "config"
                else:
                    print(SETUP.get("interactive_abort", {}).get(lang))
                    safe_exit(0)

            elif moode_change == "major" or core_change == "major":
                ans = input(SETUP.get("interactive_major_prompt", {}).get(lang, "⚙️ Major update, A complete installation is required.\n  Proceed to installation [I] or abort [A]? [I/A] ")).strip().lower()
                if ans in ("i", ""):
                    cmd = "install"
                else:
                    print(SETUP.get("interactive_abort", {}).get(lang))
                    safe_exit(0)

            else:
                ans = input(SETUP.get("interactive_update_prompt", {}).get(lang, "⚙️ An update is available.\n  Perform an update [U], complete install (Update + Configuration)[I], or cancel [A]? [U/I/A] ")).strip().lower()
                if ans in ("u", ""):
                    cmd = "update"
                elif ans == "i":
                    cmd = "install"
                else:
                    print(SETUP.get("interactive_abort", {}).get(lang))
                    safe_exit(0)
        else:
            ans = input(SETUP.get("first_install_prompt", {}).get(lang, "⚙️ It seems that is a first installation, do you want to install [I] or abort [A]? [I/A] ")).strip().lower()
            if ans in ("i", ""):
                cmd = "install"
            else:
                print(SETUP.get("interactive_abort", {}).get(lang))
                safe_exit(0)

    try:
        if cmd == "dev_mode":
            print("install_olipi.py launched on dev mode...")
            if not reexecuted:
                skip = input("Skip cloning repo? [y/n] ").strip().lower()
                if skip not in ("o", "y"):
                    install_olipi_moode(mode="dev_mode")
                    install_olipi_core(mode="dev_mode")
                    try:
                        REEXEC_FLAG.parent.mkdir(parents=True, exist_ok=True)
                        REEXEC_FLAG.touch()
                    except Exception as e:
                        log_line(error=f"Failed creating reexec flag: {e}", context="main")
                        script_path = os.path.abspath(__file__)
                        print(SETUP.get("reexecut_script", {}).get(lang, "\n🔁 Re-executing freshly cloned install_olipi.py to pick up updates..."))
                        print(f"[debug] → relaunching with args: --dev")
                        os.execv(sys.executable, [sys.executable, script_path, "--dev"])
                else:
                    print("[dev] Repo cloning skipped")
            install_apt_dependencies()
            sync_user_themes()
            install_venv = check_virtualenv()
            if install_venv:
                setup_virtualenv(DEFAULT_VENV_PATH)
            configure_screen(OLIPI_MOODE_DIR, OLIPI_CORE_DIR)
            user = detect_user()
            run_install_services(DEFAULT_VENV_PATH, user)
            append_to_profile()
            install_done()
            print(SETUP.get("develop_done", {}).get(lang, "✅ Development mode setup complete."))

        elif cmd == "install":
            if not reexecuted:
                install_olipi_moode(mode="install")
                install_olipi_core(mode="install")
                try:
                    REEXEC_FLAG.parent.mkdir(parents=True, exist_ok=True)
                    REEXEC_FLAG.touch()
                except Exception as e:
                    log_line(error=f"Failed creating reexec flag: {e}", context="main")
                script_path = os.path.abspath(__file__)
                print(SETUP.get("reexecut_script", {}).get(lang, "\n🔁 Re-executing freshly cloned install_olipi.py to pick up updates..."))
                os.execv(sys.executable, [sys.executable, script_path, "--install"])
            install_apt_dependencies()
            sync_user_themes()
            install_venv = check_virtualenv()
            if install_venv:
                setup_virtualenv(DEFAULT_VENV_PATH)
            configure_screen(OLIPI_MOODE_DIR, OLIPI_CORE_DIR)
            user = detect_user()
            run_install_services(DEFAULT_VENV_PATH, user)
            append_to_profile()
            install_done()

        elif cmd == "update":
            if not reexecuted:
                install_olipi_moode(mode="update")
                install_olipi_core(mode="update")
                try:
                    REEXEC_FLAG.parent.mkdir(parents=True, exist_ok=True)
                    REEXEC_FLAG.touch()
                except Exception as e:
                    log_line(error=f"Failed creating reexec flag: {e}", context="main")
                script_path = os.path.abspath(__file__)
                print(SETUP.get("reexecut_script", {}).get(lang, "\n🔁 Re-executing freshly cloned install_olipi.py to pick up updates..."))
                os.execv(sys.executable, [sys.executable, script_path, "--update"])
            install_apt_dependencies()
            sync_user_themes()
            install_venv = check_virtualenv()
            if install_venv:
                setup_virtualenv(DEFAULT_VENV_PATH)
            append_to_profile()
            print(SETUP.get("update_done", {}).get(lang, "✅ Update complete."))
            with TMP_LOG_FILE.open("a", encoding="utf-8") as fh:
                fh.write(f"+++++++++\n[SUCCESS] ✅ Update finished successfully")
            finalize_log(0)
            reboot = input(SETUP["reboot_prompt"][lang]).strip().lower()
            if reboot in ["", "o", "y"]:
                run_command("sudo reboot", log_out=True, show_output=True, check=False)
            else:
                print(SETUP["reboot_cancelled"][lang])
            
        elif cmd == "config":
            configure_screen(OLIPI_MOODE_DIR, OLIPI_CORE_DIR)
            with TMP_LOG_FILE.open("a", encoding="utf-8") as fh:
                fh.write(f"+++++++++\n[SUCCESS] Screen configured successfully")
            finalize_log(0)
            reboot = input(SETUP["reboot_prompt"][lang]).strip().lower()
            if reboot in ["", "o", "y"]:
                run_command("sudo reboot", log_out=True, show_output=True, check=False)
            else:
                print(SETUP["reboot_cancelled"][lang])

        else:
            print("Unknown command")
            safe_exit(1)

    except KeyboardInterrupt:
        with TMP_LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(f"+++++++++\n[ABORTED] ❌ Installation interrupted by user (Ctrl+C).\n")
        print(SETUP["install_abort"][lang])
        clean_reex_flag()
        safe_exit(130)

    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        log_line(error=str(e), context="main")
        clean_reex_flag()
        safe_exit(1, error=e)

if __name__ == "__main__":
    main()
