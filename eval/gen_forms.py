"""Synthetic labeled tax-document test set, per docs/EVAL.md.

Approach: download official BLANK IRS form PDFs (public domain US
government works, see eval/blank_forms/) and overlay fake data at
measured coordinates using PyMuPDF (render) + PIL (draw). Every form
type below used the overlay path -- none needed the pure-PIL fallback.

Deterministic: one seeded random.Random consumed in a fixed order, so
re-running this script produces identical images and an identical
labels.json every time.

Each doc is written (image + labels.json entry) in the same loop
iteration, so labels can never drift from images.
"""

import json
import os
import random

import fitz  # pymupdf
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
BLANK_DIR = os.path.join(HERE, "blank_forms")
OUT_DIR = os.path.join(HERE, "testset")
LABELS_PATH = os.path.join(HERE, "labels.json")

SEED = 20260718
DPI = 200
ZOOM = DPI / 72.0
INK = (15, 15, 130)  # dark blue -- distinguishes filled-in values from preprinted black form text

os.makedirs(OUT_DIR, exist_ok=True)

labels = {}

# --------------------------------------------------------------------- fonts

def font(size, bold=False):
    paths = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def mono_font(size):
    for p in ["/System/Library/Fonts/Supplemental/Courier New.ttf", "/System/Library/Fonts/Menlo.ttc"]:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


# ---------------------------------------------------------------- fake data

FIRST_NAMES = [
    "Marcus", "Priya", "Tobias", "Leilani", "Dominic", "Nadia", "Ezra", "Simone",
    "Callum", "Ingrid", "Rashid", "Fiona", "Desmond", "Yara", "Gunnar", "Bianca",
]
LAST_NAMES = [
    "Whitfield", "Sundaram", "Okafor", "Marchetti", "Halvorsen", "Delacroix",
    "Bergstrom", "Nakamura", "Fitzgerald", "Kowalski", "Abernathy", "Novak",
]
COMPANY_ROOTS = [
    "Cascade Logistics", "Blue Ridge Analytics", "Ironwood Manufacturing",
    "Sable Point Consulting", "Redstone Freight", "Harborline Media",
    "Granite Peak Builders", "Coppervale Software", "Thistledown Farms",
    "Meridian Data Systems",
]
COMPANY_SUFFIXES = ["LLC", "Inc.", "LLP", "Co."]
BANK_ROOTS = [
    "Union Trust", "Cascade Federal", "Prairie State", "Harborview",
    "First Meridian", "Copperline",
]
STREET_NAMES = [
    "Industrial Pkwy", "Cedar Hollow Rd", "Birchwood Ave", "Sycamore Ln",
    "Fremont St", "Highland Dr", "Bellview Ct", "Winslow Ave", "Alder St",
    "Ridgemont Dr",
]
CITIES = [
    ("Provo", "UT", "84604"), ("Orem", "UT", "84058"), ("Boise", "ID", "83702"),
    ("Reno", "NV", "89501"), ("Spokane", "WA", "99201"), ("Fresno", "CA", "93701"),
    ("Tulsa", "OK", "74103"), ("Omaha", "NE", "68102"), ("Boulder", "CO", "80301"),
    ("Eugene", "OR", "97401"),
]

rng = random.Random(SEED)


def fake_person():
    return f"{rng.choice(FIRST_NAMES)} {rng.choice('ABCDEFGHJKLMNPRST')}. {rng.choice(LAST_NAMES)}"


def fake_company():
    return f"{rng.choice(COMPANY_ROOTS)} {rng.choice(COMPANY_SUFFIXES)}"


def fake_bank():
    return f"{rng.choice(BANK_ROOTS)} Bank"


def fake_address():
    city, state, zipc = rng.choice(CITIES)
    return f"{rng.randint(10, 9899)} {rng.choice(STREET_NAMES)}", f"{city}, {state} {zipc}"


def fake_ssn():
    return f"4{rng.randint(0, 99):02d}-{rng.randint(1, 99):02d}-{rng.randint(1, 9999):04d}"


def fake_ein():
    return f"{rng.randint(10, 99)}-{rng.randint(1000000, 9999999)}"


def fake_tin():
    return fake_ssn() if rng.random() < 0.5 else fake_ein()


def money_label(v):
    """Value as stored in labels.json: no $, no commas."""
    return f"{v:.2f}"


def money_display(v):
    """Value as rendered on the form image: comma-grouped."""
    return f"{v:,.2f}"


