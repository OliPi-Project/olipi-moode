#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2025 OliPi Project (Benoit Toufflet)

import os
import sys
import subprocess
import shutil
import time
import stat
import json
import traceback
import argparse
import urllib.request
import urllib.error
import re
from pathlib import Path
from lang import SETUP

# --- Constants ---
APT_DEPENDENCIES = [
    "git", "python3-pil", "python3-venv", "python3-pip", "python3-tk", "libasound2-dev", "libatlas-base-dev",
    "i2c-tools", "libgpiod-dev", "python3-libgpiod", "python3-lgpio", "python3-setuptools"
]

LOW_RAM_THRESHOLD_MB = 512
ZRAM_RECOMMENDED_MB = 256

REQUIRED_MOODE_VERSION = "9.3.7"
OLIPI_CORE_REPO = "https://github.com/OliPi-Project/olipi-core.git"
OLIPI_MOODE_REPO = "https://github.com/OliPi-Project/olipi-moode.git"
OLIPI_MOODE_DEV_BRANCH = "dev"
OLIPI_CORE_DEV_BRANCH = "dev"
PRESERVE_FILES = ["config.ini"] # path relative to local_dir e.g. ["config/user_key.ini, config.ini"]
CONFIG_FILES = ["config.ini"] # path relative to local_dir e.g. ["config/user_key.ini, config.ini"]

lang = "en"

INSTALL_DIR = os.path.dirname(os.path.abspath(__file__))  # directory containing setup.py
OLIPI_MOODE_DIR = os.path.dirname(INSTALL_DIR)  # parent → olipi-moode
OLIPI_CORE_DIR = os.path.join(OLIPI_MOODE_DIR, "olipi_core")
DEFAULT_VENV_PATH = os.path.expanduser("~/.olipi-moode-venv")
INSTALL_LIRC_REMOTE_PATH = os.path.join(INSTALL_DIR, "install_lirc_remote.py")
SETTINGS_FILE = Path(INSTALL_DIR) / ".setup-settings.json"
TMP_LOG_FILE = Path("/tmp/setup.log")

_LOG_INITIALIZED = False

# -----------------------
# Logging & shell helpers
# -----------------------
def finalize_log(exit_code=0):
    """Move the temporary log file to INSTALL_DIR/logs with status."""
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
    """Exit safely, log error if any, and finalize log."""
    try:
        if error is not None:
            with TMP_LOG_FILE.open("a", encoding="utf-8") as fh:
                fh.write(f"+++++++++\n[ERROR] {time.strftime('%Y-%m-%d %H:%M:%S')}: {repr(error)}\n")
                fh.write(traceback.format_exc())
    except Exception:
        pass
    finalize_log(exit_code=code)
    sys.exit(code)

def log_line(msg=None, error=None, context=None):
    """Append a short message to TMP_LOG_FILE."""
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
    """Run a shell command with logging and optional output display."""
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

# -----------------------
# Utilities
# -----------------------
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
        # critical: apt install must succeed -> use check=True but hide verbose apt output
        run_command(f"sudo apt-get update", log_out=False, show_output=True, check=True)
        run_command(f"sudo apt-get install -y {' '.join(missing)}", log_out=True, show_output=True, check=True)

    print(SETUP["apt_ok"][lang])

def safe_cleanup(path: Path, preserve_files=None, base: Path = None):
    """
    Delete contents of a directory but preserve specific files (by relative path).
    """
    preserve_files = preserve_files or []
    base = base or path

    for item in path.iterdir():
        rel_path = str(item.relative_to(base))
        if item.is_dir():
            safe_cleanup(item, preserve_files=preserve_files, base=base)
            try:
                item.rmdir()
            except OSError as e:
                log_line(error=f"Failed to remove {item}: {e}", context="install_repo_cleanup (safe_cleanup)")
        else:
            if rel_path in preserve_files:
                continue
            item.unlink()


def move_contents(src: Path, dst: Path, preserve_files=None, base: Path = None):
    """
    Move all files/dirs from src into dst, preserving some files (by relative path).
    """
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


def merge_ini_with_dist(user_file: Path, dist_file: Path, preserve_files=None, base: Path = None):
    """
    Merge dist file into user config file while preserving comments, formatting,
    and existing values. Adds new keys and their comments if missing.
    Skips merge if file is in preserve_files.
    """
    preserve_files = preserve_files or []
    base = base or user_file.parent.parent
    rel_path = str(user_file.relative_to(base))

    if rel_path in preserve_files:
        return

    if not dist_file.exists():
        return

    if not user_file.exists():
        user_file.write_text(dist_file.read_text(), encoding="utf-8")
        return

    user_lines = user_file.read_text(encoding="utf-8").splitlines()
    dist_lines = dist_file.read_text(encoding="utf-8").splitlines()

    existing_keys = set()
    current_section = None
    for line in user_lines:
        striped = line.strip()
        if striped.startswith("[") and striped.endswith("]"):
            current_section = striped
        elif striped and not striped.startswith(("#", ";")) and "=" in striped:
            key = striped.split("=", 1)[0].strip()
            existing_keys.add((current_section, key))

    merged_lines = []
    current_section = None
    current_section_dist = None

    for line in user_lines:
        merged_lines.append(line)
        striped = line.strip()
        if striped.startswith("[") and striped.endswith("]"):
            current_section = striped

            # look in the dist to see if there are any missing keys to add for this section
            dist_section_lines = []
            current_section_dist = None
            for idx, dline in enumerate(dist_lines):
                dstrip = dline.strip()
                if dstrip.startswith("[") and dstrip.endswith("]"):
                    current_section_dist = dstrip
                elif current_section_dist == current_section and "=" in dstrip and not dstrip.startswith(("#",";")):
                    key = dstrip.split("=",1)[0].strip()
                    if (current_section, key) not in existing_keys:
                        # Add comments above the key
                        comments_before = []
                        j = idx-1
                        while j>=0 and dist_lines[j].strip().startswith(("#",";")):
                            comments_before.insert(0, dist_lines[j])
                            j-=1
                        dist_section_lines.extend(comments_before+[dline])
            if dist_section_lines:
                merged_lines.extend(dist_section_lines)

    # Complete missing sections
    existing_sections = {line.strip() for line in user_lines if line.strip().startswith("[") and line.strip().endswith("]")}
    current_section_dist = None
    missing_section_lines = []
    for dline in dist_lines:
        dstrip = dline.strip()
        if dstrip.startswith("[") and dstrip.endswith("]"):
            current_section_dist = dstrip
            if current_section_dist not in existing_sections:
                missing_section_lines.append("")
                missing_section_lines.append(dline)
        elif current_section_dist and current_section_dist not in existing_sections:
            missing_section_lines.append(dline)

    if missing_section_lines:
        merged_lines.append("")
        merged_lines.extend(missing_section_lines)

    user_file.write_text("\n".join(merged_lines) + "\n", encoding="utf-8")

