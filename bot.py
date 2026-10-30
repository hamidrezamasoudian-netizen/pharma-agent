import os
import re
import json
import random
import asyncio
import tempfile
from pathlib import Path
from urllib.parse import quote

import requests
import edge_tts
import arabic_reshaper
from google import genai
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from moviepy.editor import (
    ImageClip,
    AudioFileClip,
    CompositeAudioClip,
    concatenate_videoclips,
    afx,
)

# ===================== تنظیمات =====================
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

HEADERS = {"User-Agent": "PharmaAgent/1.0 (educational content bot)"}

# تصاویر مستقیم و مرتبط برای داروهای رایج (پشتیبان دقیق)
DRUG_IMAGE_MAP = {
    "metformin": [
        "https://upload.wikimedia.org/wikipedia/commons/thumb/0/0b/Metformin_500mg_Tablets.jpg/1280px-Metformin_500mg_Tablets.jpg",
        "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4a/Metformin.jpg/1024px-Metformin.jpg",
    ],
    "insulin": [
        "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3b/Insulin_vial.jpg/1024px-Insulin_vial.jpg",
        "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8a/Insulin_pen.jpg/1024px-Insulin_pen.jpg",
    ],
    "vitamin d": [
        "https://upload.wikimedia.org/wikipedia/commons/thumb/9/9a/Vitamin_D_capsules.jpg/1024px-Vitamin_D_capsules.jpg",
    ],
    "omega": [
        "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8c/Omega-3_fish_oil_capsules.jpg/1024px-Omega-3_fish_oil_capsules.jpg",
    ],
    "antibiotic": [
        "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5d/Amoxicillin_capsules.jpg/1024px-Amoxicillin_capsules.jpg",
        "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1f/Antibiotics.jpg/1024px-Antibiotics.jpg",
    ],
    "syringe": [
        "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7e/Syringe.jpg/1024px-Syringe.jpg",
        "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5a/Injection_syringe.jpg/1024px-Injection_syringe.jpg",
    ],
    "injection": [
        "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7e/Syringe.jpg/1024px-Syringe.jpg",
        "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4d/Ampoule.jpg/800px-Ampoule.jpg",
    ],
    "ampoule": [
        "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4d/Ampoule.jpg/800px-Ampoule.jpg",
        "https://upload.wikimedia.org/wikipedia/commons/thumb/0/0e/Glass_ampoule.jpg/800px-Glass_ampoule.jpg",
    ],
    "tablet": [
        "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7a/Pills_and_tablets.jpg/1280px-Pills_and_tablets.jpg",
    ],
    "capsule": [
        "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2b/Capsules.jpg/1024px-Capsules.jpg",
    ],
    "pharmacy": [
        "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8a/Pharmacy.jpg/1280px-Pharmacy.jpg",
        "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3e/Drugstore.jpg/1280px-Drugstore.jpg",
    ],
    "blood pressure": [
        "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1c/Sphygmomanometer.jpg/1024px-Sphygmomanometer.jpg",
    ],
    "depression": [
        "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7a/Pills_and_tablets.jpg/1280px-Pills_and_tablets.jpg",
    ],
    "cold": [
        "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5d/Cough_syrup.jpg/800px-Cough_syrup.jpg",
    ],
}

FALLBACK_BG = [
    "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7a/Pills_and_tablets.jpg/1280px-Pills_and_tablets.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8a/Pharmacy.jpg/1280px-Pharmacy.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4d/Ampoule.jpg/800px-Ampoule.jpg",
]

SOFT_MUSIC_URLS = [
    "https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf07a.mp3?filename=empty-mind-118973.mp3",
    "https://cdn.pixabay.com/download/audio/2021/11/25/audio_9174bd675d.mp3?filename=soft-piano-ambient-114064.mp3",
]


