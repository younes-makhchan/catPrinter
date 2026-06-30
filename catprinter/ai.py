"""Pollinations image generation for the thermal-printer workflow."""

import os
from urllib.parse import quote, urlencode

import requests


MODEL = "flux"
IMAGE_ENDPOINT = "https://gen.pollinations.ai/image"
PRINTER_ART_DIRECTION = """Create a single-panel, playful comic/cartoon illustration.
Use bold black ink outlines, high contrast, a pure white background, and large,
readable shapes. Use no gradients, no grey shading, and no text. Compose it as a
portrait image optimized for a 384-dot monochrome thermal printer.

Scene to illustrate: {what the user said}"""


def build_prompt(user_prompt):
    """Combine a user's scene description with constraints for thermal printing."""
    return f"{PRINTER_ART_DIRECTION}\n<request>{user_prompt.strip()}</request>"


def generate_image(user_prompt, model=MODEL):
    """Generate an image in memory and return its bytes.

    The generated image is deliberately not saved; the caller decides whether to
    preview and print it.
    """
    if not user_prompt or not user_prompt.strip():
        raise RuntimeError("AI prompt cannot be empty.")

    api_key = os.getenv("POLLINATIONS_API_KEY", "").strip()
    if api_key.lower().startswith("bearer "):
        api_key = api_key.split(None, 1)[1]

    prompt = build_prompt(user_prompt)
    query = urlencode({"model": model})
    url = f"{IMAGE_ENDPOINT}/{quote(prompt, safe='')}?{query}"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        image_data = response.content
        response.close()
    except requests.HTTPError as error:
        body = error.response.text if error.response is not None else ""
        detail = f": {body}" if body else ""
        raise RuntimeError(
            f"AI image generation failed: Pollinations returned HTTP "
            f"{error.response.status_code}{detail}"
        ) from error
    except requests.RequestException as error:
        raise RuntimeError(f"AI image generation failed: {error}") from error

    if not image_data:
        raise RuntimeError("AI image generation returned no image.")
    return image_data