def save_settings(settings: dict):
    """Save setup settings to a JSON file for later use (update/uninstall)."""
    try:
        with SETTINGS_FILE.open("w", encoding="utf-8") as fh:
            json.dump(settings, fh, indent=2)
        log_line(msg=f"Saved settings: {settings}", context="save_settings")
    except Exception as e:
        log_line(error=f"Failed to save settings: {e}", context="save_settings")

def load_settings():
    if SETTINGS_FILE.exists():
        try:
            with SETTINGS_FILE.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            log_line(msg="Failed to load settings, initializing empty", context="load_settings")
            return {}
    return {}

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
    """Convert 'https://github.com/owner/repo.git' -> 'owner/repo'"""
    # Accept either ssh or https
    if repo_url.startswith("git@github.com:"):
        slug = repo_url[len("git@github.com:"):].rstrip(".git")
    else:
        # strip https://github.com/
        slug = repo_url.replace("https://github.com/", "").replace("http://github.com/", "").rstrip(".git")
    return slug

def github_get_releases(slug: str):
    """Return list of releases (raw JSON) for a repo from GitHub API, or [] on error."""
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
    """
    Return the latest release tag for the branch.
    - If path_or_repo is a local path and exists, inspect local repo tags reachable from branch.
    - If remote URL, call GitHub API and pick a release associated with the branch (or fallback).
    """
    # Local repo case
    if Path(path_or_repo).exists():
        # try to fetch tags and branch from origin
        run_command(f"git -C {path_or_repo} fetch --tags origin", log_out=True, show_output=False)
        run_command(f"git -C {path_or_repo} fetch origin {branch}", log_out=True, show_output=False)
        rc = subprocess.run(
            f"git -C {path_or_repo} tag --sort=-creatordate --merged origin/{branch} | head -n 1",
            shell=True, capture_output=True, text=True
        )
        if rc.returncode == 0:
            tag = rc.stdout.strip()
            return tag if tag else ""
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
    """Extract numeric prefix from tag like v1.2.3 or 1.2.3-moode -> returns (1,2,3)."""
    if not tag:
        return ()
    # match leading digits and dots
    m = re.match(r"v?(\d+(?:\.\d+)*)", tag)
    if not m:
        return ()
    parts = tuple(int(p) for p in m.group(1).split("."))
    return parts

def version_is_newer(local: str, remote: str) -> bool:
    """Return True if remote > local according to semantic-ish compare."""
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
    local_core = local.lstrip("v").split("-")[0]
    remote_core = remote.lstrip("v").split("-")[0]

    l_major, l_minor, l_patch = map(int, local_core.split("."))
    r_major, r_minor, r_patch = map(int, remote_core.split("."))

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