def fake_money(lo, hi):
    return round(rng.uniform(lo, hi), 2)


# ------------------------------------------------------------------ overlay

def open_page(pdf_name, page_idx):
    doc = fitz.open(os.path.join(BLANK_DIR, pdf_name))
    return doc, doc[page_idx]


def render(doc, page, draws, out_path):
    """draws: list of (x_pt, y_pt, text, size, bold) in PDF-point space."""
    pix = page.get_pixmap(dpi=DPI, colorspace=fitz.csRGB, alpha=False)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    d = ImageDraw.Draw(img)
    for x_pt, y_pt, text, size, bold in draws:
        d.text((x_pt * ZOOM, y_pt * ZOOM), text, font=font(size, bold), fill=INK)
    img.save(out_path)
    doc.close()


# ============================================================== W-2 (fw2.pdf)

def gen_w2(n):
    doc, page = open_page("fw2.pdf", 2)  # Copy 1 - clean black-ink page
    name = fake_person()
    ssn = fake_ssn()
    employer = fake_company()
    ein = fake_ein()
    emp_addr1, emp_addr2 = fake_address()
    ee_addr1, ee_addr2 = fake_address()
    wages = fake_money(28000, 145000)
    fed_wh = round(wages * rng.uniform(0.09, 0.19), 2)
    ss_wages = round(wages + rng.uniform(0, 2500), 2)
    ss_wh = round(ss_wages * 0.062, 2)
    medicare_wh = round(ss_wages * 0.0145, 2)

    draws = [
        (45, 50, ssn, 15, False),
        (45, 74, f"EIN {ein}", 13, False),
        (45, 99, employer, 15, False),
        (45, 120, emp_addr1, 13, False),
        (45, 141, emp_addr2, 13, False),
        (45, 196, name, 15, False),
        (45, 222, ee_addr1, 13, False),
        (45, 244, ee_addr2, 13, False),
        (344, 74, money_display(wages), 15, False),
        (467, 74, money_display(fed_wh), 15, False),
        (344, 99, money_display(ss_wages), 13, False),
        (467, 99, money_display(ss_wh), 13, False),
        (344, 122, money_display(ss_wages), 13, False),
        (467, 122, money_display(medicare_wh), 13, False),
    ]
    fname = f"w2_clean_{n:02d}.png"
    render(doc, page, draws, os.path.join(OUT_DIR, fname))
    labels[fname] = {
        "doc_type": "W-2",
        "fields": {
            "employee_name": name,
            "ssn": ssn,
            "employer": employer,
            "box1_wages": money_label(wages),
            "box2_fed_withheld": money_label(fed_wh),
        },
    }


# ==================================================== 1099-NEC (f1099nec.pdf)

def gen_1099nec(n):
    doc, page = open_page("f1099nec.pdf", 2)  # Copy 1 - clean black-ink page
    payer = fake_company()
    payer_addr1, payer_addr2 = fake_address()
    recipient = fake_person()
    recipient_addr1, recipient_addr2 = fake_address()
    payer_tin = fake_ein()
    recipient_tin = fake_tin()
    comp = fake_money(1500, 62000)

    draws = [
        (56, 52, payer, 13, False),
        (56, 64, payer_addr1 + ", " + payer_addr2, 10, False),
        (56, 160, payer_tin, 12, False),
        (180, 160, recipient_tin, 12, False),
        (58, 197, recipient, 13, False),
        (58, 210, recipient_addr1 + ", " + recipient_addr2, 10, False),
        (312, 133, money_display(comp), 14, False),
    ]
    fname = f"1099nec_clean_{n:02d}.png"
    render(doc, page, draws, os.path.join(OUT_DIR, fname))
    labels[fname] = {
        "doc_type": "1099-NEC",
        "fields": {
            "recipient_name": recipient,
            "recipient_tin": recipient_tin,
            "payer": payer,
            "box1_nonemployee_comp": money_label(comp),
        },
    }


# ==================================================== 1099-INT (f1099int.pdf)

