import os
import re
import json
import random
import asyncio
import hashlib
import tempfile
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

import requests
import edge_tts
import arabic_reshaper
from google import genai
from google.genai import types
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
    "User-Agent": "PharmaAgent/4.1 (educational; https://github.com/hamidrezamasoudian-netizen/pharma-agent)",
    "Accept": "image/*,*/*;q=0.8",
}

CURRENT_TOPIC = ""
ACTIVE_CATEGORY = "tablets"
PRESENTER_PATH = None

PRONUNCIATION_MAP = [
    (r"منیزیوم", "مَگ‌نِ‌زیوم"),
    (r"منیزیم", "مَگ‌نِ‌زیوم"),
    (r"magnesium", "مَگ‌نِ‌زیوم"),
    (r"کلسیم", "کَل‌سی‌یوم"),
    (r"calcium", "کَل‌سی‌یوم"),
    (r"زینک", "زینک"),
    (r"zinc", "زینک"),
    (r"آهن", "آ‌هَن"),
    (r"متفورمین", "مت‌فور‌مین"),
    (r"metformin", "مت‌فور‌مین"),
    (r"انسولین", "اِن‌سو‌لین"),
    (r"insulin", "اِن‌سو‌لین"),
    (r"ویتامین\s*D\b", "ویتامین دی"),
    (r"ویتامین\s*d\b", "ویتامین دی"),
    (r"ویتامین\s*دی", "ویتامین دی"),
    (r"امگا\s*۳", "اُمگا سه"),
    (r"امگا\s*3", "اُمگا سه"),
    (r"آموکسی‌سیلین", "آموکسی‌سی‌لین"),
    (r"amoxicillin", "آموکسی‌سی‌لین"),
    (r"NSAID", "اِن‌سِید"),
    (r"ایبوپروفن", "ایبو‌پروفن"),
    (r"استامینوفن", "اِستامینوفن"),
    (r"لوزارتان", "لوزار‌تان"),
    (r"آملودیپین", "آملو‌دیپین"),
    (r"اُزِمپیک", "اُزِمپیک"),
    (r"Ozempic", "اُزِمپیک"),
    (r"سماگلوتاید", "سِما‌گلو‌تاید"),
    (r"پرل", "پِرل"),
    (r"۵۰\s*هزار", "پنجاه هزار"),
    (r"50\s*هزار", "پنجاه هزار"),
    (r"mg\b", "میلی‌گرم"),
    (r"IU\b", "آی‌یو"),
]

PROP_PROMPTS = {
    "ampoule": "holding a clear glass medicine ampoule and a medical syringe elegantly in her hands, pharmaceutical injection theme",
    "tablet": "holding a white medicine tablet and a small blister pack of pills in her hands",
    "capsule": "holding a two-tone medicine capsule between her fingers",
    "syrup": "holding a small amber cough syrup bottle with a measuring spoon",
}

