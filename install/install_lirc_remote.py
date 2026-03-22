#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2025 OliPi Project

import os
import sys
import subprocess
import shutil
import argparse
import tempfile
import re
import time
import threading
import configparser
from pathlib import Path

INSTALL_DIR = os.path.dirname(os.path.abspath(__file__)) # directory containing install_lirc_remote.py
OLIPI_MOODE_DIR = os.path.dirname(INSTALL_DIR) # parent → olipi-moode
OLIPI_CORE_DIR = os.path.join(OLIPI_MOODE_DIR, "olipi_core")
CONFIG_INI = os.path.join(OLIPI_MOODE_DIR, "config.ini")
INSTALL_LIRC_REMOTE_PATH = os.path.join(INSTALL_DIR, "install_lirc_remote.py")
CONFIG_TXT = "/boot/firmware/config.txt"
LIRC_OPTIONS = "/etc/lirc/lirc_options.conf"
LIRC_CONF_DIR = "/etc/lirc/lircd.conf.d"
TMP_LOG_FILE = Path("/tmp/install_lirc_remote.log")


MESSAGES = {
    "choose_language": {"en": "Please choose your language:", "fr": "Veuillez choisir votre langue :"},
    "language_options": {"en": "[1] English\n[2] Français", "fr": "[1] Anglais\n[2] Français"},
    "invalid_choice": {"en": "Invalid choice. Defaulting to English.", "fr": "Choix invalide. Anglais sélectionné par défaut."},
    "lirc_missing": {
        "en": "❌ LIRC is not installed.\n",
        "fr": "❌ LIRC n'est pas installé.\n"
    },
    "lirc_installed": {
        "en": "✅ LIRC is installed.\n",
        "fr": "✅ LIRC est installé.\n"
    },
    "start_config_lirc": {
        "en": "⇨ Install and Config LIRC for GPIO IR receiver...",
        "fr": "⇨ Installation et Configuration de LIRC pour récepteur IR GPIO..."
    },
    "explain": {
        "en": (
            "This will configure LIRC for IR receiver type TSOP* connected to a GPIO pin.\n"
            "Steps:\n"
            "  1. Install and configure LIRC if missing\n"
            "  2. Add or update dtoverlay=gpio-ir,gpio_pin=<pin> to /boot/firmware/config.txt\n"
            "  3. Update /etc/lirc/lirc_options.conf\n"
            "  4. Create backups of modified files\n"
            "  At the end, reboot required before remote setup\n"
        ),
        "fr": (
            "Cette opération configure LIRC pour les récepteurs IR type TSOP* connecté sur broche GPIO.\n"
            "Étapes:\n"
            "  1. Installe et configure LIRC si nécessaire\n"
            "  2. Ajoute ou modifie dtoverlay=gpio-ir,gpio_pin=<pin> dans /boot/firmware/config.txt\n"
            "  3. Configure /etc/lirc/lirc_options.conf\n"
            "  4. Fait des sauvegardes des fichiers modifiés\n"
            "  A la fin, un redémarrage est nécessaire avant de configuré la télécommande\n"
        )
    },
    "lirc_prompt": {
        "en": "Would you like to reinstall LIRC? Choose 'n' to go remote configuration [Y/n] > ",
        "fr": "Voulez-vous réinstaller LIRC? Choissisez 'n' pour configurer la télécommande [O/n] > "
    },
    "installing_lirc": {
        "en": "📦 Installing LIRC...",
        "fr": "📦 Installation de LIRC..."
    },
    "accept_prompt": {
        "en": "⚠️ Do you want to continue? [Y/n] > ",
        "fr": "⚠️ Voulez-vous continuer ? [O/n] > "
    },
    "accept_cancelled": {
        "en": "⚠️ LIRC configuration skipped. You can configure it later manually or via:\n' python3 {} '",
        "fr": "⚠️ Configuration de LIRC ignorée. Vous pourrez la configurer plus tard manuellement ou via :\n' python3 {} '"
    },
    "enter_pin": {
        "en": "Enter the GPIO pin number for IR receiver (BCM) > ",
        "fr": "Entrez le numéro de GPIO du récepteur IR (BCM) > "
    },
    "keep_existing_pin": {
        "en": "⚙️ Found existing gpio-ir overlay with gpio_pin={}. Keep this value? [Y/n] > ",
        "fr": "⚙️ Overlay gpio-ir existant détecté avec gpio_pin={}. Conserver cette valeur ? [O/n] > "
    },
    "backup_created": {
        "en": "🔒 Backup created: {}",
        "fr": "🔒 Sauvegarde créée : {}"
    },
    "backup_exist": {
        "en": "🔒 Backup already exist: {}",
        "fr": "🔒 La Sauvegarde existe déjà: {}"
    },
    "updating_config": {
        "en": "🛠 Updating /boot/firmware/config.txt...",
        "fr": "🛠 Mise à jour de /boot/firmware/config.txt..."
    },
    "lirc_conf_update": {
        "en": "🛠 Updating /etc/lirc/lirc_options.conf...",
        "fr": "🛠 Mise à jour de /etc/lirc/lirc_options.conf..."
    },
    "enable_use_lirc": {
        "en": "🛠 Enabling 'use_lirc' in config.ini...",
        "fr": "🛠 Activation de 'use_lirc' dans config.ini..."
    },
    "use_lirc_enabled": {
        "en": "✅ 'use_lirc' set to true in config.ini.",
        "fr": "✅ 'use_lirc' réglé sur true dans config.ini."
    },
    "use_lirc_not_found": {
        "en": "⚠️ 'use_lirc' entry not found in config.ini. Please update manually.",
        "fr": "⚠️ Entrée 'use_lirc' introuvable dans config.ini. Veuillez la mettre à jour manuellement."
    },
    "remote_setup_info": {
        "en": "ℹ️  After reboot, run again ' python3 {} ' to configure your remote.",
        "fr": "ℹ️  Après redémarrage, exécutez à nouveau ' python3 {} ' pour configurer votre télécommande."
    },
    "reboot_prompt": {
        "en": "⚠️  Reboot required for IR changes. Reboot now? [Y/n] > ",
        "fr": "⚠️  Redémarrage requis pour les changements IR. Redémarrer maintenant ? [O/n] > "
    },
    "rebooting": {
        "en": "⇨ Rebooting...",
        "fr": "⇨ Redémarrage en cours..."
    },
    "reboot_cancelled": {
        "en": "⚠️ Reboot cancelled. Please reboot manually later.",
        "fr": "⚠️ Redémarrage annulé. Veuillez redémarrer manuellement plus tard."
    },

    # Messages used by remote manager
    "start_config_remote": {"en": "⇨ IR Remote configuration", "fr": "⇨ Configuration de la télécommande IR"},
    "help_unavailable": {
        "en": "⚠️ Cannot open help window.\nEnable X forwarding or check the README:\nhttps://github.com/OliPi-Project/olipi-moode",
        "fr": "⚠️ Ouverture de l'aide à la configuration des touches impossible.\nActivez la redirection X11 si possible ou consultez le README:\nhttps://github.com/OliPi-Project/olipi-moode"
    },
    "menu": {
        "en": (
            "\n[1] Test IR hardware (mode2) - Check if the IR receiver is working\n"
            "[2] Download a pre-configured remote from the database (irdb-get)\n"
            "[3] Learn a new remote (irrecord) - If no similar config is available\n"
            "[4] Manage configs - Edit, add keys, enable/disable, delete\n"
            "[5] Test key decoding (irw) - Verify that LIRC is properly interpreting keys\n"
            "[6] Map keys to OliPi MoOde actions (If your keys do not match those of olipi-moode)\n"
            "[7] Edit key mapping (individually)\n"
            "[8] Quit\n> "
        ),
        "fr": (
            "\n[1] Test matériel IR (mode2) - Vérifier si le récepteur IR fonctionne\n"
            "[2] Télécharger une configuration de télécommande existante (irdb-get)\n"
            "[3] Apprentissage d'une télécommande (irrecord) - Si aucune config similaire\n"
            "[4] Gérer les configurations - Éditer, ajouter des touches, activer/désactiver, supprimer\n"
            "[5] Test du décodage des touches (irw) - Vérifier que LIRC interprète correctement les touches\n"
            "[6] Mapper les touches avec les actions OliPi MoOde (Si vos touches ne correspondent pas à celles de olipi-moode)\n"
            "[7] Modifier le mappage des touches (individuellement)\n"
            "[8] Quitter\n> "
        ),
    },
    "search_prompt": {
        "en": "Enter brand or model to search: ",
        "fr": "Entrez la marque ou le modèle à rechercher: "
    },
    "search_results": {
        "en": "\nIf your remote is not listed, try a similar model or with *generic*, else use learning.\n⇨ Search results (page {}/{}):",
        "fr": "\nSi votre télécommande n'est pas listée essayez un modèle similaire ou avec *generic*, sinon utilisez l'apprentissage.\n⇨ Résultats de la recherche (page {}/{}):"
    },
    "search_choice": {
        "en": "Enter index to download, 'n' next page, 'p' previous page, 'q' cancel: ",
        "fr": "Entrez l'index pour télécharger, 'n' page suivante, 'p' page précédente, 'q' annuler: "
    },
    "downloading": {"en": "⬇️ Downloading {} ...", "fr": "⬇️ Téléchargement de {} ..."},
    "download_done": {"en": "✅ Remote configuration saved to {}", "fr": "✅ Configuration de la télécommande enregistrée dans {}"},
    "testing_info": {
        "en": "▶️ mode2 will display raw IR pulses to check if your receiver is working.\nIf nothing appears, check your wiring or hardware (Ctrl+C to go back to menu).",
        "fr": "▶️ mode2 affichera les signaux IR bruts pour vérifier si votre récepteur fonctionne.\nSi rien n'apparaît, vérifiez votre câblage ou votre matériel (Ctrl+C pour revenir au menu)."
    },
    "learning_info": {
        "en": "▶️ Learning mode started (irrecord).", 
        "fr": "▶️ Mode apprentissage démarré (irrecord)."
    },
    "testing_irw": {
        "en": "▶️ Testing key decoding (irw). (Ctrl+C to go back to menu)", 
        "fr": "▶️ Test du décodage des touches (irw). (Ctrl+C pour revenir au menu)"
    },
    "config_list": {
        "en": "\nIf your remote is not configured, use learning or search.\n⇨ Select the configuration to be modified (page {}/{}):",
        "fr": "\nSi votre télécommande n'est pas configurée utilisez l'apprentissage ou la recherche.\n⇨ Choisissez la configuration à modifier (page {}/{}):"
    },
    "config_actions": {
        "en": "[1] Edit config manually\n[2] Add new keys (irrecord -u)\n[3] {}\n[4] Delete config\n[5] Back\nn> ",
        "fr": "[1] Éditer la config manuellement\n[2] Ajouter des nouvelles touches (irrecord -u)\n[3] {}\n[4] Supprimer config\n[5] Retour\n> "
    },
    "disable_config": {
        "en": "Disable config (.back)",
        "fr": "Désactiver config (.back)"
    },
    "enable_config": {
        "en": "Enable config",
        "fr": "Réactiver config"
    },
    "disabled": {
        "en": "✅ Config disabled.",
        "fr": "✅ Configuration désactivée."
    },
    "enabled": {
        "en": "✅ Config re-enabled.",
        "fr": "✅ Configuration réactivée."
    },
    "deleted": {
        "en": "✅ Config deleted.",
        "fr": "✅ Configuration supprimée."
    },
    "invalid_choice": {"en": "❌ Invalid choice.", "fr": "❌ Choix invalide."},
    "exiting": {"en": "Exiting.", "fr": "Sortie."},
    "lirc_restart": {
        "en": "✅ LIRC service restarted.",
        "fr": "✅ Service LIRC redémarré."
    },
    "ui_playing_restart": {
        "en": "✅ olipi-ui-playing service restarted.",
        "fr": "✅ Service olipi-ui-playing redémarré."
    },
    "ui_playing_stop": {
        "en": "✅ olipi-ui-playing service stoped.",
        "fr": "✅ Service olipi-ui-playing arreté."
    },
    "mapping_start": {"en": "🎛 Starting remote key mapping...", "fr": "🎛 Démarrage du mappage des touches..."},
    "mapping_press_key": {"en": "Recording button for '{}', Press ENTER to start (or type 'skip' to ignore): ", "fr": "Enregistrement de la touche pour '{}', Appuyez sur ENTREE pour démarrer (ou tapez 'skip' pour ignorer): "},
    "mapping_listen": {"en": "▶️ Press the remote key for '{}' (Ctrl+C to cancel)...", "fr": "▶️ Appuyez sur la touche de la télécommande pour '{}' (Ctrl+C pour annuler)..."},
    "mapping_detected": {"en": "➡️ Detected key: {}", "fr": "➡️ Touche détectée : {}"},
    "mapping_saved": {"en": "✅ Mapping saved in config.ini", "fr": "✅ Mappage enregistré dans config.ini"},
    "mapping_cancelled": {"en": "⚠️ Mapping cancelled.", "fr": "⚠️ Mappage annulé."},
    "mapping_conflict": {"en": "⚠️ The key '{}' is already assigned to '{}'.", "fr": "⚠️ La touche '{}' est déjà assignée à '{}'."},
    "mapping_override": {"en": "Do you want to reassign it to the new action? (o/N): ", "fr": "Voulez-vous la réassigner à la nouvelle action ? (o/N) : "},
    "mapping_reassigned": {"en": "✅ '{}' reassigned to '{}'.", "fr": "✅ '{}' réassignée à '{}'."},
    "mapping_reserved": {"en": "⚠️ '{}' is a OliPi MoOde system key.", "fr": "⚠️ '{}' est une touche système de OliPi MoOde."},
    "mapping_force_reserved": {"en": "Do you want to assign it anyway? (o/N): ", "fr": "Voulez-vous quand même l'assigner ? (o/N) : "},
    "optional_keys_prompt": {"en": "Would you like to configure optional multimedia keys (volume, mute, next, prev...)? [Y/n] > ", "fr": "Voulez-vous aussi configurer les touches multimédia optionnelles (volume, mute, suivant, précédent...)? [O/n] > "}
}

