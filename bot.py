import os
import re
import json
import random
import asyncio
import hashlib
import shutil
import tempfile
from pathlib import Path
from urllib.parse import quote

import requests
import edge_tts
import arabic_reshaper
from google import genai
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageOps
from moviepy.editor import (
    ImageClip,
    AudioFileClip,
    CompositeAudioClip,
    concatenate_videoclips,
    afx,
)

GOOGLE_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
CUSTOM_TOPIC = os.environ.get("CUSTOM_TOPIC", "").strip()

client = genai.Client(api_key=GOOGLE_API_KEY)
MODEL = "gemini-3.5-flash-lite"

TRENDING_TOPICS = [
    "کمبود داروهای حیاتی در داروخانه‌های ایران و راه‌های مدیریت آن",
    "متفورمین و کاربردهای جدید آن فراتر از دیابت",
    "مکمل‌های ویتامین D و اشتباهات رایج مصرف در ایران",
    "داروهای ضدالتهاب NSAID و عوارض گوارشی آن‌ها",
    "انسولین‌ها و نکات مهم نگهداری و تزریق برای بیماران",
    "آنتی‌بیوتیک‌ها و مقاومت میکروبی؛ هشدار به بیماران",
    "داروهای فشار خون و تداخلات مهم غذایی",
    "کپسول امگا۳ و واقعیت‌های علمی پشت تبلیغات",
    "داروهای ضد افسردگی و زمان شروع اثر واقعی",
    "شربت‌های سرماخوردگی کودکان و هشدارهای مصرف",
]

WIDTH, HEIGHT = 1080, 1920
MIN_SLIDE_DUR = 3.5
MAX_SLIDE_DUR = 14.0
HEADERS = {
    "User-Agent": "PharmaAgent/3.0 (educational; https://github.com/hamidrezamasoudian-netizen/pharma-agent)",
    "Accept": "image/*,*/*;q=0.8",
}

USED_URLS = set()
USED_HASHES = set()
CURRENT_TOPIC = ""
ACTIVE_CATEGORY = "tablets"
SUCCESSFUL_BGS = []

PRONUNCIATION_MAP = [
    (r"منیزیوم", "مَگ‌نِ‌زیوم"),
    (r"منیزیم", "مَگ‌نِ‌زیوم"),
    (r"magnesium", "مَگ‌نِ‌زیوم"),
    (r"مَگنزیوم", "مَگ‌نِ‌زیوم"),
    (r"مگ‌نیزیوم", "مَگ‌نِ‌زیوم"),
    (r"کلسیم", "کَل‌سی‌یوم"),
    (r"calcium", "کَل‌سی‌یوم"),
    (r"زینک", "زینک"),
    (r"zinc", "زینک"),
    (r"آهن", "آ‌هَن"),
    (r"فولیک", "فولیک"),
    (r"متفورمین", "مت‌فور‌مین"),
    (r"مت فورمین", "مت‌فور‌مین"),
    (r"metformin", "مت‌فور‌مین"),
    (r"گلوکوفاژ", "گلوکو‌فاژ"),
    (r"انسولین", "اِن‌سو‌لین"),
    (r"insulin", "اِن‌سو‌لین"),
    (r"ویتامین\s*D\b", "ویتامین دی"),
    (r"ویتامین\s*d\b", "ویتامین دی"),
    (r"ویتامین\s*دی", "ویتامین دی"),
    (r"vitamin\s*d\b", "ویتامین دی"),
    (r"امگا\s*۳", "اُمگا سه"),
    (r"امگا\s*3", "اُمگا سه"),
    (r"omega\s*3", "اُمگا سه"),
    (r"آموکسی‌سیلین", "آموکسی‌سی‌لین"),
    (r"آموکسی سیلین", "آموکسی‌سی‌لین"),
    (r"amoxicillin", "آموکسی‌سی‌لین"),
    (r"آنتی‌بیوتیک", "آنتی‌بیوتیک"),
    (r"آنتی بیوتیک", "آنتی‌بیوتیک"),
    (r"NSAID", "اِن‌سِید"),
    (r"ایبوپروفن", "ایبو‌پروفن"),
    (r"استامینوفن", "اِستامینوفن"),
    (r"لوزارتان", "لوزار‌تان"),
    (r"آملودیپین", "آملو‌دیپین"),
    (r"آتورواستاتین", "آتو‌روا‌استاتین"),
    (r"وارفارین", "وارفارین"),
    (r"کلونازپام", "کلونا‌زپام"),
    (r"اُزِمپیک", "اُزِمپیک"),
    (r"Ozempic", "اُزِمپیک"),
    (r"سماگلوتاید", "سِما‌گلو‌تاید"),
    (r"semaglutide", "سِما‌گلو‌تاید"),
    (r"لیراگلوتاید", "لیرا‌گلو‌تاید"),
    (r"پرل", "پِرل"),
    (r"۵۰\s*هزار", "پنجاه هزار"),
    (r"50\s*هزار", "پنجاه هزار"),
    (r"میلی‌گرم", "میلی‌گرم"),
    (r"mg\b", "میلی‌گرم"),
    (r"IU\b", "آی‌یو"),
]


