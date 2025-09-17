# 🛠️ OliPi MoOde - Troubleshooting

This guide covers common problems and their solutions when using OliPi MoOde.

---

## Wiring screen / does not turn on after installation

- Double-check the wiring:
  - For SPI screens:
    - GND => GND
    - VDD => 3.3V
    - SCL => SCLK (GPIO 11)
    - SDA => MOSI (GPIO 10)
    - CS  => CE0  (GPIO 8)
    - RST and DC can use any free GPIO (take care if your dac use pin for mute or if it has a built-in ir receiver)
    - BLK (backlight) must be connected to **3.3V** (not yet supported in software).
          
  - For I2C screens:
    - GND => GND
    - VDD => 3.3V
    - SCL => SCL (GPIO 3)
    - SDA => SDA (GPIO 2)

- If you have wired your screen correctly but nothing is displayed:
    - Ready-script are turned ON in Moode Audio parameter?
    - Check the logs of the service:   
      `journalctl -u olipi-ui-playing -f`

    - For SPI screens check the ouptut of:  
      `dmesg | grep fb`

    - Also you can try launch script manualy with python3:
        - `sudo systemctl stop olipi-ui-playing` (stop service)
        - `source ~/.olipi-moode-venv/bin/activate` (activates the virtual environment)
        - `python3 ~/olipi-moode/ui_playing.py` (start now playing script)
        - Look the output in terminal...
    - [Report problem](#-still-having-issues)

## Wiring IR Receiver / Remote control is not detected

- Check the wiring of your IR receiver:
    - Pin 1 (OUT) → Any free GPIO
    - Pin 2 (GND) → GND 
    - Pin 3 (VCC) → 3V3

- Re-run the interactive setup:
  
  `python3 ~/olipi-moode/install/install_lirc_remote.py`
  
  Check if you have entered the correct GPIO And try (mode2) or (irw) in the prompt menu

## I don't have enough gpio ports to connect everything!

If you use SPI screen and no other SPI peripheriphe You can use CE1 (GPIO 8) as normal GPIOs (CE0 must remain activated for the screen):  
CE1 must be disabled in the system (otherwise conflicts may occur) with add `dtoverlay=spi0-1cs` in `/boot/firmware/config.txt`.  
If you don't use SPI you can disable CE0 and CE1 with `dtoverlay=spi0-0cs`

## 🔹 Low memory devices (512 MB RAM)

- Devices like Pi Zero 2W or Pi 3 A+ may run into memory issues.

- The installer will propose installing **ZRAM** automatically.

- Swap is disabled to improve performance and avoid SD card wear.

- Recommended to avoid audio glitches with yt-dlp or heavy menus.



## 🔹 Can OliPi MoOde be used without Moode?

- Not directly. OliPi MoOde is tightly integrated with Moode’s API and scripts.

- For more generic cases, you can use base [OliPi-Core](https://github.com/OliPi-Project/olipi-core).



## 🔹 Still having issues?

- Please open an [issue](https://github.com/OliPi-Project/olipi-moode/issues) with details about your setup: 
  - Raspberry Pi model 
  - Screen type 
  - Moode version 
  - Error logs
  - Setup logs on install directory
  - Or anything can help to debug your problem.

- Or open a topic on [Discord](https://discord.gg/pku67XsFEE)
