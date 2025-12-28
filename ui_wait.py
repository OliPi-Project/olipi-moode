#!/usr/bin/python3
import time
import os
import sys
import subprocess
import requests
from pathlib import Path

OLIPIMOODE_DIR = Path(__file__).resolve().parent
os.environ.setdefault("OLIPI_DIR", str(OLIPIMOODE_DIR))

from olipi_core import core_common as core

TIMEOUT_MOODE = 300

font_large = core.get_font("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)

def show_message_centered(text1, text2=""):
    core.draw.rectangle((0, 0, core.width, core.height), fill=core.COLOR_BG)
    bbox1 = core.draw.textbbox((0, 0), text1, font=font_large)
    tw1 = bbox1[2] - bbox1[0]
    th1 = bbox1[3] - bbox1[1]
    x1 = (core.width - tw1) // 2
    if text2:
        bbox2 = core.draw.textbbox((0, 0), text2, font=font_large)
        tw2 = bbox2[2] - bbox2[0]
        th2 = bbox2[3] - bbox2[1]
        x2 = (core.width - tw2) // 2
        total_h = th1 + th2 + 7
        y1 = (core.height - total_h) // 2
        y2 = y1 + th1 + 7
        core.draw.text((x1, y1), text1, font=font_large, fill=core.COLOR_TEXT)
        core.draw.text((x2, y2), text2, font=font_large, fill=core.COLOR_TEXT)
    else:
        y1 = (core.height - th1) // 2
        core.draw.text((x1, y1), text1, font=font_large, fill=core.COLOR_TEXT)
    core.refresh()

def wait_for_moode(timeout=TIMEOUT_MOODE):
    frames = ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"]
    start = time.time()
    frame = 0
    while True:
        try:
            r = requests.get("http://localhost/command/?cmd=status", timeout=0.2)
            if "state:" in r.text:
                return True
        except Exception:
            pass

        msg1 = "Waiting MoOde"
        msg2 = f"{frames[frame % len(frames)]}"
        show_message_centered(msg1, msg2)

        frame += 1
        time.sleep(0.2)

        if time.time() - start > timeout:
            show_message_centered("MoOde Not Ready", "Restarting Wait Service")
            time.sleep(1)
            return False

if not wait_for_moode():
    sys.exit("MoOde not Avaible")

show_message_centered("MoOde Ready!")
time.sleep(1)

print("Lancement de olipi-ui-playing.service...")
subprocess.call(["sudo", "systemctl", "start", "olipi-ui-playing"])
sys.exit(0)