def wiki(name: str, width: int = 1280) -> str:
    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{quote(name)}?width={width}"


IMAGE_POOL = {
    "metformin": [wiki("Metformin 500mg Tablets.jpg")],
    "insulin": [
        wiki("Insulin syringe foto.jpg"),
        wiki("Insulin syringe in disassembled form.jpg"),
        wiki("Baxa syringe.jpg"),
    ],
    "injection": [
        wiki("Dantrolene Ampoule.JPG"),
        wiki("Diazepam Ampulle ratiopharm 10 mg. 2 ml.JPG"),
        wiki("Ampoule, iodine (AM 1999.114.3-1).jpg"),
        wiki("Insulin syringe foto.jpg"),
        wiki("Baxa syringe.jpg"),
    ],
    "tablets": [
        wiki("Metformin 500mg Tablets.jpg"),
        wiki("Robenacoxib blister package.jpg"),
        wiki("Anterone (cyproterone acetate) tablets in Australia, with three blister packs.jpg"),
        wiki("Medicine Health.jpg"),
    ],
    "capsules": [wiki("Medicine Health.jpg"), wiki("Robenacoxib blister package.jpg")],
    "vitamin": [wiki("Medicine Health.jpg"), wiki("Robenacoxib blister package.jpg")],
    "antibiotic": [wiki("Robenacoxib blister package.jpg"), wiki("Medicine Health.jpg")],
    "blood_pressure": [
        wiki("Sphygmomanometer&Cuff.JPG"),
        wiki("2017 Sfigmomanometr elektroniczny.jpg"),
        wiki("2020 Sfigmomanometr elektroniczny.jpg"),
    ],
    "syrup": [
        wiki("Cough medicine.jpg"),
        wiki("Cough mixture (17050264752).jpg"),
        wiki("Dynatussin Syrup cough medicine4.jpg"),
        wiki("Sirop toux.jpg"),
    ],
    "pharmacy": [
        wiki("Medicine Health.jpg"),
        wiki("Robenacoxib blister package.jpg"),
        wiki("Metformin 500mg Tablets.jpg"),
        wiki("Insulin syringe foto.jpg"),
    ],
}

SOFT_MUSIC_URLS = [
    "https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf07a.mp3?filename=empty-mind-118973.mp3",
    "https://cdn.pixabay.com/download/audio/2021/11/25/audio_9174bd675d.mp3?filename=soft-piano-ambient-114064.mp3",
]


def get_topic() -> str:
    global CURRENT_TOPIC
    if CUSTOM_TOPIC:
        print(f"موضوع دستی: {CUSTOM_TOPIC}")
        CURRENT_TOPIC = CUSTOM_TOPIC
        return CUSTOM_TOPIC
    topic = random.choice(TRENDING_TOPICS)
    print(f"موضوع روز: {topic}")
    CURRENT_TOPIC = topic
    return topic