_LOG_INITIALIZED = False

def finalize_log(exit_code=0):
    """Move the temporary log file to INSTALL_DIR/logs with status."""
    if TMP_LOG_FILE.exists():
        status = "success" if exit_code == 0 else "aborted" if exit_code == 130 else "error"
        timestamp = time.strftime("%Y-%m-%d")
        dest = Path(INSTALL_DIR) / "logs" / f"install-lirc-remote_{timestamp}_{status}.log"
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(TMP_LOG_FILE), dest)
            print(f"install_lirc_remote log saved to {dest}")
        except Exception:
            pass

def safe_exit(code=1, error=None):
    """Exit safely: log error (if any), finalize log and sys.exit."""
    if error is not None:
        try:
            with TMP_LOG_FILE.open("a", encoding="utf-8") as fh:
                fh.write(f"+++++++++\n[ERROR] {time.strftime('%Y-%m-%d %H:%M:%S')}: {repr(error)}\n")
                fh.write(traceback.format_exc())
        except Exception:
            pass
    finalize_log(exit_code=code)
    sys.exit(code)

def log_line(msg=None, error=None, context=None):
    """Append a short message to TMP_LOG_FILE."""
    prefix = "INFO" if msg else "ERROR"
    log_text = msg if msg else error
    sep = "-" * 30
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    header = f"\n{sep}\n[-- {timestamp}] Logging {context}\n\n"
    try:
        TMP_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with TMP_LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(header)
            fh.write(f"[{prefix}] {log_text}\n")
    except Exception:
        pass

