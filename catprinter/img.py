import cv2
from math import ceil
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from catprinter import logger


def render_text(
    text,
    print_width,
    font_size=40,
    margin=16,
    top_margin=None,
    bottom_margin=None,
    align='center',
):
    """Render text into the printer's boolean bitmap representation.

    ``True`` represents a black dot, matching :func:`read_img`.
    """
    if not text:
        raise RuntimeError('Text cannot be empty.')
    if font_size <= 0:
        raise RuntimeError('Text size must be greater than zero.')
    if margin < 0 or margin * 2 >= print_width:
        raise RuntimeError('Text margin must leave room inside the print width.')
    top_margin = margin if top_margin is None else top_margin
    bottom_margin = margin if bottom_margin is None else bottom_margin
    if top_margin < 0 or bottom_margin < 0:
        raise RuntimeError('Text top and bottom margins cannot be negative.')

    try:
        font = ImageFont.truetype('DejaVuSans.ttf', font_size)
    except OSError:
        font = ImageFont.load_default()

    measure = ImageDraw.Draw(Image.new('L', (1, 1)))
    max_line_width = print_width - (margin * 2)
    lines = []
    for paragraph in text.splitlines() or ['']:
        words = paragraph.split(' ')
        line = ''
        for word in words:
            candidate = word if not line else f'{line} {word}'
            if line and measure.textlength(candidate, font=font) > max_line_width:
                lines.append(line)
                line = word
            else:
                line = candidate
        lines.append(line)

    if hasattr(font, 'getmetrics'):
        ascent, descent = font.getmetrics()
        line_height = ascent + descent
    else:
        line_height = font_size
    line_spacing = max(2, font_size // 8)
    height = (
        top_margin
        + bottom_margin
        + len(lines) * line_height
        + (len(lines) - 1) * line_spacing
    )
    image = Image.new('L', (print_width, height), color=255)
    draw = ImageDraw.Draw(image)

    y = top_margin
    for line in lines:
        line_width = draw.textlength(line, font=font)
        if align == 'left':
            x = margin
        elif align == 'right':
            x = print_width - margin - line_width
        else:
            x = (print_width - line_width) / 2
        draw.text((x, y), line, fill=0, font=font)
        y += line_height + line_spacing

    return np.asarray(image) < 128


def add_vertical_margins(bin_img, top_margin=0, bottom_margin=0):
    """Add blank printer rows above and below a boolean printer bitmap."""
    if top_margin < 0 or bottom_margin < 0:
        raise RuntimeError('Top and bottom margins cannot be negative.')
    if not top_margin and not bottom_margin:
        return bin_img
    return np.pad(
        bin_img,
        ((top_margin, bottom_margin), (0, 0)),
        mode='constant',
        constant_values=False,
    )


def floyd_steinberg_dither(img, threshold=127):
    '''Applies the Floyd-Steinberg dithering to img, in place.
    img is expected to be a 8-bit grayscale image.

    Algorithm borrowed from wikipedia.org/wiki/Floyd%E2%80%93Steinberg_dithering.
    '''
    h, w = img.shape

    def adjust_pixel(y, x, delta):
        if y < 0 or y >= h or x < 0 or x >= w:
            return
        img[y][x] = min(255, max(0, img[y][x] + delta))

    for y in range(h):
        for x in range(w):
            new_val = 255 if img[y][x] > threshold else 0
            err = img[y][x] - new_val
            img[y][x] = new_val
            adjust_pixel(y, x + 1, err * 7/16)
            adjust_pixel(y + 1, x - 1, err * 3/16)
            adjust_pixel(y + 1, x, err * 5/16)
            adjust_pixel(y + 1, x + 1, err * 1/16)
    return img

def atkinson_dither(img, threshold=127):
    '''
    Applies the Atkinson dithering to img, in place.
    img is expected to be a 8-bit grayscale image.

    Algorithm from https://tannerhelland.com/2012/12/28/dithering-eleven-algorithms-source-code.html
    '''
    h, w = img.shape

    def adjust_pixel(y, x, delta):
        if y < 0 or y >= h or x < 0 or x >= w:
            return
        img[y][x] = min(255, max(0, img[y][x] + delta))

    for y in range(h):
        for x in range(w):
            new_val = 255 if img[y][x] > threshold else 0
            err = img[y][x] - new_val
            img[y][x] = new_val
            adjust_pixel(y, x + 1, err * 1/8)
            adjust_pixel(y, x + 2, err * 1/8)
            adjust_pixel(y + 1, x - 1, err * 1/8)
            adjust_pixel(y + 1, x, err * 1/8)
            adjust_pixel(y + 1, x + 1, err * 1/8)
            adjust_pixel(y + 2, x, err * 1/8)
    return img


def halftone_dither(img):
    '''Applies Halftone dithering using different sized circles

    Algorithm is borrowed from https://github.com/GravO8/halftone
    '''

    def square_avg_value(square):
        '''
        Calculates the average grayscale value of the pixels in a square of the
        original image
        Argument:
            square: List of N lists, each with N integers whose value is between 0
            and 255
        '''
        sum = 0
        n = 0
        for row in square:
            for pixel in row:
                sum += pixel
                n += 1
        return sum/n

    side = 4
    jump = 4  # Todo: make this configurable
    alpha = 3
    height, width = img.shape

    if not jump:
        jump = ceil(min(height, height)*0.007)
    assert jump > 0, "jump must be greater than 0"

    height_output, width_output = side*ceil(height/jump), side*ceil(width/jump)
    canvas = np.zeros((height_output, width_output), np.uint8)
    output_square = np.zeros((side, side), np.uint8)
    x_output, y_output = 0, 0
    for y in range(0, height, jump):
        for x in range(0, width, jump):
            output_square[:] = 255
            intensity = 1 - square_avg_value(img[y:y+jump, x:x+jump])/255
            radius = int(alpha*intensity*side/2)
            if radius > 0:
                # draw a circle
                cv2.circle(
                    output_square,
                    center=(side//2, side//2),
                    radius=radius,
                    color=(0, 0, 0),
                    thickness=-1,
                    lineType=cv2.FILLED
                )
            # place the square on the canvas
            canvas[y_output:y_output+side,
                   x_output:x_output+side] = output_square
            x_output += side
        y_output += side
        x_output = 0
    return canvas


def read_img(
    filename,
    print_width,
    img_binarization_algo,
    threshold_percent=50,
):
    im = cv2.imread(filename, cv2.IMREAD_GRAYSCALE)
    if im is None:
        raise RuntimeError(f'Unable to read image: {filename}')
    return prepare_img(im, print_width, img_binarization_algo, threshold_percent)


def read_img_bytes(
    image_bytes,
    print_width,
    img_binarization_algo,
    threshold_percent=50,
):
    """Decode an in-memory image and prepare it for the printer."""
    encoded = np.frombuffer(image_bytes, dtype=np.uint8)
    im = cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE)
    if im is None:
        raise RuntimeError('Unable to decode generated image.')
    return prepare_img(im, print_width, img_binarization_algo, threshold_percent)


def prepare_img(
    im,
    print_width,
    img_binarization_algo,
    threshold_percent=50,
):
    """Resize and convert a grayscale image into printer dots."""
    if not 0 <= threshold_percent <= 100:
        raise RuntimeError('Threshold must be between 0 and 100.')

    threshold = round(255 * threshold_percent / 100)
    height = im.shape[0]
    width = im.shape[1]
    factor = print_width / width
    resized = cv2.resize(
        im,
        (
            print_width,
            int(height * factor)
        ),
        interpolation=cv2.INTER_AREA)

    if img_binarization_algo == 'atkinson':
        logger.info('⏳ Applying Atkinson dithering to image...')
        resized = atkinson_dither(resized, threshold)
        logger.info('✅ Done.')
        resized = resized > threshold
    elif img_binarization_algo == 'floyd-steinberg':
        logger.info('⏳ Applying Floyd-Steinberg dithering to image...')
        resized = floyd_steinberg_dither(resized, threshold)
        logger.info('✅ Done.')
        resized = resized > threshold
    elif img_binarization_algo == 'halftone':
        logger.info('⏳ Applying halftone dithering to image...')
        resized = halftone_dither(resized)
        logger.info('✅ Done.')
        resized = resized > threshold
    elif img_binarization_algo == 'mean-threshold':
        # Keep 50% equivalent to the original image-average threshold, while
        # allowing the caller to shift it toward a darker or lighter print.
        mean_threshold = resized.mean() + (threshold_percent - 50) * 2.55
        resized = resized > np.clip(mean_threshold, 0, 255)
    elif img_binarization_algo == 'fixed-threshold':
        # Directly classify each pixel instead of turning light gray areas into
        # dither dots. Useful for clean AI-generated line art.
        resized = resized > threshold
    elif img_binarization_algo == 'none':
        if width == print_width:
            resized = im > threshold
        else:
            raise RuntimeError(
                f'Wrong width of {width} px. '
                f'An image with a width of {print_width} px '
                f'is required for "none" binarization'
            )

    else:
        raise RuntimeError(
            f'unknown image binarization algorithm: '
            f'{img_binarization_algo}'
        )

    # Invert the image before returning it.
    return ~resized


def show_preview(bin_img, bottom_padding=0):
    # Convert from our boolean representation to float and invert.
    if bottom_padding:
        bin_img = np.pad(
            bin_img,
            ((0, bottom_padding), (0, 0)),
            mode='constant',
            constant_values=False,
        )
    preview_img = (~bin_img).astype(float)
    cv2.imshow('Preview', preview_img)
    logger.info('ℹ️  Displaying preview.')
    # Calling waitKey(1) tells OpenCV to process its GUI events and actually display our image.
    cv2.waitKey(1)
    if input('🤔 Go ahead with print? [Y/n]? ').lower() == 'n':
        raise RuntimeError('Aborted print.')
