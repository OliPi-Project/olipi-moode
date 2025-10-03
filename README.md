 ![License](https://img.shields.io/github/license/OliPi-Project/olipi-moode)
![Python](https://img.shields.io/badge/python-3.9+-blue)
![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi-red)
![GitHub Release](https://img.shields.io/github/v/release/OliPi-Project/olipi-moode?include_prereleases&sort=date&display_name=tag)
![Discord](https://img.shields.io/discord/1410910825870266391?logo=discord&logoColor=white&logoSize=auto&label=Discord&color=blue&link=https%3A%2F%2Fdiscord.gg%2Fpku67XsFEE)


# OliPi MoOde

OliPi MoOde is an user interface for OLED/LCD screens >= 128x64 for [Moode Audio](https://moodeaudio.org/) with control via IR remote control and/or GPIO buttons/rotary encoder.

<p align="center">
  <img src="https://github.com/OliPi-Project/olipi-moode/blob/main/docs/screenshots/TFT_demo.gif" width="400" alt="All Screens Demo">
  <img src="https://github.com/OliPi-Project/olipi-moode/blob/main/docs/screenshots/SSD1306_demo.gif" width="400" alt="Menus Demo">
</p>

Video presentation:
[https://youtu.be/9Y13UeyyT7k?si=hkOkiP9gk0rjxlB8](https://youtu.be/9Y13UeyyT7k?si=hkOkiP9gk0rjxlB8)

---

## ❔ What's new?
**<u>V0.2.x-pre</u>**

*Change of approach for SPI displays: they now use the FBTFT overlay directly instead of going through the Adafruit lib. For I2C screens, I've switched to Luma.oled.* 

**<u>You need to uninstall completely Olipi Moode</u>** if you have version v0.1.x installed:  

Retrieve the latest uninstall script:  
```
curl -sSL https://raw.githubusercontent.com/OliPi-Project/olipi-moode/main/install/uninstall-olipi-moode.sh -o uninstall-olipi-moode.sh
```  
And executed the script:

```
sudo bash uninstall-olipi-moode.sh
```

> Release note:
>   - Improved  management of rotary encoder and its parameters in config.ini.
>   - Ready-script replaced by a systemd service with starting animation waiting for Moode to start. you can disable ready-script in Moode.
>   - It is no longer necessary to activate the "lcd updater", infos is retrieved via mpd or locally.
>   - FBTFT overlay for SPI screens.
>   - Luma.oled for I2C screens (Now you need to select the I2C address of your screen during installation).
>   - Setup script improved for install/update, with OliPi Moode folder backup.
>       - Now based on release version.
>       - Patch / Minor / Major Update are treated differently.
>       - Force new config.ini on major update with full install/configuration.
>       - Preserve config.ini and merge with .dist files on Minor update.
>       - Don't modify config.ini on Patch update.
>       - Backup existing configs before overwriting.
>       - Safe cleanup and move of cloned repo files.
>       - Use dedicaced section `# --- Olipi-moode ---` and `# @marker:***` on config.txt.
>   - A small performance improvement for Pi zero 2w / Pi3 A/B+ with highter screen resolution (still a lot of work to do).
>       - refresh_interval is now set according to the model of raspberry detected. 
>       - SPI speed and buffer size is now set according to the model of screen selected.
>   - Improved spectrometer.
>       - More audio formats supported.
>       - Now spectro releases the loopback when a track changes (Output format is no longer locked to the format read at opening).
>   - Delete some options and clean up config.ini
>   - And other odds and ends...


## 💖 Support OliPi

*If you find OliPi useful, consider supporting the project — every donation helps keep it alive.*

[![Donate](https://img.shields.io/badge/Donate-PayPal-blue.svg)](https://www.paypal.com/donate/?business=QN7HL6CB2H3QJ&no_recurring=0&item_name=Thanks+for+supporting+OliPi+Project%21+%0A&currency_code=EUR)


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

- **Now Playing UI**: Displays the current track, metadata, playback status, hardware info, etc. Media controls, add/remove favorites (follows the playlist configured in Moode), playback modes, renderers (Bluetooth, Airplay, and UPNP), search for the currently playing artist in the music library… And a little extra: Logs radio track titles (via the "favorites" button) into a text file to list them in the menu, and lets you search them via yt-dlp and replay them via a local stream/radio (no download).
- **Browser UI**: Browse the mpd music library, search, move, copy, delete to/from local or USB storage.
- **Playlist/Queue UI**: Display and manage the playback queue. Can create or replace Playlist from queue.
- **Configuration help and IR remote mapping**: Assisted and fully customizable LIRC configuration with conflict detection. Ability to add custom actions to unused keys in OliPi MoOde (see the `handle_custom_key` function in `media_key_actions.py`... *to be made more user-friendly*).
- **GPIO button and rotary encoder support** using `rpi_lgpio` . Enable and configure pins in `config.ini` under the "manual" section.


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
  | ST7735R     | 128×160    | 1.77     | 116 | RGB        | ST7735R.py                   |
  | ST7789 1.9" | 170×320    | 1.9      | 191 | RGB        | ST7789W.py                   |
  | ST7789 2"   | 240×320    | 2.0      | 200 | RGB        | ST7789V.py                   |
  
  Below 150 PPI font size are fixed.
  Above 150 PPI font size are scaled by (ppi / 150) x 1.2 caped at x1.6
  
  For SPI screen Plan your wiring carefully: OliPi-Moode uses several GPIOs for buttons, IR and audio control if you use I2s DAC and/or GPIOs buttons/rotary. 
  
  For more information about wiring, check the [FAQ & Troubleshooting guide](./TROUBLESHOOTING.md).
  
- **APT dependencies** (installed automatically if needed):
  
  ```
  git python3-pil python3-venv python3-pip python3-tk libatlas-base-dev libopenblas0-pthread libgfortran5 i2c-tools libgpiod-dev python3-libgpiod python3-lgpio python3-setuptools
  ```

- **Python dependencies** (installed automatically with the virtual environment):
  
  ```txt
  luma.oled~=3.14.0
  luma_core~=2.5.1
  Pillow~=11.3.0
  python_mpd2~=3.0.5
  PyYAML~=6.0.2
  Requests~=2.32.5
  rpi_lgpio~=0.6
  pyalsaaudio~=0.11.0
  numpy~=2.3.3
  scipy~=1.16.2
  yt_dlp[default]>=2025.9.5
  ```

---

## 🚀 Installation

**<u>If you have [MoodeOled](https://github.com/Trachou2Bois/MoodeOled) installed</u>**, check [**here**](https://github.com/Trachou2Bois/MoodeOled/blob/main/README.md#moodeoled-has-grown) to **uninstall it** before install OliPi Moode.

First of all:
- if you have already installed Olipi Moode check [here](#-whats-new) if new version require uninstalling.
- Make sure you've wired your screen, buttons and IR receiver correctly.
[See wiring guide](TROUBLESHOOTING.md#wiring--screen-does-not-turn-on-after-installation).

After that you can:

1. Clone this repository:
   
   ```bash
   sudo apt update && sudo apt install git
   git clone https://github.com/OliPi-Project/olipi-moode
   ```

2. Run the setup script:
   
   ```bash
   python3 ~/olipi-moode/install/install_olipi.py
   ```

3. Follow the on-screen instructions.  
   
       This script performs the following actions:
       
       - Detects Moode version.
       - Installs APT dependencies.
       - Clone latest release from olipi-core
       - Offers to select from supported screens
       - Configures I²C or SPI if disabled.
       - Offers to fill in the pins for SPI or select I2C adress
       - Offers ZRAM configuration if 512MB RAM and/or swap detected.
       - Creates a virtual environment (`~/.olipi-moode-venv` by default).
       - Install Python dependencies in venv.
       - Installs systemd services.
       - Append some lines with useful commands to .profile
       - Create file with versions and paths in install dir.
       
       It can be reused for update OliPi Moode or force reinstall  

4. ❗ <u>Moode configuration reminder</u>

    To display the spectrometer you need to enable loopback in Moode UI: `configure > Audio > ALSA Options`. And change `show_spectrum = false` to `true` in `~/olipi-moode/config.ini`.

## 🖥 Services

The following systemd services are created during installation:

| Service               | Description                                      |
| --------------------- | ------------------------------------------------ |
| `olipi-ui-playing`    | Displays "Now Playing" screen (ui_playing.py)    |
| `olipi-ui-browser`    | Music library navigation (ui_browser.py)         |
| `olipi-ui-queue`      | Playback queue display (ui_queue.py)             |
| `olipi-starting-wait` | Launch ui_wait.py at startup for waiting Moode   |
| `olipi-ui-off`        | Turns off (clear) screen at shutdown (ui_off.py) |

Switch between the 3 main display scripts using the `KEY_BACK` button.  
Service `olipi-ui-off` is enabled and execute ui_off.py for clearing display at shutdown. (Need better handling for turning off LCD backlight)
Service `olipi-starting-wait` is enabled and launch ui_wait.py who play animation for waiting Moode to be ready.

## 📡 IR remote configuration

OliPi MoOde includes an interactive script to configure LIRC:

```bash
python3 ~/olipi-moode/install/install_lirc_remote.py
```

Features:

- Install and configure LIRC.
- Hardware test (`mode2`, `irw`).
- Download a configuration from `irdb-get`.
- Learn a remote control (`irrecord`).
- Move *.lircd.conf to /etc/lirc/lircd.conf.d
- Manage/edit *.lircd.conf stored in /etc/lirc/lircd.conf.d
- Mapping editor:
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

## 🎛 GPIO and rotary encoder support

OliPi MoOde uses `rpi_lgpio`, you can configure GPIO buttons or rotary encoders in `config.ini`. Be careful not to use pins that are used for other things. Check your hardware and wiring before enabling "use_buttons" and "use_rotary""

Example:

```ini
[input]
use_buttons = true
use_rotary = true

[buttons]
KEY_LEFT = 17
KEY_RIGHT = 27

[rotary]
pin_a = 22
pin_b = 23
```

## ⌨ Key configuration

### 🔑 Essential keys

These keys are **required** to navigate and control all interfaces:

| Key                 | Generic role (all UI)                               | Specific usage in `ui_playing`                     |
| ------------------- | --------------------------------------------------- | -------------------------------------------------- |
| **KEY_UP**          | Move up                                             | Volume + if outside menu                           |
| **KEY_DOWN**        | Move down                                           | Volume - if outside menu                           |
| **KEY_LEFT**        | Move left                                           | Previous / Seek -10s (long press) if outside menu  |
| **KEY_RIGHT**       | Move right                                          | Next / Seek +10s (long press) if outside menu      |
| **KEY_OK**          | Open menu / Tools menu (long press) / Confirm       |                                                    |
| **KEY_BACK**        | Switch to `ui_browser`/`ui_queue`/`ui_playing`      | Switch to `ui_browser` (short) / `ui_queue` (long) |
| **KEY_INFO**        | Show contextual help                                |                                                    |
| **KEY_CHANNELUP**   | Context action                                      | Add/Remove favorites, if radio: add to songlog     |
| **KEY_CHANNELDOWN** | Context action                                      | Remove from queue                                  |
| **KEY_PLAY**        | Only on Now Playing UI                              | Play/Pause / Shutdown (long press)                 |

**For more info, press `KEY_INFO` in each context.**

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


## 🔧 Configuration via tools menu in Now Playing UI

A small on-screen configuration menu allows you to change:

- Screen sleep delay  
- Local stream quality (radio favorites)  
- Language (currently English and French)  
- Enable/disable debug mode  
- Change color theme


## 🧠 ZRAM on low-memory devices

If your Raspberry Pi has **512MB RAM** (e.g., Zero 2W or 3 A+):

- The installer offers to install `zram-tools` and configure ZRAM (256 MB, lz4).
- Completely disables swap.


## 🔧 Uninstall

You can uninstall all without leaving any residue with the following command:

`sudo bash ~/olipi-moode/install/uninstall-olipi-moode.sh`

(Can use with --dry-run to check without changing anything):

`sudo bash ~/olipi-moode/install/uninstall-olipi-moode.sh --dry-run`


## ❓ Troubleshooting and FAQ

If you want to learn more about OliPi Moode or if you encounter issues (black screen, IR remote not detected, GPIO not working, etc.), please check the [FAQ & Troubleshooting guide](./TROUBLESHOOTING.md).


## 🤝 Contributing

Contributions and feature suggestions are welcome!  

You can contribute in several ways:  

  - Participating in the development of current or future features/project.
  - Reporting bugs, typo errors, security problems etc...  
  - Suggesting new ideas.  
  - Create more themes color.  
  - Translate into more languages.  
  - Documentation improvements.  
  
Possible future improvements:  

  - Support for additional displays.  
  - Show other infos on display according to project (covers, screensaver with picture from web/local or animation, meteo, etc...)  

If you want to help you can take a look on [issues](https://github.com/OliPi-Project/olipi-moode/issues) or [discussions](https://github.com/OliPi-Project/olipi-moode/discussions), open a new [issue](https://github.com/OliPi-Project/olipi-moode/issues/new/choose), or come tchat on [Discord](https://discord.gg/pku67XsFEE)!  
Also you can make a [donation](#💖-support-olipi) that could be used to acquire new equipment to test/integrate into the project.  


---

## 📄 License

License and attribution

This project is licensed under the GNU General Public License v3.0 (GPLv3).  
See the [LICENSE](./LICENSE) file for details.

This project requires the [Moode audio player](https://moodeaudio.org/) and reuses some php code logic to update certain configurations. (currently in audioout-toggle.php and update_local_stream.php )
Moode is licensed under GPLv3: https://moodeaudio.org/LICENSE.txt

## ⚠️ **Disclaimer**

This project is neither affiliated with nor endorsed by the official Moode Audio team.

The software and other items in this repository are distributed under the [GNU General Public License Version 3](https://github.com/Trachou2Bois/olipi-moode/blob/main/LICENSE), which includes the following disclaimer:

> 15. Disclaimer of Warranty.  
>     THERE IS NO WARRANTY FOR THE PROGRAM, TO THE EXTENT PERMITTED BY APPLICABLE LAW. EXCEPT WHEN OTHERWISE STATED IN WRITING THE COPYRIGHT HOLDERS AND/OR OTHER PARTIES PROVIDE THE PROGRAM "AS IS" WITHOUT WARRANTY OF ANY KIND, EITHER EXPRESSED OR IMPLIED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE. THE ENTIRE RISK AS TO THE QUALITY AND PERFORMANCE OF THE PROGRAM IS WITH YOU. SHOULD THE PROGRAM PROVE DEFECTIVE, YOU ASSUME THE COST OF ALL NECESSARY SERVICING, REPAIR OR CORRECTION.
> 
> 16. Limitation of Liability.  
>     IN NO EVENT UNLESS REQUIRED BY APPLICABLE LAW OR AGREED TO IN WRITING WILL ANY COPYRIGHT HOLDER, OR ANY OTHER PARTY WHO MODIFIES AND/OR CONVEYS THE PROGRAM AS PERMITTED ABOVE, BE LIABLE TO YOU FOR DAMAGES, INCLUDING ANY GENERAL, SPECIAL, INCIDENTAL OR CONSEQUENTIAL DAMAGES ARISING OUT OF THE USE OR INABILITY TO USE THE PROGRAM (INCLUDING BUT NOT LIMITED TO LOSS OF DATA OR DATA BEING RENDERED INACCURATE OR LOSSES SUSTAINED BY YOU OR THIRD PARTIES OR A FAILURE OF THE PROGRAM TO OPERATE WITH ANY OTHER PROGRAMS), EVEN IF SUCH HOLDER OR OTHER PARTY HAS BEEN ADVISED OF THE POSSIBILITY OF SUCH DAMAGES.

This means the user of this software is responsible for any damage resulting from its use, regardless of whether it is caused by misuse or by a bug in the software.