def get_topic() -> str:
    if CUSTOM_TOPIC:
        print(f"موضوع دستی: {CUSTOM_TOPIC}")
        return CUSTOM_TOPIC
    topic = random.choice(TRENDING_TOPICS)
    print(f"موضوع روز: {topic}")
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
  "slides": [
    {{
      "title": "عنوان کوتاه ۱",
      "body": "متن واضح حداکثر ۱۸ کلمه",
      "narration": "۱ تا ۲ جمله گفتاری طبیعی و روان",
      "image_query": "نام انگلیسی دقیق دارو یا شکل دارو برای جستجوی تصویر (مثال: semaglutide injection pen, metformin 500mg tablets, insulin vial, ampoule glass medicine)"
    }},
    {{
      "title": "عنوان ۲",
      "body": "متن واضح حداکثر ۱۸ کلمه",
      "narration": "جمله گفتاری طبیعی",
      "image_query": "exact English drug name or dosage form for image search"
    }},
    {{
      "title": "عنوان ۳",
      "body": "متن واضح حداکثر ۱۸ کلمه",
      "narration": "جمله گفتاری طبیعی",
      "image_query": "exact English drug/product visual query"
    }},
    {{
      "title": "عنوان ۴",
      "body": "متن واضح حداکثر ۱۸ کلمه",
      "narration": "جمله گفتاری طبیعی",
      "image_query": "exact English drug/product visual query"
    }},
    {{
      "title": "جمع‌بندی",
      "body": "نتیجه کوتاه",
      "narration": "جمع‌بندی گرم و دعوت به تعامل",
      "image_query": "pharmacy medicines shelves"
    }}
  ]
}}
قوانین مهم برای image_query:
- حتما نام انگلیسی دارو یا شکل دارویی واقعی باشد (tablets, capsules, ampoule, syringe, insulin pen)
- از کلمات کلی مثل healthcare یا wellness به‌تنهایی استفاده نکن
- اگر موضوع آمپول لاغری است بنویس: GLP-1 injection pen یا semaglutide pen یا liraglutide injection
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


def download_image(url: str, path: str) -> bool:
    try:
        r = requests.get(url, timeout=45, headers=HEADERS, allow_redirects=True)
        if r.status_code == 200 and len(r.content) > 4000:
            ctype = r.headers.get("Content-Type", "")
            if "html" in ctype.lower():
                return False
            with open(path, "wb") as f:
                f.write(r.content)
            try:
                im = Image.open(path)
                im.verify()
                return True
            except Exception:
                return False
    except Exception as e:
        print(f"دانلود خطا: {e}")
    return False


def search_wikimedia(query: str, limit: int = 6) -> list:
    """جستجوی تصویر در ویکی‌مدیا کامانز"""
    try:
        api = "https://commons.wikimedia.org/w/api.php"
        params = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrnamespace": 6,
            "gsrsearch": query,
            "gsrlimit": limit,
            "prop": "imageinfo",
            "iiprop": "url|mime|size",
            "iiurlwidth": 1280,
        }
        r = requests.get(api, params=params, headers=HEADERS, timeout=30)
        data = r.json()
        pages = data.get("query", {}).get("pages", {})
        urls = []
        for page in pages.values():
            info = (page.get("imageinfo") or [{}])[0]
            mime = info.get("mime", "")
            if not mime.startswith("image/"):
                continue
            url = info.get("thumburl") or info.get("url")
            if url:
                urls.append(url)
        print(f"wikimedia({query}): {len(urls)} تصویر")
        return urls
    except Exception as e:
        print(f"wikimedia error: {e}")
        return []


