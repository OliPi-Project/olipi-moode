# 🛠️ OliPi MoOde - Troubleshooting

This guide covers common problems and their solutions when using OliPi MoOde.

---

## 🔹 Wiring / Screen does not turn on after installation

- Double-check the wiring:
  - For SPI screens:
    - GND => GND
    - VDD => 3.3V
    - SCL => SCLK (GPIO 11)
    - SDA => MOSI (GPIO 10)
    - RST, DC, CS can use any free GPIO (take care if your dac use pin for mute or if it has a built-in ir receiver)
    - BLK (backlight) must be connected to **3.3V** (not yet supported in software).
    - CE0 / CE1 are the Raspberry Pi hardware SPI chip-select pins.
    - If you want to use CE0/CE1 for wiring your screen or as normal GPIOs:
      - They must be disabled in the system (otherwise conflicts may occur).
      - Only do this if you have no other SPI devices using chip-select.
      - Can learn more here => [SPI Sensors &amp; Devices | CircuitPython Libraries on Linux and Raspberry Pi | Adafruit Learning System](https://learn.adafruit.com/circuitpython-on-raspberrypi-linux/spi-sensors-devices)
  - For I2C screens:
    - GND => GND
    - VDD => 3.3V
    - SCL => SCL (GPIO 3)
    - SDA => SDA (GPIO 2)

- Make sure SPI or I²C is enabled:
  
  `sudo raspi-config`

- Check the logs of the service:
  
  `journalctl -u ui_playing -f`

---

## 🔹 Remote control is not detected

- Check the wiring of your IR receiver

- Re-run the interactive setup:
  
  `python3 ~/olipi-moode/install/install_lirc_remote.py`
  
  Check if you have entered the correct GPIO And try (mode2) or (irw) in the prompt menu


## 🔹 Low memory devices (512 MB RAM)

- Devices like Pi Zero 2W or Pi 3 A+ may run into memory issues.

- The installer will propose installing **ZRAM** automatically.

- Swap is disabled to improve performance and avoid SD card wear.

- Recommended to avoid audio glitches with yt-dlp or heavy menus.

---

## 🔹 Can OliPi MoOde be used without Moode?

- Not directly. OliPi MoOde is tightly integrated with Moode’s MPD server and ready scripts.

- For more generic use cases, check [OliPi-Core](https://github.com/OliPi-Project/olipi-core).

---

## 🔹 Still having issues?

- Please open an [issue](https://github.com/OliPi-Project/olipi-moode/issues) with details about your setup:
  
  - Raspberry Pi model
  
  - Screen type
  
  - Moode version
  
  - Error logs (from `journalctl`)

  - Setup logs on install directory if the problem concerns the installation or the update

  - Or anything can help to debug your problem.
