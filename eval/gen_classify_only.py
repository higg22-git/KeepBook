"""Synthetic classify-only eval bucket (T65).

Renders a small set of classify-only sample documents (charitable donation
receipt, Form W-9 top page, consolidated brokerage statement) as pure-PIL
text-on-white images, in the same spirit as gen_forms.py's receipt/letter
generators (no blank IRS PDF exists for these). Each gets a labels.json entry
with `doc_type` + `classify_only: true` and NO fields — these documents are
classified + human-confirmed, never field-extracted (extract: false).

    python gen_classify_only.py

Deterministic (fixed content, no RNG) and idempotent: it MERGES its entries
into eval/labels.json rather than clobbering the hand-maintained file, and
re-rendering produces identical images.

STATUS: UNVERIFIED. The images render offline here, but the model has NOT been
run against this bucket yet (no Ollama/GPU in this lane). The GPU eval run that
scores classify accuracy on these samples is deferred to the orchestrator; the
bucket stays labeled UNVERIFIED until that run lands. See eval/CLASSIFY_ONLY.md.
"""

import json
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "testset")
LABELS_PATH = os.path.join(HERE, "labels.json")

INK = "black"
BLUE = (15, 15, 130)  # filled-in values, matching gen_forms.py's INK

os.makedirs(OUT_DIR, exist_ok=True)


def font(size, bold=False):
    paths = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
        if bold
        else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def mono(size):
    for p in [
        "/System/Library/Fonts/Supplemental/Courier New.ttf",
        "/System/Library/Fonts/Menlo.ttc",
    ]:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def gen_charitable_receipt():
    W, H = 850, 1050
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    y = 70
    d.text((60, y), "Cedar Hollow Community Foundation", font=font(24, True), fill=INK)
    y += 34
    d.text((60, y), "418 Birchwood Ave, Boise, ID 83702", font=font(14), fill=INK)
    y += 22
    d.text((60, y), "A registered 501(c)(3) nonprofit  ·  EIN 82-4471902", font=font(14), fill=INK)
    y += 50
    d.text((W / 2, y), "CHARITABLE CONTRIBUTION RECEIPT", font=font(19, True), fill=INK, anchor="mm")
    y += 46
    d.text((60, y), "Date: December 18, 2025", font=font(15), fill=INK)
    y += 40
    d.text((60, y), "Donor:", font=font(15, True), fill=INK)
    d.text((160, y), "Priya N. Sundaram", font=font(15), fill=BLUE)
    y += 28
    d.text((60, y), "Amount received:", font=font(15, True), fill=INK)
    d.text((260, y), "$1,500.00", font=font(15), fill=BLUE)
    y += 28
    d.text((60, y), "Contribution type:", font=font(15, True), fill=INK)
    d.text((260, y), "Cash (electronic transfer)", font=font(15), fill=BLUE)
    y += 50
    for line in [
        "Thank you for your generous gift. This letter serves as your official",
        "receipt for tax purposes. No goods or services were provided in exchange",
        "for this contribution. Please retain this acknowledgment with your tax",
        "records; it may support a charitable deduction on your federal return.",
    ]:
        d.text((60, y), line, font=font(15), fill=INK)
        y += 26
    y += 40
    d.text((60, y), "Authorized signature: M. Okafor, Executive Director", font=font(14), fill=INK)
    img.save(os.path.join(OUT_DIR, "charitable_receipt_01.png"))
    return "charitable_receipt_01.png", "charitable receipt"


