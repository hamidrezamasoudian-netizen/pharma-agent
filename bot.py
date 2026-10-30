import os
import re
import json
import random
import asyncio
import tempfile
from pathlib import Path

import requests
import edge_tts
import arabic_reshaper
from bidi.algorithm import get_display
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
SLIDE_DURATION = 5.0

# تصاویر پس‌زمینه مرتبط با دارو (Unsplash - رایگان)
BG_URLS = [
    "https://images.unsplash.com/photo-1587854692152-cbe660dbde88?w=1080&h=1920&fit=crop",
    "https://images.unsplash.com/photo-1471864190281-a93a3070b6de?w=1080&h=1920&fit=crop",
    "https://images.unsplash.com/photo-1631549916768-4119b2e5f926?w=1080&h=1920&fit=crop",
    "https://images.unsplash.com/photo-1585435557343-3b092031a831?w=1080&h=1920&fit=crop",
    "https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?w=1080&h=1920&fit=crop",
    "https://images.unsplash.com/photo-1576602976047-174e57a47881?w=1080&h=1920&fit=crop",
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
تو یک استراتژیست محتوای تخصصی داروسازی برای اینستاگرام در ایران هستی.
موضوع: «{topic}»

خروجی را فقط به صورت JSON معتبر بده (بدون متن اضافه):
{{
  "caption": "کپشن کامل پست (۳ تا ۵ پاراگراف علمی، جذاب، غیرتبلیغاتی درمانی)",
  "hashtags": "۱۲ هشتگ فارسی و انگلیسی در یک خط",
  "story_text": "متن کوتاه استوری حداکثر ۲ خط",
  "slides": [
    {{"title": "عنوان کوتاه اسلاید ۱", "body": "متن واضح حداکثر ۲۵ کلمه"}},
    {{"title": "عنوان اسلاید ۲", "body": "متن واضح حداکثر ۲۵ کلمه"}},
    {{"title": "عنوان اسلاید ۳", "body": "متن واضح حداکثر ۲۵ کلمه"}},
    {{"title": "عنوان اسلاید ۴", "body": "متن واضح حداکثر ۲۵ کلمه"}},
    {{"title": "جمع‌بندی", "body": "نتیجه و دعوت به تعامل حداکثر ۲۵ کلمه"}}
  ],
  "narration": "متن نریشن پیوسته برای کل ویدیو (۸۰ تا ۱۲۰ کلمه، گفتاری و روان، مناسب خواندن با صدای گوینده)",
  "music_mood": "آرام و حرفه‌ای"
}}
قوانین: فارسی روان، بدون توصیه درمانی قطعی، JSON خالص.
"""
    response = client.models.generate_content(model=MODEL, contents=prompt)
    text = response.text.strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("JSON معتبر از جمینای دریافت نشد")
    return json.loads(match.group())


def fa(text: str) -> str:
    """آماده‌سازی متن فارسی برای نمایش صحیح (RTL + اتصال حروف)"""
    if not text:
        return ""
    reshaped = arabic_reshaper.reshape(str(text))
    return get_display(reshaped)


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
        # برای اندازه‌گیری از نسخه reshapeشده استفاده می‌کنیم
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


def download_background(index: int, path: str) -> bool:
    url = BG_URLS[index % len(BG_URLS)]
    try:
        r = requests.get(url, timeout=40, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200 and len(r.content) > 5000:
            with open(path, "wb") as f:
                f.write(r.content)
            return True
    except Exception as e:
        print(f"خطا در دانلود پس‌زمینه: {e}")
    return False


def create_slide_image(title: str, body: str, index: int, total: int, out_path: str, bg_path: str = None):
    """اسلاید با پس‌زمینه دارویی + کارت متن در پایین"""
    # پس‌زمینه
    if bg_path and os.path.exists(bg_path):
        bg = Image.open(bg_path).convert("RGB")
        bg = bg.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
        # کمی تیره و محو برای خوانایی متن
        bg = ImageEnhance.Brightness(bg).enhance(0.55)
        bg = bg.filter(ImageFilter.GaussianBlur(radius=1.2))
    else:
        bg = Image.new("RGB", (WIDTH, HEIGHT), (12, 28, 42))

    img = bg.copy()
    draw = ImageDraw.Draw(img, "RGBA")

    # لایه تیره پایین برای کارت متن
    card_top = int(HEIGHT * 0.58)
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.rectangle([0, card_top, WIDTH, HEIGHT], fill=(10, 25, 40, 210))
    # نوار رنگی بالای کارت
    odraw.rectangle([0, card_top, WIDTH, card_top + 8], fill=(0, 180, 160, 255))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    title_font = load_font(54, bold=True)
    body_font = load_font(42)
    footer_font = load_font(28)

    margin = 70
    max_w = WIDTH - 2 * margin
    y = card_top + 40

    # شماره اسلاید
    badge = fa(f"{index} / {total}")
    draw.text((margin, card_top + 16), badge, font=footer_font, fill=(0, 200, 180))

    # عنوان
    for line in wrap_fa(title, title_font, max_w, draw):
        line_fa = fa(line)
        bbox = draw.textbbox((0, 0), line_fa, font=title_font)
        w = bbox[2] - bbox[0]
        draw.text(((WIDTH - w) // 2, y), line_fa, font=title_font, fill=(255, 255, 255))
        y += 70

    y += 10
    # متن بدنه
    for line in wrap_fa(body, body_font, max_w, draw):
        line_fa = fa(line)
        bbox = draw.textbbox((0, 0), line_fa, font=body_font)
        w = bbox[2] - bbox[0]
        draw.text(((WIDTH - w) // 2, y), line_fa, font=body_font, fill=(220, 230, 240))
        y += 58

    # فوتر
    footer = fa("داروخانه دکتر مسعودیان  |  @drhrmasoudian")
    bbox = draw.textbbox((0, 0), footer, font=footer_font)
    w = bbox[2] - bbox[0]
    draw.text(((WIDTH - w) // 2, HEIGHT - 70), footer, font=footer_font, fill=(140, 180, 190))

    img.save(out_path, quality=95)
    print(f"اسلاید {index} ساخته شد")


async def make_narration(text: str, out_path: str):
    """نریشن فارسی با edge-tts"""
    # صداهای فارسی مایکروسافت
    voices = ["fa-IR-DilaraNeural", "fa-IR-FaridNeural"]
    voice = voices[0]
    communicate = edge_tts.Communicate(text, voice=voice, rate="-5%")
    await communicate.save(out_path)
    print(f"نریشن ساخته شد: {out_path}")


def download_soft_music(path: str) -> bool:
    urls = [
        "https://cdn.pixabay.com/download/audio/2022/03/15/audio_2bafa8c5f0.mp3?filename=soft-background-112199.mp3",
        "https://cdn.pixabay.com/download/audio/2021/08/04/audio_12b0c7443c.mp3?filename=relaxing-145038.mp3",
    ]
    for url in urls:
        try:
            r = requests.get(url, timeout=30)
            if r.status_code == 200 and len(r.content) > 10000:
                with open(path, "wb") as f:
                    f.write(r.content)
                return True
        except Exception:
            pass
    return False


def build_video(slide_paths, narration_path, music_path, output_path):
    clips = [
        ImageClip(p).set_duration(SLIDE_DURATION).fadein(0.35).fadeout(0.35)
        for p in slide_paths
    ]
    video = concatenate_videoclips(clips, method="compose")

    audio_clips = []
    if narration_path and os.path.exists(narration_path):
        try:
            nar = AudioFileClip(narration_path)
            # اگر نریشن کوتاه‌تر/بلندتر از ویدیو بود تنظیم کن
            if nar.duration < video.duration:
                # سکوت اضافه نمی‌کنیم؛ ویدیو را به طول نریشن نزدیک می‌کنیم
                pass
            else:
                nar = nar.subclip(0, video.duration)
            audio_clips.append(nar.volumex(1.0))
        except Exception as e:
            print(f"خطا نریشن: {e}")

    if music_path and os.path.exists(music_path):
        try:
            bgm = AudioFileClip(music_path)
            if bgm.duration < video.duration:
                bgm = afx.audio_loop(bgm, duration=video.duration)
            else:
                bgm = bgm.subclip(0, video.duration)
            audio_clips.append(bgm.volumex(0.18))
        except Exception as e:
            print(f"خطا موزیک: {e}")

    if audio_clips:
        video = video.set_audio(CompositeAudioClip(audio_clips))

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

        for i, s in enumerate(slides, 1):
            bg_file = str(tmp / f"bg_{i}.jpg")
            download_background(i - 1, bg_file)
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

        # نریشن
        narration_text = package.get("narration") or " ".join(
            f"{s.get('title', '')}. {s.get('body', '')}" for s in slides
        )
        nar_path = str(tmp / "narration.mp3")
        try:
            asyncio.run(make_narration(narration_text, nar_path))
        except Exception as e:
            print(f"نریشن ساخته نشد: {e}")
            nar_path = ""

        music_path = str(tmp / "bgm.mp3")
        has_music = download_soft_music(music_path)

        video_path = str(tmp / "instagram_reel.mp4")
        build_video(
            slide_paths,
            nar_path,
            music_path if has_music else "",
            video_path,
        )

        full_text = f"""✅ بسته جدید اینستاگرام (نسخه بهبودیافته)

📌 موضوع: {topic}

——— کپشن ———
{package.get('caption', '')}

{package.get('hashtags', '')}

——— استوری ———
{package.get('story_text', '')}

——— متن نریشن ———
{narration_text}

🎬 ویدیو اسلایدشویی با نریشن + آلبوم تصاویر ارسال شد.
"""
        send_message(full_text)
        send_photos(slide_paths)
        send_video(video_path, caption="🎬 ریلز اسلایدشویی با نریشن آماده انتشار")

    print("✅ تمام")


if __name__ == "__main__":
    main()
