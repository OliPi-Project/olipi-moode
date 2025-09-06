#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2025 OliPi Project (Benoit Toufflet)

import os, sys, subprocess, traceback, argparse, shutil, time, json
from pathlib import Path

INSTALL_DIR = Path(__file__).resolve().parent
OLIPI_MOODE_DIR = INSTALL_DIR.parent
OLIPI_CORE_DIR = OLIPI_MOODE_DIR / "olipi_core"
SETTINGS_FILE = INSTALL_DIR / ".setup-settings.json"

TMP_LOG_FILE = Path("/tmp/update.log")
_LOG_INITIALIZED = False

OLIPI_MOODE_BRANCH = "main"
OLIPI_CORE_BRANCH = "main"

lang = "en"

MESSAGES = {
    "choose_language": {
        "en": "Please choose your language:",
        "fr": "Veuillez choisir votre langue :"
    },
    "language_options": {
        "en": "[1] English\n[2] Français",
        "fr": "[1] Anglais\n[2] Français"
    },
    "invalid_choice": {
        "en": "Invalid choice. Defaulting to English.",
        "fr": "Choix invalide. Anglais sélectionné par défaut."
    },
    "start_update": {
        "en": "=== Starting OliPi-Moode update ===",
        "fr": "=== Démarrage de la mise à jour OliPi-Moode ==="
    },
    "missing_path": {
        "en": "⚠️ Some expected directories were not found. Continue anyway? [y/N] ",
        "fr": "⚠️ Certains dossiers attendus sont introuvables. Continuer quand même ? [o/N] "
    },
    "updating_repo": {
        "en": "Checking updates for repository at {} ...",
        "fr": "Vérification des mises à jour pour le dépôt à {} ..."
    },
    "already_uptodate": {
        "en": "Already up-to-date (local {}, remote {}).",
        "fr": "Déjà à jour (local {}, distant {})."
    },
    "updating_from_to": {
        "en": "Updating from {} to {} ...",
        "fr": "Mise à jour de {} vers {} ..."
    },
    "no_remote_tag": {
        "en": "⚠️ Could not detect remote tag, performing normal pull...",
        "fr": "⚠️ Impossible de détecter le tag distant, exécution d’un pull normal..."
    },
    "venv_update": {
        "en": "Updating Python virtual environment...",
        "fr": "Mise à jour de l'environnement virtuel Python..."
    },
    "update_done": {
        "en": "✅ Update complete.",
        "fr": "✅ Mise à jour terminée."
    },
    "venv_missing": {
        "en": "❌ Virtual environment not found: {}",
        "fr": "❌ Environnement virtuel introuvable : {}"
    },
}

# --- Logging & command utilities ---

def finalize_log(exit_code=0):
    if TMP_LOG_FILE.exists():
        status = "success" if exit_code == 0 else "error"
        timestamp = time.strftime("%Y-%m-%d")
        dest = INSTALL_DIR / "logs" / f"update_{timestamp}_{status}.log"
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(TMP_LOG_FILE), dest)
            print(f"Update log saved to {dest}")
        except Exception:
            pass

def safe_exit(code=1, error=None):
    if error:
        try:
            with TMP_LOG_FILE.open("a", encoding="utf-8") as fh:
                fh.write(f"[ERROR] {time.strftime('%Y-%m-%d %H:%M:%S')}: {repr(error)}\n")
                fh.write(traceback.format_exc())
        except Exception:
            pass
    finalize_log(exit_code=code)
    sys.exit(code)

def log_line(msg=None, error=None, context=None):
    prefix = "INFO" if msg else "ERROR"
    log_text = msg if msg else error
    header = f"\n[-- {time.strftime('%Y-%m-%d %H:%M:%S')}] {context or ''}\n"
    try:
        TMP_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with TMP_LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(header)
            fh.write(f"[{prefix}] {log_text}\n")
    except Exception:
        pass

def run_command(cmd, log_out=True, show_output=False, check=False):
    global _LOG_INITIALIZED
    header = f"\n[--- {time.strftime('%Y-%m-%d %H:%M:%S')}] Running: {cmd}\n"
    TMP_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    mode = "w" if not _LOG_INITIALIZED else "a"
    with TMP_LOG_FILE.open(mode, encoding="utf-8") as fh:
        fh.write(header)
    _LOG_INITIALIZED = True
    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    stdout_lines = []
    with TMP_LOG_FILE.open("a", encoding="utf-8") as logfh:
        for line in process.stdout:
            stdout_lines.append(line)
            if log_out: logfh.write(line)
            if show_output: print(line, end="")
    rc = process.wait()
    if check and rc != 0:
        print(f"❌ Command failed (exit {rc}): {cmd}")
        log_line(error=f"Command failed: {cmd} (rc={rc})", context="run_command")
        safe_exit(1, error=f"Command failed (exit {rc})")
    return rc

# --- Language selection ---

def choose_language():
    global lang
    print(MESSAGES["choose_language"][lang])
    print(MESSAGES["language_options"][lang])
    choice = input(" > ").strip()
    if choice == "2": lang = "fr"
    elif choice != "1": print(MESSAGES["invalid_choice"][lang])

# --- Settings ---

def load_settings():
    if SETTINGS_FILE.exists():
        try:
            with SETTINGS_FILE.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}
    return {}