def run_command(cmd, sudo=False, log_out=True, show_output=False, check=True, interactive=False):
    global _LOG_INITIALIZED
    if sudo:
        cmd_line = f"sudo {cmd}"
    else:
        cmd_line = cmd
    sep = "-" * 60
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    header = f"\n{sep}\n[--- {timestamp}] Running: {cmd_line}\n\n"
    TMP_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not _LOG_INITIALIZED:
        with TMP_LOG_FILE.open("w", encoding="utf-8") as fh:
            fh.write(header)
        _LOG_INITIALIZED = True
    else:
        with TMP_LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(header)

    if interactive:
        try:
            rc = subprocess.run(cmd_line, shell=True)
            stdout = ""
            stderr = ""
            result = subprocess.CompletedProcess(args=cmd_line, returncode=rc.returncode, stdout=stdout, stderr=stderr)
            if rc.returncode != 0 and check:
                log_line(error=f"Command failed: {cmd_line} (rc={rc.returncode})", context="run_command")
                safe_exit(1, error=f"Command failed: {cmd_line} (rc={rc.returncode})")
            return result
        except Exception as e:
            log_line(error=str(e), context="run_command")
            if check:
                safe_exit(1, error=e)
            return subprocess.CompletedProcess(args=cmd_line, returncode=1, stdout="", stderr=str(e))

    process = subprocess.Popen(
        cmd_line,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
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
        args=cmd_line,
        returncode=rc,
        stdout="".join(stdout_lines),
        stderr=""  # stderr fusionné dans stdout
    )
    if check and result.returncode != 0:
        print(f"❌ Command failed (exit {result.returncode}): {cmd_line}")
        log_line(error=f"Command failed: {cmd_line} (rc={result.returncode})", context="run_command")
        safe_exit(1, error=f"Command failed (exit {result.returncode}): {result.stdout}")
    return result

def can_open_tkinter():
    return "DISPLAY" in os.environ and os.environ["DISPLAY"]

