#!/usr/bin/env python3
"""Regenerate the synthetic online-order screenshots in fixtures/.

Every fixture is an HTML page rendered with headless Chrome. All names,
addresses, and order numbers are fake. Dates are fixed in November 2026 to line
up with the "today" pinned in cases.json, so the expected values never rot.

Dev-only (not needed to run the eval, which just reads the committed PNGs):

    pip install playwright   # any venv; uses the system Chrome, no browser download
    python make_fixtures.py [--chrome /usr/bin/google-chrome]
"""

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent / "fixtures"
FONT = "'Inter','Liberation Sans','Noto Sans',Arial,sans-serif"
ADDR = "123 Example St<br>Springfield, CA 90000-0000<br>United States"

ORNAMENT_TITLE = "Shiny Brite Glass Christmas Ornaments 12-Piece Set Multicolor in Original Box"
THUMB = (
    '<div style="width:84px;height:84px;background:#1f6b3a;border:3px solid #d4af37;'
    "display:flex;align-items:center;justify-content:center;color:#f5e08a;"
    'font:italic 700 15px Georgia,serif;text-align:center;line-height:1.1">Shiny<br>Brite</div>'
)


def page(body: str, css: str = "") -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
    body{{margin:0;background:#fff;color:#191919;font-family:{FONT};font-size:15px}}
    {css}</style></head><body>{body}</body></html>"""


EBAY_PANEL_CSS = """
.wrap{padding:28px 32px;width:680px}
.row{display:grid;grid-template-columns:150px 1fr;padding:11px 0;line-height:1.45}
.row .l{color:#707070}.row .v{font-weight:700}
.item{display:flex;gap:18px;margin-top:22px;padding-top:22px;border-top:1px solid #e5e5e5}
.item .t{font-size:16px;line-height:1.4;max-width:470px}.item .c{color:#707070;margin-top:6px}
"""


def ebay_panel() -> str:
    return f"""<div class="wrap">
    <div class="row"><div class="l">Get it</div><div class="v">Nov 30 - Dec 5</div></div>
    <div class="row"><div class="l">Shipping to</div><div class="v">{ADDR}</div></div>
    <div class="row"><div class="l">Order</div><div class="v">06-15482-40835</div></div>
    <div class="row"><div class="l">Total</div><div class="v">$68.23</div></div>
    <div class="item">{THUMB}<div><div class="t">{ORNAMENT_TITLE}</div><div class="c">Used</div></div></div>
    </div>"""


EBAY_LOGO = (
    '<span style="font:700 40px Arial,sans-serif;letter-spacing:-2px">'
    '<span style="color:#e53238">e</span><span style="color:#0064d2">b</span>'
    '<span style="color:#f5af02">a</span><span style="color:#86b817">y</span></span>'
)


def ebay_header() -> str:
    return page(
        f"""<div style="padding:18px 32px;border-bottom:1px solid #e5e5e5;display:flex;justify-content:space-between;align-items:center">
        {EBAY_LOGO}<span style="color:#555">My eBay &nbsp;·&nbsp; Alex &#9662;</span></div>
        <div style="padding:26px 32px 0"><div style="font-size:26px;font-weight:700">Thanks for your order, Alex!</div>
        <div style="color:#555;margin-top:6px">We've sent a confirmation to a***@example.com</div></div>
        {ebay_panel()}""",
        EBAY_PANEL_CSS,
    )


def ebay_crop() -> str:
    return page(ebay_panel(), EBAY_PANEL_CSS)


def amazon_desktop() -> str:
    return page(
        """<div style="background:#131921;color:#fff;padding:14px 28px;display:flex;gap:30px;align-items:center">
        <span style="font:700 26px Arial">amazon<span style="color:#ff9900">.com</span></span><span>Hello, Alex</span><span>Returns &amp; Orders</span></div>
        <div style="padding:22px 40px;width:900px">
        <div style="font-size:28px;margin-bottom:14px">Order Details</div>
        <div style="color:#555">Ordered on November 18, 2026 &nbsp;|&nbsp; Order# 112-3456789-0123456</div>
        <div style="border:1px solid #ddd;border-radius:8px;margin-top:16px">
          <div style="background:#f0f2f2;padding:14px 18px;display:flex;gap:70px;font-size:13px">
            <div><b>Ship to</b><br>Alex Example<br>123 Example St<br>Springfield, CA 90000-0000</div>
            <div><b>Payment method</b><br>Visa ending in 4242</div>
            <div style="margin-left:auto"><b>Order Summary</b>
              <table style="margin-top:4px;font-size:13px">
              <tr><td>Item(s) Subtotal:</td><td align=right>$36.97</td></tr>
              <tr><td>Shipping &amp; Handling:</td><td align=right>$0.00</td></tr>
              <tr><td>Total before tax:</td><td align=right>$36.97</td></tr>
              <tr><td>Estimated tax to be collected:</td><td align=right>$3.20</td></tr>
              <tr><td><b>Grand Total:</b></td><td align=right><b>$40.17</b></td></tr></table></div></div>
          <div style="padding:18px;display:flex;gap:16px;border-top:1px solid #ddd"><div style="width:90px;height:90px;background:#cfd8dc"></div>
            <div><b>Delivered Nov 20</b><br><span style="color:#007185">Anker USB C Charger, 65W 3-Port Fast Wall Charger</span><br><span style="font-size:13px;color:#555">Sold by: Anker Direct</span><br>$24.99</div></div>
          <div style="padding:18px;display:flex;gap:16px;border-top:1px solid #ddd"><div style="width:90px;height:90px;background:#d7ccc8"></div>
            <div><span style="color:#007185">Pilot G2 Retractable Gel Pens, Fine Point, Black, 12 Count</span><br><span style="font-size:13px;color:#555">Sold by: Amazon.com Services LLC</span><br>$11.98</div></div>
        </div></div>""",
    )


def amazon_mobile() -> str:
    return page(
        """<div style="background:#232f3e;color:#fff;padding:12px 14px;font:700 20px Arial">amazon<span style="color:#ff9900">.com</span></div>
        <div style="padding:16px 14px">
        <div style="font-size:22px;font-weight:700">Order details</div>
        <div style="color:#555;font-size:13px;margin:6px 0 14px">Ordered Nov 21, 2026<br>Order # 114-9876543-2109876</div>
        <div style="border:1px solid #ddd;border-radius:8px;padding:12px">
          <div style="font-weight:700;color:#007600">Arriving Wednesday</div>
          <div style="display:flex;gap:12px;margin-top:10px"><div style="width:72px;height:72px;background:#cfd8dc;flex:none"></div>
          <div style="font-size:14px">Ninja Foodi 6-in-1 Air Fryer Cooking Pot Liners, Pack of 50<br><b>$17.49</b></div></div></div>
        <div style="border:1px solid #ddd;border-radius:8px;padding:12px;margin-top:14px;font-size:14px">
          <b>Order Summary</b>
          <div style="display:flex;justify-content:space-between;margin-top:6px"><span>Item(s) Subtotal:</span><span>$17.49</span></div>
          <div style="display:flex;justify-content:space-between"><span>Shipping &amp; Handling:</span><span>$0.00</span></div>
          <div style="display:flex;justify-content:space-between"><span>Estimated tax:</span><span>$1.51</span></div>
          <div style="display:flex;justify-content:space-between;margin-top:6px;font-weight:700"><span>Grand Total:</span><span>$19.00</span></div></div>
        </div>""",
    )


def etsy_desktop() -> str:
    return page(
        """<div style="padding:14px 36px;border-bottom:1px solid #ddd;display:flex;gap:26px;align-items:center">
        <span style="font:700 30px Georgia,serif;color:#f1641e">Etsy</span><span style="color:#555">Purchases and reviews</span></div>
        <div style="padding:26px 40px;width:820px">
        <div style="font-size:22px;font-weight:700">Order from WillowAndPineStudio</div>
        <div style="color:#555;margin-top:6px">Order #3412345678 &nbsp;·&nbsp; Placed on Nov 15, 2026</div>
        <div style="display:flex;gap:18px;margin-top:22px"><div style="width:100px;height:100px;background:#d7b98e;flex:none"></div>
        <div><div style="font-size:16px">Personalized Walnut Cutting Board, Custom Engraved Family Name</div>
        <div style="color:#555;margin-top:6px;font-size:13px">Size: Large · Engraving: The Examples</div><div style="margin-top:6px">$32.00</div></div></div>
        <table style="margin-top:24px;width:360px;margin-left:auto;font-size:14px">
         <tr><td>Item total</td><td align=right>$32.00</td></tr><tr><td>Shipping</td><td align=right>$5.50</td></tr>
         <tr><td>Sales tax</td><td align=right>$2.40</td></tr>
         <tr style="font-weight:700;font-size:16px"><td style="padding-top:8px">Order total</td><td align=right style="padding-top:8px">$39.90</td></tr></table>
        <div style="margin-top:20px;color:#555;font-size:13px">Ship to: Alex Example, 123 Example St, Springfield, CA 90000-0000</div></div>""",
    )


def etsy_mobile() -> str:
    return page(
        """<div style="padding:12px 14px;border-bottom:1px solid #ddd;font:700 24px Georgia,serif;color:#f1641e">Etsy</div>
        <div style="padding:16px 14px;font-size:14px">
        <div style="font-weight:700;font-size:18px">Thanks for your order!</div>
        <div style="color:#555;margin-top:4px">From <b>VintageThreadsByMae</b> · Nov 19, 2026</div>
        <div style="display:flex;gap:12px;margin-top:14px"><div style="width:80px;height:80px;background:#b39ddb;flex:none"></div>
        <div>Vintage 1970s Hand-Knit Wool Cardigan Sweater, Cream, Size M<br><b>$58.00</b></div></div>
        <div style="margin-top:16px;border-top:1px solid #ddd;padding-top:10px">
        <div style="display:flex;justify-content:space-between"><span>Subtotal</span><span>$58.00</span></div>
        <div style="display:flex;justify-content:space-between"><span>Shipping</span><span>$7.25</span></div>
        <div style="display:flex;justify-content:space-between"><span>Tax</span><span>$0.00</span></div>
        <div style="display:flex;justify-content:space-between;font-weight:700;margin-top:6px"><span>Total</span><span>$65.25</span></div></div></div>""",
    )


def target_desktop() -> str:
    return page(
        """<div style="background:#cc0000;color:#fff;padding:16px 36px;font:700 22px Arial">&#9678; Target</div>
        <div style="padding:26px 40px;width:860px">
        <div style="font-size:26px;font-weight:700">Thanks for your order, Alex!</div>
        <div style="margin-top:8px;color:#555">Order #912003456789 · Placed Nov 22, 2026</div>
        <div style="display:flex;gap:40px;margin-top:22px"><div style="flex:1">
          <div style="font-weight:700;margin-bottom:10px">Arriving Nov 27 – Nov 30</div>
          <div style="display:flex;gap:14px;margin-bottom:14px"><div style="width:64px;height:64px;background:#ffcdd2;flex:none"></div><div>Threshold 6pc Cotton Bath Towel Set - Gray<br><span style="color:#666">Qty 1 · $39.99</span></div></div>
          <div style="display:flex;gap:14px"><div style="width:64px;height:64px;background:#c5e1a5;flex:none"></div><div>Cat &amp; Jack Kids' Fleece Pullover Hoodie - Green, M<br><span style="color:#666">Qty 2 · $14.00 each</span></div></div></div>
        <div style="width:290px;border:1px solid #ddd;padding:16px;font-size:14px;align-self:flex-start"><b>Order summary</b>
          <div style="display:flex;justify-content:space-between;margin-top:8px"><span>Subtotal (3 items)</span><span>$67.99</span></div>
          <div style="display:flex;justify-content:space-between"><span>Shipping</span><span>$0.00</span></div>
          <div style="display:flex;justify-content:space-between"><span>Estimated tax</span><span>$5.64</span></div>
          <div style="display:flex;justify-content:space-between;font-weight:700;font-size:17px;margin-top:8px;border-top:1px solid #ddd;padding-top:8px"><span>Order total</span><span>$73.63</span></div>
          <div style="color:#666;margin-top:8px;font-size:12px">Paid with Visa ending in 4242</div></div></div></div>""",
    )


def target_mobile() -> str:
    return page(
        """<div style="background:#cc0000;color:#fff;padding:12px 14px;font:700 18px Arial">&#9678; Target</div>
        <div style="padding:16px 14px;font-size:14px">
        <div style="font-size:20px;font-weight:700">Order placed</div>
        <div style="color:#555;margin-top:4px">#912007654321 · Nov 23, 2026</div>
        <div style="background:#f3f3f3;border-radius:8px;padding:12px;margin-top:12px"><b>Drive Up</b> · Ready today by 4:00 pm<br>Springfield Store</div>
        <div style="display:flex;gap:12px;margin-top:14px"><div style="width:64px;height:64px;background:#ffe082;flex:none"></div><div>Pedigree Adult Complete Nutrition Dry Dog Food - 28lb<br><span style="color:#666">Qty 1 · $26.99</span></div></div>
        <div style="margin-top:14px;border-top:1px solid #ddd;padding-top:10px">
        <div style="display:flex;justify-content:space-between"><span>Subtotal</span><span>$26.99</span></div>
        <div style="display:flex;justify-content:space-between"><span>Estimated tax</span><span>$2.23</span></div>
        <div style="display:flex;justify-content:space-between;font-weight:700;margin-top:6px"><span>Order total</span><span>$29.22</span></div></div></div>""",
    )


def bestbuy_email() -> str:
    return page(
        """<div style="padding:22px 28px;width:760px">
        <div style="font-size:22px;margin-bottom:6px">Your Best Buy order has shipped</div>
        <div style="color:#555;font-size:13px;display:flex;justify-content:space-between;border-bottom:1px solid #ddd;padding-bottom:12px">
          <span><b style="color:#222">Best Buy</b> &lt;BestBuyInfo@emailinfo.example.com&gt;<br>to me</span><span>Mon, Nov 23, 2026, 4:12 PM</span></div>
        <div style="background:#0046be;color:#fff;font:700 26px Arial;padding:14px 20px;margin-top:18px;letter-spacing:-1px">BEST BUY</div>
        <div style="padding:18px 20px;border:1px solid #ddd;border-top:0">
          <div style="font-size:18px;font-weight:700">Order #BBY01-806512345678</div>
          <div style="margin-top:14px;display:flex;gap:16px"><div style="width:90px;height:90px;background:#bbdefb;flex:none"></div>
          <div>Sony - WH-CH520 Wireless On-Ear Bluetooth Headphones - Black<br><span style="color:#666">Qty: 1</span><br>$39.99</div></div>
          <table style="margin-top:18px;width:300px;margin-left:auto;font-size:14px">
          <tr><td>Subtotal</td><td align=right>$39.99</td></tr><tr><td>Shipping</td><td align=right>$0.00</td></tr>
          <tr><td>Tax</td><td align=right>$3.30</td></tr>
          <tr style="font-weight:700"><td style="padding-top:6px">Order Total</td><td align=right style="padding-top:6px">$43.29</td></tr></table>
          <div style="margin-top:16px;font-size:13px;color:#555">Ships to: Alex Example, 123 Example St, Springfield, CA 90000-0000</div></div></div>""",
    )


def amazon_cart() -> str:
    # Negative case: a shopping cart is not a purchase.
    return page(
        """<div style="background:#131921;color:#fff;padding:14px 28px;font:700 26px Arial">amazon<span style="color:#ff9900">.com</span></div>
        <div style="padding:22px 40px;width:860px"><div style="font-size:28px">Shopping Cart</div>
        <div style="display:flex;gap:16px;margin-top:18px"><div style="width:90px;height:90px;background:#cfd8dc"></div>
        <div><span style="color:#007185">Anker USB C Charger, 65W 3-Port Fast Wall Charger</span><br><span style="color:#007600;font-size:13px">In Stock</span><br>Qty: 1 &nbsp; Delete</div><div style="margin-left:auto"><b>$24.99</b></div></div>
        <div style="text-align:right;margin-top:20px;font-size:18px">Subtotal (1 item): <b>$24.99</b></div>
        <div style="text-align:right;margin-top:10px"><span style="background:#ffd814;border-radius:20px;padding:8px 28px">Proceed to checkout</span></div></div>""",
    )


def ebay_crop_mobile() -> str:
    css = """
    .wrap{padding:18px 16px;width:358px}
    .row{display:grid;grid-template-columns:96px 1fr;padding:9px 0;line-height:1.4;font-size:14px}
    .row .l{color:#707070}.row .v{font-weight:700}
    .item{display:flex;gap:12px;margin-top:16px;padding-top:16px;border-top:1px solid #e5e5e5;font-size:14px}
    .item .c{color:#707070;margin-top:4px}
    """
    return page(ebay_panel().replace("width:84px;height:84px", "width:64px;height:64px;flex:none"), css)


def ebay_no_total() -> str:
    # Crop that cuts off before the Total row: the total must come back empty, not derived.
    return page(
        f"""<div class="wrap">
    <div class="row"><div class="l">Get it</div><div class="v">Dec 2 - Dec 8</div></div>
    <div class="row"><div class="l">Shipping to</div><div class="v">{ADDR}</div></div>
    <div class="row"><div class="l">Order</div><div class="v">11-04417-62093</div></div>
    <div class="item">{THUMB}<div><div class="t">Vintage Pyrex Butterprint Turquoise 1.5 Qt Casserole Dish with Lid</div><div class="c">Pre-Owned</div></div></div>
    </div>""",
        EBAY_PANEL_CSS,
    )


def amazon_orders_list() -> str:
    return page(
        """<div style="background:#131921;color:#fff;padding:14px 28px;font:700 26px Arial">amazon<span style="color:#ff9900">.com</span></div>
        <div style="padding:20px 40px;width:900px"><div style="font-size:26px;margin-bottom:14px">Your Orders</div>
        <div style="border:1px solid #ddd;border-radius:8px">
        <div style="background:#f0f2f2;padding:12px 18px;display:flex;gap:60px;font-size:12px;color:#555;text-transform:uppercase">
          <div>Order placed<br><span style="font-size:14px;color:#111;text-transform:none">November 19, 2026</span></div>
          <div>Total<br><span style="font-size:14px;color:#111">$27.48</span></div>
          <div>Ship to<br><span style="font-size:14px;color:#007185;text-transform:none">Alex Example</span></div>
          <div style="margin-left:auto;text-align:right">Order # 113-5550123-7788991<br><span style="color:#007185;text-transform:none">View order details</span></div></div>
        <div style="padding:18px;display:flex;gap:16px"><div style="width:90px;height:90px;background:#c8e6c9"></div>
          <div><b>Delivered Nov 22</b><br><span style="color:#007185">Miracle-Gro Indoor Potting Mix, 8 Quarts</span><br><span style="font-size:13px;color:#555">Return window closes Dec 22, 2026</span></div></div></div>
</div>""",
    )


def amazon_mobile_dark() -> str:
    return page(
        """<div style="background:#0f1111;min-height:520px;color:#e6e6e6;padding:0">
        <div style="background:#1a1a1a;padding:12px 14px;font:700 20px Arial;color:#fff">amazon<span style="color:#ff9900">.com</span></div>
        <div style="padding:16px 14px"><div style="font-size:22px;font-weight:700">Order details</div>
        <div style="color:#9a9a9a;font-size:13px;margin:6px 0 14px">Ordered Nov 10, 2026<br>Order # 111-2223334-5556667</div>
        <div style="border:1px solid #333;border-radius:8px;padding:12px"><div style="font-weight:700;color:#4caf50">Delivered Nov 12</div>
        <div style="display:flex;gap:12px;margin-top:10px"><div style="width:64px;height:64px;background:#37474f;flex:none"></div>
        <div style="font-size:14px">Duracell Coppertop AA Batteries, 24 Count<br><b>$21.99</b></div></div></div>
        <div style="border:1px solid #333;border-radius:8px;padding:12px;margin-top:14px;font-size:14px"><b>Order Summary</b>
        <div style="display:flex;justify-content:space-between;margin-top:6px"><span>Items:</span><span>$21.99</span></div>
        <div style="display:flex;justify-content:space-between"><span>Tax:</span><span>$1.90</span></div>
        <div style="display:flex;justify-content:space-between;margin-top:6px;font-weight:700"><span>Grand Total:</span><span>$23.89</span></div></div></div></div>""",
    )


def walmart_mobile() -> str:
    return page(
        """<div style="background:#0071dc;color:#fff;padding:12px 14px;font:700 20px Arial">Walmart <span style="color:#ffc220">&#10033;</span></div>
        <div style="padding:16px 14px;font-size:14px"><div style="font-size:20px;font-weight:700">Thanks for your order</div>
        <div style="color:#555;margin-top:4px">Order# 2000123-456789 · Placed Nov 20, 2026</div>
        <div style="background:#e6f1fc;border-radius:8px;padding:10px;margin-top:12px"><b>Pickup</b> · Nov 21, 10 am - 12 pm</div>
        <div style="margin-top:14px;display:flex;justify-content:space-between"><span>Great Value Whole Milk, 1 gal</span><span>$3.98</span></div>
        <div style="display:flex;justify-content:space-between;margin-top:8px"><span>Bananas, 3 lb</span><span>$1.74</span></div>
        <div style="display:flex;justify-content:space-between;margin-top:8px"><span>Eggs, Large, 18 ct</span><span>$4.52</span></div>
        <div style="margin-top:14px;border-top:1px solid #ddd;padding-top:10px">
        <div style="display:flex;justify-content:space-between"><span>Subtotal</span><span>$10.24</span></div>
        <div style="display:flex;justify-content:space-between"><span>Taxes</span><span>$0.00</span></div>
        <div style="display:flex;justify-content:space-between;font-weight:700;margin-top:6px"><span>Total</span><span>$10.24</span></div></div></div>""",
    )


def doordash_mobile() -> str:
    return page(
        """<div style="padding:14px;border-bottom:1px solid #eee;font:700 20px Arial;color:#eb1700">DoorDash</div>
        <div style="padding:16px 14px;font-size:14px"><div style="font-size:20px;font-weight:700">Order receipt</div>
        <div style="color:#555;margin-top:4px">Chipotle Mexican Grill · Delivered Nov 17, 2026, 7:42 PM</div>
        <div style="margin-top:14px;display:flex;justify-content:space-between"><span>1 x Chicken Burrito Bowl</span><span>$11.25</span></div>
        <div style="margin-top:8px;display:flex;justify-content:space-between"><span>1 x Chips &amp; Guacamole</span><span>$5.35</span></div>
        <div style="margin-top:14px;border-top:1px solid #ddd;padding-top:10px;line-height:1.7">
        <div style="display:flex;justify-content:space-between"><span>Subtotal</span><span>$16.60</span></div>
        <div style="display:flex;justify-content:space-between"><span>Delivery Fee</span><span>$1.99</span></div>
        <div style="display:flex;justify-content:space-between"><span>Service Fee</span><span>$2.49</span></div>
        <div style="display:flex;justify-content:space-between"><span>Tax</span><span>$1.52</span></div>
        <div style="display:flex;justify-content:space-between"><span>Dasher Tip</span><span>$3.00</span></div>
        <div style="display:flex;justify-content:space-between;font-weight:700;margin-top:6px"><span>Total</span><span>$25.60</span></div></div></div>""",
    )


def ebay_crop_alt() -> str:
    # Held-out variant: different layout/wording, still no eBay branding.
    return page(
        """<div style="padding:26px 30px;width:700px;font-size:15px;line-height:1.5">
        <div style="font-size:20px;font-weight:700;margin-bottom:12px">Order details</div>
        <div style="display:flex;gap:16px;border:1px solid #ddd;border-radius:8px;padding:16px">
        <div style="width:90px;height:90px;background:#8d6e63;color:#fff;display:flex;align-items:center;justify-content:center;font:italic 14px Georgia,serif;text-align:center;flex:none">Pyrex<br>Bowl Set</div>
        <div><div style="font-size:16px">Vintage Pyrex Primary Colors Mixing Bowls Nesting Set of 4 (401-404)</div>
        <div style="color:#707070;margin-top:4px">Condition: Pre-Owned</div><div style="color:#707070">Qty: 1</div></div></div>
        <div style="margin-top:18px;display:grid;grid-template-columns:170px 1fr;row-gap:8px">
        <div style="color:#707070">Estimated delivery</div><div>Tue, Dec 2 - Fri, Dec 5</div>
        <div style="color:#707070">Order number</div><div>27-11034-55126</div>
        <div style="color:#707070">Item price</div><div>$54.00</div>
        <div style="color:#707070">Shipping</div><div>$14.95</div>
        <div style="color:#707070">Sales tax</div><div>$5.12</div>
        <div style="color:#707070;font-weight:700">Order total</div><div style="font-weight:700">$74.07</div>
        <div style="color:#707070">Paid with</div><div>Visa ending in 4242</div></div></div>""",
    )


# name -> (html, viewport width, device scale, full page)
FIXTURES = {
    "ebay_crop": (ebay_crop, 720, 2),
    "ebay_header": (ebay_header, 760, 2),
    "amazon_desktop": (amazon_desktop, 1000, 1.5),
    "amazon_mobile": (amazon_mobile, 390, 3),
    "etsy_desktop": (etsy_desktop, 900, 1.5),
    "etsy_mobile": (etsy_mobile, 390, 3),
    "target_desktop": (target_desktop, 960, 1.5),
    "target_mobile": (target_mobile, 390, 3),
    "bestbuy_email": (bestbuy_email, 820, 1.5),
    "ebay_crop_mobile": (ebay_crop_mobile, 390, 3),
    "ebay_crop_alt": (ebay_crop_alt, 760, 2),
    "ebay_no_total": (ebay_no_total, 720, 2),
    "amazon_orders_list": (amazon_orders_list, 1000, 1.5),
    "amazon_mobile_dark": (amazon_mobile_dark, 390, 3),
    "walmart_mobile": (walmart_mobile, 390, 3),
    "doordash_mobile": (doordash_mobile, 390, 3),
    "negative_amazon_cart": (amazon_cart, 960, 1.5),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chrome", default="/usr/bin/google-chrome")
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=args.chrome, args=["--no-sandbox"])
        for name, (fn, width, scale) in FIXTURES.items():
            ctx = browser.new_context(viewport={"width": width, "height": 400}, device_scale_factor=scale)
            pg = ctx.new_page()
            pg.set_content(fn())
            pg.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
            ctx.close()
            print("wrote", name)
        browser.close()


if __name__ == "__main__":
    main()
