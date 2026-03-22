![License](https://img.shields.io/github/license/OliPi-Project/olipi-moode)
![Python](https://img.shields.io/badge/python-3.9+-blue)
![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi-red)
![GitHub Release](https://img.shields.io/github/v/release/OliPi-Project/olipi-moode?include_prereleases&sort=date&display_name=tag)
![Discord](https://img.shields.io/discord/1410910825870266391?logo=discord&logoColor=white&logoSize=auto&label=Discord&color=blue&link=https%3A%2F%2Fdiscord.gg%2Fpku67XsFEE)


# OliPi MoOde

OliPi MoOde is an user interface for OLED/LCD screens >= 128x64 for [Moode Audio](https://moodeaudio.org/) with control via IR remote control and/or GPIO buttons/rotary encoder. And now also with MPR121 capacitive touch.
It allows to design audio boxes with built-in displays and controls.

<p align="center">
  <img src="https://github.com/OliPi-Project/olipi-moode/blob/main/docs/screenshots/Proto-V2.jpg" width="802" alt="Proto V2">
</p>
<p align="center">
  <img src="https://github.com/OliPi-Project/olipi-moode/blob/main/docs/screenshots/TFT_demo.gif" width="400" alt="All Screens Demo">
  <img src="https://github.com/OliPi-Project/olipi-moode/blob/main/docs/screenshots/SSD1306_demo.gif" width="400" alt="Menus Demo">
</p>
<p align="center">
  <img src="https://github.com/OliPi-Project/olipi-moode/blob/main/docs/screenshots/v0-3-4.JPEG" width="400" alt="v0.3.4 Demo">
  <img src="https://github.com/OliPi-Project/olipi-moode/blob/main/docs/screenshots/Proto-V2_c.jpg" width="400" alt="Under the w(h)ood">
</p>

[https://youtu.be/9Y13UeyyT7k?si=hkOkiP9gk0rjxlB8](https://youtu.be/9Y13UeyyT7k?si=hkOkiP9gk0rjxlB8)

---

## ❔ What's new?

**<u>V0.4.0-pre</u> +** 

If you're updating from a version higher than v0.3 a full update are required (don't skip screen configuration and update or reinstall venv). No need to force a config.ini reset when prompt.

If you're updating from a version prior to v0.3, a fresh install is required. You can uninstall all with: `sudo bash ~/olipi-moode/install/uninstall-olipi-moode.sh` And perform a fresh [installation](#-installation). Remember to make a backup of your config.ini if necessary. (Remote control .conf files are not deleted)

Release Note:

    Latest updates:

    - Resolution are saved in config.ini when configure screen
    - Add peak-meter and improvement of audio analysis for spectrum and peak-meter
    - Oled 64px height can now show spectrum and/or peak-meter (by deactivating icons, progress-bar and audio-infos)
    - SSD1306, SSD1315 and SSD1309 SPI are now supported

    - Now support Moode 10+ (Trixie)
    - New screensaver: "Orbital" a dynamic screensaver animated by music (Only for RGB screens)
    - Improved audio analysis for spectrometer (need more work)
    - Migrating to systemd-zram-generator for compatibility Bookworm/Trixie:
    - Separate theme_colors so you can use theme_user.yaml to change colors and don't lose your settings during an update
    - Add screensavers (LCD clock, Covers, spectrum) and menu options to select them
    - Files and folders have been reorganized
    ...
    
    Still lots of things to perform/correct before going to V1...


## 💖 Support OliPi

*If you find OliPi useful, consider supporting the project — every donation helps keep it alive.*

[![Donate](https://img.shields.io/badge/Donate-PayPal-blue.svg)](https://www.paypal.com/donate/?business=QN7HL6CB2H3QJ&no_recurring=0&item_name=Thanks+for+supporting+OliPi+Project%21+%0A&currency_code=EUR)

*And especially  consider supporting [Moode Audio Project](https://moodeaudio.org/) without which OliPi Moode could not exist.*
## 📚 Table of Contents

- [Features](#-features)
- [System requirements](#-system-requirements)
- [Installation](#-installation)
- [Services](#-services)
- [IR remote configuration](#-ir-remote-configuration)
- [GPIO and rotary encoder support](#-gpio-and-rotary-encoder-support)
- [Key configuration](#-key-configuration)
- [Configuration via display menu](#-configuration-via-menu-in-now-playing-screen)
- [Uninstall](#-uninstall)
- [Troubleshooting](#-troubleshooting-and-faq)
- [Contributing](#-contributing)
- [License](#-license)

---

## ✨ Features

- **Now Playing UI**: Displays the current track, metadata, playback status, hardware info, etc. Media controls, add/remove favorites (follows the playlist configured in Moode), playback modes, renderers (Bluetooth, Airplay, and UPNP), search for the currently playing artist in the music library… And a little extra: Logs radio track titles (via the "favorites" button) into a text file to list them in the menu, and lets you search them via yt-dlp and replay them via a local stream/radio (no download).
- **Browser UI**: Browse the mpd music library, search, move, copy, delete to/from local or USB storage.
- **Playlist/Queue UI**: Display and manage the playback queue. Can create or replace Playlist from queue.
- **Configuration help and IR remote mapping**: Assisted and fully customizable LIRC configuration with conflict detection. Ability to add custom actions to unused keys in OliPi MoOde (see the `handle_custom_key` function in `media_key_actions.py`... *to be made more user-friendly*).
- **GPIO button and rotary encoder support** using `rpi-lgpio` . Enable and configure pins in `config.ini`.


## 📦 System requirements

- **Operating system**: Moode Audio Player ≥ 9.3.7 required.

- **Hardware**: 
  
      - Raspberry Pi (Zero 2W, 3, 4, 5) 
      - I2C/SPI Screen. 
      - IR receiver type TSOP38 or similar (if used)
      - Push Button and/or Rotary Encoder (if used)
      - MPR121 capacitive touch module (if used)
  
  **Screens supported**:
  
  | Screen      | Resolution | Diag (") | Color      | 
  | ----------- | ---------- | -------- | ---------- |
  | SSD1306 I2C | 128×64     | 0.96     | Monochrome |
  | SSD1315 I2C | 128×64     | 0.96     | Monochrome |
  | SSD1309 I2C | 128×64     | 2.49     | Monochrome |
  | SSD1306/09/15 SPI | 128×64 | 0.96 - 2.49  | Monochrome |
  | SSD1351     | 128×128    | 1.5      | RGB        |
  | ST7735R     | 128×160    | 1.77     | RGB        |
  | ST7789 1.9" | 170×320    | 1.9      | RGB        |
  | ST7789 2" 2.4" 2.8" | 240×320 | 2.0 to 2.8   | RGB      |
    
  For SPI screen Plan your wiring carefully: OliPi-Moode uses several GPIOs for buttons, IR and audio control if you use I2s DAC and/or GPIOs buttons/rotary. 
  
  For more information about wiring, check the [FAQ & Troubleshooting guide](./TROUBLESHOOTING.md).
  
- **APT dependencies** (installed automatically if needed):
  
  ```
  git python3-pil python3-venv python3-pip python3-tk libasound2-dev libopenblas-dev libopenblas-pthread-dev libblas-dev liblapack-dev libgfortran5 i2c-tools python3-rpi-lgpio python3-setuptools smbus2
  ```

- **Python dependencies (PIP)** (installed automatically with the virtual environment):
  
  ```
  luma.oled luma_core Pillow python_mpd2 pyalsaaudio numpy scipy PyYAML Requests yt_dlp
  ```

---


## 🚀 Installation

**<u>If you have [MoodeOled](https://github.com/Trachou2Bois/MoodeOled) installed</u>**, check [**here**](https://github.com/Trachou2Bois/MoodeOled/blob/main/README.md#moodeoled-has-grown) to **uninstall it** before install OliPi Moode.

First of all:
- if you have already installed Olipi Moode check [here](#-whats-new) if new version require uninstalling.
- Make sure you've wired your screen correctly. [See wiring guide](TROUBLESHOOTING.md#-wiring--screen-does-not-turn-on-after-installation).

After that you can:

1. Clone this repository:
   
   ```
   sudo apt update && sudo apt install git
   git clone https://github.com/OliPi-Project/olipi-moode
   ```

2. Run the setup script:
   
   ```
   python3 ~/olipi-moode/install/install_olipi.py
   ```

3. Follow the on-screen instructions.  
   
       This script performs the following actions:
       
       - Detects Moode & OliPi version.
       - Installation/Migration from/to systemd-zram-generator if not present.
       - Clone latest release from olipi-core
       - Installs APT dependencies.
       - Creates a virtual environment at `~/.olipi-moode-venv`.
       - Install Python dependencies in venv.
       - Offers to select from supported screens
       - Configures I²C or SPI if disabled.
       - Offers to fill in the pins for SPI or select I2C adress
       - Installs systemd services.
       - Append some lines with useful commands to .profile
       
       It can be reused for update OliPi Moode, force reinstall or reconfigure screen. 

4. ❗ <u>Moode configuration reminder</u>

    To display the spectrometer or screensaver "Orbital" or peak-meter you need to enable loopback in Moode UI: `configure > Audio > ALSA Options`.

## 🖥 Services

The following systemd services are created during installation:

| Service               | Description                                      |
| --------------------- | ------------------------------------------------ |
| `olipi-ui-playing`    | Displays "Now Playing" screen (ui_playing.py)    |
| `olipi-ui-browser`    | Music library navigation (ui_browser.py)         |
| `olipi-ui-queue`      | Playback queue display (ui_queue.py)             |
| `olipi-starting-wait` | Launch ui_wait.py at startup for waiting Moode   |
| `olipi-ui-off`        | Turns off (clear) screen at shutdown (ui_off.py) |
 
Service `olipi-ui-off` is enabled and execute ui_off.py for clearing display at shutdown. (Need better handling for turning off LCD backlight)
Service `olipi-starting-wait` is enabled and launch ui_wait.py who play animation for waiting Moode to be ready.

Switch between the 3 main display scripts using the `KEY_BACK` button. 

## 📡 IR remote configuration

OliPi MoOde includes an interactive script to install and configure LIRC:

```bash
python3 ~/olipi-moode/install/install_lirc_remote.py
```

Features:

- Install and configure LIRC for use with recever type TSOP*.
- Hardware test (`mode2`, `irw`).
- Download a configuration from `irdb-get`.
- Learn a remote control (`irrecord`).
- When finish learning or download it move *.lircd.conf files to /etc/lirc/lircd.conf.d/
- Manage/edit *.lircd.conf stored in /etc/lirc/lircd.conf.d
- Mapping editor (Useful if the names of your remote control buttons don't match the names expected by Olipy):
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
If you need to change the button names or add new button in your remote control's .conf file, it's best to use names included in the namespace. You can list the valid names using the following command: `irrecord --list-namespace`

## 🎛 GPIO and rotary encoder support

OliPi MoOde uses `rpi-lgpio` which is a compatibility package intended to provide compatibility with the rpi.gpio, you can configure GPIO buttons or rotary encoders in `config.ini`. Be careful not to use pins that are used for other things. Check your hardware and wiring before enabling "use_buttons" and/or "use_rotary"". [See wiring guide](TROUBLESHOOTING.md#-wiring-push-buttons--rotary-encoder).


## 🎹 MPR121 capacitive touch support

[Wiring your MPR121](TROUBLESHOOTING.md#-wiring-mpr121--setting-pad-sensitivity), configure the address, INT(IRQ) pin and pads in config.ini and then activate it in the [input] section.


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
| **KEY_CHANNELDOWN** | Context action                                      | Remove playing track from queue                    |
| **KEY_PLAY**        | Play/Pause / Reboot (long press)                    |                                                    |

**For more info, press `KEY_INFO` in each context.**

These keys must be configured either via LIRC (`python3 ~/olipi-moode/install/install_lirc_remote.py`) either via GPIO in `[buttons] & [rotary]` section in `config.ini` or for MPR121 in `[mpr121_pads]` section.


### 🎵 Optional media keys

Recommended if available on your remote, but **not mandatory**:

| Key                | Action                                          |
| ------------------ | ----------------------------------------------- |
| **KEY_STOP**       | Stop playback / Shutdown (longpress)            |
| **KEY_NEXT**       | Next / Seek +10s (long press)                   |
| **KEY_PREVIOUS**   | Previous / Seek -10s (long press)               |
| **KEY_FORWARD**    | Seek +10s / +30 & +60 (long press & more)       |
| **KEY_REWIND**     | Seek -10s / -30 & -60 (long press & more)       |
| **KEY_VOLUMEUP**   | Volume +1 / +5 (long press)                     |
| **KEY_VOLUMEDOWN** | Volume -1 / -5 (long press)                     |
| **KEY_MUTE**       | Mute                                            |
| **KEY_POWER**      | Shutdown / Restart (long press)                 |

> **Note:** In `ui_playing`, navigation keys (`UP`, `DOWN`, `LEFT`, `RIGHT`) can be used for volume +/- and previous/next (rewind/forward on long press).

### 🆓 User Keys

You can assign additional buttons on your remote control to a radio station, playlist, album, or song.  

The easiest way is to use the "**Set shortcut**" option from the menu (**OK** button in the UI library browser) on the item you want to create a shortcut for, then press the button of your choice (excluding the essential and optional Olipy buttons), and that’s it (But make sure your remote control is set up correctly; see [IR remote configuration](#-ir-remote-configuration) if necessary). 

It is also possible to assign shortcuts to the GPIO buttons and the MPR121 pads by using custom button names in config.ini and proceeding in the same way as for remote control buttons via the "Set shortcut" menu entry.

For example, if you have a few unused MPR121 pads or GPIO pins, you can assign them unused names:

  ```ini
  [mpr121_pads]
  pad0 = KEY_CHANNELDOWN
  pad1 = KEY_CHANNELUP
  pad2 = KEY_RIGHT
  pad3 = KEY_PLAY
  pad4 = KEY_LEFT
  pad5 = KEY_STOP
  pad6 = KEY_BACK
  pad7 = KEY_INFO
  pad8 = KEY_MYRADIO1
  pad9 = KEY_MYRADIO2
  pad10 = KEY_MYPLAYLIST
  pad11 = KEY_MYOTHERKEY
  ```

And/or with GPIO button (If you use MPR121 and GPIO You can comment out all unused keys to add custom keys like bellow):

  ```ini
  [buttons]
  KEY_UP = 12
  KEY_DOWN = 13
  KEY_LEFT = 27
  KEY_RIGHT = 17
  KEY_OK = 16
  KEY_BACK = 5
  KEY_PLAY = 4
  KEY_CHANNELUP = 26
  KEY_CHANNELDOWN = 22
  #KEY_INFO = 25
  ### Can add and replace your own KEY bellow (uncommented) with any free GPIO. Need to start with KEY_ like:
  KEY_SHORTCUT = 25
  KEY_MYKEY = 23
  ```

Custom shortcuts are stored in the config.ini file under the **[library_shortcuts]** section. They can also be configured manually if you know the path (relative to the MPD library) or the name of the item you want to configure. Special characters and spaces are allowed.  

  - playlist:name of your playlist or path of radio.pls
  - file:path to your file.mp3 or path to your stream link
  - folder:path to your album folder

Here is an example but the easiest way is to go through the menu:

  ```ini
  [library_shortcuts]
  KEY_MYPLAYLIST = playlist:Default Playlist
  KEY_MYOTHERKEY = folder:USB/EA9AF9F99AF9C1DD/Scylla/Scylla & Furax Barbarossa - Portes du desert
  KEY_MYKEY = file:USB/EA9AF9F99AF9C1DD/Audio Book/Alexandre Soljénitsyne/01 Une journée de Ivan Denissovitch.mp3
  KEY_SHORTCUT = file:https://channels.fluxfm.de/chillhop/stream.mp3
  KEY_MYRADIO1 = playlist:RADIO/4ZZZ FM 102.1 - Alternative.pls
  ```

## 🔧 Configuration via menu in Now Playing UI

A small on-screen menu allows you to change:

    Menu:
    - Add to Favorites/SongLog
    - Remove track from queue
    - Modify playback modes (Random, repeat etc..)
    - Or if that's the case, show YT stream queue
    - Menu Power:
      - Shutdown
      - Reboot
      - Reload screen (script ui_playing)
      - Restart MPD

    Tools Menu:
    - Perform some actions on certain renderers (Bluetooth, Airplay, UPnP)
    - Display SongLog and allows to search logged tracks and listen to YT.
    - Display hardware stats
    - Config Menu:
      - Language (currently English and French)
      - Change color theme
      - Configure UI:
        - Show/hide: icons barre, audio infos, progress bare, spectrum, peak-meter
        - Display clock or elapsed time
      - Configure screensaver:
        - Screen sleep delay
        - Choose: blank, LCD clock, covers, spectrum, orbital
      - Toggle debug mode  


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
Also you can make a [donation](https://www.paypal.com/donate/?business=QN7HL6CB2H3QJ&no_recurring=0&item_name=Thanks+for+supporting+OliPi+Project%21+%0A&currency_code=EUR) that could be used to acquire new equipment to test/integrate into the project.  


---

## 📄 License

License and attribution

This project is licensed under the GNU General Public License v3.0 (GPLv3).  
See the [LICENSE](./LICENSE) file for details.

This project requires the [Moode audio player](https://moodeaudio.org/) and reuses some php code logic to update certain configurations. (currently in assets/audioout-toggle.php and assets/update_local_stream.php )
Moode is licensed under GPLv3: https://moodeaudio.org/LICENSE.txt

## ⚠️ Disclaimer

This project is neither affiliated with nor endorsed by the official Moode Audio team.

The software and other items in this repository are distributed under the [GNU General Public License Version 3](https://github.com/Trachou2Bois/olipi-moode/blob/main/LICENSE), which includes the following disclaimer:

> 15. Disclaimer of Warranty.  
>     THERE IS NO WARRANTY FOR THE PROGRAM, TO THE EXTENT PERMITTED BY APPLICABLE LAW. EXCEPT WHEN OTHERWISE STATED IN WRITING THE COPYRIGHT HOLDERS AND/OR OTHER PARTIES PROVIDE THE PROGRAM "AS IS" WITHOUT WARRANTY OF ANY KIND, EITHER EXPRESSED OR IMPLIED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE. THE ENTIRE RISK AS TO THE QUALITY AND PERFORMANCE OF THE PROGRAM IS WITH YOU. SHOULD THE PROGRAM PROVE DEFECTIVE, YOU ASSUME THE COST OF ALL NECESSARY SERVICING, REPAIR OR CORRECTION.
> 
> 16. Limitation of Liability.  
>     IN NO EVENT UNLESS REQUIRED BY APPLICABLE LAW OR AGREED TO IN WRITING WILL ANY COPYRIGHT HOLDER, OR ANY OTHER PARTY WHO MODIFIES AND/OR CONVEYS THE PROGRAM AS PERMITTED ABOVE, BE LIABLE TO YOU FOR DAMAGES, INCLUDING ANY GENERAL, SPECIAL, INCIDENTAL OR CONSEQUENTIAL DAMAGES ARISING OUT OF THE USE OR INABILITY TO USE THE PROGRAM (INCLUDING BUT NOT LIMITED TO LOSS OF DATA OR DATA BEING RENDERED INACCURATE OR LOSSES SUSTAINED BY YOU OR THIRD PARTIES OR A FAILURE OF THE PROGRAM TO OPERATE WITH ANY OTHER PROGRAMS), EVEN IF SUCH HOLDER OR OTHER PARTY HAS BEEN ADVISED OF THE POSSIBILITY OF SUCH DAMAGES.

This means the user of this software is responsible for any damage resulting from its use, regardless of whether it is caused by misuse or by a bug in the software.
