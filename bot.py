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

WIDTH, HEIGHT = 1080, 1920  # مناسب ریلز اینستاگرام و شورت یوتیوب
MIN_SLIDE_DUR = 3.5
MAX_SLIDE_DUR = 14.0

# تصاویر عمومی دارویی (پشتیبان)
FALLBACK_BG = [
    "https://images.unsplash.com/photo-1587854692152-cbe660dbde88?w=1080&h=1920&fit=crop",
    "https://images.unsplash.com/photo-1471864190281-a93a3070b6de?w=1080&h=1920&fit=crop",
    "https://images.unsplash.com/photo-1631549916768-4119b2e5f926?w=1080&h=1920&fit=crop",
    "https://images.unsplash.com/photo-1585435557343-3b092031a831?w=1080&h=1920&fit=crop",
    "https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?w=1080&h=1920&fit=crop",
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
      "narration": "۱ تا ۲ جمله گفتاری طبیعی و روان برای همین اسلاید",
      "image_query": "عبارت انگلیسی کوتاه برای جستجوی تصویر مرتبط (مثلا metformin tablets close up یا insulin pen injection)"
    }},
    {{
      "title": "عنوان ۲",
      "body": "متن واضح حداکثر ۱۸ کلمه",
      "narration": "جمله گفتاری طبیعی",
      "image_query": "english image search query"
    }},
    {{
      "title": "عنوان ۳",
      "body": "متن واضح حداکثر ۱۸ کلمه",
      "narration": "جمله گفتاری طبیعی",
      "image_query": "english image search query"
    }},
    {{
      "title": "عنوان ۴",
      "body": "متن واضح حداکثر ۱۸ کلمه",
      "narration": "جمله گفتاری طبیعی",
      "image_query": "english image search query"
    }},
    {{
      "title": "جمع‌بندی",
      "body": "نتیجه کوتاه",
      "narration": "جمع‌بندی گرم و دعوت به تعامل",
      "image_query": "pharmacy professional healthcare"
    }}
  ]
}}
قوانین: فارسی روان، نریشن محاوره‌ای مودبانه، بدون توصیه درمانی قطعی، image_query حتما انگلیسی و مرتبط با همان دارو/موضوع اسلاید، فقط JSON.
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
        r = requests.get(url, timeout=40, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200 and len(r.content) > 5000:
            with open(path, "wb") as f:
                f.write(r.content)
            return True
    except Exception as e:
        print(f"دانلود تصویر خطا: {e}")
    return False


def fetch_related_background(query: str, path: str, fallback_index: int) -> bool:
    """جستجوی تصویر مرتبط با دارو از Unsplash Source / LoremFlickr"""
    q = (query or "pharmacy medicine").strip()
    q_encoded = quote(q)
    candidates = [
        f"https://loremflickr.com/1080/1920/{q_encoded.replace('%20', ',')}",
        f"https://source.unsplash.com/1080x1920/?{q_encoded}",
        FALLBACK_BG[fallback_index % len(FALLBACK_BG)],
    ]
    for url in candidates:
        print(f"تلاش پس‌زمینه: {url[:80]}...")
        if download_image(url, path):
            # اعتبارسنجی باز شدن با PIL
            try:
                Image.open(path).verify()
                print(f"پس‌زمینه مرتبط ذخیره شد برای: {q}")
                return True
            except Exception:
                continue
    return False


def create_slide_image(title: str, body: str, index: int, total: int, out_path: str, bg_path: str = None):
    if bg_path and os.path.exists(bg_path):
        bg = Image.open(bg_path).convert("RGB")
        bg = bg.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
        bg = ImageEnhance.Brightness(bg).enhance(0.48)
        bg = bg.filter(ImageFilter.GaussianBlur(radius=0.8))
    else:
        bg = Image.new("RGB", (WIDTH, HEIGHT), (12, 28, 42))

    img = bg.copy()

    # کارت متن خیلی پایین‌تر (~۷۸٪)
    card_top = int(HEIGHT * 0.78)
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.rectangle([0, card_top, WIDTH, HEIGHT], fill=(6, 16, 28, 230))
    odraw.rectangle([0, card_top, WIDTH, card_top + 6], fill=(0, 180, 160, 255))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    # فونت درشت‌تر
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
    """نریشن مردانه، ملایم و روان‌تر"""
    # صدای مردانه فارسی
    voice = "fa-IR-FaridNeural"
    communicate = edge_tts.Communicate(
        text.strip(),
        voice=voice,
        rate="-15%",   # آرام‌تر و طبیعی‌تر
        pitch="-4Hz",  # کمی بم‌تر و ملایم
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
    print("ویدیو نهایی ساخته شد (مناسب ریلز و یوتیوب شورت)")


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
                print(f"نریشن مردانه اسلاید {i} آماده")
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

🎬 ویدیو عمودی 1080x1920 (مناسب ریلز و یوتیوب شورت) ارسال شد.
"""
        send_message(full_text)
        send_photos(slide_paths)
        send_video(
            video_path,
            caption="🎬 آماده انتشار در اینستاگرام ریلز و یوتیوب شورت",
        )

    print("✅ تمام")


if __name__ == "__main__":
    main()