def generate_content_package(topic: str) -> dict:
    prompt = f"""
تو استراتژیست محتوای تخصصی داروسازی برای اینستاگرام و یوتیوب‌شورت در ایران هستی.
موضوع: «{topic}»

فقط JSON معتبر برگردان:
{{
  "caption": "کپشن کامل پست (۳ تا ۵ پاراگراف علمی و جذاب)",
  "hashtags": "۱۲ هشتگ فارسی و انگلیسی",
  "story_text": "متن کوتاه استوری حداکثر ۲ خط",
  "cover_hook": "یک جمله خیلی جذاب برای فریم اول (حداکثر ۱۲ کلمه)",
  "drug_name": "نام اصلی دارو به انگلیسی کوچک",
  "image_category": "دقیقا یکی از: metformin|insulin|injection|tablets|capsules|vitamin|antibiotic|blood_pressure|syrup|pharmacy",
  "slides": [
    {{"title": "عنوان کاور", "body": "جمله کوتاه", "narration": "جمله افتتاحیه"}},
    {{"title": "عنوان ۲", "body": "حداکثر ۱۸ کلمه", "narration": "گفتاری طبیعی"}},
    {{"title": "عنوان ۳", "body": "حداکثر ۱۸ کلمه", "narration": "گفتاری طبیعی"}},
    {{"title": "عنوان ۴", "body": "حداکثر ۱۸ کلمه", "narration": "گفتاری طبیعی"}},
    {{"title": "جمع‌بندی", "body": "نتیجه کوتاه", "narration": "جمع‌بندی گرم"}}
  ]
}}
قوانین املا (خیلی مهم):
- title و body و caption و cover_hook و story_text فقط املای استاندارد فارسی: منیزیم، کلسیم، متفورمین، انسولین
- هرگز در متن روی تصویر ننویس: مگ‌نیزیوم، کَل‌سی‌یوم، مت‌فور‌مین
- narration را هم با همان املای استاندارد بنویس؛ تلفظ صدا جداگانه اصلاح می‌شود
فقط JSON.
"""
    response = client.models.generate_content(model=MODEL, contents=prompt)
    text = response.text.strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("JSON معتبر دریافت نشد")
    return json.loads(match.group())


def fa(text: str) -> str:
    if not text:
        return ""
    return arabic_reshaper.reshape(str(text))


