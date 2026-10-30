import os
import re
import json
import random
import tempfile
from pathlib import Path

import requests
from google import genai
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import (
    ImageClip,
    concatenate_videoclips,
    AudioFileClip,
    CompositeAudioClip,
    afx,
)

# ===================== تنظیمات =====================
GOOGLE_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
CUSTOM_TOPIC = os.environ.get("CUSTOM_TOPIC", "").strip()

client = genai.Client(api_key=GOOGLE_API_KEY)
MODEL = "gemini-3.5-flash-lite"

# موضوعات پرطرفدار دارویی در ایران (اگر موضوع دستی ندهی)
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

WIDTH, HEIGHT = 1080, 1920  # نسبت استوری/ریلز اینستاگرام
SLIDE_DURATION = 4.5


def get_topic() -> str:
    if CUSTOM_TOPIC:
        print(f"موضوع دستی: {CUSTOM_TOPIC}")
        return CUSTOM_TOPIC
    topic = random.choice(TRENDING_TOPICS)
    print(f"موضوع روز (پرطرفدار): {topic}")
    return topic


def generate_content_package(topic: str) -> dict:
    """تولید بسته کامل محتوایی برای اینستاگرام با جمینای"""
    prompt = f"""
تو یک استراتژیست محتوای تخصصی داروسازی برای اینستاگرام در ایران هستی.
موضوع: «{topic}»

خروجی را فقط و فقط به صورت JSON معتبر (بدون توضیح اضافه) با این ساختار بده:
{{
  "caption": "کپشن کامل پست اینستاگرام (۳ تا ۵ پاراگراف، جذاب، علمی و غیرتبلیغاتی درمانی، با دعوت به کامنت)",
  "hashtags": "۱۰ تا ۱۵ هشتگ فارسی و انگلیسی مرتبط در یک خط",
  "story_text": "متن کوتاه استوری (حداکثر ۲ خط)",
  "slides": [
    {{"title": "عنوان کوتاه اسلاید ۱", "body": "متن اصلی اسلاید ۱ (حداکثر ۳۰ کلمه، واضح و خوانا)"}},
    {{"title": "عنوان اسلاید ۲", "body": "متن اسلاید ۲"}},
    {{"title": "عنوان اسلاید ۳", "body": "متن اسلاید ۳"}},
    {{"title": "عنوان اسلاید ۴", "body": "متن اسلاید ۴"}},
    {{"title": "نتیجه‌گیری", "body": "جمع‌بندی و دعوت به فالو/کامنت"}}
  ],
  "reel_script": "اسکریپت کوتاه ریلز ۳۰-۴۵ ثانیه‌ای به صورت گفتاری",
  "music_mood": "پیشنهاد حال و هوای موزیک (مثلاً آرام و حرفه‌ای)"
}}

قوانین:
- لحن رسمی، علمی و قابل اعتماد باشد.
- هیچ توصیه درمانی قطعی نده.
- متن‌ها کاملاً فارسی و روان باشند.
- JSON خالص برگردان.
"""
    response = client.models.generate_content(model=MODEL, contents=prompt)
    text = response.text.strip()
    # استخراج JSON از پاسخ
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("پاسخ جمینای JSON معتبر نبود")
    data = json.loads(match.group())
    return data