def gen_w9():
    W, H = 900, 780
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([(20, 20), (W - 20, H - 20)], outline=INK, width=2)
    d.text((36, 34), "Form", font=font(15), fill=INK)
    d.text((36, 52), "W-9", font=font(40, True), fill=INK)
    d.text((150, 40), "Request for Taxpayer", font=font(22, True), fill=INK)
    d.text((150, 70), "Identification Number and Certification", font=font(20, True), fill=INK)
    d.text((W - 300, 40), "Give Form to the", font=font(13), fill=INK)
    d.text((W - 300, 58), "requester. Do not", font=font(13), fill=INK)
    d.text((W - 300, 76), "send to the IRS.", font=font(13), fill=INK)
    d.line([(30, 110), (W - 30, 110)], fill=INK, width=1)

    y = 130
    d.text((40, y), "1  Name (as shown on your income tax return)", font=font(13), fill=INK)
    y += 20
    d.text((48, y), "Desmond L. Fitzgerald", font=font(16), fill=BLUE)
    d.line([(40, y + 24), (W - 40, y + 24)], fill=INK, width=1)
    y += 44
    d.text((40, y), "2  Business name/disregarded entity name, if different from above", font=font(13), fill=INK)
    y += 20
    d.text((48, y), "Fitzgerald Consulting LLC", font=font(16), fill=BLUE)
    d.line([(40, y + 24), (W - 40, y + 24)], fill=INK, width=1)
    y += 44
    d.text((40, y), "3  Federal tax classification:  [X] Individual/sole proprietor   "
                    "[ ] C Corp   [ ] S Corp   [ ] Partnership", font=font(13), fill=INK)
    y += 40
    d.text((40, y), "5  Address (number, street, and apt. or suite no.)", font=font(13), fill=INK)
    y += 20
    d.text((48, y), "3421 Sycamore Ln, Reno, NV 89501", font=font(16), fill=BLUE)
    d.line([(40, y + 24), (W - 40, y + 24)], fill=INK, width=1)
    y += 54
    d.text((40, y), "Part I   Taxpayer Identification Number (TIN)", font=font(15, True), fill=INK)
    y += 26
    d.text((40, y), "Social security number:", font=font(14), fill=INK)
    d.text((260, y), "4 9 1 - 0 2 - 3 5 4 5", font=mono(18), fill=BLUE)
    img.save(os.path.join(OUT_DIR, "w9_01.png"))
    return "w9_01.png", "W-9"


def gen_brokerage_statement():
    W, H = 850, 1050
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    y = 60
    d.text((60, y), "Harborview Securities LLC", font=font(24, True), fill=INK)
    y += 34
    d.text((60, y), "Member FINRA / SIPC", font=font(14), fill=INK)
    y += 44
    d.text((W / 2, y), "2025 Consolidated Brokerage Statement", font=font(19, True), fill=INK, anchor="mm")
    y += 30
    d.text((W / 2, y), "Form 1099 Composite  ·  Tax Reporting Statement", font=font(14), fill=INK, anchor="mm")
    y += 46
    d.text((60, y), "Account holder:", font=font(14, True), fill=INK)
    d.text((230, y), "Ingrid P. Kowalski", font=font(14), fill=BLUE)
    y += 26
    d.text((60, y), "Account number:", font=font(14, True), fill=INK)
    d.text((230, y), "****-7731", font=font(14), fill=BLUE)
    y += 40
    d.line([(50, y), (W - 50, y)], fill=INK, width=2)
    y += 16
    d.text((60, y), "Summary of reportable tax information", font=font(15, True), fill=INK)
    y += 34
    rows = [
        ("1099-DIV   Total ordinary dividends (Box 1a)", "$3,204.88"),
        ("1099-DIV   Qualified dividends (Box 1b)", "$2,715.40"),
        ("1099-B     Proceeds from sales (covered)", "$41,905.22"),
        ("1099-B     Realized gain/(loss)", "$5,118.67"),
        ("1099-INT   Interest income (Box 1)", "$612.35"),
    ]
    for label, val in rows:
        d.text((70, y), label, font=mono(14), fill=INK)
        d.text((W - 70, y), val, font=mono(14), fill=BLUE, anchor="ra")
        y += 30
    y += 10
    d.line([(50, y), (W - 50, y)], fill=INK, width=1)
    y += 20
    for line in [
        "This consolidated statement combines all Forms 1099 issued for this",
        "account. Retain it for preparation of your federal and state returns.",
    ]:
        d.text((60, y), line, font=font(13), fill=INK)
        y += 22
    img.save(os.path.join(OUT_DIR, "brokerage_stmt_01.png"))
    return "brokerage_stmt_01.png", "brokerage statement"


def main():
    generators = [gen_charitable_receipt, gen_w9, gen_brokerage_statement]
    new_entries = {}
    for gen in generators:
        fname, doc_type = gen()
        new_entries[fname] = {"doc_type": doc_type, "classify_only": True, "fields": {}}

    # MERGE into labels.json (do not clobber the hand-maintained file).
    labels = {}
    if os.path.exists(LABELS_PATH):
        with open(LABELS_PATH, "r", encoding="utf-8") as fh:
            labels = json.load(fh)
    labels.update(new_entries)
    with open(LABELS_PATH, "w", encoding="utf-8") as fh:
        json.dump(labels, fh, indent=1, sort_keys=False)

    print(f"Wrote {len(new_entries)} classify-only samples to {OUT_DIR}")
    for k, v in new_entries.items():
        print(f"  {k}  ->  {v['doc_type']}  (classify_only, UNVERIFIED)")
    print(f"Merged labels into {LABELS_PATH}")


if __name__ == "__main__":
    main()