# -----------------------
# Repo install/update flow
# -----------------------
def install_repo(repo_name: str, repo_url: str, local_dir: Path, branch: str,
                 settings_keys: dict, mode: str = "install"):
 
    print(SETUP.get(f"install_{repo_name.lower()}", {}).get(lang,
          f"Installing {repo_name}..."))

    local_dir = Path(local_dir)
    remote_tag = "dev" if mode == "dev_mode" else get_latest_release_tag(repo_url, branch=branch) or "tag not found"
    local_tag = "unknown"

    repo_exists = local_dir.exists() and (local_dir / ".git").exists()
    if repo_exists:
        local_tag = get_latest_release_tag(str(local_dir), branch=branch) or "unknown"
        print(SETUP.get(f"{repo_name.lower()}_exists", {}).get(lang, f"{local_dir} already exists.").format(local_dir))

    update_needed = False
    if mode == "install":
        update_needed = True

    elif mode == "update":
        if not repo_exists:
            print(SETUP.get("repo_not_git", {}).get(lang, "⚠️ Folder {} exists but is not a Git repository. Update needed").format(local_dir))
            update_needed = True
        else:
            if version_is_newer(local_tag, remote_tag):
                upd_msg = SETUP.get("update_prompt", {}).get(lang, "✅  A newer release (local {}, remote {}) is available. Update now? [Y/n] ").format(local_tag, remote_tag)
            else:
                upd_msg = SETUP.get("already_uptodate", {}).get(lang, "✅ Already up-to-date (local {}, remote {}. Force Update? [Y/n]).").format(local_tag, remote_tag)
            ans = input(upd_msg).strip().lower()    
            if ans in ("", "y", "o"):
                update_needed = True

    elif mode == "dev_mode":
        update_needed = True

    if update_needed and repo_exists and repo_name.lower() == "moode":
        backup_ans = input(SETUP.get("repo_backup_prompt", {}).get(lang,
                            "⚠️ Folder {} already exists. Keep a backup before overwriting? [Y/n] ").format(local_dir)).strip().lower()
        if backup_ans in ("", "y", "o"):
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            backup_dir = local_dir.parent / f"{local_dir.name}_backup_{timestamp}"
            copytree_safe(local_dir, backup_dir)
            print(SETUP.get("repo_backup", {}).get(lang, "📦 Existing folder {} copied to {} before cloning.").format(local_dir, backup_dir))

    if not update_needed:
        log_line(msg=f"{repo_name} is already up-to-date (local {local_tag}, remote {remote_tag})", context="install_repo")
        return local_dir

    temp_dir = local_dir.parent / (local_dir.name + "_tmp_clone")
    if temp_dir.exists():
        shutil.rmtree(temp_dir)

    clone_cmd = f"git clone --branch {branch} {repo_url} {temp_dir}"
    run_command(clone_cmd, log_out=True, show_output=True, check=True)
    print(SETUP.get(f"{repo_name.lower()}_cloned", {}).get(lang, f"✅ {repo_name} has been cloned to {temp_dir}").format(temp_dir))

    if mode != "dev_mode" and remote_tag not in ("dev", "tag not found"):
        run_command(f"git -C {temp_dir} fetch --tags origin", log_out=True, show_output=False, check=False)
        run_command(f"git -C {temp_dir} checkout {remote_tag}", log_out=True, show_output=False, check=False)
        local_tag = remote_tag
    else:
        local_tag = "dev"

    cloned_settings_file = temp_dir / ".setup-settings.json"
    if cloned_settings_file.exists():
        with cloned_settings_file.open("r", encoding="utf-8") as fh:
            cloned_settings = json.load(fh)
        force_new_files = cloned_settings.get("force_new_files", {}).get(repo_name.lower(), [])
    else:
        force_new_files = []

    if local_dir.exists():
        safe_cleanup(local_dir, preserve_files=PRESERVE_FILES)
    else:
        local_dir.mkdir(parents=True, exist_ok=True)

    print(SETUP.get("moving_files", {}).get(lang, "📦 Moving cloned files from {} to {}...").format(temp_dir, local_dir))
    move_contents(temp_dir, local_dir, preserve_files=PRESERVE_FILES)
    temp_dir.rmdir()
    print(SETUP.get("clone_done", {}).get(lang, "✅ Done! {} deleted.").format(temp_dir))

    # Merge sensitive config files or force new file
    for cfg in CONFIG_FILES:
        dist_file = local_dir / f"{cfg}.dist"
        user_file = local_dir / cfg

        # Backup if forced
        if cfg in force_new_files and user_file.exists():
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            backup_file = user_file.parent / f"{user_file.name}_backup_{timestamp}"
            shutil.copy2(user_file, backup_file)
            print(f"Backed up {user_file.name} → {backup_file}")
            shutil.copy2(dist_file, user_file)
            print(f"Overwritten {user_file.name} with {cfg}.dist")
        elif dist_file.exists():
            merge_ini_with_dist(user_file, dist_file)
            print(f"Merged {cfg} with {cfg}.dist")

    log_line(msg=f"{repo_name} installed/updated. branch:{branch} tag:{local_tag}", context="install_repo")

    settings = load_settings()
    settings[settings_keys["branch"]] = branch
    settings[settings_keys["local_tag"]] = local_tag
    settings[settings_keys["remote_tag"]] = remote_tag
    save_settings(settings)

    return local_dir

def install_olipi_core(mode="install"):
    return install_repo(
        repo_name="Core",
        repo_url=OLIPI_CORE_REPO,
        local_dir=Path(OLIPI_CORE_DIR),
        branch=(OLIPI_CORE_DEV_BRANCH if mode=="dev_mode" else "main"),
        settings_keys={
            "branch": "branch_olipi_core",
            "local_tag": "local_tag_core",
            "remote_tag": "remote_tag_core"
        },
        mode=mode
    )

def install_olipi_moode(mode="install"):
    return install_repo(
        repo_name="Moode",
        repo_url=OLIPI_MOODE_REPO,
        local_dir=Path(OLIPI_MOODE_DIR),
        branch=(OLIPI_MOODE_DEV_BRANCH if mode=="dev_mode" else "main"),
        settings_keys={
            "branch": "branch_olipi_moode",
            "local_tag": "local_tag_moode",
            "remote_tag": "remote_tag_moode"
        },
        mode=mode
    )

def check_i2c():
    print(SETUP["i2c_check"][lang])
    result = run_command("sudo raspi-config nonint get_i2c", log_out=True, show_output=False, check=True)
    if result.returncode != 0 or result.stdout.strip() != "0":
        choice = input(SETUP["i2c_disabled"][lang] + " > ").strip().lower()
        if choice in ["", "y", "o"]:
            print(SETUP["i2c_enabling"][lang])
            # attempt to enable i2c (non-fatal here but requires reboot)
            run_command("sudo raspi-config nonint do_i2c 0", log_out=True, show_output=False, check=True)
            print(SETUP["i2c_enabled"][lang])
            print(SETUP["i2c_reboot_required"][lang])
        else:
            print(SETUP["i2c_enable_failed"][lang])
            safe_exit(1)

    for _ in range(3):
        res = run_command("i2cdetect -y 1", log_out=True, show_output=False, check=True)
        if res.stdout.strip():
            break
        time.sleep(1)

    detected_addresses = []
    for line in result.stdout.splitlines():
        if ":" in line:
            parts = line.split(":")[1].split()
            for part in parts:
                if part != "--":
                    detected_addresses.append(part.lower())
    if detected_addresses:
        print(SETUP["i2c_addresses_detected"][lang].format(", ".join(["0x" + addr for addr in detected_addresses])))
        if "3c" in detected_addresses or "3d" in detected_addresses:
            print(SETUP["i2c_display_ok"][lang])
        else:
            print(SETUP["i2c_no_display"][lang])
            print(SETUP["i2c_check_wiring"][lang])
            safe_exit(1)
    else:
        print(SETUP["i2c_no_display"][lang])
        print(SETUP["i2c_no_devices"][lang])
        safe_exit(1)

