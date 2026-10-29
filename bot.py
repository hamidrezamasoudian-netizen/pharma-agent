import os
import google.generativeai as genai
import requests

# ۱. خواندن کلیدها از گاوصندوق گیت‌هاب
GOOGLE_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# ۲. تنظیم جمینای
genai.configure(api_key=GOOGLE_API_KEY)

# استفاده از مدل قدرتمندتر و حرفه‌ای‌تر برای مطالب تخصصی داروسازی
model = genai.GenerativeModel("gemini-1.5-pro")

# ۳. ایده یا موضوع پزشکی
idea_topic = (
    "بررسی مکانیسم‌های نوین و بازکارآمدی داروی متفورمین در بیماری‌های متابولیک"
)

prompt = f"""
تو یک دستیار تخصصی و حرفه‌ای در حوزه داروسازی هستی. 
بر اساس این موضوع: '{idea_topic}'، یک محتوای علمی، جذاب و استاندارد برای کانال تلگرام تولید کن که شامل عنوان جذاب، متن اصلی علمی و هشتگ‌های تخصصی باشد.
"""

# ۴. تولید محتوا با هوش مصنوعی
response = model.generate_content(prompt)
post_content = response.text

# ۵. ارسال خودکار به کانال تلگرام
telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
payload = {
    "chat_id": TELEGRAM_CHAT_ID,
    "text": f"💊 **پست خودکار ایجنت داروسازی**\n\n{post_content}",
    "parse_mode": "Markdown",
}

res = requests.post(telegram_url, json=payload)
print("نتیجه ارسال به تلگرام:", res.json())
print("\n=== محتوای تولید شده ===")
print(post_content)