# تصاویر آماده رایگان (Pexels) — خانم داروساز / روپوش سفید
STOCK_PRESENTER = {
    "ampoule": [
        "https://images.pexels.com/photos/4047074/pexels-photo-4047074.jpeg?auto=compress&cs=tinysrgb&w=1080",
        "https://images.pexels.com/photos/3376799/pexels-photo-3376799.jpeg?auto=compress&cs=tinysrgb&w=1080",
        "https://images.pexels.com/photos/5206949/pexels-photo-5206949.jpeg?auto=compress&cs=tinysrgb&w=1080",
    ],
    "tablet": [
        "https://images.pexels.com/photos/19471013/pexels-photo-19471013.jpeg?auto=compress&cs=tinysrgb&w=1080",
        "https://images.pexels.com/photos/5206949/pexels-photo-5206949.jpeg?auto=compress&cs=tinysrgb&w=1080",
        "https://images.pexels.com/photos/5726794/pexels-photo-5726794.jpeg?auto=compress&cs=tinysrgb&w=1080",
    ],
    "capsule": [
        "https://images.pexels.com/photos/5726794/pexels-photo-5726794.jpeg?auto=compress&cs=tinysrgb&w=1080",
        "https://images.pexels.com/photos/19471013/pexels-photo-19471013.jpeg?auto=compress&cs=tinysrgb&w=1080",
    ],
    "syrup": [
        "https://images.pexels.com/photos/5206949/pexels-photo-5206949.jpeg?auto=compress&cs=tinysrgb&w=1080",
        "https://images.pexels.com/photos/19471013/pexels-photo-19471013.jpeg?auto=compress&cs=tinysrgb&w=1080",
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
قوانین املا: title/body/caption فقط املای استاندارد فارسی (منیزیم، کلسیم، متفورمین).
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


def resolve_category(topic: str, preferred: str = "", drug_name: str = "") -> str:
    t = f"{topic} {preferred} {drug_name}".lower()
    exact = [
        ("metformin", ["metformin", "متفورمین", "گلوکوفاژ"]),
        ("insulin", ["insulin", "انسولین"]),
        ("blood_pressure", ["فشار خون", "فشارخون", "losartan", "amlodipine", "لوزارتان"]),
        ("syrup", ["syrup", "شربت", "سرماخورد"]),
        ("antibiotic", ["آنتی‌بیوتیک", "آنتی بیوتیک", "amoxicillin", "آموکسی"]),
        ("vitamin", ["vitamin", "ویتامین", "امگا", "omega", "مکمل"]),
        ("injection", ["آمپول", "تزریق", "سرنگ", "injection", "ampoule", "syringe", "لاغری", "semaglutide", "ozempic"]),
        ("capsules", ["کپسول", "capsule"]),
        ("tablets", ["قرص", "tablet", "nsaid", "ایبوپروفن"]),
        ("pharmacy", ["داروخانه", "کمبود دارو"]),
    ]
    for cat, keys in exact:
        if any(k in t for k in keys):
            return cat
    return preferred if preferred else "tablets"


def prop_type_for_category(cat: str) -> str:
    c = (cat or "").lower()
    if c in ("injection", "insulin"):
        return "ampoule"
    if c == "syrup":
        return "syrup"
    if c == "capsules":
        return "capsule"
    return "tablet"


def build_presenter_prompt(category: str) -> str:
    prop = prop_type_for_category(category)
    prop_text = PROP_PROMPTS.get(prop, PROP_PROMPTS["tablet"])
    return (
        "Vertical portrait photo 9:16, photorealistic beautiful young Middle Eastern woman pharmacist, "
        "elegant professional look, soft natural makeup, warm friendly smile, long dark hair, "
        "white medical coat over modest clothing, standing in a bright modern pharmacy, "
        f"{prop_text}, "
        "the medicine item is clearly visible in her hands as the main prop, "
        "soft cinematic lighting, shallow depth of field, high detail face, Instagram Reels style, "
        "no text, no watermark, no logo, no extra floating syringes in background"
    )


def download_stock_presenter(path: str, category: str) -> bool:
    prop = prop_type_for_category(category)
    urls = list(STOCK_PRESENTER.get(prop, STOCK_PRESENTER["tablet"]))
    for extra in STOCK_PRESENTER.values():
        for u in extra:
            if u not in urls:
                urls.append(u)
    for url in urls:
        try:
            print(f"دانلود استوک: {url[:70]}...")
            r = requests.get(url, timeout=45, headers=HEADERS, allow_redirects=True)
            if r.status_code != 200 or len(r.content) < 8000:
                continue
            ctype = r.headers.get("Content-Type", "").lower()
            if "html" in ctype:
                continue
            with open(path, "wb") as f:
                f.write(r.content)
            with Image.open(path) as im:
                im.load()
                if im.size[0] < 300 or im.size[1] < 300:
                    continue
            print("✓ تصویر آماده اینترنت دانلود شد")
            return True
        except Exception as e:
            print(f"استوک خطا: {e}")
            continue
    print("✗ استوک هم موفق نشد")
    return False


def generate_presenter_image(path: str, category: str) -> bool:
    prompt = build_presenter_prompt(category)
    print("تولید تصویر مجری:", prompt[:120], "...")

    try:
        resp = client.models.generate_images(
            model="imagen-4.0-fast-generate-001",
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="9:16",
                output_mime_type="image/jpeg",
            ),
        )
        if resp.generated_images:
            img_obj = resp.generated_images[0].image
            if hasattr(img_obj, "image_bytes") and img_obj.image_bytes:
                with open(path, "wb") as f:
                    f.write(img_obj.image_bytes)
            elif hasattr(img_obj, "save"):
                img_obj.save(path)
            else:
                pil = Image.open(BytesIO(img_obj.image_bytes))
                pil.save(path, quality=95)
            print("✓ Imagen موفق")
            return True
    except Exception as e:
        print(f"Imagen ناموفق: {e}")

    try:
        resp = client.models.generate_content(
            model="gemini-2.5-flash-image",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                image_config=types.ImageConfig(aspect_ratio="9:16"),
            ),
        )
        for part in resp.candidates[0].content.parts:
            if getattr(part, "inline_data", None) and part.inline_data.data:
                with open(path, "wb") as f:
                    f.write(part.inline_data.data)
                print("✓ Gemini Image موفق")
                return True
    except Exception as e:
        print(f"Gemini Image ناموفق: {e}")

    print("✗ تولید AI ناموفق — تلاش برای تصاویر آماده اینترنت")
    return download_stock_presenter(path, category)


