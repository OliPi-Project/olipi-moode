 ![License](https://img.shields.io/github/license/OliPi-Project/olipi-moode)
![Python](https://img.shields.io/badge/python-3.9+-blue)
![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi-red)
![Discord](https://img.shields.io/discord/1410910825870266391?logo=discord&logoColor=white&logoSize=auto&label=Discord&color=blue&link=https%3A%2F%2Fdiscord.gg%2Fpku67XsFEE)
![GitHub Release](https://img.shields.io/github/v/release/OliPi-Project/olipi-moode?include_prereleases&sort=date&display_name=tag)

# OliPi MoOde

OliPi MoOde is an user interface for OLED/LCD screens >= 128x64 for [Moode Audio](https://moodeaudio.org/) with control via IR remote control and/or GPIO buttons.

<p align="center">
  <img src="https://github.com/OliPi-Project/olipi-moode/blob/main/docs/screenshots/TFT_demo.gif" width="400" alt="All Screens Demo">
  <img src="https://github.com/OliPi-Project/olipi-moode/blob/main/docs/screenshots/SSD1306_demo.gif" width="400" alt="Menus Demo">
</p>

Video presentation:
[https://youtu.be/9Y13UeyyT7k?si=hkOkiP9gk0rjxlB8](https://youtu.be/9Y13UeyyT7k?si=hkOkiP9gk0rjxlB8)

---

## 📚 Table of Contents

- [Features](#-features)
- [System requirements](#-system-requirements)
- [Installation](#-installation)
- [Services](#-services)
- [IR remote configuration](#-ir-remote-configuration)
- [GPIO and rotary encoder support](#-gpio-and-rotary-encoder-support)
- [Key configuration](#-key-configuration)
- [Configuration via tools menu](#-configuration-via-tools-menu-in-uiplaying)
- [ZRAM](#-zram-on-low-memory-devices)
- [Moode configuration reminder](#-moode-configuration-reminder)
- [Uninstall](#-uninstall)
- [Troubleshooting](#-troubleshooting)
- [Contributing](#-contributing)
- [License](#-license)
- [Disclaimer](#-disclaimer)

---

## ✨ Features

- **ui_playing**: Displays the current track, metadata, playback status, hardware info, etc. Media controls, add/remove favorites (follows the playlist configured in Moode), playback modes, renderers (Bluetooth, Airplay, and UPNP), search for the currently playing artist in the music library… And a little extra: Logs radio track titles (via the "favorites" button) into a text file to list them in the menu, and lets you search them via yt-dlp and replay them via a local stream/radio (no download).
- **ui_browser**: Browse the music library, search, move, copy, delete to/from local or USB storage.
- **ui_queue**: Displays and manages the playback queue. Playlist creation.
- **Configuration help and IR remote mapping**: Assisted and fully customizable LIRC configuration with conflict detection. Ability to add custom actions to unused keys in OliPi MoOde (see the `handle_custom_key` function in `media_key_actions.py`... *to be made more user-friendly*).
- **GPIO button and rotary encoder support** using `rpi_lgpio` . Enable and configure pins in `config.ini` under the "manual" section.
- **ZRAM configuration** for low-memory devices (e.g., Raspberry Pi Zero 2W).
- Automatic integration with Moode’s "Ready Script" for smooth startup.

---

## 📦 System requirements

- **Operating system**: Moode Audio Player ≥ 9.3.7 required.

- **Hardware**: Raspberry Pi (Zero 2W, 3, 4, 5) + I2C or SPI screen. An IR receiver type TSOP38 and/or push buttons and/or rotary encoder with or without push
  
  Screens supported:
  
  | Screen      | Resolution | Diag (") | PPI | Color      | Script                       |
  | ----------- | ---------- | -------- | --- | ---------- | ---------------------------- |
  | SSD1309     | 128×64     | 2.49     | 58  | Monochrome | SSD1306.py (To be confirmed) |
  | SSD1306     | 128×64     | 0.96     | 149 | Monochrome | SSD1306.py                   |
  | SSD1315     | 128×64     | 0.96     | 149 | Monochrome | SSD1306.py                   |
  | SSD1351     | 128×128    | 1.5      | 120 | RGB        | SSD1351.py                   |
  | ST7735R     | 128×160    | 1.77     | 116 | BGR        | ST7735R.py                   |
  | ST7789 1.9" | 170×320    | 1.9      | 191 | RGB        | ST7789W.py                   |
  | ST7789 2"   | 240×320    | 2.0      | 200 | RGB        | ST7789V.py                   |
  
  Below 150 PPI font size are fixed.
  Above 150 PPI font size are scaled by (ppi / 150) x 1.2 caped at x1.6
  
  For SPI screen Plan your wiring carefully: OliPi-Moode uses several GPIOs for buttons, IR and audio control if you use I2s DAC and/or GPIOs buttons/rotary. 
  
  For more information about wiring, check the [FAQ & Troubleshooting guide](./TROUBLESHOOTING.md).
  
- **APT dependencies** (installed automatically):
  
  ```bash
  git python3-pil python3-venv python3-pip python3-tk libatlas-base-dev
  i2c-tools libgpiod-dev python3-libgpiod python3-lgpio python3-setuptools
  ```

- **Python dependencies** (installed automatically):
  
  ```txt
  Adafruit_Blinka~=8.55.0
  adafruit_circuitpython_rgb_display~=3.14.1
  adafruit_circuitpython_ssd1306~=2.12.21
  rpi_lgpio~=0.6
  Pillow~=11.3.0
  python_mpd2~=3.0.5
  PyYAML~=6.0.2
  Requests~=2.32.4
  yt_dlp>=2025.7.21
  numpy~=2.3.2
  pyalsaaudio~=0.11.0
  scipy~=1.16.1
  ```

---

## 🚀 Installation

***Beware of performance issues on the Pi Zero2 W and Pi3a/B+ with higher resolutions like 170x320 or 240x320 (need to up the `spidev.bufsiz=131072` in /boot/firmware/cmdline.txt keep all text on 1 line, and set the `baudrate = 100000000` with a `refresh_interval = 0.01` in the config.ini )...
For better smooth scrolling, I2C screens (like ssd1306) it's a good thing to increase the bauderate to 400k with `dtparam=i2c_baudrate=400000` in /boot/firmware/config.txt (400k seems to be compatible with DACs)
I'm looking for a solution to use the Raspberry-Pi FBTFT overlays directly rather than going through the Adafruit libraries.***

First of all, make sure you've wired your screen, buttons and IR receiver correctly.
[See wiring guide](TROUBLESHOOTING.md#wiring--screen-does-not-turn-on-after-installation).

If you have [MoodeOled](https://github.com/Trachou2Bois/MoodeOled) installed, check [here](https://github.com/Trachou2Bois/MoodeOled/blob/main/README.md#moodeoled-has-grown) to uninstall it before install OliPi Moode.


1. Clone this repository:
   
   ```bash
   sudo apt update && sudo apt install git
   git clone https://github.com/OliPi-Project/olipi-moode
   ```

2. Run the setup script:
   
   ```bash
   python3 ~/olipi-moode/install/setup.py
   ```

3. Follow the on-screen instructions.
   
       This script performs the following actions:
       
       - Detects Moode version.
       - Installs APT and Python dependencies.
       - Clone latest release from olipi-core
       - Offers to select from supported screens
       - Configures I²C or SPI if disabled.
       - Offers to fill in the pins for the spi screens
       - Offers ZRAM configuration if 512MB RAM and/or swap detected.
       - Creates a virtual environment (`~/.olipi-moode-venv` by default).
       - Installs systemd services.
       - Modify ready script for starting ui_playing service after Moode boot
       - Append some lines with useful commands to .profile
       - Create file with versions and paths in install dir.
       
       It can be reused for update OliPi Moode or force reinstall

---

## 🖥 Services

The following systemd services are created during installation:

| Service      | Description                   |
| ------------ | ----------------------------- |
| `ui_playing` | Displays "Now Playing" screen |
| `ui_browser` | Music library navigation      |
| `ui_queue`   | Playback queue display        |
| `ui_off`     | Turns off screen at shutdown  |

Switch between the 3 main display scripts using the `KEY_BACK` button.

---

## 🎛 IR remote configuration

OliPi MoOde includes an interactive script to configure LIRC:

```bash
python3 ~/olipi-moode/install/install_lirc_remote.py
```

Features:

- Install and configure LIRC.
- Hardware test (`mode2`, `irw`).
- Download a configuration from `irdb-get`.
- Learn a remote control (`irrecord`).
- **Mapping editor**:
  - Reassign all keys or individually.
  - Conflict detection (confirmation if a key is already mapped).
  - Warning if mapping a system key (e.g., `KEY_UP`).

Mappings are stored in `config.ini`:

```ini
[remote_mapping]
#KEY_OLIPIMOODE = YOUR_REMOTE_KEY
# Required keys
KEY_PLAY = KEY_PLAYPAUSE
KEY_BACK = KEY_ESC
...
# Optional keys
KEY_FORWARD = KEY_FASTFORWARD
KEY_NEXT = KEY_NEXTSONG
```

---

## ⌨ GPIO and rotary encoder support

OliPi MoOde uses `rpi_lgpio`, you can configure GPIO buttons or rotary encoders in `config.ini`. Be careful not to use pins that are used for other things. Check your hardware before enabling "use_gpio" and "use_rotary""

Example:

```ini
[manual]
use_gpio = true
use_rotary = true

[buttons]
KEY_PLAY = 17
KEY_STOP = 27

[rotary]
pin_a = 22
pin_b = 23
pin_btn = 24
```

---

## **🎛 Key configuration**

### 🔑 Essential keys

These keys are **required** to navigate and control all interfaces:

| Key                 | Generic role                                        | Specific usage in `ui_playing`                     |
| ------------------- | --------------------------------------------------- | -------------------------------------------------- |
| **KEY_UP**          | Move up                                             | Volume + if outside menu                           |
| **KEY_DOWN**        | Move down                                           | Volume - if outside menu                           |
| **KEY_LEFT**        | Move left                                           | Previous / Seek -10s (long press) if outside menu  |
| **KEY_RIGHT**       | Move right                                          | Next / Seek +10s (long press) if outside menu      |
| **KEY_OK**          | Open menu / Tools menu (long press) / Confirm       | Same                                               |
| **KEY_BACK**        | Switch to `ui_browser`/`ui_queue`/`ui_playing`      | Switch to `ui_browser` (short) / `ui_queue` (long) |
| **KEY_INFO**        | Show contextual help                                | Same                                               |
| **KEY_CHANNELUP**   | Context action                                      | Add/Remove favorites, if radio: add to songlog     |
| **KEY_CHANNELDOWN** | Context action                                      | Remove from queue                                  |
| **KEY_PLAY**        | If outside menu: Play/Pause / Shutdown (long press) | Same                                               |

These keys must be configured either via LIRC (`python3 ~/olipi-moode/install/install_lirc_remote.py`) or via GPIO (`[buttons]` section in `config.ini`).

### 🎵 Optional media keys

Recommended if available on your remote, but **not mandatory**:

| Key                | Action                            |
| ------------------ | --------------------------------- |
| **KEY_STOP**       | Stop playback                     |
| **KEY_NEXT**       | Next / Seek +10s (long press)     |
| **KEY_PREVIOUS**   | Previous / Seek -10s (long press) |
| **KEY_FORWARD**    | Seek +10s                         |
| **KEY_REWIND**     | Seek -10s                         |
| **KEY_VOLUMEUP**   | Volume +                          |
| **KEY_VOLUMEDOWN** | Volume -                          |
| **KEY_MUTE**       | Mute                              |
| **KEY_POWER**      | Restart / Shutdown (long press)   |

> **Note:** In `ui_playing`, navigation keys (`UP`, `DOWN`, `LEFT`, `RIGHT`) can replace optional media keys if they are not present.

---

## 🔧 Configuration via tools menu in ui_playing

A small on-screen configuration menu allows you to change:

- Screen sleep delay  
- Local stream quality (radio favorites)  
- Language (currently English and French)  
- Enable/disable debug mode  
- Change color theme

---

## 🧠 ZRAM on low-memory devices

If your Raspberry Pi has **512MB RAM** (e.g., Zero 2W or 3 A+):

- The installer offers to install `zram-tools` and configure ZRAM (256 MB, lz4).
- Completely disables swap.

---

## ⚠️ Moode configuration reminder

In **Moode > System Config**:

- Enable **Ready Script** (System).
- Enable **LCD Updater** (Peripherals).

---

## 🔧 Uninstall

You can uninstall all without leaving any residue with the following command:

`sudo bash ~/olipi-moode/install/uninstall-olipi-moode.sh`

(Can use with --dry-run to check without changing anything):

`sudo bash ~/olipi-moode/install/uninstall-olipi-moode.sh --dry-run`

---


## ❓ Troubleshooting and FAQ

If you want to learn more about OliPi Moode or if you encounter issues (black screen, IR remote not detected, GPIO not working, etc.), please check the [FAQ & Troubleshooting guide](./TROUBLESHOOTING.md).

---

## 🤝 Contributing

Contributions and feature suggestions are welcome!  
Possible future improvements:

- Support for additional displays.
- Offers more themes color
- Show other infos on display (covers, screensaver with picture from web/local or animation, etc...)
- Translation into more languages.
- Documentation improvements.

Come [discuss it on Discord](https://discord.gg/pku67XsFEE)  or if you want, [you can get your hands dirty with the engine](./CONTRIBUTING.md).

---

## 📄 License

License and attribution

This project is licensed under the GNU General Public License v3.0 (GPLv3).  
See the [LICENSE](./LICENSE) file for details.

This project is based on Moode Audio Player and may reuse various code patterns and configuration approaches.  
Moode is licensed under GPLv3: https://moodeaudio.org/LICENSE.txt

## **Disclaimer**

This project is neither affiliated with nor endorsed by the official Moode Audio team.

The software and other items in this repository are distributed under the [GNU General Public License Version 3](https://github.com/Trachou2Bois/olipi-moode/blob/main/LICENSE), which includes the following disclaimer:

> 15. Disclaimer of Warranty.  
>     THERE IS NO WARRANTY FOR THE PROGRAM, TO THE EXTENT PERMITTED BY APPLICABLE LAW. EXCEPT WHEN OTHERWISE STATED IN WRITING THE COPYRIGHT HOLDERS AND/OR OTHER PARTIES PROVIDE THE PROGRAM "AS IS" WITHOUT WARRANTY OF ANY KIND, EITHER EXPRESSED OR IMPLIED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE. THE ENTIRE RISK AS TO THE QUALITY AND PERFORMANCE OF THE PROGRAM IS WITH YOU. SHOULD THE PROGRAM PROVE DEFECTIVE, YOU ASSUME THE COST OF ALL NECESSARY SERVICING, REPAIR OR CORRECTION.
> 
> 16. Limitation of Liability.  
>     IN NO EVENT UNLESS REQUIRED BY APPLICABLE LAW OR AGREED TO IN WRITING WILL ANY COPYRIGHT HOLDER, OR ANY OTHER PARTY WHO MODIFIES AND/OR CONVEYS THE PROGRAM AS PERMITTED ABOVE, BE LIABLE TO YOU FOR DAMAGES, INCLUDING ANY GENERAL, SPECIAL, INCIDENTAL OR CONSEQUENTIAL DAMAGES ARISING OUT OF THE USE OR INABILITY TO USE THE PROGRAM (INCLUDING BUT NOT LIMITED TO LOSS OF DATA OR DATA BEING RENDERED INACCURATE OR LOSSES SUSTAINED BY YOU OR THIRD PARTIES OR A FAILURE OF THE PROGRAM TO OPERATE WITH ANY OTHER PROGRAMS), EVEN IF SUCH HOLDER OR OTHER PARTY HAS BEEN ADVISED OF THE POSSIBILITY OF SUCH DAMAGES.

This means the user of this software is responsible for any damage resulting from its use, regardless of whether it is caused by misuse or by a bug in the software.
