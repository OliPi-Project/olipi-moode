# OliPi MoOde

OliPi MoOde is an user interface for OLED/LCD screens >= 128x64 for [Moode Audio](https://moodeaudio.org/) with control via IR remote control and/or GPIO buttons.

<p align="center">
  <img src="https://github.com/OliPi-Project/olipi-moode/blob/main/docs/screenshots/TFT_demo.gif" width="400" alt="All Screens Demo">
  <img src="https://github.com/OliPi-Project/olipi-moode/blob/main/docs/screenshots/SSD1306_demo.gif" width="400" alt="Menus Demo">
</p>

Video presentation:
[https://youtu.be/9Y13UeyyT7k?si=hkOkiP9gk0rjxlB8](https://youtu.be/9Y13UeyyT7k?si=hkOkiP9gk0rjxlB8)

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

- **Hardware**: Raspberry Pi (Zero 2W, 3, 4, 5) + Oled ssd1306/1315 i2c. And IR receiver type TSOP38 or similar (if used).

- **APT dependencies** (installed automatically):
  
  ```bash
  python3-pil python3-venv python3-pip python3-tk
  i2c-tools libgpiod-dev python3-libgpiod python3-lgpio python3-setuptools
  ```

- **Python dependencies** (installed automatically):
  
  ```txt
  Adafruit_Blinka~=8.55.0
  adafruit_circuitpython_ssd1306~=2.12.21
  Pillow~=11.3.0
  python_mpd2~=3.0.5
  PyYAML~=6.0.2
  Requests~=2.32.4
  rpi_lgpio~=0.6
  yt_dlp~=2025.7.21
  ```

---

## 🚀 Installation

1. Clone this repository:
   
   ```bash
   sudo apt update && sudo apt install git
   git clone https://github.com/Trachou2Bois/olipi-moode.git
   ```

2. Run the setup script:
   
   ```bash
   python3 ~/olipi-moode/install/setup.py
   ```
   
   - Detects Moode version.
   - Installs APT and Python dependencies.
   - Configures I²C if disabled.
   - Creates a virtual environment (`~/.olipi-moode-venv` by default).
   - Offers ZRAM configuration if <1 GB RAM detected.
   - Installs systemd services.
   - Offers LIRC installation.

3. Follow the on-screen instructions.

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

OliPi MoOde uses `rpi_lgpio`, you can configure GPIO buttons or rotary encoders in `config.ini`. You can use `gpioinfo` to check which pins are free.

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

---

## 🧠 ZRAM on low-memory devices

If the Raspberry Pi has less than **1 GB RAM** (e.g., Zero 2W):

- The installer offers to install `zram-tools` and configure ZRAM (280 MB, lz4).
- Completely disables swap.

---

## ⚠️ Moode configuration reminder

In **Moode > System Config**:

- Enable **Ready Script** (System).
- Enable **LCD Updater** (Peripherals).

---

## 🤝 Contributing

Contributions and feature suggestions are welcome!  
Possible future improvements:

- Support for additional displays.
- Translation into more languages.
- Documentation improvements.

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