def solid_pharmacy_bg(path: str):
    img = Image.new("RGB", (WIDTH, HEIGHT), (12, 40, 48))
    draw = ImageDraw.Draw(img)
    for y in range(HEIGHT):
        t = y / HEIGHT
        draw.line([(0, y), (WIDTH, y)], fill=(int(12 + 20 * t), int(40 + 30 * t), int(48 + 20 * t)))
    img.save(path, quality=90)


def load_presenter_bg(path: str = None) -> Image.Image:
    src = path or PRESENTER_PATH
    if src and os.path.exists(src):
        bg = Image.open(src).convert("RGB")
        bg = ImageOps.fit(bg, (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS)
        return bg
    solid_pharmacy_bg("/tmp/_solid_bg.jpg")
    return Image.open("/tmp/_solid_bg.jpg").convert("RGB")


def create_cover_slide(title: str, body: str, hook: str, out_path: str):
    bg = load_presenter_bg()
    bg = ImageEnhance.Brightness(bg).enhance(0.88)
    img = bg.copy()

    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle([0, 0, WIDTH, int(HEIGHT * 0.14)], fill=(0, 0, 0, 70))
    od.rectangle([0, int(HEIGHT * 0.62), WIDTH, HEIGHT], fill=(0, 0, 0, 160))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    title_font = load_font(68, bold=True)
    body_font = load_font(40)
    badge_font = load_font(28, bold=True)
    footer_font = load_font(26)
    max_w = WIDTH - 100

    badge = fa("داروخانه دکتر مسعودیان")
    bbox = draw.textbbox((0, 0), badge, font=badge_font)
    w = bbox[2] - bbox[0]
    draw.rounded_rectangle(
        [WIDTH // 2 - w // 2 - 22, 70, WIDTH // 2 + w // 2 + 22, 122],
        radius=16,
        fill=(0, 150, 136),
    )
    draw.text(((WIDTH - w) // 2, 80), badge, font=badge_font, fill=(255, 255, 255))

    y = int(HEIGHT * 0.66)
    for line in wrap_fa(hook or title, title_font, max_w, draw):
        lf = fa(line)
        bbox = draw.textbbox((0, 0), lf, font=title_font)
        w = bbox[2] - bbox[0]
        draw.text(((WIDTH - w) // 2, y), lf, font=title_font, fill=(255, 255, 255))
        y += 74
    for line in wrap_fa(body or "", body_font, max_w, draw):
        lf = fa(line)
        bbox = draw.textbbox((0, 0), lf, font=body_font)
        w = bbox[2] - bbox[0]
        draw.text(((WIDTH - w) // 2, y), lf, font=body_font, fill=(220, 235, 240))
        y += 50

    footer = fa("@drhrmasoudian")
    bbox = draw.textbbox((0, 0), footer, font=footer_font)
    w = bbox[2] - bbox[0]
    draw.text(((WIDTH - w) // 2, HEIGHT - 60), footer, font=footer_font, fill=(180, 210, 215))
    img.save(out_path, quality=95)
    print("کاور ساخته شد")


def create_slide_image(title: str, body: str, index: int, total: int, out_path: str):
    bg = load_presenter_bg()
    if index % 2 == 0:
        bg = ImageEnhance.Brightness(bg).enhance(0.82)
    else:
        bg = ImageEnhance.Brightness(bg).enhance(0.90)
        bg = ImageOps.mirror(bg)

    img = bg.copy()
    card_top = int(HEIGHT * 0.72)
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle([0, card_top, WIDTH, HEIGHT], fill=(6, 16, 28, 220))
    od.rectangle([0, card_top, WIDTH, card_top + 5], fill=(0, 180, 160, 255))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    title_font = load_font(52, bold=True)
    body_font = load_font(40)
    footer_font = load_font(26)
    max_w = WIDTH - 100
    y = card_top + 20

    draw.text((50, card_top + 8), fa(f"{index} / {total}"), font=footer_font, fill=(0, 200, 180))
    for line in wrap_fa(title, title_font, max_w, draw):
        lf = fa(line)
        bbox = draw.textbbox((0, 0), lf, font=title_font)
        w = bbox[2] - bbox[0]
        draw.text(((WIDTH - w) // 2, y), lf, font=title_font, fill=(255, 255, 255))
        y += 60
    for line in wrap_fa(body, body_font, max_w, draw):
        lf = fa(line)
        bbox = draw.textbbox((0, 0), lf, font=body_font)
        w = bbox[2] - bbox[0]
        draw.text(((WIDTH - w) // 2, y), lf, font=body_font, fill=(225, 235, 245))
        y += 48

    footer = fa("داروخانه دکتر مسعودیان  |  @drhrmasoudian")
    bbox = draw.textbbox((0, 0), footer, font=footer_font)
    w = bbox[2] - bbox[0]
    draw.text(((WIDTH - w) // 2, HEIGHT - 44), footer, font=footer_font, fill=(140, 180, 190))
    img.save(out_path, quality=95)
    print(f"اسلاید {index} ساخته شد")


def phonetize_for_tts(text: str) -> str:
    out = text or ""
    for pattern, replacement in PRONUNCIATION_MAP:
        out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    return out


async def make_narration_file(text: str, out_path: str):
    spoken = phonetize_for_tts(text.strip())
    print(f"TTS: {spoken[:80]}...")
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
    global ACTIVE_CATEGORY, PRESENTER_PATH
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
    print(f"دسته: {ACTIVE_CATEGORY} | پراپ: {prop_type_for_category(ACTIVE_CATEGORY)}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        presenter_file = str(tmp / "presenter.jpg")
        ok = generate_presenter_image(presenter_file, ACTIVE_CATEGORY)
        PRESENTER_PATH = presenter_file if ok else None

        slide_paths, narration_paths = [], []
        for i, s in enumerate(slides):
            out = str(tmp / f"slide_{i+1}.jpg")
            if i == 0:
                create_cover_slide(s.get("title", ""), s.get("body", ""), hook, out)
            else:
                create_slide_image(s.get("title", f"اسلاید {i+1}"), s.get("body", ""), i + 1, len(slides), out)
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

🖼️ مجری تمام‌صفحه (AI یا استوک) | 🔊 Dilara
"""
        send_message(full_text)
        send_photos(slide_paths)
        send_video(video_path, caption=f"🎬 {drug_name or ACTIVE_CATEGORY}")

    print("✅ تمام")


if __name__ == "__main__":
    main()
