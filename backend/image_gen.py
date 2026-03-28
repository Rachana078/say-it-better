import os
import base64
from google import genai
from google.genai import types

IMAGE_MODEL = "imagen-4.0-fast-generate-001"

IMAGE_PROMPT_TEMPLATE = """A clean minimal message card. Dark navy background.
White sans-serif text centered on the card.
The following message displayed clearly in the center:
"{exact_words}"
Subtle warm amber glow around the edges.
Professional, calm, beautiful. No people, no icons."""

CARD_PATH = os.path.join(os.path.dirname(__file__), '..', 'card.png')


def generate_card(exact_words: str, api_key: str) -> str:
    """Generate card.png from exact_words. Returns absolute path to saved card."""
    client = genai.Client(api_key=api_key)
    prompt = IMAGE_PROMPT_TEMPLATE.format(exact_words=exact_words)

    response = client.models.generate_images(
        model=IMAGE_MODEL,
        prompt=prompt,
        config=types.GenerateImagesConfig(number_of_images=1),
    )

    if not response.generated_images:
        raise RuntimeError("No image returned from image generation API")

    card_path = os.path.abspath(CARD_PATH)
    with open(card_path, "wb") as f:
        f.write(response.generated_images[0].image.image_bytes)
    return card_path


def card_to_base64(card_path: str) -> str:
    with open(card_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")