def check_spi():
    print(SETUP["spi_check"][lang])
    # Ask raspi-config whether SPI is enabled (nonint getter)
    result = run_command("sudo raspi-config nonint get_spi", log_out=True, show_output=False, check=True)
    if result.returncode != 0 or result.stdout.strip() != "0":
        # SPI reported disabled -> offer to enable (requires reboot)
        choice = input(SETUP["spi_disabled"][lang] + " > ").strip().lower()
        if choice in ["", "y", "o"]:
            print(SETUP["spi_enabling"][lang])
            run_command("sudo raspi-config nonint do_spi 0", log_out=True, show_output=False, check=True)
            print(SETUP["spi_enabled"][lang])
            print(SETUP["spi_reboot_required"][lang])
        else:
            print(SETUP["spi_enable_failed"][lang])
            safe_exit(1)

    # Detect /dev/spidev* entries (common device nodes for SPI)
    # Use a shell-friendly pattern and capture stdout
    for _ in range(3):
        res = run_command("ls /dev/spidev* 2>/dev/null || true", log_out=True, show_output=False, check=False)
        if res.stdout.strip():
            break
        time.sleep(1)

    devices = []
    if res.returncode == 0 and res.stdout.strip():
        # split on whitespace in case multiple devices listed
        for p in res.stdout.strip().split():
            if p.startswith("/dev/"):
                devices.append(p)
    if devices:
        print(SETUP["spi_devices_detected"][lang].format(", ".join(devices)))
        print(SETUP.get("spi_ready", {}).get(lang, "✅ SPI interface looks OK."))
        log_line(msg=f"SPI devices found: {', '.join(devices)}", context="check_spi")
        return True
    else:
        print(SETUP["spi_no_devices"][lang])
        print(SETUP["spi_check_wiring"][lang])
        log_line(error="No SPI devices detected", context="check_spi")
        safe_exit(1)

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

def safe_input(prompt, default=None):
    """Ask the user for input and return either typed value or default."""
    if default is None:
        return input(prompt + " > ").strip()
    resp = input(f"{prompt} [{default}] > ").strip()
    return resp if resp else default

def configure_screen(olipi_moode_dir, olipi_core_dir):
    os.environ["OLIPI_DIR"] = str(Path(olipi_moode_dir))
    if str(Path(olipi_moode_dir)) not in sys.path:
        sys.path.insert(0, str(Path(olipi_moode_dir)))

    try:
        from olipi_core import core_config
    except Exception as e:
        print(SETUP.get("screen_discovery_fail", {}).get(lang,
              "❌ Could not import olipi_core.core_config; screen setup will be skipped."))
        safe_exit(1, error=f"❌ Could not import olipi_core.core_config; screen setup will be skipped. {e}")
        return False

    # discover available screens
    screens = discover_screens_from_olipicore(olipi_core_dir)
    if not screens:
        print(SETUP.get("screen_none_found", {}).get(lang, "No screen modules found."))
        safe_exit(1, error=f"❌ No screen found.")
        return False

    # present choices
    keys = sorted(screens.keys())
    print(SETUP.get("screen_choose_list", {}).get(lang, "Available screens:"))
    for i, key in enumerate(keys, start=1):
        info = screens[key]
        print(f"  [{i}] {key} — {info.get('resolution')} — {info.get('type').upper()} — {info.get('color')}")

    choice = safe_input(SETUP.get("screen_choose_prompt", {}).get(lang, "Choose your screen by number"), "1")
    try:
        idx = int(choice)
        if not (1 <= idx <= len(keys)):
            raise ValueError("out of range")
    except Exception:
        print(SETUP.get("screen_invalid_choice", {}).get(lang, "Invalid choice. Aborting screen configuration."))
        safe_exit(1, error=f"❌ Invalid choice. Aborting screen configuration. {e}")
        return False

    selected = keys[idx - 1]
    meta = screens[selected]
    selected_id = meta["id"]
    print(SETUP.get("screen_selected", {}).get(lang, "Selected: {}").format(selected))
    log_line(msg=f"User selected screen {selected} (type={meta.get('type')})", context="configure_screen")

    if meta["type"] == "i2c":
        check_i2c()
    elif meta["type"] == "spi":
        check_spi()

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
        cs = safe_input(SETUP.get("screen_cs_prompt", {}).get(lang, "CS pin (chip select)"))
        dc = safe_input(SETUP.get("screen_dc_prompt", {}).get(lang, "DC pin (data/command)"))
        rst = safe_input(SETUP.get("screen_reset_prompt", {}).get(lang, "RESET pin"))
        bl = safe_input(SETUP.get("screen_bl_prompt", {}).get(lang, "BL pin (backlight) — leave empty if none)"))

        try:
            core_config.save_config("cs_pin", cs.upper(), section="screen", preserve_case=True)
            core_config.save_config("dc_pin", dc.upper(), section="screen", preserve_case=True)
            core_config.save_config("reset_pin", rst.upper(), section="screen", preserve_case=True)
            if bl:
                core_config.save_config("bl_pin", bl.upper(), section="screen", preserve_case=True)
            log_line(msg=f"Saved SPI pins cs={cs}, dc={dc}, reset={rst}, bl={bl}", context="configure_screen")
        except Exception as e:
            print(SETUP.get("screen_save_fail", {}).get(lang, "❌ Failed to save pin configuration"))
            safe_exit(1, error=f"❌ Failed to save pin configuration. {e}")
            return False

        core_config.reload_config()
        print(SETUP.get("screen_saved_ok", {}).get(lang, "Screen configuration saved."))
        return True

    # If I2C just reload config and finish
    core_config.reload_config()
    print(SETUP.get("screen_saved_ok", {}).get(lang, "Screen configuration saved."))
    return True

