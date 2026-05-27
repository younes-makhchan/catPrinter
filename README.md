![Cat Printer](./media/hackoclock.jpg)

Cat printer is a portable thermal printer sold on AliExpress for around $20.

This repository contains Python code for talking to the cat printer over Bluetooth Low Energy (BLE). The code has been reverse engineered from the [official Android app](https://play.google.com/store/apps/details?id=com.frogtosea.iprint&hl=en_US&gl=US).

# Installation
```bash
# Clone the repository.
$ git clone git@github.com:rbaron/catprinter.git
$ cd catprinter
# Create a virtualenv on venv/ and activate it.
$ virtualenv --python=python3 venv
$ source venv/bin/activate
# Install requirements from requirements.txt.
$ pip install -r requirements.txt
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

Text can be rendered directly to the printer bitmap without ImageMagick:

```bash
$ ./print.py --text "YOU GOT HACKED" --text-size 40
```

Useful options:

```bash
$ ./print.py --text "hello" --text-align center --text-margin 16
$ ./print.py --text "fast test" --device <address-or-name> --chunk-delay 0.01
```

To inspect the generated bitmap bounds before printing, use the preview with a
debug border:

```bash
$ ./print.py --text "YOU GOT HACKED" --text-size 40 --text-border --show-preview
```

Reduce vertical whitespace with smaller margins and tighter line spacing:

```bash
$ ./print.py --text "YOU GOT HACKED" --text-size 40 --text-margin 4 --text-line-spacing 1.0
$ ./print.py --text "YOU GOT HACKED" --text-size 40 --text-top-margin 0 --text-bottom-margin 0
```

Make text heavier:

```bash
$ ./print.py --text "YOU GOT HACKED" --text-size 40 --text-thickness 5
```

Reduce the paper feed after printing. Do not set it too low if the last line
does not fully leave the print head:

```bash
$ ./print.py --text "YOU GOT HACKED" --feed 8
$ ./print.py --text "YOU GOT HACKED" --feed 0
```

If your printer still leaves a gap between separate print jobs, also reduce the
number of repeated tail-feed commands:

```bash
$ ./print.py --text "YOU GOT HACKED" --feed 0 --feed-repeats 0 --finish-feed 0
```


# Different Algorithms

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