def find_font(size: int):
    """فونت مناسب فارسی"""
    candidates = [
        "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def wrap_text(text: str, font, max_width: int, draw) -> list:
    """شکستن متن فارسی به خطوط"""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [text]


def create_slide_image(title: str, body: str, index: int, total: int, out_path: str):
    """ساخت تصویر اسلاید حرفه‌ای با متن خوانا"""
    # پس‌زمینه گرادیان تیره داروخانه‌ای
    img = Image.new("RGB", (WIDTH, HEIGHT), (15, 32, 48))
    draw = ImageDraw.Draw(img)

    # نوار رنگی بالا
    draw.rectangle([0, 0, WIDTH, 18], fill=(0, 150, 136))
    # نوار پایین
    draw.rectangle([0, HEIGHT - 18, WIDTH, HEIGHT], fill=(0, 150, 136))

    title_font = find_font(64)
    body_font = find_font(48)
    footer_font = find_font(32)

    margin = 90
    max_text_width = WIDTH - 2 * margin

    # شماره اسلاید
    badge = f"{index}/{total}"
    draw.text((WIDTH - margin - 80, 50), badge, font=footer_font, fill=(0, 200, 180))

    # عنوان
    y = 220
    title_lines = wrap_text(title, title_font, max_text_width, draw)
    for line in title_lines:
        bbox = draw.textbbox((0, 0), line, font=title_font)
        w = bbox[2] - bbox[0]
        draw.text(((WIDTH - w) // 2, y), line, font=title_font, fill=(255, 255, 255))
        y += 85

    y += 40
    # خط جداکننده
    draw.line([(margin, y), (WIDTH - margin, y)], fill=(0, 150, 136), width=3)
    y += 60

    # متن بدنه
    body_lines = wrap_text(body, body_font, max_text_width, draw)
    for line in body_lines:
        bbox = draw.textbbox((0, 0), line, font=body_font)
        w = bbox[2] - bbox[0]
        draw.text(((WIDTH - w) // 2, y), line, font=body_font, fill=(220, 230, 240))
        y += 70

    # فوتر برند
    footer = "داروخانه دکتر مسعودیان | @drhrmasoudian"
    bbox = draw.textbbox((0, 0), footer, font=footer_font)
    w = bbox[2] - bbox[0]
    draw.text(((WIDTH - w) // 2, HEIGHT - 100), footer, font=footer_font, fill=(120, 160, 170))

    img.save(out_path, quality=95)
    print(f"اسلاید ساخته شد: {out_path}")


def download_soft_music(path: str):
    """دانلود یک موزیک پس‌زمینه کوتاه و آزاد (یا ساخت سکوت نرم در صورت شکست)"""
    # فایل کوتاه آزاد از منابع عمومی (در صورت شکست، ویدیو بدون صدا ساخته می‌شود)
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
                print("موزیک پس‌زمینه دانلود شد")
                return True
        except Exception as e:
            print(f"خطا در دانلود موزیک: {e}")
    print("موزیک دانلود نشد؛ ویدیو بدون صدا ساخته می‌شود")
    return False


def build_slideshow_video(slide_paths: list, music_path: str, output_path: str):
    """ساخت ویدیو اسلایدشویی با موزیک"""
    clips = []
    for p in slide_paths:
        clip = ImageClip(p).set_duration(SLIDE_DURATION).fadein(0.4).fadeout(0.4)
        clips.append(clip)

    video = concatenate_videoclips(clips, method="compose")

    if music_path and os.path.exists(music_path):
        try:
            audio = AudioFileClip(music_path)
            # حلقه یا برش موزیک به طول ویدیو
            if audio.duration < video.duration:
                audio = afx.audio_loop(audio, duration=video.duration)
            else:
                audio = audio.subclip(0, video.duration)
            audio = audio.volumex(0.25)  # صدای آرام پس‌زمینه
            video = video.set_audio(audio)
        except Exception as e:
            print(f"خطا در افزودن موزیک: {e}")

    video.write_videofile(
        output_path,
        fps=24,
        codec="libx264",
        audio_codec="aac",
        preset="ultrafast",
        threads=2,
        logger=None,
    )
    print(f"ویدیو ساخته شد: {output_path}")
    video.close()


def send_telegram_message(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    # تلگرام محدودیت طول دارد؛ در صورت نیاز تقسیم کن
    max_len = 4000
    chunks = [text[i : i + max_len] for i in range(0, len(text), max_len)]
    for chunk in chunks:
        res = requests.post(
            url,
            json={"chat_id": TELEGRAM_CHAT_ID, "text": chunk},
            timeout=60,
        )
        print("ارسال متن:", res.json().get("ok"))


def send_telegram_video(video_path: str, caption: str = ""):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
    with open(video_path, "rb") as f:
        res = requests.post(
            url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": caption[:1000],
            },
            files={"video": f},
            timeout=180,
        )
    print("ارسال ویدیو:", res.json())


def send_telegram_photos(image_paths: list):
    """ارسال اسلایدها به صورت آلبوم"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMediaGroup"
    media = []
    files = {}
    for i, path in enumerate(image_paths):
        key = f"photo{i}"
        media.append({"type": "photo", "media": f"attach://{key}"})
        files[key] = open(path, "rb")
    try:
        res = requests.post(
            url,
            data={"chat_id": TELEGRAM_CHAT_ID, "media": json.dumps(media)},
            files=files,
            timeout=120,
        )
        print("ارسال آلبوم تصاویر:", res.json().get("ok"))
    finally:
        for f in files.values():
            f.close()


def main():
    topic = get_topic()
    print("در حال تولید محتوا با جمینای...")
    package = generate_content_package(topic)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        slides = package.get("slides", [])[:5]
        if not slides:
            raise ValueError("اسلایدی تولید نشد")

        slide_paths = []
        for i, s in enumerate(slides, 1):
            path = str(tmp / f"slide_{i}.jpg")
            create_slide_image(
                title=s.get("title", f"اسلاید {i}"),
                body=s.get("body", ""),
                index=i,
                total=len(slides),
                out_path=path,
            )
            slide_paths.append(path)

        music_path = str(tmp / "bgm.mp3")
        has_music = download_soft_music(music_path)

        video_path = str(tmp / "instagram_slideshow.mp4")
        build_slideshow_video(
            slide_paths,
            music_path if has_music else "",
            video_path,
        )

        # متن کامل برای کپی در اینستاگرام
        full_text = f"""✅ بسته محتوای اینستاگرام آماده شد

📌 موضوع: {topic}

——— کپشن پست ———
{package.get('caption', '')}

{package.get('hashtags', '')}

——— متن استوری ———
{package.get('story_text', '')}

——— اسکریپت ریلز ———
{package.get('reel_script', '')}

——— حال موزیک پیشنهادی ———
{package.get('music_mood', 'آرام و حرفه‌ای')}

🎬 ویدیو اسلایدشویی + تصاویر جداگانه هم ارسال شد.
فقط کپی کن و در اینستاگرام منتشر کن.
"""

        send_telegram_message(full_text)
        send_telegram_photos(slide_paths)
        send_telegram_video(
            video_path,
            caption="🎬 ویدیو اسلایدشویی آماده انتشار در اینستاگرام",
        )

    print("✅ همه مراحل با موفقیت انجام شد")


if __name__ == "__main__":
    main()
