import os
import base64
import textwrap
from PIL import Image, ImageDraw, ImageFilter, ImageFont

CARD_PATH   = os.path.join(os.path.dirname(__file__), '..', 'card.png')
CARD_A_PATH = os.path.join(os.path.dirname(__file__), '..', 'card_a.png')
CARD_B_PATH = os.path.join(os.path.dirname(__file__), '..', 'card_b.png')

_FONT_CANDIDATES = [
    "/System/Library/Fonts/SFNS.ttf",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]


def _font(size: int) -> ImageFont.FreeTypeFont:
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _add_edge_glow(img: Image.Image, color: tuple, strength: float) -> Image.Image:
    """Draw a thin colored border, blur it softly, then blend onto img."""
    W, H = img.size
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.rectangle([0, 0, W - 1, H - 1], outline=color, width=40)
    glow = glow.filter(ImageFilter.GaussianBlur(radius=38))
    return Image.blend(img, glow, alpha=strength)


def _draw_centered_text(draw: ImageDraw.Draw, text: str, font, img_w: int, y_mid: int,
                         fill: tuple, line_gap: int = 14) -> None:
    """Word-wrap text and draw each line horizontally centered around y_mid."""
    avg_w = font.getlength("n")
    max_chars = max(12, int(img_w * 0.72 / avg_w))
    lines = textwrap.wrap(text, width=max_chars)

    # Measure line height from the font
    sample_bbox = draw.textbbox((0, 0), "Ag", font=font)
    line_h = sample_bbox[3] - sample_bbox[1]

    total_h = len(lines) * line_h + (len(lines) - 1) * line_gap
    y = y_mid - total_h // 2

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        lw = bbox[2] - bbox[0]
        draw.text(((img_w - lw) // 2, y), line, font=font, fill=fill)
        y += line_h + line_gap


# ── Public API ───────────────────────────────────────────────────────────────

def generate_card(exact_words: str, api_key: str = None) -> str:
    """Render a dark card with exact_words in crisp white text. Returns saved path."""
    W, H = 800, 480
    img = Image.new("RGB", (W, H), (10, 10, 26))         # dark navy background
    img = _add_edge_glow(img, (245, 158, 11), 0.3)        # subtle warm amber edge glow

    draw = ImageDraw.Draw(img)
    font = _font(40)
    _draw_centered_text(draw, exact_words, font, W, H // 2, fill=(238, 238, 248))

    path = os.path.abspath(CARD_PATH)
    img.save(path, "PNG")
    return path


def generate_decide_cards(option_a: str, option_b: str, api_key: str = None) -> tuple[str, str]:
    """Render two decision cards. Returns (card_a_b64, card_b_b64)."""
    W, H = 600, 380

    def make_card(option: str, label: str, glow_color: tuple,
                  label_color: tuple, path: str) -> str:
        img = Image.new("RGB", (W, H), (10, 10, 26))
        img = _add_edge_glow(img, glow_color, 0.38)

        draw = ImageDraw.Draw(img)

        # Small label near top
        lf = _font(17)
        lb = draw.textbbox((0, 0), label, font=lf)
        lw = lb[2] - lb[0]
        draw.text(((W - lw) // 2, 44), label, font=lf, fill=label_color)

        # Main option text — centered in lower 3/4 of card
        of = _font(33)
        _draw_centered_text(draw, option, of, W, H // 2 + 22, fill=(238, 238, 248))

        p = os.path.abspath(path)
        img.save(p, "PNG")
        return card_to_base64(p)

    card_a_b64 = make_card(
        option_a,
        "What you think you should do",
        (96, 165, 250),   # blue glow
        (148, 163, 184),  # slate label
        CARD_A_PATH,
    )
    card_b_b64 = make_card(
        option_b,
        "What you actually want",
        (245, 158, 11),   # amber glow
        (245, 158, 11),   # amber label
        CARD_B_PATH,
    )
    return card_a_b64, card_b_b64


def card_to_base64(card_path: str) -> str:
    with open(card_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")