def show_help_window(lang):
    def open_help(lang):
        try:
            import tkinter as tk
            from tkinter import scrolledtext

            help_text = {
                "en": (
                    "ℹ️ LIRC Remote Configuration Help\n\n"
                    "Required keys for OliPi MoOde scripts:\n\n"
                    "• KEY_UP        → Navigate up / Volume + (outside menu)\n"
                    "• KEY_DOWN      → Navigate down / Volume - (outside menu)\n"
                    "• KEY_LEFT      → Previous / Seek -10s (long press) or menu left\n"
                    "• KEY_RIGHT     → Next / Seek +10s (long press) or menu right\n"
                    "• KEY_OK        → Open menu / Tools menu (long press) / Confirm\n"
                    "• KEY_BACK      → Switch between ui_playing/ui_browser/ui_queue (short/long)\n"
                    "• KEY_INFO      → Show context help\n"
                    "• KEY_CHANNELUP → Context action (e.g. add to favorites, multi-selection)\n"
                    "• KEY_CHANNELDOWN → Context action (e.g. remove from queue, unselect)\n"
                    "• KEY_PLAY      → Play/Pause or Reboot (long press)\n\n"
                    "Optional keys (if available on remote):\n\n"
                    "• KEY_STOP      → Stop playback or Shutdown (long press)\n"
                    "• KEY_NEXT      → Next / Seek +10s & +30s (long press & more)\n"
                    "• KEY_PREVIOUS  → Previous / Seek -10s & -30s (long press & more)\n"
                    "• KEY_FORWARD   → Seek +10s / +30s & +60s (long press & more)\n"
                    "• KEY_REWIND    → Seek -10s / -30s & -60s (long press & more)\n"
                    "• KEY_VOLUMEUP  → Volume +1 / -5 (long press)\n"
                    "• KEY_VOLUMEDOWN → Volume -1 / -5 (long press)\n"
                    "• KEY_MUTE      → Mute\n"
                    "• KEY_POWER     → Shutdown or Reboot (long press)\n\n"
                    "⚠️ After any change in LIRC configuration, LIRC and ui_playing will be restarted automatically.\n"
                ),
                "fr": (
                    "ℹ️ Aide configuration télécommande LIRC\n\n"
                    "(Liste des noms de touches à renseigner lors de l'apprentissage via irrecord)\n\n"
                    "Touches indispensables pour les scripts OliPi MoOde:\n"
                    "• KEY_UP        → Navigation haut / Volume + (hors menu)\n"
                    "• KEY_DOWN      → Navigation bas / Volume - (hors menu)\n"
                    "• KEY_LEFT      → Précédent / Seek -10s (appui long) ou menu gauche\n"
                    "• KEY_RIGHT     → Suivant / Seek +10s (appui long) ou menu droit\n"
                    "• KEY_OK        → Ouvrir menu / Menu Outils (appui long) / Validation\n"
                    "• KEY_BACK      → Basculer entre ui_playing/ui_browser/ui_queue (court/long)\n"
                    "• KEY_INFO      → Afficher l'aide contextuelle\n"
                    "• KEY_CHANNELUP → Action contextuelle (ex: ajouter favoris)\n"
                    "• KEY_CHANNELDOWN → Action contextuelle (ex: retirer de la file)\n"
                    "• KEY_PLAY      → Lecture/Pause ou Extinction (appui long)\n\n"
                    "Touches optionnelles (si présentes sur la télécommande):\n"
                    "• KEY_STOP      → Arrêter lecture\n"
                    "• KEY_NEXT      → Suivant / Seek +10s (appui long)\n"
                    "• KEY_PREVIOUS  → Précédent / Seek -10s (appui long)\n"
                    "• KEY_FORWARD   → Seek +10s\n"
                    "• KEY_REWIND    → Seek -10s\n"
                    "• KEY_VOLUMEUP  → Volume +\n"
                    "• KEY_VOLUMEDOWN → Volume -\n"
                    "• KEY_MUTE      → Mute\n"
                    "• KEY_POWER     → Redémarrer ou Éteindre (appui long)\n\n"
                    "⚠️ Après toute modification de configuration LIRC, les services LIRC et ui_playing seront redémarrés automatiquement.\n"
                )
            }

            window = tk.Tk()
            window.title("Help - LIRC" if lang == "en" else "Aide - LIRC")
            window.geometry("600x400")

            text_area = scrolledtext.ScrolledText(window, wrap=tk.WORD, font=("Arial", 12))
            text_area.insert(tk.END, help_text[lang])
            text_area.configure(state="disabled")
            text_area.pack(expand=True, fill="both")

            btn_close = tk.Button(window, text="OK", command=window.destroy)
            btn_close.pack(pady=5)

            window.mainloop()
        except Exception as e:
            log_line(error=f"⚠️ Failed to load Tkinter: {e}", context="show_help_window")
            pass

    thread = threading.Thread(target=open_help, args=(lang,), daemon=True)
    thread.start()

def safe_read_file_as_lines(path, critical=True):
    """Read file as lines as root."""
    try:
        res = run_command(f"cat {path}", sudo=True, log_out=True, show_output=False, check=False)
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
    """Write file as root: create a tmp file then sudo mv into place (preserve content)."""
    try:
        with tempfile.NamedTemporaryFile('w', delete=False, encoding="utf-8") as tmp:
            if isinstance(lines, list):
                for line in lines:
                    tmp.write(line if line.endswith("\n") else line + "\n")
            else:
                tmp.write(lines if lines.endswith("\n") else lines + "\n")
            tmp_path = tmp.name
        run_command(f"cp {tmp_path} {path}", sudo=True, log_out=False, show_output=False, check=True)
        run_command(f"rm -f {tmp_path}", sudo=True, log_out=False, show_output=False, check=False)
    except Exception as e:
        log_line(error=f"❌ Write file as root of {path} failed: {e}", context="safe_write_file_as_root")
        if critical:
            safe_exit(1, error=f"❌ Write file as root of {path} failed: {e}")
        else:
            print(f"⚠️ Write file as root of {path} failed, continuing anyway or ctrl+c to quit and check what wrong.")
            pass

def get_moode_version():
    res = run_command("moodeutl --mooderel", log_out=True, show_output=False, check=False)
    if res.returncode == 0 and res.stdout:
        return res.stdout.strip().split()[0]
    return None

def create_backup(path, lang, critical=True):
    moode_version = get_moode_version()
    if os.path.exists(path):
        backup_path = f"{path}.olipi-back-moode{moode_version}"
        if os.path.exists(backup_path):
            print(MESSAGES["backup_exist"][lang].format(backup_path))
            pass
        else:
            try:
                run_command(f"cp -p {path} {backup_path}", sudo=True, log_out=True, show_output=True, check=True)
                print(MESSAGES["backup_created"][lang].format(backup_path))
            except Exception as e:
                log_line(error=f"⚠ Backup of {path} failed: {e}", context="create_backup")
                if critical:
                    safe_exit(1, error=f"❌ Direct read of {path} failed: {e}")
                else:
                    print(f"⚠ Backup of {path} failed, continuing anyway or ctrl+c to quit and check what wrong.")
                    pass