def get_active_swaps():
    """Return a list of active swap device names (e.g. ['/dev/zram0', '/var/swap'])."""
    swaps = []
    try:
        with open("/proc/swaps", "r", encoding="utf-8") as f:
            lines = f.read().strip().splitlines()[1:]  # skip header
        for line in lines:
            parts = line.split()
            if parts:
                swaps.append(parts[0])
    except Exception as e:
        log_line(error=e, context="get_active_swaps")
        pass
    return swaps

def is_zram_active():
    """Return True if a zram swap appears active."""
    try:
        res = run_command("swapon --show --noheadings", log_out=True, show_output=False, check=False)
        if res.returncode == 0 and res.stdout.strip():
            for ln in res.stdout.strip().splitlines():
                if "zram" in ln or "/dev/zram" in ln:
                    return True
        # fallback: check sysfs
        if os.path.exists("/sys/block/zram0"):
            return True
    except Exception as e:
        log_line(error=e, context="is_zram_active")
        pass
    return False

def is_dphys_active():
    """Return True if dphys-swapfile service is active (if systemctl exists)."""
    try:
        res = run_command("systemctl is-active dphys-swapfile", log_out=True, show_output=False, check=False)
        return res.returncode == 0 and res.stdout.strip() == "active"
    except Exception as e:
        log_line(error=e, context="is_dphys_active")
        return False

def stop_and_disable_dphys():
    """Stop/disable dphys-swapfile and swapoff non-zram swaps; optionally propose removal of swap files."""
    # Stop and disable service if present
    try:
        run_command("sudo systemctl stop dphys-swapfile", log_out=True, show_output=True, check=False)
        run_command("sudo systemctl disable dphys-swapfile", log_out=True, show_output=True, check=False)
    except Exception as e:
        log_line(error=e, context="stop_and_disable_dphys")
        pass

    # Swapoff for non-zram swap devices
    swaps = get_active_swaps()
    non_zram = [s for s in swaps if "zram" not in s]
    for sw in non_zram:
        try:
            run_command(f"sudo swapoff {sw}", log_out=True, show_output=True, check=False)
        except Exception as e:
            log_line(error=e, context="stop_and_disable_dphys")
            pass
        # if it's a regular file, propose deletion
        if os.path.isabs(sw) and os.path.exists(sw) and stat.S_ISREG(os.stat(sw).st_mode):
            choice = input(SETUP["confirm_remove_swapfile"][lang].format(sw) + " > ").strip().lower()
            if choice in ["", "y", "o"]:
                try:
                    os.remove(sw)
                    print(SETUP["removed_swapfile"][lang].format(sw))
                except Exception as e:
                    log_line(error=e, context="stop_and_disable_dphys")
                    pass
    print(SETUP["disable_swap_done"][lang])

def configure_zram(reconfigure=False):
    """
    Install/configure zramswap using /etc/default/zramswap.
    - critical operations (apt install, writing /etc) use check=True.
    - enabling/restarting systemd services is attempted but non-fatal when failing.
    """
    if is_zram_active() and not reconfigure:
        print(SETUP.get("zram_already_active", {}).get(lang, "ZRAM already active."))
        return True

    print(SETUP.get("zram_installing", {}).get(lang, "Installing zram-tools..."))
    # install zram-tools (critical)
    run_command("sudo apt-get install -y zram-tools", log_out=True, show_output=True, check=True)

    zramswap_conf = "/etc/default/zramswap"
    if os.path.exists(zramswap_conf):
        backup_path = f"/etc/default/zramswap.olipi-bak"
        if os.path.exists(backup_path):
            print(SETUP.get("zram_nobackup", {}).get(lang, "Backing up of zramswap config already exist to {}").format(backup_path))
            pass
        else:
            run_command(f"sudo cp {zramswap_conf} {backup_path}", log_out=True, show_output=False, check=True)
            print(SETUP.get("zram_backup", {}).get(lang, "Backing up zramswap config to {}").format(backup_path))

    # Write recommended config to a temp file then move into place (mv is critical)
    config_content = f"""# Generated by olipi setup
# Compression algorithm selection
# speed: lz4 > zstd > lzo
# compression: zstd > lzo > lz4
# This is not inclusive of all that is available in latest kernels
# See /sys/block/zram0/comp_algorithm (when zram module is loaded) to see
# what is currently set and available for your kernel[1]
# [1]  https://github.com/torvalds/linux/blob/master/Documentation/blockdev/zram.txt#L86
ALGO=lz4

# Specifies the amount of RAM that should be used for zram
# based on a percentage the total amount of available memory
# This takes precedence and overrides SIZE below
#PERCENT=50

# Specifies a static amount of RAM that should be used for
# the ZRAM devices, this is in MiB
# Use 256 for a Raspberry Pi Zero 2 with 512MB of RAM
SIZE={ZRAM_RECOMMENDED_MB}
# Use 1024 for a Raspberry Pi 4 or Raspberry Pi 5 with 4GB of RAM
#SIZE=1024

# Specifies the priority for the swap devices, see swapon(2)
# for more details. Higher number = higher priority
# This should be higher than hdd/ssd swaps.
PRIORITY=100
"""
    tmp_path = "/tmp/zramswap"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(config_content)
    run_command(f"sudo mv {tmp_path} {zramswap_conf}", log_out=True, show_output=False, check=True)

    # reload systemd daemon (non-fatal) and restart/enable service (try to make it active)
    run_command("sudo systemctl daemon-reload", log_out=True, show_output=True, check=False)
    run_command("sudo systemctl restart zramswap", log_out=True, show_output=True, check=False)
    run_command("sudo systemctl enable zramswap", log_out=True, show_output=True, check=False)

    # final check
    if is_zram_active():
        print(SETUP.get("zram_done", {}).get(lang, "ZRAM configured."))
        return True
    else:
        print(SETUP.get("zram_service_restart_failed", {}).get(lang, "ZRAM configured but service may not be active."))
        log_line(msg="ZRAM configured but service may not be active.", context="configure_zram")
        return False

