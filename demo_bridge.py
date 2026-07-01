#!/usr/bin/env python3
"""Bridge the ESP32 demo's USB serial events to the real Cat Printer."""

import argparse
import asyncio
from pathlib import Path
import sys

import serial
from serial.tools import list_ports

from catprinter.ble import run_ble
from catprinter.cmds import PRINT_WIDTH, cmds_print_img
from catprinter.img import read_img


DEFAULT_PRINTER_DEVICE = "230BD164-E303-D0B1-7476-F83BB4E81722"
DEFAULT_IMAGE = Path(__file__).parent / "firmware" / "data" / "demo.jpg"


def find_esp32_port():
    """Return the most likely ESP32 USB serial device."""
    ports = list(list_ports.comports())
    preferred = [
        port for port in ports
        if any(marker in f"{port.device} {port.description}".lower()
               for marker in ("usbmodem", "esp32", "usb jtag", "usb serial"))
    ]
    candidates = preferred or ports
    if not candidates:
        raise RuntimeError("No serial ports found. Connect the ESP32-S3 over USB.")
    return candidates[0].device


def print_demo_image(image_path, printer_device):
    """Prepare and print the demo image through the existing BLE implementation."""
    bin_img = read_img(
        str(image_path),
        PRINT_WIDTH,
        "fixed-threshold",
        threshold_percent=50,
    )
    commands = cmds_print_img(bin_img, include_end_paper_commands=False)
    asyncio.run(run_ble(commands, device=printer_device))


def send_line(connection, message):
    connection.write(f"{message}\n".encode("utf-8"))
    connection.flush()


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="ESP32 serial port; auto-detected if omitted")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE)
    parser.add_argument("--device", default=DEFAULT_PRINTER_DEVICE,
                        help="Cat Printer BLE UUID or name")
    return parser.parse_args()


def main():
    args = parse_args()
    image_path = args.image.resolve()
    if not image_path.is_file():
        raise SystemExit(f"Demo image not found: {image_path}")

    try:
        port = args.port or find_esp32_port()
    except RuntimeError as error:
        raise SystemExit(str(error)) from error

    print(f"ESP32: {port} @ {args.baud}")
    print(f"Printer: {args.device}")
    print(f"Image: {image_path}")

    with serial.Serial(port, args.baud, timeout=0.5) as connection:
        while True:
            raw_line = connection.readline()
            if not raw_line:
                continue
            message = raw_line.decode("utf-8", errors="replace").strip()
            if not message or message.startswith("ACK:"):
                continue
            print(f"ESP32 > {message}")
            if message != "PRINT_DEMO":
                continue

            send_line(connection, "PRINTING")
            try:
                print_demo_image(image_path, args.device)
            except Exception as error:
                print(f"Print failed: {error}", file=sys.stderr)
                send_line(connection, f"PRINT_ERROR:{error}")
            else:
                print("Print completed.")
                send_line(connection, "PRINT_OK")


if __name__ == "__main__":
    main()

