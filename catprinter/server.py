#!/usr/bin/env python3
"""Local voice-to-sticker web UI that prints through the Cat printer's BLE path."""

import argparse
import asyncio
import base64
from io import BytesIO
import time
import uuid

from flask import Flask, jsonify, render_template, request
from PIL import Image

from catprinter.ai import generate_image
from catprinter.cmds import PRINT_WIDTH, cmds_print_img


app = Flask(__name__)

PRINTER_DEVICE = ''
PRINT_ENERGY = 0xFFFF
PRINT_THRESHOLD = 50
TOP_MARGIN = 0
BOTTOM_MARGIN = 0
INCLUDE_END_PAPER_COMMANDS = False
STICKER_JOBS = {}
MAX_STICKER_JOBS = 12


def image_bytes_to_data_url(image_bytes):
    """Return a generated image as a browser-displayable data URL."""
    with Image.open(BytesIO(image_bytes)) as image:
        image_format = (image.format or 'PNG').lower()
    mime_type = {
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'webp': 'image/webp',
    }.get(image_format, 'image/png')
    encoded = base64.b64encode(image_bytes).decode('ascii')
    return f'data:{mime_type};base64,{encoded}'


def prepare_image_for_print(image_bytes):
    """Resize a generated image to printer width and convert it to black dots."""
    with Image.open(BytesIO(image_bytes)) as image:
        grayscale = image.convert('L')
    source_width, source_height = grayscale.size
    target_height = max(1, int(source_height * PRINT_WIDTH / source_width))
    resized = grayscale.resize((PRINT_WIDTH, target_height), Image.Resampling.LANCZOS)
    threshold = round(255 * PRINT_THRESHOLD / 100)
    pixels = resized.load()
    bin_img = [
        [pixels[x, y] <= threshold for x in range(PRINT_WIDTH)]
        for y in range(target_height)
    ]
    blank_row = [False] * PRINT_WIDTH
    return ([blank_row.copy() for _ in range(TOP_MARGIN)] + bin_img +
            [blank_row.copy() for _ in range(BOTTOM_MARGIN)])


def print_image_bytes(image_bytes):
    """Use the same BLE command generation and Bluetooth transport as print.py."""
    bin_img = prepare_image_for_print(image_bytes)
    data = cmds_print_img(
        bin_img,
        energy=PRINT_ENERGY,
        include_end_paper_commands=INCLUDE_END_PAPER_COMMANDS,
    )
    send_print_data(data)
    return (len(bin_img), PRINT_WIDTH), len(data)


def send_print_data(data):
    """Load BLE only when printing, so the local web UI starts immediately."""
    from catprinter.ble import run_ble
    asyncio.run(run_ble(data, device=PRINTER_DEVICE))


@app.route('/', methods=['GET'])
def stickerbox_ui():
    return render_template('index.html')


@app.route('/api/stickers', methods=['POST'])
def create_sticker():
    """Generate a sticker and return its preview before printing."""
    payload = request.get_json(silent=True) or {}
    prompt = str(payload.get('prompt', '')).strip()
    if not prompt:
        return jsonify({'error': 'Say or type what you want to make.'}), 400
    if len(prompt) > 500:
        return jsonify({'error': 'Please keep the idea under 500 characters.'}), 400

    try:
        print(f"\n[>>] Generating sticker: {prompt}")
        image_bytes = generate_image(prompt)
        job_id = uuid.uuid4().hex
        STICKER_JOBS[job_id] = {'image_bytes': image_bytes, 'created_at': time.time()}
        while len(STICKER_JOBS) > MAX_STICKER_JOBS:
            oldest_job_id = min(STICKER_JOBS, key=lambda key: STICKER_JOBS[key]['created_at'])
            del STICKER_JOBS[oldest_job_id]
        return jsonify({
            'job_id': job_id,
            'prompt': prompt,
            'image_url': image_bytes_to_data_url(image_bytes),
        })
    except Exception as error:
        print(f"[-] Sticker generation failed: {error}")
        return jsonify({'error': f'Could not generate the sticker: {error}'}), 502


@app.route('/api/stickers/<job_id>/print', methods=['POST'])
def print_sticker(job_id):
    """Print a generated sticker via Bluetooth Low Energy."""
    job = STICKER_JOBS.get(job_id)
    if job is None:
        return jsonify({'error': 'Sticker preview expired. Please make it again.'}), 404

    try:
        print('[>>] Printing sticker over Bluetooth…')
        image_shape, command_length = print_image_bytes(job['image_bytes'])
        print('[+] Sticker printed!')
        return jsonify({
            'status': 'printed',
            'dimensions': f'{image_shape[1]}x{image_shape[0]}',
            'command_bytes': command_length,
        })
    except Exception as error:
        print(f"[-] Sticker print failed: {error}")
        return jsonify({'error': f'Could not print the sticker: {error}'}), 502


@app.route('/status', methods=['GET'])
def status():
    return jsonify({
        'server': 'ready',
        'printer_transport': 'bluetooth',
        'device': PRINTER_DEVICE or 'auto-discover',
    })


def parse_args():
    parser = argparse.ArgumentParser(description='Voice-to-sticker web UI for a Cat Bluetooth printer')
    parser.add_argument('--host', default='127.0.0.1', help='Web server host (default: 127.0.0.1)')
    parser.add_argument('--port', type=int, default=5000, help='Web server port (default: 5000)')
    parser.add_argument('-d', '--device', default='', help='Printer BLE address or name; auto-discover if omitted')
    parser.add_argument('-e', '--energy', type=lambda h: int(h.removeprefix('0x'), 16), default=0xFFFF,
                        help='Thermal energy in hex, e.g. 0xffff (default: 0xffff)')
    parser.add_argument('--threshold', type=float, default=50,
                        help='AI black/white cutoff percentage, 0-100 (default: 50)')
    parser.add_argument('--top-margin', type=int, default=0,
                        help='Blank printer rows before each sticker (default: 0)')
    parser.add_argument('--bottom-margin', type=int, default=0,
                        help='Blank printer rows after each sticker (default: 0)')
    parser.add_argument('--include-end-paper-commands', action='store_true',
                        help='Send the three end-paper commands that advance paper on some printers')
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    if not 0 <= args.threshold <= 100:
        raise SystemExit('--threshold must be between 0 and 100')
    if args.top_margin < 0 or args.bottom_margin < 0:
        raise SystemExit('--top-margin and --bottom-margin cannot be negative')

    PRINTER_DEVICE = args.device
    PRINT_ENERGY = args.energy
    PRINT_THRESHOLD = args.threshold
    TOP_MARGIN = args.top_margin
    BOTTOM_MARGIN = args.bottom_margin
    INCLUDE_END_PAPER_COMMANDS = args.include_end_paper_commands

    print(f"""
Sticker Press is ready.
Open http://{args.host}:{args.port}
Printer: {PRINTER_DEVICE or 'auto-discover over Bluetooth'}
""")
    app.run(host=args.host, port=args.port, debug=False)