def gen_1099int(n):
    doc, page = open_page("f1099int.pdf", 2)  # Copy 1 - clean black-ink page
    payer = fake_bank()
    payer_addr1, payer_addr2 = fake_address()
    recipient = fake_person()
    recipient_addr1, recipient_addr2 = fake_address()
    interest = fake_money(15, 8200)

    draws = [
        (56, 55, payer, 13, False),
        (56, 68, payer_addr1 + ", " + payer_addr2, 10, False),
        (58, 198, recipient, 13, False),
        (58, 211, recipient_addr1 + ", " + recipient_addr2, 10, False),
        (308, 97, money_display(interest), 14, False),
    ]
    fname = f"1099int_clean_{n:02d}.png"
    render(doc, page, draws, os.path.join(OUT_DIR, fname))
    labels[fname] = {
        "doc_type": "1099-INT",
        "fields": {
            "recipient_name": recipient,
            "payer": payer,
            "box1_interest_income": money_label(interest),
        },
    }


# =========================================================== 1098 (f1098.pdf)

def gen_1098(n):
    doc, page = open_page("f1098.pdf", 2)  # Copy B - clean black-ink page
    lender = fake_bank()
    lender_addr1, lender_addr2 = fake_address()
    borrower = fake_person()
    borrower_addr1, borrower_addr2 = fake_address()
    interest = fake_money(2200, 24500)

    draws = [
        (56, 55, lender, 13, False),
        (56, 68, lender_addr1 + ", " + lender_addr2, 10, False),
        (58, 198, borrower, 13, False),
        (58, 211, borrower_addr1 + ", " + borrower_addr2, 10, False),
        (310, 121, money_display(interest), 13, False),
    ]
    fname = f"1098_clean_{n:02d}.png"
    render(doc, page, draws, os.path.join(OUT_DIR, fname))
    labels[fname] = {
        "doc_type": "1098",
        "fields": {
            "borrower_name": borrower,
            "lender": lender,
            "box1_mortgage_interest": money_label(interest),
        },
    }


# =========================================================== K-1 (f1065sk1.pdf)

def gen_k1(n):
    doc, page = open_page("f1065sk1.pdf", 0)  # single page, already clean black ink
    partnership = fake_company()
    part_addr1, part_addr2 = fake_address()
    ein = fake_ein()
    partner = fake_person()
    partner_addr1, partner_addr2 = fake_address()
    income = fake_money(-8000, 210000)

    draws = [
        (60, 175, ein, 11, False),
        (60, 200, partnership, 11, False),
        (60, 214, part_addr1 + ", " + part_addr2, 9, False),
        (60, 310, partner, 11, False),
        (60, 324, partner_addr1 + ", " + partner_addr2, 9, False),
        (337, 88, money_display(income), 9, False),
    ]
    fname = f"k1_clean_{n:02d}.png"
    render(doc, page, draws, os.path.join(OUT_DIR, fname))
    labels[fname] = {
        "doc_type": "K-1",
        "fields": {
            "partner_name": partner,
            "partnership_name": partnership,
            "partnership_ein": ein,
            "ordinary_income": money_label(income),
        },
    }


# ================================================== UNRECOGNIZED: receipt/letter

STORE_NAMES = ["Willow Market", "Trailhead Outfitters", "Copper Kettle Cafe"]
ITEM_POOL = [
    ("ORGANIC BANANAS", 2.49), ("WHOLE MILK 1GAL", 3.79), ("SOURDOUGH LOAF", 4.99),
    ("FREE RANGE EGGS", 5.49), ("CHEDDAR BLOCK 8OZ", 4.29), ("ROAST COFFEE 12OZ", 9.99),
    ("PAPER TOWELS 6PK", 11.49), ("HAND SOAP REFILL", 3.99), ("GRANOLA BARS 12CT", 6.29),
    ("SPARKLING WATER 8PK", 5.99),
]