# ---------- LIRC install / config functions ----------
def ask_gpio_pin(lang):
    while True:
        pin = input(MESSAGES["enter_pin"][lang]).strip()
        if pin.isdigit() and 0 <= int(pin) <= 40:
            return int(pin)
        print("❌ Invalid GPIO pin. Please enter a number between 0 and 40.")

def update_olipi_section(lines, marker, new_lines=None, replace_prefixes=None, clear=False):
    """
    Update the Olipi-moode section in config.txt and a '# @marker: {marker}' sub-block.
    - replace_prefixes: list of prefixes; any line in the whole file matching will be removed first.
    - clear=True: remove the contents under the marker (not the marker itself).
    """
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

def update_config_txt(lang):
    create_backup(CONFIG_TXT, lang)
    lines = safe_read_file_as_lines(CONFIG_TXT, critical=True)
    regex = re.compile(r"^dtoverlay=gpio-ir,\s*gpio_pin=(\d+)\s*$")
    existing_pin = None
    for line in lines:
        m = regex.match(line.strip())
        if m:
            existing_pin = int(m.group(1))
            break
    if existing_pin is not None:
        choice = input(MESSAGES["keep_existing_pin"][lang].format(existing_pin)).strip().lower()
        gpio_pin = existing_pin if choice not in ["n", "no"] else ask_gpio_pin(lang)
    else:
        gpio_pin = ask_gpio_pin(lang)
    lines = update_olipi_section(lines, "ir overlay", [f"dtoverlay=gpio-ir,gpio_pin={gpio_pin}"], replace_prefixes=["dtoverlay=gpio-ir,gpio_pin"])
    safe_write_file_as_root(CONFIG_TXT, lines, critical=True)
    print(MESSAGES["updating_config"][lang])
    log_line(msg=f"Updated {CONFIG_TXT} with gpio_pin={gpio_pin}", context="update_config_txt")

def update_lirc_options(lang):
    create_backup(LIRC_OPTIONS, lang)
    lines = safe_read_file_as_lines(LIRC_OPTIONS, critical=True)
    updated_lines = []
    in_lircd = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[lircd]"):
            in_lircd = True
            updated_lines.append(line if line.endswith("\n") else line + "\n")
            continue
        if stripped.startswith("[") and stripped != "[lircd]":
            in_lircd = False
            updated_lines.append(line if line.endswith("\n") else line + "\n")
            continue
        if in_lircd:
            if stripped.startswith("driver"):
                updated_lines.append("driver          = default\n")
            elif stripped.startswith("device"):
                updated_lines.append("device          = /dev/lirc0\n")
            elif stripped.startswith("output"):
                updated_lines.append("output          = /run/lirc/lircd\n")
            elif stripped.startswith("pidfile"):
                updated_lines.append("pidfile         = /run/lirc/lircd.pid\n")
            else:
                updated_lines.append(line if line.endswith("\n") else line + "\n")
        else:
            updated_lines.append(line if line.endswith("\n") else line + "\n")
    safe_write_file_as_root(LIRC_OPTIONS, updated_lines, critical=True)
    print(MESSAGES["lirc_conf_update"][lang])
    log_line(msg=f"Updated {LIRC_OPTIONS} (driver, device, socket sync)", context="update_lirc_options")

def enable_use_lirc_in_config(lang):
    if not os.path.exists(CONFIG_INI):
        print("⚠️ Config.ini not found. Please reinstall OliPi Moode.")
        log_line(msg=f"{CONFIG_INI} not found", context="enable_use_lirc_in_config")
        return
    try:
        with open(CONFIG_INI, "r", encoding="utf-8") as f:
            lines = f.readlines()
        found = False
        for i, line in enumerate(lines):
            if line.strip().lower().startswith("use_lirc"):
                parts = line.split("=")
                if len(parts) >= 2:
                    lines[i] = "use_lirc = true\n"
                    found = True
                break
        if found:
            print(MESSAGES["enable_use_lirc"][lang])
            with open(CONFIG_INI, "w", encoding="utf-8") as f:
                f.writelines(lines)
            print(MESSAGES["use_lirc_enabled"][lang])
            log_line(msg="'use_lirc' set true in config.ini", context="enable_use_lirc_in_config")
        else:
            print(MESSAGES["use_lirc_not_found"][lang])
            log_line(msg="'use_lirc' not found in config.ini", context="enable_use_lirc_in_config")
    except Exception as e:
        log_line(error=f"❌ Error writing config.ini: {e}", context="enable_use_lirc_in_config")
        print(f"⚠️ Error writing in config.ini: {e}, continuing anyway or ctrl+c to quit and check what wrong.")
        pass

# ---------- Remote manager functions ----------
def restart_lirc_and_ui_playing(lang, sudo=True):
    try:
        # Stop UI first (important: it uses irw)
        run_command("systemctl stop olipi-ui-playing", sudo=sudo, interactive=False, show_output=True, log_out=True, check=False)
        #print(MESSAGES["ui_playing_stop"][lang])
        time.sleep(0.3)

        # Fully reset LIRC (service + socket)
        run_command("systemctl stop lircd.service lircd.socket", sudo=sudo, interactive=False, show_output=True, log_out=True, check=False)
        time.sleep(0.3)

        run_command("systemctl start lircd.socket", sudo=sudo, interactive=False, show_output=True, log_out=True, check=False)
        time.sleep(0.3)

        run_command("systemctl start lircd.service", sudo=sudo, interactive=False, show_output=True, log_out=True, check=False)
        print(MESSAGES["lirc_restart"][lang])
        time.sleep(0.5)

        # Restart UI last
        run_command("systemctl start olipi-ui-playing",sudo=sudo, interactive=False, show_output=True, log_out=True, check=False)
        print(MESSAGES["ui_playing_restart"][lang])

    except Exception as e:
        log_line(error=f"⚠ Error restart service: {e}", context="restart_lirc_and_ui_playing")
        print(f"⚠️ Error restart service: {e}")

