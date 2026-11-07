# pharma-agent

ایجنت تولید محتوای علمی داروسازی برای ویدئوهای عمودی YouTube Shorts و Instagram Reels.

## قابلیت‌های فعلی

- انتخاب موضوع از Google Trends RSS ایران و، در صورت تنظیم کلید، از نتایج پرطرفدار YouTube.
- حذف موضوع‌های تکراری با نگهداری تاریخچه در `state/topic_history.json`.
- تولید سناریوی ۵ بخشی با هوک ابتدای ویدئو، نکته‌های کوتاه، هشدار ایمنی و جمع‌بندی.
- خروجی ۹:۱۶ با حرکت آرام Ken Burns، نریشن فارسی، صدای پس‌زمینه کم‌حجم و زیرنویس چسبیده فارسی با فرمت ASS.
- مناسب برای خروجی کوتاه ۳۰ تا ۶۰ ثانیه؛ موضوعات دستی تلگرام همچنان با `CUSTOM_TOPIC` پشتیبانی می‌شوند.

## تنظیمات اختیاری

- `TREND_RSS_URLS`: فهرست URLهای RSS جداشده با کاما؛ به‌صورت پیش‌فرض Google Trends ایران استفاده می‌شود.
- `YOUTUBE_API_KEY`: برای اضافه‌کردن سیگنال جست‌وجوی پرطرفدار YouTube.
- `TREND_QUERY`: عبارت جست‌وجوی پیش‌فرض برای YouTube؛ مقدار پیش‌فرض `دارو سلامت پزشکی` است.
- `TOPIC_STATE_FILE`: مسیر تاریخچه موضوع‌ها؛ مقدار پیش‌فرض `state/topic_history.json` است.

تاریخچه موضوع‌ها توسط GitHub Actions commit می‌شود تا اجرای بعدی موضوع‌های قبلی را دوباره انتخاب نکند. انتشار در شبکه‌های اجتماعی باید در مرحله تأیید تلگرام انجام شود و تولید ویدئو به‌تنهایی پستی را منتشر نمی‌کند.

## اجرا

```bash
pip install -r requirements.txt
python bot.py
```

برای اجرای بدون موضوع دستی، `GEMINI_API_KEY` و برای ارسال تلگرام، متغیرهای Telegram موجود در Workflow را تنظیم کنید.

## تأیید تلگرام و انتشار

پس از تولید، پیش‌نمایش به `TELEGRAM_APPROVAL_CHAT_ID` ارسال می‌شود و فقط کاربری که شناسه‌اش در `TELEGRAM_ADMIN_ID` است می‌تواند دکمه تأیید را بزند. درخواست‌ها در `state/pending_approvals.json` ذخیره می‌شوند و پس از ۲۴ ساعت منقضی می‌شوند.

Secretهای لازم برای Workflow پل تلگرام:

- `TELEGRAM_ADMIN_ID` و در صورت تفاوت `TELEGRAM_APPROVAL_CHAT_ID`
- `YOUTUBE_CLIENT_SECRETS_JSON` و `YOUTUBE_REFRESH_TOKEN`
- `INSTAGRAM_USER_ID` و `INSTAGRAM_ACCESS_TOKEN`
- `YOUTUBE_PRIVACY_STATUS` (پیشنهاد: `unlisted` برای تست)
- `ENABLE_YOUTUBE_PUBLISH` و `ENABLE_INSTAGRAM_PUBLISH`

هر دو انتشار فقط بعد از callback تأیید انجام می‌شوند. برای تست مستقل، ابتدا `ENABLE_YOUTUBE_PUBLISH=false` و `ENABLE_INSTAGRAM_PUBLISH=false` تنظیم کنید؛ سپس هرکدام را جداگانه فعال کنید.

## ساخت Refresh Token یوتیوب

فایل OAuth Client را فقط روی رایانه خود نگه دارید و آن را commit نکنید. سپس در همان رایانه اجرا کنید:

```bash
pip install -r requirements.txt
python tools/youtube_oauth.py /path/to/client_secret.json
```

پنجره Google باز می‌شود؛ با حساب کانال YouTube وارد شوید و دسترسی upload را تأیید کنید. مقدار چاپ‌شده را فقط در GitHub Actions Secret با نام `YOUTUBE_REFRESH_TOKEN` قرار دهید. خود فایل Client نیز باید به‌صورت متن کامل JSON در Secret `YOUTUBE_CLIENT_SECRETS_JSON` قرار گرفته باشد. هیچ‌کدام را در چت یا GitHub code قرار ندهید.

## حالت فعلی: خروجی انیمه و بارگذاری دستی

سبک پیش‌فرض تولید `anime` است. ویدیو، کپشن، هشتگ، نریشن و زیرنویس فارسی در تلگرام ارسال می‌شوند تا به‌صورت دستی در YouTube Shorts و Instagram Reels بارگذاری شوند. حالت خودکار ناشرها در Workflow با `MANUAL_UPLOAD_MODE=true` خاموش شده است؛ کد اتصال و ناشرها برای استفاده آینده حفظ شده‌اند. برای تغییر سبک به حالت قبلی می‌توان `VISUAL_STYLE=photorealistic` را تنظیم کرد.

## برنامه زمانی تولید

تولید خودکار روزانه دو بار در ساعت ۱۰:۰۰ و ۲۲:۰۰ به وقت تهران تنظیم شده است. منابع موضوع شامل Google Trends ایران و فیدهای سلامت/دارو و پربازدید رسانه‌های فارسی است؛ تاریخچه و تشابه معنایی عنوان‌ها برای جلوگیری از تکرار بررسی می‌شود.


شخصیت مرجع انیمه در `assets/anime_pharmacist_master.jpg` ذخیره شده و به‌صورت پیش‌فرض در همه ویدیوها استفاده می‌شود تا چهره و سبک ثابت بماند و وابستگی به سهمیه تولید تصویر Gemini حذف شود. لب‌خوانی دقیق در سطح حرفه‌ای هنوز فعال نشده است؛ برای آن باید یک موتور lip-sync ویدیویی جداگانه مثل Wav2Lip/SadTalker یا سرویس ویدیویی دارای API وارد خط تولید شود، چون FFmpeg به‌تنهایی حرکت طبیعی لب تولید نمی‌کند.