def gen_receipt(n):
    store = rng.choice(STORE_NAMES)
    addr1, addr2 = fake_address()
    n_items = rng.randint(4, 7)
    items = rng.sample(ITEM_POOL, n_items)
    subtotal = round(sum(p for _, p in items), 2)
    tax = round(subtotal * 0.0725, 2)
    total = round(subtotal + tax, 2)
    date_str = f"{rng.randint(1,12):02d}/{rng.randint(1,28):02d}/2026  {rng.randint(9,20):02d}:{rng.randint(0,59):02d}"

    W, H = 620, 1400
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    f_hdr = mono_font(24)
    f_body = mono_font(16)
    y = 40
    d.text((W / 2, y), store, font=f_hdr, fill="black", anchor="mm")
    y += 40
    d.text((W / 2, y), addr1, font=f_body, fill="black", anchor="mm")
    y += 22
    d.text((W / 2, y), addr2, font=f_body, fill="black", anchor="mm")
    y += 22
    d.text((W / 2, y), f"REGISTER 03  CASHIER: JT", font=f_body, fill="black", anchor="mm")
    y += 22
    d.text((W / 2, y), date_str, font=f_body, fill="black", anchor="mm")
    y += 30
    d.line([(30, y), (W - 30, y)], fill="black", width=2)
    y += 20
    for label, price in items:
        d.text((30, y), label, font=f_body, fill="black")
        d.text((W - 30, y), f"{price:>6.2f}", font=f_body, fill="black", anchor="ra")
        y += 26
    y += 8
    d.line([(30, y), (W - 30, y)], fill="black", width=2)
    y += 20
    for label, val in [("SUBTOTAL", subtotal), ("TAX", tax), ("TOTAL", total)]:
        d.text((30, y), label, font=f_body, fill="black")
        d.text((W - 30, y), f"{val:>6.2f}", font=f_body, fill="black", anchor="ra")
        y += 26
    y += 20
    d.text((W / 2, y), "VISA ****4471", font=f_body, fill="black", anchor="mm")
    y += 40
    d.text((W / 2, y), "THANK YOU FOR SHOPPING WITH US", font=f_body, fill="black", anchor="mm")
    y += 22
    d.text((W / 2, y), "RETURNS WITHIN 30 DAYS WITH RECEIPT", font=f_body, fill="black", anchor="mm")

    fname = "receipt_01.png"
    img.save(os.path.join(OUT_DIR, fname))
    labels[fname] = {"doc_type": "UNRECOGNIZED", "fields": {}}


LETTER_SENDERS = [
    ("Ridgeline Property Management", "220 Fremont St, Suite 400", "Boise, ID 83702"),
]


def gen_letter(n):
    sender_name, sender_addr1, sender_addr2 = LETTER_SENDERS[0]
    recipient = fake_person()
    recipient_addr1, recipient_addr2 = fake_address()
    date_str = "April 6, 2026"

    W, H = 850, 1100
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    f_hdr = font(22, True)
    f_body = font(15)

    y = 60
    d.text((60, y), sender_name, font=f_hdr, fill="black")
    y += 30
    d.text((60, y), sender_addr1, font=f_body, fill="black")
    y += 20
    d.text((60, y), sender_addr2, font=f_body, fill="black")
    y += 50
    d.text((60, y), date_str, font=f_body, fill="black")
    y += 40
    d.text((60, y), recipient, font=f_body, fill="black")
    y += 20
    d.text((60, y), recipient_addr1, font=f_body, fill="black")
    y += 20
    d.text((60, y), recipient_addr2, font=f_body, fill="black")
    y += 45
    d.text((60, y), f"Dear {recipient.split()[0]},", font=f_body, fill="black")
    y += 35

    body = [
        "Thank you for being a valued tenant at Ridgeline Property Management.",
        "This letter is to confirm that your lease renewal has been processed",
        "and no changes to your monthly rent will take effect this term.",
        "",
        "Please review the enclosed renewal summary and let our office know",
        "if you have any questions before the start of the new lease period.",
        "",
        "We appreciate your continued residency and look forward to another",
        "great year.",
    ]
    for line in body:
        d.text((60, y), line, font=f_body, fill="black")
        y += 24

    y += 30
    d.text((60, y), "Sincerely,", font=f_body, fill="black")
    y += 50
    d.text((60, y), "Marta Lindqvist", font=f_body, fill="black")
    y += 20
    d.text((60, y), "Property Manager", font=f_body, fill="black")

    fname = "letter_01.png"
    img.save(os.path.join(OUT_DIR, fname))
    labels[fname] = {"doc_type": "UNRECOGNIZED", "fields": {}}


# ============================================================================

def main():
    for i in range(1, 4):
        gen_w2(i)
    for i in range(1, 4):
        gen_1099nec(i)
    for i in range(1, 3):
        gen_1099int(i)
    for i in range(1, 3):
        gen_1098(i)
    for i in range(1, 3):
        gen_k1(i)
    gen_receipt(1)
    gen_letter(1)

    with open(LABELS_PATH, "w") as f:
        json.dump(labels, f, indent=2)

    print(f"Wrote {len(labels)} labeled docs to {OUT_DIR}")
    print(f"Labels: {LABELS_PATH}")


if __name__ == "__main__":
    main()