def stop_ui_playing(lang, sudo=True):
    try:
        run_command("systemctl stop olipi-ui-playing", sudo=sudo, interactive=False, show_output=True, log_out=True, check=False)
        print(MESSAGES["ui_playing_stop"][lang])
    except Exception as e:
        log_line(error=f"⚠ Error stop service: {e}", context="stop_ui_playing")
        print(f"⚠️ Error stop service: {e}, continuing anyway or ctrl+c to quit and check what wrong.")
        pass

def test_ir(lang):
    print(MESSAGES["testing_info"][lang])
    stop_ui_playing(lang)
    try:
        run_command("mode2 -d /dev/lirc0", sudo=False, interactive=True, check=False)
    except KeyboardInterrupt:
        log_line(msg=f"Test IR interrupted by user (Ctrl+C)", context="test_ir")
        pass
    restart_lirc_and_ui_playing(lang)

def search_remotes(query):
    res = run_command(f"irdb-get find '{query}'", sudo=False, interactive=False, show_output=False, log_out=True, check=False)
    lines = [l.strip() for l in res.stdout.strip().splitlines() if l.strip()] if res.stdout else []
    return lines

def download_remote(selected, lang):
    print(MESSAGES["downloading"][lang].format(selected))
    run_command(f"cd {LIRC_CONF_DIR} && sudo irdb-get download '{selected}'", sudo=False, interactive=False, show_output=True, log_out=True, check=False)
    print(MESSAGES["download_done"][lang].format(LIRC_CONF_DIR))
    restart_lirc_and_ui_playing(lang)

def learn_ir(lang):
    print(MESSAGES["learning_info"][lang])
    stop_ui_playing(lang)
    try:
        run_command(f"cd {LIRC_CONF_DIR} && sudo irrecord -k -d /dev/lirc0", sudo=False, interactive=True, check=False)
    except KeyboardInterrupt:
        log_line(msg=f"Learn IR interrupted by user (Ctrl+C)", context="learn_ir")
        pass
    restart_lirc_and_ui_playing(lang)

def list_configs():
    try:
        files = sorted([f for f in os.listdir(LIRC_CONF_DIR) if f.endswith(".lircd.conf") or f.endswith(".lircd.conf.back")])
        return [os.path.join(LIRC_CONF_DIR, f) for f in files]
    except Exception as e:
        log_line(error=f"❌ Failed to list LIRC config files in {LIRC_CONF_DIR}: {e}", context="list_configs")
        print(f"⚠️ Could not access {LIRC_CONF_DIR}: {e}, continuing anyway or ctrl+c to quit and check what wrong.")
        return []

def test_irw(lang):
    print(MESSAGES["testing_irw"][lang])
    stop_ui_playing(lang)
    try:
        run_command("irw", sudo=False, interactive=True, check=False)
    except KeyboardInterrupt:
        log_line(msg=f"Test irw interrupted by user (Ctrl+C)", context="testing_irw")
        pass
    restart_lirc_and_ui_playing(lang)

def toggle_config_state(config_file, lang):
    if config_file.endswith(".back"):
        new_file = config_file.removesuffix(".back")
        run_command(f"mv '{config_file}' '{new_file}'", sudo=True, interactive=False, check=True)
        print(MESSAGES["enabled"][lang])
    else:
        new_file = config_file + ".back"
        run_command(f"mv '{config_file}' '{new_file}'", sudo=True, interactive=False, check=True)
        print(MESSAGES["disabled"][lang])
    restart_lirc_and_ui_playing(lang)

def delete_config(config_file, lang):
    run_command(f"rm '{config_file}'", sudo=True, interactive=False, check=True)
    print(MESSAGES["deleted"][lang])
    restart_lirc_and_ui_playing(lang)