def check_ram():
    # Read MemTotal
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            mem_mb = 0
            for line in f:
                if line.startswith("MemTotal"):
                    mem_mb = int(line.split()[1]) // 1024
                    log_line(msg=f"Avaible ram: {mem_mb}", context="check_ram")
                    break
    except Exception as e:
        log_line(error=e, context="check_ram")
        mem_mb = 0

    if mem_mb >= LOW_RAM_THRESHOLD_MB:
        # Enough RAM — nothing to do
        return

    # Low RAM -> show active swaps and consider zram
    print(SETUP["low_ram_warning"][lang].format(LOW_RAM_THRESHOLD_MB))
    swaps = get_active_swaps()
    if swaps:
        print(SETUP.get("swap_active_list", {}).get(lang, "Active swap devices: {}").format(", ".join(swaps)))
    else:
        print(SETUP.get("swap_active_list", {}).get(lang, "Active swap devices: {}").format("none"))

    zram_active = is_zram_active()
    dphys_active = is_dphys_active()

    if not zram_active:
        print(SETUP.get("zram_not_present", {}).get(lang, "ZRAM device not present."))
        choice = input(SETUP["zram_prompt"][lang].format(ZRAM_RECOMMENDED_MB) + " > ").strip().lower()
        if choice not in ["", "y", "o"]:
            print(SETUP.get("zram_installation_aborted", {}).get(lang, "ZRAM installation aborted by user."))
            return
        # if classic swaps present, propose to disable them
        if dphys_active or any("zram" not in s for s in swaps):
            non_zram = [s for s in swaps if "zram" not in s]
            candidate = ", ".join(non_zram) if non_zram else "dphys-swapfile"
            disable_choice = input(SETUP["disable_swap_prompt"][lang].format(candidate) + " > ").strip().lower()
            if disable_choice in ["", "y", "o"]:
                stop_and_disable_dphys()
        configure_zram(reconfigure=False)
        return

    # zram active
    if dphys_active or any("zram" not in s for s in swaps):
        non_zram = [s for s in swaps if "zram" not in s]
        candidate = ", ".join(non_zram) if non_zram else "dphys-swapfile"
        print(SETUP["zram_and_swap_warning"][lang].format(candidate))
        choice = input(SETUP["disable_swap_prompt"][lang].format(candidate) + " > ").strip().lower()
        if choice in ["", "y", "o"]:
            stop_and_disable_dphys()
            reconf = input(SETUP["reconfigure_zram_prompt"][lang] + " > ").strip().lower()
            if reconf in ["", "y", "o"]:
                configure_zram(reconfigure=True)
        return
    else:
        reconf = input(SETUP["reconfigure_zram_prompt"][lang] + " > ").strip().lower()
        if reconf in ["", "y", "o"]:
            configure_zram(reconfigure=True)
        return

def is_valid_venv(path):
    return os.path.isfile(os.path.join(path, "bin", "python"))

def validate_venv_path(path):
    try:
        path = os.path.expanduser(path.strip())
        path = os.path.abspath(path)
        path = path.rstrip("/")

        parent_dir = os.path.dirname(path)
        if not os.path.exists(parent_dir):
            print(SETUP["venv_invalid_parent"][lang].format(parent_dir))
            return None
        if not os.access(parent_dir, os.W_OK):
            print(SETUP["venv_invalid_parent"][lang].format(parent_dir))
            return None
        return path
    except Exception as e:
        log_line(error=e, context="validate_venv_path")
        print(f"❌ Exception during path validation: {e}")
        return None

def prompt_yes_no(message):
    while True:
        response = input(message + " > ").strip().lower()
        if response in ["", "y", "o"]:
            return True
        elif response == "n":
            return False
        else:
            print(SETUP["prompt_invalid"][lang])

def check_virtualenv():
    if os.path.exists(DEFAULT_VENV_PATH):
        print(SETUP["venv_found"][lang].format(DEFAULT_VENV_PATH))
        print(SETUP["venv_reuse_choice"][lang])
        while True:
            choice = input(" > ").strip()
            if choice == "1":
                return DEFAULT_VENV_PATH
            elif choice == "2":
                print(SETUP["venv_delete"][lang])
                try:
                    shutil.rmtree(DEFAULT_VENV_PATH)
                except Exception as e:
                    print(f"❌ Failed to delete {DEFAULT_VENV_PATH}: {e}")
                    safe_exit(1, e)
                break
            elif choice == "3":
                print(SETUP["venv_cancelled"][lang])
                log_line(msg="❌ venv Installation cancelled.", context="check_virtualenv")
                safe_exit(130)
            else:
                print(SETUP["prompt_invalid"][lang])

    print(SETUP["venv_main_choice"][lang].format(DEFAULT_VENV_PATH))
    while True:
        choice = input(" > ").strip()
        if choice in ["1", ""]:
            return DEFAULT_VENV_PATH
        elif choice == "2":
            while True:
                print(SETUP["venv_enter_path"][lang])
                user_path = input(" > ").strip()
                if user_path == "":
                    print(SETUP["venv_cancelled"][lang])
                    safe_exit(0)

                venv_path = validate_venv_path(user_path)
                if not venv_path:
                    continue

                if os.path.exists(venv_path):
                    if is_valid_venv(venv_path):
                        return venv_path
                    else:
                        print(SETUP["venv_invalid_path"][lang])
                        continue
                else:
                    if prompt_yes_no(SETUP["venv_confirm_create"][lang].format(venv_path)):
                        return venv_path
                    else:
                        print(SETUP["venv_invalid_path"][lang])
                        continue
        elif choice == "3":
            print(SETUP["venv_cancelled"][lang])
            log_line(msg="❌ venv Installation cancelled.", context="check_virtualenv")
            safe_exit(130)
        else:
            print(SETUP["prompt_invalid"][lang])

