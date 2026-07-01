![Cat Printer](./media/hackoclock.jpg)

Cat printer is a portable thermal printer sold on AliExpress for around $20.

This repository contains Python code for talking to the cat printer over Bluetooth Low Energy (BLE). The code has been reverse engineered from the [official Android app](https://play.google.com/store/apps/details?id=com.frogtosea.iprint&hl=en_US&gl=US).

# Installation
```bash
# Clone the repository.
$ git clone git@github.com:rbaron/catprinter.git
$ cd catprinter
# Create a Python 3.10+ virtualenv and activate it.
$ python3.10 -m venv venv
$ source venv/bin/activate
# Install the project dependencies from pyproject.toml.
$ pip install .
```

# Usage
```bash
$ ./print.py --help
usage: print.py [-h] [-l {debug,info,warn,error}] [-b {mean-threshold,floyd-steinberg,atkinson,halftone,none}] [-s] [-d DEVICE] [-e ENERGY]
                filename

prints an image on your cat thermal printer

positional arguments:
  filename

options:
  -h, --help            show this help message and exit
  -l {debug,info,warn,error}, --log-level {debug,info,warn,error}
  -b {mean-threshold,floyd-steinberg,atkinson,halftone,none}, --img-binarization-algo {mean-threshold,floyd-steinberg,atkinson,halftone,none}
                        Which image binarization algorithm to use. If 'none' is used, no binarization will be used. In this case the image has to
                        have a width of 384 px.
  -s, --show-preview    If set, displays the final image and asks the user for confirmation before printing.
  -d DEVICE, --device DEVICE
                        The printer's Bluetooth Low Energy (BLE) address (MAC address on Linux; UUID on macOS) or advertisement name (e.g.:
                        "GT01", "GB02", "GB03"). If omitted, the the script will try to auto discover the printer based on its advertised BLE
                        services.
  -e ENERGY, --energy ENERGY
                        Thermal energy. Between 0x0000 (light) and 0xffff (darker, default).
```

# Example
```bash
% ./print.py --show-preview test.png
⏳ Applying Floyd-Steinberg dithering to image...
✅ Done.
ℹ️ Displaying preview.
🤔 Go ahead with print? [Y/n]?
✅ Read image: (42, 384) (h, w) pixels
✅ Generated BLE commands: 2353 bytes
⏳ Looking for a BLE device named GT01...
✅ Got it. Address: 09480C21-65B5-477B-B475-C797CD0D6B1C: GT01
⏳ Connecting to 09480C21-65B5-477B-B475-C797CD0D6B1C: GT01...
✅ Connected: True; MTU: 104
⏳ Sending 2353 bytes of data in chunks of 101 bytes...
✅ Done.
```

# Text Printing

Text can be rendered directly to the printer bitmap with Pillow; ImageMagick is
not required:

```bash
$ ./print.py --text "YOU GOT HACKED" --text-size 40
```

# AI Illustration Printing

Generate a playful black-and-white cartoon illustration with Pollinations Flux,
inspect the exact printer bitmap, then approve it before it is sent to the
printer. AI jobs use a direct black/white cutoff by default, so they do not add
Floyd-Steinberg dither dots. AI jobs always require approval, even without
`--show-preview`.

```bash
$ ./print.py --ai "A happy cat riding a bicycle through a small town"
```

Set `POLLINATIONS_API_KEY` to use your own Pollinations account and credits.
If it is unset, the command uses Pollinations' public endpoint, which can have
stricter availability and rate limits.

Flux is the default model. Choose another Pollinations image model with
`--ai-model`:

```bash
$ ./print.py --ai-model flux --ai "A cheerful robot walking a dog"
```

The generated image stays in memory and is not written to disk. Use
`--threshold` to make the final thermal-printer conversion lighter or darker.

# Voice Sticker Web UI

The project also includes a small StickerBox-inspired local web UI. Hold
the on-screen button while speaking, release it to transcribe and generate an
illustration, then the preview is shown before it is sent directly to the
Bluetooth printer.

Install the web-server dependency, start the server, then open the address in
Chrome on the same phone:

```bash
$ uv sync
$ .venv/bin/python -m catprinter.server --device <address-or-name>
# Open http://127.0.0.1:5000
```

The browser asks for microphone permission the first time. Chrome's built-in
speech recognition is used for the hold-to-talk interaction; if it is not
available, the UI provides a text field instead. Use `127.0.0.1` on the phone
rather than a LAN address: browsers allow microphone access on localhost over
HTTP, whereas an ordinary HTTP LAN page may require HTTPS.

# ESP32-S3 Physical Demo

An emulated hardware demo lives in `firmware/`. A physical button drives the same
listening, thinking, transcript, and image sequence on an SPI display. The laptop
bridge in `demo_bridge.py` receives the final serial event and prints the LittleFS
demo image to PD01 over Bluetooth. See `firmware/README.md` for wiring and commands.

Useful options:

```bash
$ ./print.py --text "hello" --text-align center --text-margin 16
$ ./print.py --text "fast test" --device <address-or-name>
```

Use the preview to inspect the generated bitmap before printing:

```bash
$ ./print.py --text "YOU GOT HACKED" --text-size 40 --show-preview
```

Reduce whitespace with a smaller margin:

```bash
$ ./print.py --text "YOU GOT HACKED" --text-size 40 --text-margin 4
```

# Different Algorithms

Use `--threshold` to control how much of an image becomes black. `50` is the
default midpoint; higher values print darker, and lower values print lighter:

```bash
$ ./print.py --threshold 65 --show-preview photo.jpg
```

For clean black-and-white line art without dither dots, use a fixed cutoff. A
lower threshold removes more light-gray background detail:

```bash
$ ./print.py --img-binarization-algo fixed-threshold --threshold 40 --show-preview photo.jpg
```

**Mean Threshold:**

![Mean threshold](./media/grumpymeanthreshold.png)


**Floyd Steinberg (default):**

![Floyd Steinberg](./media/grumpyfloydsteinbergexample.png)

**Atkinson:**

![Atkinson](./media/grumpyatkinsonexample.png)

**Halftone dithering:**

![Halftone](./media/grumpyhalftone.png)

**None (image must be 384px wide):**

![None](./media/grumpynone.png)
# catPrinter
