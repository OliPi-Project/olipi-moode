# 🛠️ OliPi MoOde - Troubleshooting and AFQ

This guide covers common problems and their solutions when using OliPi MoOde.

---

## 🔌 Wiring screen / does not turn on after installation

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
    - Check the logs of the service:   
      `journalctl -u olipi-ui-playing -f`
      `journalctl -u olipi-starting-wait -f`

    - For SPI screens check the ouptut of:  
      `dmesg | grep fb`

    - Also you can try launch script manualy with python3:
        - `sudo systemctl stop olipi-ui-playing` (stop service)
        - `source ~/.olipi-moode-venv/bin/activate` (activates the virtual environment)
        - `python3 ~/olipi-moode/ui_playing.py` (start now playing script)
        - Look the output in terminal...
    - [Report problem](#-still-having-issues)

## 💻 Console cursor flashes in background

Since bookworm with KMS, force hotplug no longer works in config.txt.
If you are in "Kernel Mode" and your Raspberry is not connected to an hdmi screen, the system console will be displayed on the spi screen. To remedy this, force hdmi activation in `/boot/firmware/cmdline.txt` by adding at the end and on the same line, separated by a space: `vc4.force_hotplug=1`. And reboot. Your cmdline.txt should then end like this:  
`...rootwait cfg80211.ieee80211_regdom=FR vc4.force_hotplug=1`  

## 📡 Wiring IR Receiver / Remote control is not detected

- Check the wiring of your IR receiver:
    - Pin 1 (OUT) → Any free GPIO
    - Pin 2 (GND) → GND 
    - Pin 3 (VCC) → 3V3

- Re-run the interactive setup:
  
  `python3 ~/olipi-moode/install/install_lirc_remote.py`
  
  Check if you have entered the correct GPIO And try (mode2) or (irw) in the prompt menu

## ➰ I don't have enough gpio ports to connect everything!

If you use SPI screen and no other SPI device, you can disable and use CE1 (GPIO 7) as normal GPIOs (CE0 must remain activated for the screen) with add `dtoverlay=spi0-1cs` in `/boot/firmware/config.txt`.  
If you don't use SPI you can disable CE0 and CE1 with `dtoverlay=spi0-0cs`

## 🧠 Low memory devices (512 MB RAM)

- Devices like Pi Zero 2W or Pi 3 A+ may run into audio glitches with yt-dlp
- The installer will propose installing **ZRAM** automatically.
- Swap is disabled to improve performance and avoid SD card wear.


## 💡 Can OliPi MoOde be used without Moode?

- Not directly. OliPi MoOde is tightly integrated with Moode’s API and scripts.
- For more generic cases, you can use base [OliPi-Core](https://github.com/OliPi-Project/olipi-core). (need to be documented)



## 🆘 Still having issues?

- Please open an [issue](https://github.com/OliPi-Project/olipi-moode/issues) with details about your setup: 
  - Raspberry Pi model 
  - Screen type 
  - Moode version 
  - Error logs
  - Setup logs on install directory
  - Or anything can help to debug your problem.

- Come chat or open a topic on [Discord](https://discord.gg/pku67XsFEE)