def setup_virtualenv(venv_path):
    requirements_path = os.path.join(OLIPI_MOODE_DIR, "requirements.txt")

    if not os.path.exists(venv_path):
        print(f"Creating virtual environment at {venv_path} ...")
        # critical: venv creation must succeed
        run_command(f"python3 -m venv {venv_path}", log_out=True, show_output=True, check=True)

    pip_path = os.path.join(venv_path, "bin", "pip")
    if not os.path.isfile(pip_path):
        print(f"❌ pip not found in the virtual environment at {pip_path}.")
        safe_exit(1)

    # upgrade pip and install requirements inside venv (critical)
    run_command(f"{pip_path} install --upgrade pip", log_out=True, show_output=True, check=True)
    print(SETUP["install_pip"][lang])
    run_command(f"{pip_path} install --requirement {requirements_path}", log_out=True, show_output=True, check=True)
    log_line(msg="Installing venv finished", context="setup_virtualenv")

def detect_user():
    user = os.getenv("SUDO_USER") or os.getenv("USER") or "unknown"
    print(SETUP["user_detected"][lang].format(user))
    return user

# -----------------------
# Services & ready-script (merged)
# -----------------------
# Service templates (same as before)
SERVICES = {
    "olipi-ui-playing": """[Unit]
Description=OliPi MoOde Now-Playing Screen (ui_playing)
After=network.target sound.target
Wants=sound.target

[Service]
Type=simple
ExecStart={venv}/bin/python3 {project}/ui_playing.py
WorkingDirectory={project}
User={user}
Group={user}
Restart=on-failure
RestartSec=10
StartLimitIntervalSec=200
StartLimitBurst=10

[Install]
WantedBy=multi-user.target
""",
    "olipi-ui-browser": """[Unit]
Description=OliPi MoOde Library Browser Screen (ui_browser)
After=network.target sound.target
Wants=sound.target

[Service]
Type=simple
ExecStart={venv}/bin/python3 {project}/ui_browser.py
WorkingDirectory={project}
User={user}
Group={user}
Restart=on-failure
RestartSec=10
StartLimitIntervalSec=200
StartLimitBurst=10

[Install]
WantedBy=multi-user.target
""",
    "olipi-ui-queue": """[Unit]
Description=OliPi MoOde Queue Management Screen (ui_queue)
After=network.target sound.target
Wants=sound.target

[Service]
Type=simple
ExecStart={venv}/bin/python3 {project}/ui_queue.py
WorkingDirectory={project}
User={user}
Group={user}
Restart=on-failure
RestartSec=10
StartLimitIntervalSec=200
StartLimitBurst=10

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
    """Interactive install services flow executed inside setup.py process."""
    project_path = OLIPI_MOODE_DIR
    log_line(msg=f"install_services started (user={user}, venv={venv})", context="run_install_services")
    print(SETUP["install_services"][lang])

    for name, template in SERVICES.items():
        while True:
            print(SETUP["service_menu"][lang].format(name))
            try:
                choice = input(" > ").strip()
            except EOFError:
                # if stdin closed, treat as skip
                choice = "3"
            if choice == "2":
                print(SETUP["service_view_header"][lang].format(name))
                print(template.format(venv=venv, project=project_path, user=user))
                print("--------------------")
            elif choice == "1":
                service_content = template.format(venv=venv, project=project_path, user=user)
                try:
                    write_service(name, service_content)
                    if name == "olipi-ui-off":
                        run_command(f"sudo systemctl enable {name}", log_out=True, show_output=False, check=True)
                        print(SETUP["service_enabled"][lang].format(name))
                except PermissionError:
                    print(SETUP["permission_denied"][lang])
                    safe_exit(1, error="Permission denied while writing/enabling service")
                except Exception as e:
                    log_line(error=f"Failed to install service {name}: {e}", context="run_install_services")
                    print(SETUP.get("service_save_failed", {}).get(lang, "❌ Failed to install service."))
                break
            else:
                print(SETUP["service_skipped"][lang].format(name))
                break
    log_line(msg="install_services finished", context="run_install_services")

def update_ready_script():
    READY_SCRIPT_TEMPLATE = os.path.join(INSTALL_DIR, "ready-script.sh")

    print(SETUP["ready_script_update"][lang])
    log_line(msg="Updating ready-script", context="update_ready_script")

    READY_SCRIPT_PATH = "/var/local/www/commandw/ready-script.sh"
    if os.path.exists(READY_SCRIPT_PATH):
        READY_SCRIPT_BACKUP = "/var/local/www/commandw/ready-script.sh.olipi-bak"
        if os.path.exists(READY_SCRIPT_BACKUP):
            print(SETUP["ready_script_nobackup"][lang].format(READY_SCRIPT_BACKUP))
            pass
        else:
            run_command(f"sudo cp {READY_SCRIPT_PATH} {READY_SCRIPT_BACKUP}", log_out=True, show_output=False, check=True)
            print(SETUP["ready_script_backup"][lang].format(READY_SCRIPT_BACKUP))

    run_command(f"sudo cp {READY_SCRIPT_TEMPLATE} {READY_SCRIPT_PATH}", log_out=True, show_output=False, check=True)
    run_command(f"sudo chmod 755 {READY_SCRIPT_PATH}", log_out=True, show_output=False, check=True)
    run_command(f"sudo chown root:root {READY_SCRIPT_PATH}", log_out=True, show_output=False, check=True)
    print(SETUP["ready_script_done"][lang])
    log_line(msg="Ready-script updated", context="update_ready_script")

def append_to_profile():
    profile_path = os.path.expanduser("~/.profile")
    lines_to_add = [
        'echo " "',
        'echo "Moode debug => moodeutl -l"',
        'echo "Force Moode update => sudo /var/www/util/system-updater.sh moode9"',
        f'echo "Configure IR remote => python3 {INSTALL_LIRC_REMOTE_PATH}"'
    ]
    print(SETUP["profile_update"][lang])
    log_line(msg="Appending to ~/.profile", context="append_to_profile")
    try:
        if os.path.exists(profile_path):
            with open(profile_path, "r", encoding="utf-8") as f:
                content = f.read()
        else:
            content = ""
        with open(profile_path, "a", encoding="utf-8") as f:
            for line in lines_to_add:
                if line not in content:
                    f.write("\n" + line)
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
            fh.write(f"+++++++++\n[SUCCESS] ✅ Setup.py finished successfully")
    finalize_log(0)
    reboot = input(SETUP["reboot_prompt"][lang]).strip().lower()
    if reboot in ["", "o", "y"]:
        run_command("sudo reboot", log_out=True, show_output=True, check=False)
    else:
        print(SETUP["reboot_cancelled"][lang])


# -----------------------
# Command-line entry
# -----------------------
def main():
    parser = argparse.ArgumentParser(description="OliPi setup (install / update / develop)")
    parser.add_argument("--install", action="store_true", help="Perform a full install of OliPi")
    parser.add_argument("--update", action="store_true", help="Update existing OliPi installation")
    parser.add_argument("--dev", action="store_true", help="Developer mode: use branches/latest commits instead of releases")
    args = parser.parse_args()

    choose_language()
    check_moode_version()
    install_apt_dependencies()
    settings = load_settings()


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
        local_tag_moode = settings.get("local_tag_moode", "")
        local_tag_core = settings.get("local_tag_core", "")
        remote_tag_moode = get_latest_release_tag(OLIPI_MOODE_REPO, branch="main") or ""
        remote_tag_core = get_latest_release_tag(OLIPI_CORE_REPO, branch="main") or ""

        moode_major_change = parse_semver_prefix(remote_tag_moode)[:1] != parse_semver_prefix(local_tag_moode)[:1]
        core_major_change = parse_semver_prefix(remote_tag_core)[:1] != parse_semver_prefix(local_tag_core)[:1]

        force_install = moode_major_change or core_major_change or not core_present

        if force_install:
            ans = input(SETUP.get("interactive_install_prompt", {}).get(lang,
                        "⚙️ First install or Major update, Do you want to re/install (I) or abort (A)? [I/A] ")).strip().lower()
            if ans in ("i", ""):
                cmd = "install"
            else:
                print(SETUP.get("interactive_abort", {}).get(lang))
                safe_exit(0)
        elif moode_present and core_present:
            ans = input(SETUP.get("interactive_update_prompt", {}).get(lang, "⚙️ Do you want to update (U), force fresh reinstall (F), or skip (S)? [U/F/S] ")).strip().lower()
            if ans in ("u", ""):
                cmd = "update"
            elif ans == "f":
                cmd = "install"
            else:
                print(SETUP.get("interactive_abort", {}).get(lang))
                safe_exit(0)
        else:
            cmd = "install"

    try:
        if cmd == "dev_mode":
            # full dev rolling install
            print("Setup.py launched on dev mode...")
            install_olipi_moode(mode="dev_mode")
            install_olipi_core(mode="dev_mode")
            configure_screen(OLIPI_MOODE_DIR, OLIPI_CORE_DIR)
            check_ram()
            venv_path = check_virtualenv()
            setup_virtualenv(venv_path)
            user = detect_user()
            run_install_services(venv_path, user)
            update_ready_script()
            append_to_profile()
            settings.update({
                "venv_path": str(venv_path),
                "project_dir": str(OLIPI_MOODE_DIR),
                "install_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
            settings.pop("force_new_files", None)
            save_settings(settings)
            install_done()
            print(SETUP.get("develop_done", {}).get(lang, "✅ Development mode setup complete."))

        elif cmd == "install":
            # full release install
            install_olipi_moode(mode="install")
            install_olipi_core(mode="install")
            configure_screen(OLIPI_MOODE_DIR, OLIPI_CORE_DIR)
            check_ram()
            venv_path = check_virtualenv()
            setup_virtualenv(venv_path)
            user = detect_user()
            run_install_services(venv_path, user)
            update_ready_script()
            append_to_profile()
            settings.update({
                "venv_path": str(venv_path),
                "project_dir": str(OLIPI_MOODE_DIR),
                "core_dir": str(OLIPI_CORE_DIR),
                "install_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
            settings.pop("force_new_files", None)
            save_settings(settings)
            install_done()

        elif cmd == "update":
            # minor update only
            install_olipi_moode(mode="update")
            install_olipi_core(mode="update")
            settings.update({
                "update_date": time.strftime("%Y-%m-%d %H:%M:%S"),
                "project_dir": str(OLIPI_MOODE_DIR),
                "core_dir": str(OLIPI_CORE_DIR)
            })
            settings.pop("force_new_files", None)
            save_settings(settings)
            print(SETUP.get("update_done", {}).get(lang, "✅ Update complete."))
            with TMP_LOG_FILE.open("a", encoding="utf-8") as fh:
                fh.write(f"+++++++++\n[SUCCESS] ✅ Update finished successfully")
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
        safe_exit(130)

    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        log_line(error=str(e), context="main")
        safe_exit(1, error=e)

if __name__ == "__main__":
    main()