def load_font(size: int, bold: bool = False):
    base = Path("fonts")
    candidates = []
    if bold:
        candidates.append(base / "Vazirmatn-Bold.ttf")
    candidates += [
        base / "Vazirmatn-Regular.ttf",
        Path("/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for p in candidates:
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size)
            except Exception:
                continue
    return ImageFont.load_default()


def wrap_fa(text: str, font, max_width: int, draw) -> list:
    words = str(text).split()
    lines, current = [], ""
    for w in words:
        test = (current + " " + w).strip()
        bbox = draw.textbbox((0, 0), fa(test), font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines or [str(text)]


def file_hash(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def download_image(url: str, path: str) -> bool:
    if not url:
        return False
    try:
        r = requests.get(url, timeout=50, headers=HEADERS, allow_redirects=True)
        if r.status_code != 200 or len(r.content) < 3000:
            print(f"ناموفق {r.status_code} {url[:80]}")
            return False
        ctype = r.headers.get("Content-Type", "").lower()
        if "html" in ctype or "json" in ctype:
            return False
        with open(path, "wb") as f:
            f.write(r.content)
        with Image.open(path) as im:
            im.load()
            if im.size[0] < 200 or im.size[1] < 200:
                return False
        USED_URLS.add(url)
        USED_HASHES.add(file_hash(path))
        return True
    except Exception as e:
        print(f"دانلود خطا: {e}")
        return False


def resolve_category(topic: str, preferred: str = "", drug_name: str = "") -> str:
    t = f"{topic} {preferred} {drug_name}".lower()
    exact = [
        ("metformin", ["metformin", "متفورمین", "گلوکوفاژ"]),
        ("insulin", ["insulin", "انسولین"]),
        ("blood_pressure", ["blood pressure", "فشار خون", "فشارخون", "losartan", "amlodipine", "لوزارتان", "آملودیپین"]),
        ("syrup", ["syrup", "شربت", "سرماخورد"]),
        ("antibiotic", ["antibiotic", "آنتی‌بیوتیک", "آنتی بیوتیک", "amoxicillin", "آموکسی"]),
        ("vitamin", ["vitamin", "ویتامین", "امگا", "omega", "مکمل"]),
        ("injection", ["آمپول", "تزریق", "سرنگ", "injection", "ampoule", "syringe", "لاغری", "semaglutide", "ozempic", "glp"]),
        ("capsules", ["کپسول", "capsule"]),
        ("tablets", ["قرص", "tablet", "nsaid", "ایبوپروفن", "استامینوفن"]),
        ("pharmacy", ["داروخانه", "کمبود دارو", "pharmacy"]),
    ]
    for cat, keys in exact:
        if any(k in t for k in keys):
            return cat
    if preferred in IMAGE_POOL:
        return preferred
    return "tablets"


def fetch_related_background(path: str, slide_index: int) -> bool:
    cat = ACTIVE_CATEGORY if ACTIVE_CATEGORY in IMAGE_POOL else "tablets"
    pool = list(IMAGE_POOL.get(cat, IMAGE_POOL["tablets"]))
    print(f"=== اسلاید {slide_index + 1} | دسته: {cat}")
    if pool:
        start = slide_index % len(pool)
        ordered = pool[start:] + pool[:start]
    else:
        ordered = []
    for url in ordered:
        print(f"تلاش: {url[:100]}")
        if download_image(url, path):
            SUCCESSFUL_BGS.append(path)
            print(f"✓ تصویر مرتبط با {cat}")
            return True
    print("✗ دانلود نشد")
    return False


def fill_background_from_success(path: str, slide_index: int) -> bool:
    if not SUCCESSFUL_BGS:
        return False
    src = SUCCESSFUL_BGS[slide_index % len(SUCCESSFUL_BGS)]
    if not os.path.exists(src):
        src = SUCCESSFUL_BGS[0]
    try:
        img = Image.open(src).convert("RGB")
        if slide_index % 2 == 1:
            img = ImageOps.mirror(img)
        if slide_index % 3 == 0:
            img = ImageEnhance.Brightness(img).enhance(0.92)
        elif slide_index % 3 == 1:
            img = ImageEnhance.Contrast(img).enhance(1.08)
        img.save(path, quality=92)
        SUCCESSFUL_BGS.append(path)
        print("✓ فریم با کپی/آینه پر شد")
        return True
    except Exception as e:
        print(f"خطا در پر کردن فریم: {e}")
        return False


def solid_pharmacy_bg(path: str):
    img = Image.new("RGB", (WIDTH, HEIGHT), (0, 95, 95))
    draw = ImageDraw.Draw(img)
    for y in range(HEIGHT):
        t = y / HEIGHT
        draw.line([(0, y), (WIDTH, y)], fill=(int(10 * t), int(95 - 40 * t), int(95 - 30 * t)))
    img.save(path, quality=90)


def prop_type_for_category(cat: str) -> str:
    c = (cat or "").lower()
    if c in ("injection", "insulin"):
        return "ampoule"
    if c == "syrup":
        return "syrup"
    if c == "capsules":
        return "capsule"
    return "tablet"


def draw_drug_prop(draw, prop: str, hx: int, hy: int):
    if prop == "ampoule":
        draw.rounded_rectangle([hx, hy - 10, hx + 18, hy + 70], radius=4, fill=(220, 240, 255), outline=(100, 140, 180), width=2)
        draw.rectangle([hx + 4, hy - 22, hx + 14, hy - 8], fill=(180, 210, 230), outline=(90, 120, 150))
        draw.ellipse([hx + 2, hy + 62, hx + 16, hy + 78], fill=(255, 120, 120))
    elif prop == "syrup":
        draw.rounded_rectangle([hx - 4, hy, hx + 28, hy + 55], radius=8, fill=(120, 200, 160), outline=(60, 120, 90), width=2)
        draw.rectangle([hx + 6, hy - 18, hx + 18, hy + 2], fill=(200, 220, 210), outline=(80, 100, 90))
        draw.ellipse([hx - 2, hy + 48, hx + 26, hy + 62], fill=(100, 180, 140))
    elif prop == "capsule":
        draw.ellipse([hx - 6, hy + 10, hx + 38, hy + 42], fill=(255, 140, 90), outline=(200, 90, 50), width=2)
        draw.ellipse([hx - 6, hy + 10, hx + 16, hy + 42], fill=(255, 220, 100))
    else:
        draw.ellipse([hx - 4, hy + 8, hx + 36, hy + 40], fill=(255, 255, 255), outline=(180, 190, 200), width=2)
        draw.ellipse([hx + 2, hy + 14, hx + 30, hy + 34], fill=(240, 248, 255))
        draw.line([hx + 16, hy + 10, hx + 16, hy + 38], fill=(200, 210, 220), width=2)


def make_avatar_layer(prop: str = "tablet", size: int = 420) -> Image.Image:
    av = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(av)
    cx, cy = size // 2, size // 2 + 20
    d.ellipse([cx - 110, size - 70, cx + 110, size - 10], fill=(0, 0, 0, 40))
    d.ellipse([cx - 130, cy + 40, cx + 130, size + 40], fill=(245, 250, 255, 255))
    d.rectangle([cx - 100, cy + 70, cx + 100, size], fill=(245, 250, 255, 255))
    d.polygon([(cx - 50, cy + 55), (cx, cy + 95), (cx + 50, cy + 55)], fill=(0, 160, 150, 255))
    d.rectangle([cx - 22, cy + 20, cx + 22, cy + 70], fill=(255, 214, 186, 255))
    d.ellipse([cx - 85, cy - 120, cx + 85, cy + 50], fill=(255, 214, 186, 255))
    d.ellipse([cx - 95, cy - 140, cx + 95, cy - 20], fill=(60, 35, 25, 255))
    d.ellipse([cx - 100, cy - 90, cx - 55, cy + 80], fill=(60, 35, 25, 255))
    d.ellipse([cx + 55, cy - 90, cx + 100, cy + 80], fill=(60, 35, 25, 255))
    d.ellipse([cx - 70, cy - 125, cx + 70, cy - 40], fill=(255, 214, 186, 255))
    d.ellipse([cx - 42, cy - 55, cx - 18, cy - 30], fill=(255, 255, 255, 255))
    d.ellipse([cx + 18, cy - 55, cx + 42, cy - 30], fill=(255, 255, 255, 255))
    d.ellipse([cx - 34, cy - 48, cx - 22, cy - 35], fill=(40, 60, 90, 255))
    d.ellipse([cx + 26, cy - 48, cx + 38, cy - 35], fill=(40, 60, 90, 255))
    d.arc([cx - 48, cy - 70, cx - 12, cy - 50], 200, 340, fill=(50, 30, 20, 255), width=3)
    d.arc([cx + 12, cy - 70, cx + 48, cy - 50], 200, 340, fill=(50, 30, 20, 255), width=3)
    d.arc([cx - 28, cy - 15, cx + 28, cy + 20], 20, 160, fill=(220, 90, 100, 255), width=3)
    d.ellipse([cx - 70, cy - 20, cx - 48, cy], fill=(255, 180, 170, 90))
    d.ellipse([cx + 48, cy - 20, cx + 70, cy], fill=(255, 180, 170, 90))
    hand_x, hand_y = cx + 70, cy + 90
    d.ellipse([hand_x - 15, hand_y - 10, hand_x + 35, hand_y + 40], fill=(255, 214, 186, 255))
    draw_drug_prop(d, prop, hand_x + 8, hand_y - 5)
    d.ellipse([cx - 120, cy + 100, cx - 70, cy + 150], fill=(255, 214, 186, 255))
    return av


def paste_avatar(base_rgb: Image.Image, category: str) -> Image.Image:
    prop = prop_type_for_category(category)
    av = make_avatar_layer(prop=prop, size=380)
    img = base_rgb.convert("RGBA")
    ax, ay = 24, HEIGHT - 520
    img.alpha_composite(av, (ax, ay))
    return img.convert("RGB")


def create_cover_slide(title: str, body: str, hook: str, out_path: str, bg_path: str = None):
    if bg_path and os.path.exists(bg_path):
        bg = Image.open(bg_path).convert("RGB")
        bg = ImageOps.fit(bg, (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS)
        bg = ImageEnhance.Brightness(bg).enhance(0.75)
        bg = ImageEnhance.Contrast(bg).enhance(1.12)
    else:
        solid_pharmacy_bg(out_path + ".bg.jpg")
        bg = Image.open(out_path + ".bg.jpg").convert("RGB")

    img = bg.copy()
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle([0, 0, WIDTH, int(HEIGHT * 0.18)], fill=(0, 0, 0, 75))
    od.rectangle([0, int(HEIGHT * 0.55), WIDTH, HEIGHT], fill=(0, 0, 0, 135))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    title_font = load_font(70, bold=True)
    body_font = load_font(42)
    badge_font = load_font(30, bold=True)
    footer_font = load_font(28)
    max_w = WIDTH - 120

    badge = fa("داروخانه دکتر مسعودیان")
    bbox = draw.textbbox((0, 0), badge, font=badge_font)
    w = bbox[2] - bbox[0]
    draw.rounded_rectangle([WIDTH // 2 - w // 2 - 24, 80, WIDTH // 2 + w // 2 + 24, 138], radius=18, fill=(0, 150, 136))
    draw.text(((WIDTH - w) // 2, 90), badge, font=badge_font, fill=(255, 255, 255))

    y = int(HEIGHT * 0.58)
    for line in wrap_fa(hook or title, title_font, max_w, draw):
        lf = fa(line)
        bbox = draw.textbbox((0, 0), lf, font=title_font)
        w = bbox[2] - bbox[0]
        draw.text(((WIDTH - w) // 2, y), lf, font=title_font, fill=(255, 255, 255))
        y += 78
    for line in wrap_fa(body or "", body_font, max_w, draw):
        lf = fa(line)
        bbox = draw.textbbox((0, 0), lf, font=body_font)
        w = bbox[2] - bbox[0]
        draw.text(((WIDTH - w) // 2, y), lf, font=body_font, fill=(220, 235, 240))
        y += 54

    footer = fa("@drhrmasoudian")
    bbox = draw.textbbox((0, 0), footer, font=footer_font)
    w = bbox[2] - bbox[0]
    draw.text(((WIDTH - w) // 2, HEIGHT - 70), footer, font=footer_font, fill=(180, 210, 215))
    img = paste_avatar(img, ACTIVE_CATEGORY)
    img.save(out_path, quality=95)
    print("کاور + آواتار ساخته شد")


def create_slide_image(title: str, body: str, index: int, total: int, out_path: str, bg_path: str = None):
    if bg_path and os.path.exists(bg_path):
        bg = Image.open(bg_path).convert("RGB")
        bg = ImageOps.fit(bg, (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS)
        if index % 2 == 0:
            bg = ImageEnhance.Brightness(bg).enhance(0.62)
        else:
            bg = ImageEnhance.Brightness(bg).enhance(0.70)
            bg = ImageOps.mirror(bg)
    else:
        solid_pharmacy_bg(out_path + ".bg.jpg")
        bg = Image.open(out_path + ".bg.jpg").convert("RGB")

    img = bg.copy()
    card_top = int(HEIGHT * 0.78)
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle([0, card_top, WIDTH, HEIGHT], fill=(6, 16, 28, 230))
    od.rectangle([0, card_top, WIDTH, card_top + 6], fill=(0, 180, 160, 255))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    title_font = load_font(56, bold=True)
    body_font = load_font(44)
    footer_font = load_font(28)
    max_w = WIDTH - 112
    y = card_top + 22

    draw.text((56, card_top + 10), fa(f"{index} / {total}"), font=footer_font, fill=(0, 200, 180))
    for line in wrap_fa(title, title_font, max_w, draw):
        lf = fa(line)
        bbox = draw.textbbox((0, 0), lf, font=title_font)
        w = bbox[2] - bbox[0]
        draw.text(((WIDTH - w) // 2, y), lf, font=title_font, fill=(255, 255, 255))
        y += 66
    for line in wrap_fa(body, body_font, max_w, draw):
        lf = fa(line)
        bbox = draw.textbbox((0, 0), lf, font=body_font)
        w = bbox[2] - bbox[0]
        draw.text(((WIDTH - w) // 2, y), lf, font=body_font, fill=(225, 235, 245))
        y += 54

    footer = fa("داروخانه دکتر مسعودیان  |  @drhrmasoudian")
    bbox = draw.textbbox((0, 0), footer, font=footer_font)
    w = bbox[2] - bbox[0]
    draw.text(((WIDTH - w) // 2, HEIGHT - 48), footer, font=footer_font, fill=(140, 180, 190))
    img = paste_avatar(img, ACTIVE_CATEGORY)
    img.save(out_path, quality=95)
    print(f"اسلاید {index} + آواتار ساخته شد")


def phonetize_for_tts(text: str) -> str:
    out = text or ""
    for pattern, replacement in PRONUNCIATION_MAP:
        out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    out = re.sub(r"(\d)\s*(میلی)", r"\1 \2", out)
    return out


async def make_narration_file(text: str, out_path: str):
    spoken = phonetize_for_tts(text.strip())
    print(f"TTS audio only: {spoken[:80]}...")
    communicate = edge_tts.Communicate(
        spoken,
        voice="fa-IR-DilaraNeural",
        rate="-12%",
        pitch="+2Hz",
    )
    await communicate.save(out_path)


def download_soft_music(path: str) -> bool:
    for url in SOFT_MUSIC_URLS:
        try:
            r = requests.get(url, timeout=30)
            if r.status_code == 200 and len(r.content) > 8000:
                with open(path, "wb") as f:
                    f.write(r.content)
                return True
        except Exception:
            continue
    return False


def build_video(slide_paths, narration_paths, music_path, output_path):
    clips = []
    for i, img_path in enumerate(slide_paths):
        dur = MIN_SLIDE_DUR
        nar_path = narration_paths[i] if i < len(narration_paths) else None
        if nar_path and os.path.exists(nar_path):
            try:
                a = AudioFileClip(nar_path)
                dur = min(MAX_SLIDE_DUR, max(MIN_SLIDE_DUR, a.duration + 0.7))
                a.close()
            except Exception:
                pass
        clip = ImageClip(img_path).set_duration(dur)
        clip = clip.fadeout(0.25) if i == 0 else clip.fadein(0.25).fadeout(0.25)
        if nar_path and os.path.exists(nar_path):
            try:
                clip = clip.set_audio(AudioFileClip(nar_path).volumex(1.08))
            except Exception as e:
                print(f"نریشن {i+1}: {e}")
        clips.append(clip)

    video = concatenate_videoclips(clips, method="compose")
    if music_path and os.path.exists(music_path):
        try:
            bgm = AudioFileClip(music_path)
            bgm = afx.audio_loop(bgm, duration=video.duration) if bgm.duration < video.duration else bgm.subclip(0, video.duration)
            bgm = bgm.volumex(0.05)
            video = video.set_audio(CompositeAudioClip([video.audio, bgm]) if video.audio else bgm)
        except Exception as e:
            print(f"موزیک: {e}")

    video.write_videofile(output_path, fps=24, codec="libx264", audio_codec="aac", preset="ultrafast", threads=2, logger=None)
    video.close()
    print("ویدیو ساخته شد")


def send_message(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for i in range(0, len(text), 4000):
        res = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text[i:i+4000]}, timeout=60)
        print("متن:", res.json().get("ok"))


def send_photos(paths):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMediaGroup"
    media, files = [], {}
    for i, p in enumerate(paths):
        key = f"p{i}"
        media.append({"type": "photo", "media": f"attach://{key}"})
        files[key] = open(p, "rb")
    try:
        res = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "media": json.dumps(media)}, files=files, timeout=120)
        print("آلبوم:", res.json().get("ok"))
    finally:
        for f in files.values():
            f.close()


def send_video(path: str, caption: str = ""):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
    with open(path, "rb") as f:
        res = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption[:1000]}, files={"video": f}, timeout=180)
    print("ویدیو:", res.json().get("ok"))


def main():
    global ACTIVE_CATEGORY, SUCCESSFUL_BGS
    SUCCESSFUL_BGS = []
    topic = get_topic()
    print("تولید محتوا...")
    package = generate_content_package(topic)
    slides = package.get("slides", [])[:5]
    if not slides:
        raise ValueError("اسلایدی تولید نشد")

    hook = package.get("cover_hook") or slides[0].get("title", "")
    preferred = (package.get("image_category") or "").strip()
    drug_name = (package.get("drug_name") or "").strip()
    ACTIVE_CATEGORY = resolve_category(topic, preferred, drug_name)
    print(f"دسته تصویر: {ACTIVE_CATEGORY}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        slide_paths, narration_paths = [], []

        for i, s in enumerate(slides):
            bg_file = str(tmp / f"bg_{i+1}.jpg")
            ok = fetch_related_background(bg_file, i)
            if not ok:
                if not fill_background_from_success(bg_file, i):
                    solid_pharmacy_bg(bg_file)

            out = str(tmp / f"slide_{i+1}.jpg")
            if i == 0:
                create_cover_slide(s.get("title", ""), s.get("body", ""), hook, out, bg_file)
            else:
                create_slide_image(s.get("title", f"اسلاید {i+1}"), s.get("body", ""), i + 1, len(slides), out, bg_file)
            slide_paths.append(out)

            nar_text = s.get("narration") or f"{s.get('title', '')}. {s.get('body', '')}"
            nar_file = str(tmp / f"nar_{i+1}.mp3")
            try:
                asyncio.run(make_narration_file(nar_text, nar_file))
                narration_paths.append(nar_file)
            except Exception as e:
                print(f"نریشن {i+1}: {e}")
                narration_paths.append("")

        music_path = str(tmp / "bgm.mp3")
        has_music = download_soft_music(music_path)
        video_path = str(tmp / "short_video.mp4")
        build_video(slide_paths, narration_paths, music_path if has_music else "", video_path)

        full_nar = " ".join((s.get("narration") or "") for s in slides)
        full_text = f"""✅ بسته اینستاگرام / یوتیوب شورت

📌 موضوع: {topic}
🧪 دارو/دسته: {drug_name or ACTIVE_CATEGORY}

——— کپشن ———
{package.get('caption', '')}

{package.get('hashtags', '')}

——— استوری ———
{package.get('story_text', '')}

——— نریشن ———
{full_nar}

🖼️ آواتار خانم + پراپ دارو | 🔊 صدای Dilara
"""
        send_message(full_text)
        send_photos(slide_paths)
        send_video(video_path, caption=f"🎬 {drug_name or ACTIVE_CATEGORY}")

    print("✅ تمام")


if __name__ == "__main__":
    main()
