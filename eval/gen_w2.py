from PIL import Image, ImageDraw, ImageFont
import random

W, H = 1000, 720
img = Image.new("RGB", (W, H), "white")
d = ImageDraw.Draw(img)

def font(sz, bold=False):
    paths = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for p in paths:
        try: return ImageFont.truetype(p, sz)
        except: continue
    return ImageFont.load_default()

f_sm = font(15); f_md = font(19); f_lg = font(30, True); f_box = font(13)

# Title block
d.text((30, 20), "Form W-2  Wage and Tax Statement", font=f_lg, fill="black")
d.text((30, 60), "2025   Department of the Treasury - Internal Revenue Service", font=f_sm, fill="black")

# Employee / employer
d.rectangle([30, 100, 480, 180], outline="black", width=2)
d.text((40, 105), "a Employee's SSN", font=f_box, fill="gray")
d.text((40, 130), "412-55-9083", font=f_md, fill="black")
d.text((40, 150), "b EIN  84-2210091", font=f_box, fill="black")

d.rectangle([30, 190, 480, 300], outline="black", width=2)
d.text((40, 195), "c Employer name, address", font=f_box, fill="gray")
d.text((40, 220), "Cascade Logistics LLC", font=f_md, fill="black")
d.text((40, 248), "1420 Industrial Pkwy", font=f_sm, fill="black")
d.text((40, 270), "Provo, UT 84604", font=f_sm, fill="black")

d.rectangle([30, 310, 480, 420], outline="black", width=2)
d.text((40, 315), "e Employee name", font=f_box, fill="gray")
d.text((40, 340), "Marcus D. Whitfield", font=f_md, fill="black")
d.text((40, 368), "88 Cedar Hollow Rd", font=f_sm, fill="black")
d.text((40, 390), "Orem, UT 84058", font=f_sm, fill="black")

# Numbered boxes (right column)
boxes = [
    ("1 Wages, tips, other comp.", "68,420.15"),
    ("2 Federal income tax withheld", "9,183.44"),
    ("3 Social security wages", "70,110.00"),
    ("4 Social security tax withheld", "4,346.82"),
    ("5 Medicare wages and tips", "70,110.00"),
    ("6 Medicare tax withheld", "1,016.60"),
    ("15 State  UT", "16 State wages 68,420.15"),
    ("17 State income tax", "3,214.09"),
]
x0 = 510; y = 100
for label, val in boxes:
    d.rectangle([x0, y, 970, y+58], outline="black", width=1)
    d.text((x0+8, y+5), label, font=f_box, fill="gray")
    d.text((x0+8, y+28), val, font=f_md, fill="black")
    y += 66

img = img.rotate(-1.4, expand=True, fillcolor="white")
# mild noise / brightness to mimic phone capture
img.save("w2_test.png")
print("saved w2_test.png", img.size)
