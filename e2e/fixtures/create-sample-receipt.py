#!/usr/bin/env python3
"""Generate e2e/fixtures/sample-receipt.jpg via Pillow.

Run once to produce the test fixture:
    python e2e/fixtures/create-sample-receipt.py
"""

import io
import os

from PIL import Image, ImageDraw, ImageFont

OUTPUT = os.path.join(os.path.dirname(__file__), "sample-receipt.jpg")
WIDTH, HEIGHT = 400, 600


def main() -> None:
    img = Image.new("RGB", (WIDTH, HEIGHT), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    try:
        font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
        font_med = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except OSError:
        font_large = ImageFont.load_default()
        font_med = font_large
        font_small = font_large

    # Header
    draw.text((WIDTH // 2, 40), "WHOLE FOODS MARKET", fill=(0, 0, 0), font=font_large, anchor="mm")
    draw.text((WIDTH // 2, 70), "123 Market Street, Springfield", fill=(80, 80, 80), font=font_small, anchor="mm")
    draw.text((WIDTH // 2, 88), "Tel: (555) 123-4567", fill=(80, 80, 80), font=font_small, anchor="mm")

    # Divider
    draw.line([(20, 105), (WIDTH - 20, 105)], fill=(0, 0, 0), width=2)

    # Date/time
    draw.text((20, 115), "Date: 2026-03-21", fill=(0, 0, 0), font=font_small)
    draw.text((20, 133), "Time: 14:32", fill=(0, 0, 0), font=font_small)
    draw.text((20, 151), "Cashier: #0042", fill=(0, 0, 0), font=font_small)

    draw.line([(20, 170), (WIDTH - 20, 170)], fill=(0, 0, 0), width=1)

    # Items
    items = [
        ("Organic Bananas 1.2lb", "$1.49"),
        ("Whole Milk 1gal", "$4.99"),
        ("Free-Range Eggs 12ct", "$6.49"),
        ("Sourdough Bread", "$5.99"),
        ("Cheddar Cheese 8oz", "$7.49"),
        ("Cherry Tomatoes 1pt", "$4.29"),
        ("Baby Spinach 5oz", "$3.99"),
        ("Greek Yogurt 32oz", "$6.99"),
        ("Orange Juice 52oz", "$5.49"),
    ]
    y = 180
    for name, price in items:
        draw.text((20, y), name, fill=(0, 0, 0), font=font_small)
        draw.text((WIDTH - 20, y), price, fill=(0, 0, 0), font=font_small, anchor="ra")
        y += 20

    draw.line([(20, y + 5), (WIDTH - 20, y + 5)], fill=(0, 0, 0), width=1)
    y += 15

    # Totals
    draw.text((20, y), "Subtotal:", fill=(0, 0, 0), font=font_med)
    draw.text((WIDTH - 20, y), "$47.21", fill=(0, 0, 0), font=font_med, anchor="ra")
    y += 26
    draw.text((20, y), "Tax (0.05%):", fill=(0, 0, 0), font=font_med)
    draw.text((WIDTH - 20, y), "$0.02", fill=(0, 0, 0), font=font_med, anchor="ra")
    y += 26

    draw.line([(20, y), (WIDTH - 20, y)], fill=(0, 0, 0), width=2)
    y += 8

    draw.text((20, y), "TOTAL:", fill=(0, 0, 0), font=font_large)
    draw.text((WIDTH - 20, y), "$47.23", fill=(0, 0, 0), font=font_large, anchor="ra")
    y += 36

    # Payment
    draw.text((20, y), "VISA *4242", fill=(0, 0, 0), font=font_small)
    draw.text((WIDTH - 20, y), "$47.23", fill=(0, 0, 0), font=font_small, anchor="ra")
    y += 20

    draw.line([(20, y + 5), (WIDTH - 20, y + 5)], fill=(0, 0, 0), width=1)

    # Footer
    draw.text((WIDTH // 2, HEIGHT - 50), "Thank you for shopping!", fill=(0, 0, 0), font=font_med, anchor="mm")
    draw.text((WIDTH // 2, HEIGHT - 28), "www.wholefoods.com", fill=(80, 80, 80), font=font_small, anchor="mm")

    # Save with quality that yields ~25KB
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85, optimize=True)
    size = buf.tell()

    with open(OUTPUT, "wb") as f:
        f.write(buf.getvalue())

    print(f"Written {OUTPUT} ({size:,} bytes)")


if __name__ == "__main__":
    main()
