#!/usr/bin/env python
import argparse
import asyncio
import logging
import sys
import os

from catprinter import logger
from catprinter.ai import MODEL as DEFAULT_AI_MODEL, generate_image
from catprinter.cmds import PRINT_WIDTH, cmds_print_img
from catprinter.ble import run_ble
from catprinter.img import (
    add_vertical_margins,
    read_img,
    read_img_bytes,
    render_text,
    show_preview,
)


DEFAULT_PRINTER_DEVICE = '230BD164-E303-D0B1-7476-F83BB4E81722'


def parse_args():
    args = argparse.ArgumentParser(
        description='prints an image on your cat thermal printer')
    args.add_argument('filename', type=str, nargs='?',
                      help='Image file to print (PNG, JPEG, etc.)')
    args.add_argument('--text', type=str,
                      help='Text to render and print instead of an image file.')
    args.add_argument('--ai', type=str,
                      help='Generate an illustration from a prompt, preview it, then print it.')
    args.add_argument('--ai-model', type=str, default=DEFAULT_AI_MODEL,
                      help=f'Pollinations image model (default: {DEFAULT_AI_MODEL}).')
    args.add_argument('--text-size', type=int, default=40,
                      help='Text size in pixels (default: 40).')
    args.add_argument('--text-margin', type=int, default=16,
                      help='Horizontal text margin, and the default top/bottom margin, in pixels (default: 16).')
    args.add_argument('--text-top-margin', type=int,
                      help='Text whitespace above the first line in pixels. Defaults to --text-margin.')
    args.add_argument('--text-bottom-margin', type=int,
                      help='Text whitespace below the last line in pixels. Defaults to --text-margin.')
    args.add_argument('--top-margin', type=int,
                      help='Blank rows before the final print. Works with images, AI, and text; '
                           'overrides --text-top-margin for text.')
    args.add_argument('--bottom-margin', type=int,
                      help='Blank rows after the final print. Works with images, AI, and text; '
                           'overrides --text-bottom-margin for text.')
    args.add_argument('--text-align', choices=['left', 'center', 'right'], default='center',
                      help='Text alignment (default: center).')
    args.add_argument('-l', '--log-level', type=str,
                      choices=['debug', 'info', 'warn', 'error'], default='info')
    args.add_argument('-b', '--img-binarization-algo', type=str,
                      choices=['mean-threshold',
                               'fixed-threshold', 'floyd-steinberg', 'atkinson',
                               'halftone', 'none'],
                      default=None,
                      help=f'Which image binarization algorithm to use. If \'none\'  \
                             is used, no binarization will be used. In this case the \
                             image has to have a width of {PRINT_WIDTH} px. Defaults to \
                             Floyd-Steinberg for image files and fixed-threshold for AI.')
    args.add_argument('--threshold', type=float, default=50,
                      help='Black/white cutoff as a percentage (0–100; default: 50). '
                           'Higher values print more dots.')
    args.add_argument('-s', '--show-preview', action='store_true',
                      help='If set, displays the final image and asks the user for \
                          confirmation before printing. AI jobs always require approval.')
    args.add_argument('-d', '--device', type=str, default=DEFAULT_PRINTER_DEVICE,
                      help=(
                          'The printer\'s Bluetooth Low Energy (BLE) address '
                          '(MAC address on Linux; UUID on macOS) '
                          'or advertisement name (e.g.: "GT01", "GB02", "GB03"). '
                          f'Default: {DEFAULT_PRINTER_DEVICE} (PD01).'
                      ))
    args.add_argument('-e', '--energy', type=lambda h: int(h.removeprefix("0x"), 16),
                      help="Thermal energy. Between 0x0000 (light) and 0xffff (darker, default).",
                      default="0xffff")
    args.add_argument('--skip-end-paper-commands', action='store_true',
                      help='Diagnostic: omit the three undocumented end-of-print '
                           'paper-control commands. Use to test excess paper advance.')
    args.add_argument('--chunk-delay-ms', type=float, default=5,
                      help='Delay after each BLE write chunk in milliseconds (default: 5).')
    parsed = args.parse_args()
    input_count = sum(bool(value) for value in (parsed.filename, parsed.text, parsed.ai))
    if input_count != 1:
        args.error('provide exactly one image filename, --text TEXT, or --ai PROMPT')
    return parsed


def configure_logger(log_level):
    logger.setLevel(log_level)
    h = logging.StreamHandler(sys.stdout)
    h.setLevel(log_level)
    logger.addHandler(h)


def main():
    args = parse_args()

    log_level = getattr(logging, args.log_level.upper())
    configure_logger(log_level)

    if args.filename and not os.path.exists(args.filename):
        logger.info('🛑 File not found. Exiting.')
        return

    try:
        if args.ai:
            logger.info('⏳ Generating AI illustration...')
            generated_image = generate_image(args.ai, model=args.ai_model)
            # AI line art should keep its solid black lines; do not introduce
            # Floyd-Steinberg dither dots unless the user explicitly asks for it.
            binarization_algo = args.img_binarization_algo or 'fixed-threshold'
            bin_img = read_img_bytes(
                generated_image,
                PRINT_WIDTH,
                binarization_algo,
                threshold_percent=args.threshold,
            )
            logger.info('✅ Generated AI illustration.')
        elif args.text:
            bin_img = render_text(
                args.text,
                PRINT_WIDTH,
                font_size=args.text_size,
                margin=args.text_margin,
                top_margin=(
                    args.top_margin
                    if args.top_margin is not None
                    else args.text_top_margin
                ),
                bottom_margin=(
                    args.bottom_margin
                    if args.bottom_margin is not None
                    else args.text_bottom_margin
                ),
                align=args.text_align,
            )
            logger.info('✅ Rendered text.')
        else:
            binarization_algo = args.img_binarization_algo or 'floyd-steinberg'
            bin_img = read_img(
                args.filename,
                PRINT_WIDTH,
                binarization_algo,
                threshold_percent=args.threshold,
            )
        if not args.text:
            bin_img = add_vertical_margins(
                bin_img,
                top_margin=args.top_margin or 0,
                bottom_margin=args.bottom_margin or 0,
            )
        if args.show_preview or args.ai:
            show_preview(bin_img)
    except RuntimeError as e:
        logger.error(f'🛑 {e}')
        return

    logger.info(f'✅ Read image: {bin_img.shape} (h, w) pixels')
    data = cmds_print_img(
        bin_img,
        energy=args.energy,
        include_end_paper_commands=not args.skip_end_paper_commands,
    )
    logger.info(f'✅ Generated BLE commands: {len(data)} bytes')

    # Connect directly to the configured printer UUID by default.
    try:
        asyncio.run(run_ble(
            data,
            device=args.device,
            chunk_delay_s=max(0, args.chunk_delay_ms) / 1000,
        ))
    except RuntimeError as error:
        logger.error(f'🛑 {error}')


if __name__ == '__main__':
    main()