def search_openverse(query: str, limit: int = 6) -> list:
    """جستجوی تصویر آزاد در Openverse"""
    try:
        api = "https://api.openverse.org/v1/images/"
        params = {
            "q": query,
            "page_size": limit,
            "license": "cc0,pdm,by,by-sa",
            "category": "photograph",
        }
        r = requests.get(api, params=params, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            return []
        results = r.json().get("results", [])
        urls = [item.get("url") for item in results if item.get("url")]
        print(f"openverse({query}): {len(urls)} تصویر")
        return urls
    except Exception as e:
        print(f"openverse error: {e}")
        return []


def mapped_drug_urls(query: str) -> list:
    q = (query or "").lower()
    found = []
    for key, urls in DRUG_IMAGE_MAP.items():
        if key in q:
            found.extend(urls)
    # کلیدواژه‌های فارسی موضوع هم کمک می‌کند
    return found


def fetch_related_background(query: str, path: str, fallback_index: int) -> bool:
    """پیدا کردن تصویر واقعاً مرتبط با دارو"""
    q = (query or "medicine tablets").strip()
    print(f"=== جستجوی تصویر برای: {q}")

    candidates = []
    # ۱) نقشه داروهای رایج
    candidates.extend(mapped_drug_urls(q))
    # ۲) ویکی‌مدیا با چند ترکیب جستجو
    for term in [q, f"{q} tablet", f"{q} medicine", f"{q} pill"]:
        candidates.extend(search_wikimedia(term, limit=4))
        if len(candidates) >= 8:
            break
    # ۳) Openverse
    candidates.extend(search_openverse(q, limit=5))
    # ۴) پشتیبان
    candidates.append(FALLBACK_BG[fallback_index % len(FALLBACK_BG)])

    # حذف تکراری با حفظ ترتیب
    seen = set()
    unique = []
    for u in candidates:
        if u and u not in seen:
            seen.add(u)
            unique.append(u)

    for url in unique:
        print(f"تلاش: {url[:90]}")
        if download_image(url, path):
            print(f"✓ پس‌زمینه مرتبط ذخیره شد")
            return True
    print("✗ تصویر مرتبط پیدا نشد")
    return False


def create_slide_image(title: str, body: str, index: int, total: int, out_path: str, bg_path: str = None):
    if bg_path and os.path.exists(bg_path):
        bg = Image.open(bg_path).convert("RGB")
        bg = bg.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
        bg = ImageEnhance.Brightness(bg).enhance(0.50)
        bg = bg.filter(ImageFilter.GaussianBlur(radius=0.6))
    else:
        bg = Image.new("RGB", (WIDTH, HEIGHT), (12, 28, 42))

    img = bg.copy()
    card_top = int(HEIGHT * 0.78)
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.rectangle([0, card_top, WIDTH, HEIGHT], fill=(6, 16, 28, 230))
    odraw.rectangle([0, card_top, WIDTH, card_top + 6], fill=(0, 180, 160, 255))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    title_font = load_font(58, bold=True)
    body_font = load_font(46)
    footer_font = load_font(28)

    margin = 56
    max_w = WIDTH - 2 * margin
    y = card_top + 22

    badge = fa(f"{index} / {total}")
    draw.text((margin, card_top + 10), badge, font=footer_font, fill=(0, 200, 180))

    for line in wrap_fa(title, title_font, max_w, draw):
        line_fa = fa(line)
        bbox = draw.textbbox((0, 0), line_fa, font=title_font)
        w = bbox[2] - bbox[0]
        draw.text(((WIDTH - w) // 2, y), line_fa, font=title_font, fill=(255, 255, 255))
        y += 68

    y += 4
    for line in wrap_fa(body, body_font, max_w, draw):
        line_fa = fa(line)
        bbox = draw.textbbox((0, 0), line_fa, font=body_font)
        w = bbox[2] - bbox[0]
        draw.text(((WIDTH - w) // 2, y), line_fa, font=body_font, fill=(225, 235, 245))
        y += 56

    footer = fa("داروخانه دکتر مسعودیان  |  @drhrmasoudian")
    bbox = draw.textbbox((0, 0), footer, font=footer_font)
    w = bbox[2] - bbox[0]
    draw.text(((WIDTH - w) // 2, HEIGHT - 48), footer, font=footer_font, fill=(140, 180, 190))

    img.save(out_path, quality=95)
    print(f"اسلاید {index} ساخته شد")


async def make_narration_file(text: str, out_path: str):
    voice = "fa-IR-FaridNeural"
    communicate = edge_tts.Communicate(
        text.strip(),
        voice=voice,
        rate="-15%",
        pitch="-4Hz",
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
        clip = ImageClip(img_path).set_duration(dur).fadein(0.25).fadeout(0.25)
        if nar_path and os.path.exists(nar_path):
            try:
                nar = AudioFileClip(nar_path).volumex(1.08)
                clip = clip.set_audio(nar)
            except Exception as e:
                print(f"نریشن اسلاید {i+1}: {e}")
        clips.append(clip)

    video = concatenate_videoclips(clips, method="compose")

    if music_path and os.path.exists(music_path):
        try:
            bgm = AudioFileClip(music_path)
            if bgm.duration < video.duration:
                bgm = afx.audio_loop(bgm, duration=video.duration)
            else:
                bgm = bgm.subclip(0, video.duration)
            bgm = bgm.volumex(0.05)
            if video.audio is not None:
                video = video.set_audio(CompositeAudioClip([video.audio, bgm]))
            else:
                video = video.set_audio(bgm)
        except Exception as e:
            print(f"خطا موزیک: {e}")

    video.write_videofile(
        output_path,
        fps=24,
        codec="libx264",
        audio_codec="aac",
        preset="ultrafast",
        threads=2,
        logger=None,
    )
    video.close()
    print("ویدیو نهایی ساخته شد")


def send_message(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for i in range(0, len(text), 4000):
        res = requests.post(
            url,
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text[i : i + 4000]},
            timeout=60,
        )
        print("متن:", res.json().get("ok"))


def send_photos(paths):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMediaGroup"
    media, files = [], {}
    for i, p in enumerate(paths):
        key = f"p{i}"
        media.append({"type": "photo", "media": f"attach://{key}"})
        files[key] = open(p, "rb")
    try:
        res = requests.post(
            url,
            data={"chat_id": TELEGRAM_CHAT_ID, "media": json.dumps(media)},
            files=files,
            timeout=120,
        )
        print("آلبوم:", res.json().get("ok"))
    finally:
        for f in files.values():
            f.close()


def send_video(path: str, caption: str = ""):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
    with open(path, "rb") as f:
        res = requests.post(
            url,
            data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption[:1000]},
            files={"video": f},
            timeout=180,
        )
    print("ویدیو:", res.json().get("ok"), res.json().get("description", ""))


def main():
    topic = get_topic()
    print("تولید محتوا...")
    package = generate_content_package(topic)
    slides = package.get("slides", [])[:5]
    if not slides:
        raise ValueError("اسلایدی تولید نشد")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        slide_paths = []
        narration_paths = []

        for i, s in enumerate(slides, 1):
            bg_file = str(tmp / f"bg_{i}.jpg")
            query = s.get("image_query") or topic
            fetch_related_background(query, bg_file, i - 1)

            out = str(tmp / f"slide_{i}.jpg")
            create_slide_image(
                title=s.get("title", f"اسلاید {i}"),
                body=s.get("body", ""),
                index=i,
                total=len(slides),
                out_path=out,
                bg_path=bg_file,
            )
            slide_paths.append(out)

            nar_text = s.get("narration") or f"{s.get('title', '')}. {s.get('body', '')}"
            nar_file = str(tmp / f"nar_{i}.mp3")
            try:
                asyncio.run(make_narration_file(nar_text, nar_file))
                narration_paths.append(nar_file)
                print(f"نریشن اسلاید {i} آماده")
            except Exception as e:
                print(f"نریشن اسلاید {i} خطا: {e}")
                narration_paths.append("")

        music_path = str(tmp / "bgm.mp3")
        has_music = download_soft_music(music_path)

        video_path = str(tmp / "short_video.mp4")
        build_video(
            slide_paths,
            narration_paths,
            music_path if has_music else "",
            video_path,
        )

        full_nar = " ".join(
            (s.get("narration") or f"{s.get('title', '')}. {s.get('body', '')}")
            for s in slides
        )
        full_text = f"""✅ بسته اینستاگرام / یوتیوب شورت

📌 موضوع: {topic}

——— کپشن ———
{package.get('caption', '')}

{package.get('hashtags', '')}

——— استوری ———
{package.get('story_text', '')}

——— نریشن ———
{full_nar}

🎬 ویدیو با پس‌زمینه مرتبط‌تر با دارو ارسال شد.
"""
        send_message(full_text)
        send_photos(slide_paths)
        send_video(
            video_path,
            caption="🎬 نسخه جدید با تصاویر مرتبط‌تر دارویی",
        )

    print("✅ تمام")


if __name__ == "__main__":
    main()
