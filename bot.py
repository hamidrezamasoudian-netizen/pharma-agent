import os
import re
import json
import random
import asyncio
import hashlib
import tempfile
from pathlib import Path

import requests
import edge_tts
import arabic_reshaper
from google import genai
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageOps
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
HEADERS = {"User-Agent": "PharmaAgent/1.0 (educational; github actions)"}

USED_URLS = set()
USED_HASHES = set()

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
  "cover_hook": "یک جمله خیلی جذاب برای فریم اول (حداکثر ۱۲ کلمه)",
  "slides": [
    {{"title": "عنوان کاور", "body": "جمله کوتاه", "narration": "جمله افتتاحیه", "image_query": "کوئری انگلیسی خیلی خاص برای تصویر کاور (نام دارو + شکل)"}},
    {{"title": "عنوان ۲", "body": "حداکثر ۱۸ کلمه", "narration": "گفتاری طبیعی", "image_query": "کوئری انگلیسی متفاوت اسلاید ۲"}},
    {{"title": "عنوان ۳", "body": "حداکثر ۱۸ کلمه", "narration": "گفتاری طبیعی", "image_query": "کوئری انگلیسی متفاوت اسلاید ۳"}},
    {{"title": "عنوان ۴", "body": "حداکثر ۱۸ کلمه", "narration": "گفتاری طبیعی", "image_query": "کوئری انگلیسی متفاوت اسلاید ۴"}},
    {{"title": "جمع‌بندی", "body": "نتیجه کوتاه", "narration": "جمع‌بندی گرم", "image_query": "کوئری انگلیسی متفاوت اسلاید ۵"}}
  ]
}}
هر image_query باید متفاوت باشد. نام دارو + شکل (tablets/capsules/ampoule/pen). فقط JSON.
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
    if url in USED_URLS:
        return False
    try:
        r = requests.get(url, timeout=45, headers=HEADERS, allow_redirects=True)
        if r.status_code == 200 and len(r.content) > 5000:
            if "html" in r.headers.get("Content-Type", "").lower():
                return False
            with open(path, "wb") as f:
                f.write(r.content)
            try:
                Image.open(path).verify()
                digest = file_hash(path)
                if digest in USED_HASHES:
                    return False
                USED_URLS.add(url)
                USED_HASHES.add(digest)
                return True
            except Exception:
                return False
    except Exception as e:
        print(f"دانلود خطا: {e}")
    return False


def search_wikimedia(query: str, limit: int = 8) -> list:
    try:
        params = {
            "action": "query", "format": "json", "generator": "search",
            "gsrnamespace": 6, "gsrsearch": query, "gsrlimit": limit,
            "prop": "imageinfo", "iiprop": "url|mime|size", "iiurlwidth": 1280,
        }
        r = requests.get("https://commons.wikimedia.org/w/api.php", params=params, headers=HEADERS, timeout=30)
        pages = r.json().get("query", {}).get("pages", {})
        urls = []
        for page in pages.values():
            info = (page.get("imageinfo") or [{}])[0]
            if not str(info.get("mime", "")).startswith("image/"):
                continue
            url = info.get("thumburl") or info.get("url")
            if url and url not in USED_URLS:
                urls.append(url)
        random.shuffle(urls)
        print(f"wikimedia({query}): {len(urls)}")
        return urls
    except Exception as e:
        print(f"wikimedia error: {e}")
        return []