def save_settings(settings: dict):
    try:
        with SETTINGS_FILE.open("w", encoding="utf-8") as fh:
            json.dump(settings, fh, indent=2)
    except Exception as e:
        log_line(error=f"Failed to save settings: {e}", context="save_settings")

# --- Git helpers ---

def get_latest_tag(path: Path, remote: bool = False, branch: str = "main") -> str:
    if remote:
        run_command(f"git -C {path} fetch --tags origin", log_out=True)
        cmd = f"git -C {path} describe --tags --abbrev=0 origin/{branch}"
    else:
        cmd = f"git -C {path} describe --tags --abbrev=0"
    rc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return rc.stdout.strip() if rc.returncode == 0 else ""

def version_is_newer(local: str, remote: str) -> bool:
    def parse(v): return tuple(map(int, v.lstrip("v").split(".")))
    try: return parse(remote) > parse(local)
    except Exception: return False

# --- Repo & venv updates ---

def update_repo(path: Path, branch: str, dry_run: bool = False, force: bool = False):
    if not path.exists(): return False
    print(MESSAGES["updating_repo"][lang].format(path))

    local_tag = get_latest_tag(path, remote=False, branch=branch)
    remote_tag = get_latest_tag(path, remote=True, branch=branch)

    # Save local tag in settings
    settings = load_settings()
    if path == OLIPI_MOODE_DIR:
        settings["branch_olipi_moode"] = OLIPI_MOODE_BRANCH
        settings["local_tag_moode"] = local_tag
        settings["remote_tag_moode"] = remote_tag
    elif path == OLIPI_CORE_DIR:
        settings["branch_olipi_core"] = OLIPI_CORE_BRANCH
        settings["local_tag_core"] = local_tag
        settings["remote_tag_core"] = remote_tag
    save_settings(settings)

    if not remote_tag:
        print(MESSAGES["no_remote_tag"][lang])
        if not dry_run:
            run_command(f"git -C {path} checkout {branch}", log_out=True, show_output=True)
            run_command(f"git -C {path} pull", log_out=True, show_output=True)
        return True

    if force or not local_tag or version_is_newer(local_tag, remote_tag):
        print(MESSAGES["updating_from_to"][lang].format(local_tag or "none", remote_tag))
        if not dry_run:
            run_command(f"git -C {path} checkout {branch}", log_out=True, show_output=True)
            run_command(f"git -C {path} pull", log_out=True, show_output=True)
    else:
        print(MESSAGES["already_uptodate"][lang].format(local_tag, remote_tag))
    return True

def update_venv(venv_path: Path, dry_run: bool = False, force: bool = False):
    if not venv_path.exists():
        print(MESSAGES["venv_missing"][lang].format(venv_path))
        return False
    print(MESSAGES["venv_update"][lang])
    pip_path = venv_path / "bin" / "pip"
    req_file = OLIPI_MOODE_DIR / "requirements.txt"
    if dry_run:
        print(f"[DRY-RUN] Would upgrade pip and install {req_file}")
        if force: print("[DRY-RUN] Force enabled: would reinstall all packages")
        return True
    run_command(f"{pip_path} install --upgrade pip", log_out=True, show_output=True)
    if force:
        run_command(f"{pip_path} install --force-reinstall --requirement {req_file}", log_out=True, show_output=True)
    else:
        run_command(f"{pip_path} install --requirement {req_file}", log_out=True, show_output=True)
    return True

# --- Main ---

def main():
    parser = argparse.ArgumentParser(description="OliPi update script")
    parser.add_argument("--dry-run", action="store_true", help="Check updates without applying changes")
    parser.add_argument("--force", action="store_true", help="Force update even if tags are identical")
    args = parser.parse_args()

    choose_language()
    print(MESSAGES["start_update"][lang])

    settings = load_settings()
    venv_path = Path(settings.get("venv_path"))

    missing = []
    if not OLIPI_MOODE_DIR.exists(): missing.append(str(OLIPI_MOODE_DIR))
    if not OLIPI_CORE_DIR.exists(): missing.append(str(OLIPI_CORE_DIR))
    if not venv_path.exists(): missing.append(str(venv_path))

    if missing:
        ans = input(MESSAGES["missing_path"][lang]).strip().lower()
        if ans not in ("y", "o"): safe_exit(1, error=f"Missing paths: {missing}")

    update_repo(OLIPI_MOODE_DIR, OLIPI_MOODE_BRANCH, dry_run=args.dry_run, force=args.force)
    update_repo(OLIPI_CORE_DIR, OLIPI_CORE_BRANCH, dry_run=args.dry_run, force=args.force)
    update_venv(venv_path, dry_run=args.dry_run, force=args.force)

    if not args.dry_run:
        print(MESSAGES["update_done"][lang])
        with TMP_LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(f"+++++++++\n[SUCCESS] ✅ Update finished successfully")
        finalize_log(exit_code=0)
    else:
        print("ℹ️ Dry-run mode: no changes applied.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        with TMP_LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(f"+++++++++\n[ABORTED] ❌ Update interrupted by user (Ctrl+C).\n")
        print("❌ Update interrupted by user (Ctrl+C).")
        safe_exit(130)
    except Exception as e:
        safe_exit(1, error=e)
