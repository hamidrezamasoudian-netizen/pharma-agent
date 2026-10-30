"""
رابط مدیریتی ایجنت از طریق بات تلگرام

دستورات (در چت خصوصی با بات):
  /start          راهنما
  /help           راهنما
  /idea موضوع     تولید محتوا با موضوع دلخواه
  /status         وضعیت
  یا فقط متن موضوع را بفرستید
"""

import os
import json
import subprocess
import sys
from pathlib import Path

import requests

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHANNEL_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
# آیدی عددی تلگرام شما (اختیاری ولی توصیه‌شده) — فقط این کاربر اجازه مدیریت دارد
ADMIN_ID = os.environ.get("TELEGRAM_ADMIN_ID", "").strip()

API = f"https://api.telegram.org/bot{BOT_TOKEN}"
STATE_FILE = Path("state/last_update_id.txt")


def tg(method: str, **payload):
    r = requests.post(f"{API}/{method}", json=payload, timeout=60)
    try:
        return r.json()
    except Exception:
        return {"ok": False, "description": r.text}


def send(chat_id, text: str):
    # تقسیم پیام‌های بلند
    for i in range(0, len(text), 4000):
        res = tg("sendMessage", chat_id=chat_id, text=text[i : i + 4000])
        print("sendMessage:", res.get("ok"), res.get("description", ""))


def load_offset() -> int:
    if STATE_FILE.exists():
        try:
            return int(STATE_FILE.read_text().strip() or "0")
        except Exception:
            return 0
    return 0


def save_offset(value: int):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(str(value))


def is_authorized(message: dict) -> bool:
    """اگر ADMIN_ID تنظیم شده فقط همان کاربر؛ وگرنه هر کسی که به بات پیام بدهد."""
    if not ADMIN_ID:
        return True
    user = message.get("from") or {}
    uid = str(user.get("id", ""))
    return uid == ADMIN_ID


def help_text() -> str:
    return """💊 مدیریت ایجنت داروسازی

از این بات می‌توانید موضوع محتوا بدهید تا ایجنت برایتان تولید کند.

دستورات:
• /idea موضوع دلخواه
  مثال: /idea متفورمین و کلیه

• یا فقط موضوع را در یک پیام بفرستید
  مثال: آمپول‌های لاغری و عوارض آن

• /status — وضعیت سیستم
• /help — همین راهنما

نتیجه (کپشن + اسلاید + ویدیو) در کانال منتشر می‌شود.
زمان‌بندی روزانه خودکار: هر شب ساعت ۲۲ تهران.
"""


def extract_topic(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    if text.startswith("/idea"):
        parts = text.split(maxsplit=1)
        return parts[1].strip() if len(parts) > 1 else ""
    if text.startswith("/"):
        return ""  # سایر دستورات
    return text


def run_agent(topic: str) -> int:
    env = os.environ.copy()
    env["CUSTOM_TOPIC"] = topic
    print(f"اجرای ایجنت با موضوع: {topic}")
    result = subprocess.run(
        [sys.executable, "bot.py"],
        env=env,
        cwd=os.getcwd(),
    )
    return result.returncode


def handle_message(message: dict):
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = message.get("text") or message.get("caption") or ""
    text = text.strip()

    if not chat_id or not text:
        return

    if not is_authorized(message):
        send(chat_id, "⛔ شما اجازه مدیریت این ایجنت را ندارید.")
        return

    lower = text.lower()

    if lower in ("/start", "/help", "start", "help"):
        send(chat_id, help_text())
        return

    if lower == "/status":
        send(
            chat_id,
            "✅ ایجنت آماده است.\n"
            f"کانال انتشار: {CHANNEL_ID or '—'}"
            "\nبرای تولید محتوا موضوع را بفرستید یا از /idea استفاده کنید.",
        )
        return

    topic = extract_topic(text)
    if not topic:
        send(chat_id, "موضوع مشخص نشد.\nمثال:\n/idea ویتامین D و کمبود آن در ایران")
        return

    send(
        chat_id,
        f"✅ موضوع دریافت شد:\n«{topic}»\n\n⏳ در حال تولید محتوا...\nنتیجه در کانال ارسال می‌شود.",
    )

    code = run_agent(topic)
    if code == 0:
        send(
            chat_id,
            "🎉 تولید محتوا تمام شد.\nکپشن، اسلایدها و ویدیو در کانال قرار گرفت.\nمی‌توانید مستقیماً در اینستاگرام/یوتیوب شورت منتشر کنید.",
        )
    else:
        send(
            chat_id,
            f"⚠️ تولید محتوا با خطا متوقف شد (کد {code}).\nلطفاً کمی بعد دوباره تلاش کنید یا لاگ Actions را ببینید.",
        )


def main():
    if not BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN تنظیم نشده")
        sys.exit(1)

    offset = load_offset()
    print(f"offset فعلی: {offset}")

    res = tg(
        "getUpdates",
        offset=offset + 1 if offset else None,
        timeout=10,
        allowed_updates=["message"],
    )

    if not res.get("ok"):
        print("getUpdates failed:", res)
        sys.exit(1)

    updates = res.get("result") or []
    print(f"تعداد آپدیت جدید: {len(updates)}")

    if not updates:
        print("پیام جدیدی نیست")
        return

    # فقط آخرین پیام‌های متنی را پردازش می‌کنیم تا صف شلوغ نشود
    # از قدیمی به جدید
    max_id = offset
    processed_topics = 0

    for upd in updates:
        uid = upd.get("update_id", 0)
        max_id = max(max_id, uid)
        message = upd.get("message") or upd.get("channel_post")
        if not message:
            continue

        text = (message.get("text") or "").strip()
        # نادیده گرفتن پیام‌های کانال عمومی (فقط چت خصوصی/دستور)
        chat_type = (message.get("chat") or {}).get("type")
        if chat_type == "channel":
            continue

        if text:
            handle_message(message)
            processed_topics += 1
            # در هر اجرا حداکثر ۱ موضوع تولید شود تا تایم‌اوت نخورد
            break

    save_offset(max_id)
    print(f"offset جدید: {max_id} | پردازش‌شده: {processed_topics}")


if __name__ == "__main__":
    main()