def search_openverse(query: str, limit: int = 8) -> list:
    try:
        params = {
            "q": query, "page_size": limit, "page": random.randint(1, 3),
            "license": "cc0,pdm,by,by-sa",
        }
        r = requests.get("https://api.openverse.org/v1/images/", params=params, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            return []
        urls = [i.get("url") for i in r.json().get("results", []) if i.get("url") and i.get("url") not in USED_URLS]
        random.shuffle(urls)
        print(f"openverse({query}): {len(urls)}")
        return urls
    except Exception as e:
        print(f"openverse error: {e}")
        return []


def make_gradient_fallback(path: str, seed: int = 0):
    random.seed(seed)
    pairs = [((0, 110, 120), (12, 28, 48)), ((30, 70, 110), (8, 22, 40)), ((70, 50, 90), (20, 18, 40))]
    c1, c2 = pairs[seed % len(pairs)]
    img = Image.new("RGB", (WIDTH, HEIGHT), c1)
    draw = ImageDraw.Draw(img)
    for y in range(HEIGHT):
        t = y / HEIGHT
        col = tuple(int(c1[i] * (1 - t) + c2[i] * t) for i in range(3))
        draw.line([(0, y), (WIDTH, y)], fill=col)
    for _ in range(14):
        x, y = random.randint(0, WIDTH), random.randint(0, int(HEIGHT * 0.65))
        rr = random.randint(40, 100)
        draw.ellipse([x, y, x + rr, y + int(rr * 1.6)], outline=(255, 255, 255), width=2)
    img.save(path, quality=90)


def fetch_related_background(query: str, path: str, slide_index: int) -> bool:
    q = (query or "medicine tablets").strip()
    print(f"=== تصویر اسلاید {slide_index + 1}: {q}")
    variants = [q, f"{q} close up", f"{q} pharmacy", f"{q} package", f"{q} bottle"]
    variants = variants[slide_index % len(variants):] + variants[: slide_index % len(variants)]
    candidates = []
    for term in variants:
        candidates.extend(search_wikimedia(term, limit=6))
        candidates.extend(search_openverse(term, limit=5))
        if len(candidates) >= 15:
            break
    seen, unique = set(), []
    for u in candidates:
        if u and u not in seen and u not in USED_URLS:
            seen.add(u)
            unique.append(u)
    for url in unique:
        print(f"تلاش: {url[:90]}")
        if download_image(url, path):
            print("✓ تصویر یکتا")
            return True
    print("گرادیان جایگزین")
    make_gradient_fallback(path, seed=slide_index + abs(hash(q)) % 50)
    return True


def create_cover_slide(title: str, body: str, hook: str, out_path: str, bg_path: str = None):
    if bg_path and os.path.exists(bg_path):
        bg = Image.open(bg_path).convert("RGB")
        bg = ImageOps.fit(bg, (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS)
        bg = ImageEnhance.Brightness(bg).enhance(0.68)
        bg = ImageEnhance.Contrast(bg).enhance(1.2)
    else:
        make_gradient_fallback(out_path + ".bg.jpg", seed=7)
        bg = Image.open(out_path + ".bg.jpg").convert("RGB")

    img = bg.copy()
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle([0, 0, WIDTH, int(HEIGHT * 0.2)], fill=(0, 0, 0, 90))
    od.rectangle([0, int(HEIGHT * 0.52), WIDTH, HEIGHT], fill=(0, 0, 0, 150))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    title_font = load_font(72, bold=True)
    body_font = load_font(44)
    badge_font = load_font(32, bold=True)
    footer_font = load_font(28)
    margin, max_w = 60, WIDTH - 120

    badge = fa("داروخانه دکتر مسعودیان")
    bbox = draw.textbbox((0, 0), badge, font=badge_font)
    w = bbox[2] - bbox[0]
    draw.rounded_rectangle([WIDTH // 2 - w // 2 - 24, 80, WIDTH // 2 + w // 2 + 24, 140], radius=20, fill=(0, 150, 136))
    draw.text(((WIDTH - w) // 2, 92), badge, font=badge_font, fill=(255, 255, 255))

    y = int(HEIGHT * 0.58)
    for line in wrap_fa(hook or title, title_font, max_w, draw):
        lf = fa(line)
        bbox = draw.textbbox((0, 0), lf, font=title_font)
        w = bbox[2] - bbox[0]
        draw.text(((WIDTH - w) // 2, y), lf, font=title_font, fill=(255, 255, 255))
        y += 82
    y += 8
    for line in wrap_fa(body or title, body_font, max_w, draw):
        lf = fa(line)
        bbox = draw.textbbox((0, 0), lf, font=body_font)
        w = bbox[2] - bbox[0]
        draw.text(((WIDTH - w) // 2, y), lf, font=body_font, fill=(220, 235, 240))
        y += 56

    footer = fa("@drhrmasoudian")
    bbox = draw.textbbox((0, 0), footer, font=footer_font)
    w = bbox[2] - bbox[0]
    draw.text(((WIDTH - w) // 2, HEIGHT - 70), footer, font=footer_font, fill=(180, 210, 215))
    img.save(out_path, quality=95)
    print("کاور ساخته شد")


def create_slide_image(title: str, body: str, index: int, total: int, out_path: str, bg_path: str = None):
    if bg_path and os.path.exists(bg_path):
        bg = Image.open(bg_path).convert("RGB")
        bg = ImageOps.fit(bg, (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS)
        bg = ImageEnhance.Brightness(bg).enhance(0.58)
    else:
        make_gradient_fallback(out_path + ".bg.jpg", seed=index)
        bg = Image.open(out_path + ".bg.jpg").convert("RGB")

    img = bg.copy()
    card_top = int(HEIGHT * 0.78)
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle([0, card_top, WIDTH, HEIGHT], fill=(6, 16, 28, 230))
    od.rectangle([0, card_top, WIDTH, card_top + 6], fill=(0, 180, 160, 255))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    title_font = load_font(58, bold=True)
    body_font = load_font(46)
    footer_font = load_font(28)
    margin, max_w = 56, WIDTH - 112
    y = card_top + 22

    draw.text((margin, card_top + 10), fa(f"{index} / {total}"), font=footer_font, fill=(0, 200, 180))
    for line in wrap_fa(title, title_font, max_w, draw):
        lf = fa(line)
        bbox = draw.textbbox((0, 0), lf, font=title_font)
        w = bbox[2] - bbox[0]
        draw.text(((WIDTH - w) // 2, y), lf, font=title_font, fill=(255, 255, 255))
        y += 68
    y += 4
    for line in wrap_fa(body, body_font, max_w, draw):
        lf = fa(line)
        bbox = draw.textbbox((0, 0), lf, font=body_font)
        w = bbox[2] - bbox[0]
        draw.text(((WIDTH - w) // 2, y), lf, font=body_font, fill=(225, 235, 245))
        y += 56

    footer = fa("داروخانه دکتر مسعودیان  |  @drhrmasoudian")
    bbox = draw.textbbox((0, 0), footer, font=footer_font)
    w = bbox[2] - bbox[0]
    draw.text(((WIDTH - w) // 2, HEIGHT - 48), footer, font=footer_font, fill=(140, 180, 190))
    img.save(out_path, quality=95)
    print(f"اسلاید {index} ساخته شد")


async def make_narration_file(text: str, out_path: str):
    communicate = edge_tts.Communicate(text.strip(), voice="fa-IR-FaridNeural", rate="-15%", pitch="-4Hz")
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
        if i == 0:
            clip = ImageClip(img_path).set_duration(dur).fadeout(0.25)
        else:
            clip = ImageClip(img_path).set_duration(dur).fadein(0.25).fadeout(0.25)
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
    topic = get_topic()
    print("تولید محتوا...")
    package = generate_content_package(topic)
    slides = package.get("slides", [])[:5]
    if not slides:
        raise ValueError("اسلایدی تولید نشد")
    hook = package.get("cover_hook") or slides[0].get("title", "")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        slide_paths, narration_paths = [], []

        for i, s in enumerate(slides):
            bg_file = str(tmp / f"bg_{i+1}.jpg")
            fetch_related_background(s.get("image_query") or topic, bg_file, i)
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

——— کپشن ———
{package.get('caption', '')}

{package.get('hashtags', '')}

——— استوری ———
{package.get('story_text', '')}

——— نریشن ———
{full_nar}

🎬 کاور قوی + تصاویر یکتا
"""
        send_message(full_text)
        send_photos(slide_paths)
        send_video(video_path, caption="🎬 کاور جذاب + تصاویر غیرتکراری")

    print("✅ تمام")


if __name__ == "__main__":
    main()
