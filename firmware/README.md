# ESP32 Sticker Demo

This firmware emulates the voice and AI stages while keeping the physical button,
screen, USB serial link, and Cat Printer real.

## Current hardware assumption

The display is configured as an ILI9341 SPI panel in 320x240 landscape mode. The
original description said 360x240 OLED, so confirm the controller before wiring a
different panel. The button connects GPIO 15 to GND and uses the internal pull-up.

| Signal | ESP32 DevKit pin |
| --- | ---: |
| TFT MOSI | 23 |
| TFT SCK | 18 |
| TFT CS | 5 |
| TFT DC | 2 |
| TFT RESET | 4 |
| Button | 15 |

Connect the display and ESP32 grounds together. Power the panel according to its
module specification.

## Demo flow

1. The display shows `Press to talk`.
2. Holding the button shows `Listening...`.
3. Releasing it shows `Thinking...` for two seconds.
4. The simulated transcript `six,seven` appears.
5. `/demo.jpg` is loaded from LittleFS and displayed.
6. The firmware sends `PRINT_DEMO` over USB serial.
7. The web UI receives that event through Web Serial and asks the local server
   to print the same image to PD01 over BLE.

## Upload

Install PlatformIO, connect the ESP32 with a data-capable USB cable, then run from
the repository root:

```bash
pio run -d firmware --target upload
pio run -d firmware --target uploadfs
```

To replace the demo, overwrite `firmware/data/demo.jpg` with a baseline 24-bit JPEG
and rerun only `uploadfs`. Progressive JPEG files are not supported by TJpg_Decoder.

## Run the web bridge

Install Python dependencies and start the web server:

```bash
uv sync
.venv/bin/python -m catprinter.server --device 230BD164-E303-D0B1-7476-F83BB4E81722
```

Open `http://127.0.0.1:5000` in Chrome or Edge, click `Connect ESP32`, and pick
the ESP32 serial device. Keep that tab open while using the physical button.