def manage_configs(lang):
    configs = list_configs()
    if not configs:
        print("❌ " + ("No configs found." if lang == "en" else "Aucune configuration trouvée."))
        return
    ITEMS_PER_PAGE = 20
    total_pages = (len(configs) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    page = 0
    while True:
        start = page * ITEMS_PER_PAGE
        end = min(start + ITEMS_PER_PAGE, len(configs))
        print("\n" + (("Select config (page {}/{})".format(page+1, total_pages)) if lang=="en" else ("Choisissez la configuration (page {}/{})".format(page+1, total_pages))))
        for i, conf in enumerate(configs[start:end]):
            status = "[DISABLED]" if conf.endswith(".back") else "[ACTIVE]"
            print(f"[{i}] {status} {conf}")
        choice = input("Enter index, 'n' next, 'p' prev, 'q' cancel: ").strip().lower()
        if choice == "q":
            break
        elif choice == "n" and page + 1 < total_pages:
            page += 1
        elif choice == "p" and page > 0:
            page -= 1
        elif choice.isdigit():
            idx = int(choice)
            if 0 <= idx < (end - start):
                config_file = configs[start + idx]
                print(f"\nSelected: {config_file}")
                while True:
                    toggle_label = (MESSAGES["enable_config"][lang] if config_file.endswith(".back") else MESSAGES["disable_config"][lang]) if "enable_config" in MESSAGES else "Toggle"
                    action = input(MESSAGES["config_actions"][lang].format(toggle_label)).strip()
                    if action == "1":
                        # open editor as sudo in interactive mode
                        run_command(f"nano '{config_file}'", sudo=True, interactive=True, check=False)
                        restart_lirc_and_ui_playing(lang)
                    elif action == "2":
                        stop_ui_playing(lang)
                        run_command(f"cd {LIRC_CONF_DIR} && sudo irrecord -k -d /dev/lirc0 -u '{config_file}'", sudo=False, interactive=True, check=False)
                        restart_lirc_and_ui_playing(lang)
                    elif action == "3":
                        toggle_config_state(config_file, lang)
                        break
                    elif action == "4":
                        delete_config(config_file, lang)
                        break
                    elif action == "5":
                        break
                    else:
                        print(MESSAGES["invalid_choice"][lang])
                break
            else:
                print(MESSAGES["invalid_choice"][lang])
        else:
            print(MESSAGES["invalid_choice"][lang])

def save_remote_mapping(config, required_keys, optional_keys):
    # keep comments and structure
    lines = []
    if os.path.exists(CONFIG_INI):
        with open(CONFIG_INI, "r", encoding="utf-8") as f:
            lines = f.readlines()
    new_section = []
    new_section.append("[remote_mapping]\n")
    new_section.append("\n# Required keys (essential for OliPi MoOde navigation)\n")
    for key in required_keys:
        value = config["remote_mapping"].get(key, "—")
        new_section.append(f"{key} = {value}\n")
    new_section.append("\n# Optional keys (additional multimedia controls)\n")
    for key in optional_keys:
        value = config["remote_mapping"].get(key, "—")
        new_section.append(f"{key} = {value}\n")

    start_idx = None
    end_idx = None
    for i, line in enumerate(lines):
        if line.strip().lower() == "[remote_mapping]":
            start_idx = i
            for j in range(i + 1, len(lines)):
                if lines[j].strip().startswith("[") and j > i:
                    end_idx = j
                    break
            if end_idx is None:
                end_idx = len(lines)
            break
    if start_idx is not None:
        lines = lines[:start_idx] + new_section + lines[end_idx:]
    else:
        if lines and not lines[-1].endswith("\n"):
            lines.append("\n")
        lines += ["\n"] + new_section
    with open(CONFIG_INI, "w", encoding="utf-8") as f:
        f.writelines(lines)

def map_single_key(key_name, config, lang):
    user_input = input(MESSAGES["mapping_press_key"][lang].format(key_name)).strip().lower()
    if user_input == "skip":
        return
    print(MESSAGES["mapping_listen"][lang].format(key_name))
    try:
        irw = subprocess.Popen(["irw"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except Exception as e:
        print("❌ Failed to run irw:", e)
        log_line(error=f"❌ Failed to run irw: {e}", context="map_single_key")
        return
    try:
        for line in irw.stdout:
            parts = line.strip().split()
            if len(parts) >= 3:
                detected_key = parts[2].upper()
                # conflict check
                for action, assigned_key in config["remote_mapping"].items():
                    if assigned_key == detected_key and action != key_name:
                        print(MESSAGES["mapping_conflict"][lang].format(detected_key, action))
                        choice = input(MESSAGES["mapping_override"][lang]).strip().lower()
                        if choice.startswith("o"):
                            config["remote_mapping"][action] = ""
                            print(MESSAGES["mapping_reassigned"][lang].format(detected_key, key_name))
                        else:
                            print(MESSAGES["mapping_cancelled"][lang])
                            irw.terminate()
                            return
                reserved_keys = [
                    "KEY_UP", "KEY_DOWN", "KEY_LEFT", "KEY_RIGHT",
                    "KEY_OK", "KEY_BACK", "KEY_INFO",
                    "KEY_CHANNELUP", "KEY_CHANNELDOWN", "KEY_PLAY",
                    "KEY_STOP", "KEY_NEXT", "KEY_PREVIOUS",
                    "KEY_FORWARD", "KEY_REWIND", "KEY_VOLUMEUP",
                    "KEY_VOLUMEDOWN", "KEY_MUTE", "KEY_POWER"
                ]
                if detected_key in reserved_keys and detected_key != key_name:
                    print(MESSAGES["mapping_reserved"][lang].format(detected_key))
                    choice = input(MESSAGES["mapping_force_reserved"][lang]).strip().lower()
                    if not choice.startswith("o"):
                        print(MESSAGES["mapping_cancelled"][lang])
                        irw.terminate()
                        return
                print(MESSAGES["mapping_detected"][lang].format(detected_key))
                config["remote_mapping"][key_name] = detected_key
                break
    except KeyboardInterrupt:
        print("\n" + MESSAGES["mapping_cancelled"][lang])
        log_line(msg=f"Map Single Key interrupted by user (Ctrl+C)", context="map_single_key")
    finally:
        try:
            irw.terminate()
        except Exception as e:
            log_line(error=f"⚠️ Error terminate irw: {e}", context="map_single_key")
            print(f"⚠️ Error terminate irw: {e}, continuing anyway or ctrl+c to quit and check what wrong.")
            pass

def map_remote_keys(lang, edit_mode=False):
    print(MESSAGES["mapping_start"][lang])
    required_keys = [
        "KEY_UP", "KEY_DOWN", "KEY_LEFT", "KEY_RIGHT",
        "KEY_OK", "KEY_BACK", "KEY_INFO",
        "KEY_CHANNELUP", "KEY_CHANNELDOWN", "KEY_PLAY"
    ]
    optional_keys = [
        "KEY_STOP", "KEY_NEXT", "KEY_PREVIOUS",
        "KEY_FORWARD", "KEY_REWIND", "KEY_VOLUMEUP",
        "KEY_VOLUMEDOWN", "KEY_MUTE", "KEY_POWER"
    ]
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_INI):
        config.read(CONFIG_INI)
    if "remote_mapping" not in config:
        config["remote_mapping"] = {}
    stop_ui_playing(lang)
    try:
        if not edit_mode:
            for key in required_keys:
                map_single_key(key, config, lang)
            choice = input(MESSAGES["optional_keys_prompt"][lang]).strip().lower()
            if choice in ["", "y", "o"]:
                for key in optional_keys:
                    map_single_key(key, config, lang)
        # edit loop
        while True:
            print("\n" + ("📋 Required keys:" if lang == "en" else "📋 Touches indispensables :"))
            for idx, key in enumerate(required_keys, 1):
                mapped = config["remote_mapping"].get(key, "—")
                display_value = mapped if mapped != "—" else ("Not mapped" if lang == "en" else "Non mappée")
                print(f"[{idx}] {key} → {display_value}")

            print("\n" + ("📋 Optional keys:" if lang == "en" else "📋 Touches optionnelles :"))
            for idx, key in enumerate(optional_keys, len(required_keys) + 1):
                mapped = config["remote_mapping"].get(key, "—")
                display_value = mapped if mapped != "—" else ("Not mapped" if lang == "en" else "Non mappée")
                print(f"[{idx}] {key} → {display_value}")

            prompt = "Enter index to re-map, 's' to save, 'c' to cancel:" if lang == "en" else "Entrez l'index pour re-mapper, 's' pour sauvegarder, 'c' pour annuler :"
            action = input(f"\n{prompt}\n> ").strip().lower()
            if action == "s":
                save_remote_mapping(config, required_keys, optional_keys)
                print(MESSAGES["mapping_saved"][lang])
                break
            elif action == "c":
                print(MESSAGES["mapping_cancelled"][lang])
                break
            elif action.isdigit():
                idx = int(action)
                if 1 <= idx <= len(required_keys) + len(optional_keys):
                    all_keys = required_keys + optional_keys
                    key_to_remap = all_keys[idx - 1]
                    map_single_key(key_to_remap, config, lang)
                else:
                    print(MESSAGES["invalid_choice"][lang])
            else:
                print(MESSAGES["invalid_choice"][lang])
    finally:
        restart_lirc_and_ui_playing(lang)

def check_lirc_installed(lang):
    res = run_command("dpkg -s lirc >/dev/null 2>&1", sudo=False, log_out=False, show_output=False, check=False)
    if res.returncode == 0:
        print(MESSAGES["lirc_installed"][lang])
        log_line(msg="dpkg reports lirc installed", context="check_lirc_installed")
        return True
    else:
        print(MESSAGES["lirc_missing"][lang])
        log_line(msg="dpkg reports lirc not installed", context="check_lirc_installed")
        return False
        
def install_lirc(lang):
    try:
        print(MESSAGES["installing_lirc"][lang])
        log_line(msg="Installing lirc via apt", context="install_lirc")
        run_command("apt-get update", sudo=True, log_out=True, show_output=True, check=False)
        run_command("apt-get install -y lirc", sudo=True, log_out=True, show_output=True, check=True)
        log_line(msg="lirc installed", context="install_lirc")
    except Exception as e:
        safe_exit(1, error=e)
        
# ---------- main ----------
def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--lang", required=False, choices=["en", "fr"])
    # other flags could be added in future
    args, remaining = parser.parse_known_args()
    if args.lang:
        lang = args.lang
    else:
        lang = "en"
        print(MESSAGES["choose_language"][lang])
        print(MESSAGES["language_options"][lang])
        choice = input(" > ").strip()
        if choice == "2":
            lang = "fr"
        elif choice != "1":
            print(MESSAGES["invalid_choice"][lang])

    lirc_installed = False
    reinstall_lirc = False
    if check_lirc_installed(lang):
        lirc_installed = True
        choice = input(MESSAGES["lirc_prompt"][lang]).strip().lower()
        if choice in ["o", "y"]:
            reinstall_lirc = True
        else:
            reinstall_lirc = False
    
    if not lirc_installed or reinstall_lirc:
        print(MESSAGES["start_config_lirc"][lang])
        print(MESSAGES["explain"][lang])
        accept = input(MESSAGES["accept_prompt"][lang]).strip().lower()
        if accept not in ["", "y", "o"]:
            print(MESSAGES["accept_cancelled"][lang].format(INSTALL_LIRC_REMOTE_PATH))
            with TMP_LOG_FILE.open("a", encoding="utf-8") as fh:
                fh.write(f"+++++++++\n[ABORTED] ❌ Installation interrupted by user (Ctrl+C).\n")
            print("❌ Installation interrupted by user (Ctrl+C).")
            safe_exit(130)
        # perform install/config
        install_lirc(lang)
        update_config_txt(lang)
        update_lirc_options(lang)
        enable_use_lirc_in_config(lang)
        print(MESSAGES["remote_setup_info"][lang].format(INSTALL_LIRC_REMOTE_PATH))
        reboot = input(MESSAGES["reboot_prompt"][lang]).strip().lower()
        if reboot in ["", "y", "o"]:
            print(MESSAGES["rebooting"][lang])
            log_line(msg="lirc installed and configured, rebooting", context="main reboot")
            finalize_log(0)
            run_command("reboot", sudo=True, interactive=False, check=False)
        else:
            print(MESSAGES["reboot_cancelled"][lang])
            log_line(msg="lirc installed and configured, Reboot cancelled.", context="main reboot")
            safe_exit(0)

    else:
        print(MESSAGES["start_config_remote"][lang])

    if can_open_tkinter():
        show_help_window(lang)
    else:
        print(MESSAGES["help_unavailable"][lang])

    while True:
        choice = input(MESSAGES["menu"][lang]).strip()
        if choice == "1":
            test_ir(lang)
        elif choice == "2":
            query = input("Enter brand or model to search: ").strip()
            if not query:
                print("No query.")
                continue
            lines = search_remotes(query)
            if not lines:
                print("❌ " + ("No results found." if lang == "en" else "Aucun résultat trouvé."))
                continue
            # pagination
            per_page = 20
            total_pages = (len(lines) + per_page - 1) // per_page
            page = 0
            while True:
                start = page * per_page
                end = min(start + per_page, len(lines))
                print(("\nSearch results (page {}/{})".format(page+1, total_pages) if lang=="en" else "\nRésultats (page {}/{})".format(page+1, total_pages)))
                for i, line in enumerate(lines[start:end]):
                    print(f"[{i}] {line}")
                choice_dl = input("Enter index to download, 'n' next, 'p' prev, 'q' cancel: ").strip().lower()
                if choice_dl == "q":
                    break
                elif choice_dl == "n" and page + 1 < total_pages:
                    page += 1
                elif choice_dl == "p" and page > 0:
                    page -= 1
                elif choice_dl.isdigit():
                    idx = int(choice_dl)
                    if 0 <= idx < (end - start):
                        selected = lines[start + idx]
                        download_remote(selected, lang)
                        break
                    else:
                        print(MESSAGES["invalid_choice"][lang])
                else:
                    print(MESSAGES["invalid_choice"][lang])
        elif choice == "3":
            learn_ir(lang)
        elif choice == "4":
            manage_configs(lang)
        elif choice == "5":
            test_irw(lang)
        elif choice == "6":
            map_remote_keys(lang)
        elif choice == "7":
            map_remote_keys(lang, edit_mode=True)
        elif choice == "8":
            print(MESSAGES["exiting"][lang])
            finalize_log(0)
            break
        else:
            print(MESSAGES["invalid_choice"][lang])

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        with TMP_LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(f"+++++++++\n[ABORTED] ❌ Installation interrupted by user (Ctrl+C).\n")
        print("❌ Installation interrupted by user (Ctrl+C).")
        safe_exit(130)
    except Exception as e:
        print("Unexpected error:", e)
        safe_exit(1, error=e)
