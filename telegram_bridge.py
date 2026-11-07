"""Telegram control plane: generate previews, then publish only after admin approval."""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests
from publishers import publish_approved

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHANNEL_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
ADMIN_ID = os.environ.get("TELEGRAM_ADMIN_ID", "").strip()
API = f"https://api.telegram.org/bot{BOT_TOKEN}"
STATE_FILE = Path("state/last_update_id.txt")
APPROVAL_STATE = Path("state/pending_approvals.json")
EXPIRY_SECONDS = int(os.environ.get("APPROVAL_EXPIRY_SECONDS", str(24 * 3600)))


def tg(method: str, **payload):
    r = requests.post(f"{API}/{method}", json=payload, timeout=300)
    try: return r.json()
    except Exception: return {"ok": False, "description": r.text}


def send(chat_id, text: str):
    for i in range(0, len(text), 4000):
        tg("sendMessage", chat_id=chat_id, text=text[i:i + 4000])


def load_offset():
    try: return int(STATE_FILE.read_text().strip() or "0")
    except Exception: return 0


def save_offset(value):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(str(value))


def authorized_user(obj):
    if not ADMIN_ID: return True
    return str((obj.get("from") or {}).get("id", "")) == ADMIN_ID


def load_approvals():
    try: return json.loads(APPROVAL_STATE.read_text(encoding="utf-8"))
    except Exception: return {}


def save_approvals(data):
    APPROVAL_STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = APPROVAL_STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(APPROVAL_STATE)


def extract_topic(text):
    text = (text or "").strip()
    if text.startswith("/idea"):
        parts = text.split(maxsplit=1)
        return parts[1].strip() if len(parts) > 1 else ""
    return "" if text.startswith("/") else text


def run_agent(topic):
    env = os.environ.copy(); env["CUSTOM_TOPIC"] = topic
    return subprocess.run([sys.executable, "bot.py"], env=env, cwd=os.getcwd()).returncode


def handle_message(message):
    chat_id = (message.get("chat") or {}).get("id")
    text = (message.get("text") or message.get("caption") or "").strip()
    if not chat_id or not text: return
    if not authorized_user(message):
        send(chat_id, "⛔ شما اجازه مدیریت این ایجنت را ندارید."); return
    if text.lower() in ("/start", "/help", "start", "help"):
        send(chat_id, "💊 موضوع را با /idea موضوع یا به‌صورت متن بفرستید. پس از تولید، انتشار فقط با تأیید دکمه‌ای انجام می‌شود."); return
    if text.lower() == "/status":
        send(chat_id, f"✅ آماده است. حساب تأییدکننده: {ADMIN_ID or 'محدود نشده'}"); return
    topic = extract_topic(text)
    if not topic:
        send(chat_id, "موضوع مشخص نشد. مثال: /idea تداخل دارویی گریپ‌فروت"); return
    send(chat_id, f"✅ موضوع دریافت شد: «{topic}»\n⏳ در حال تولید پیش‌نمایش...")
    code = run_agent(topic)
    if code != 0: send(chat_id, f"⚠️ تولید محتوا با خطا متوقف شد (کد {code}).")


def download_telegram_file(file_id, target):
    meta = tg("getFile", file_id=file_id)
    if not meta.get("ok"): raise RuntimeError(meta.get("description", "getFile failed"))
    file_path = (meta.get("result") or {}).get("file_path")
    if not file_path: raise RuntimeError("Telegram file path missing")
    r = requests.get(f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}", timeout=300)
    r.raise_for_status(); Path(target).write_bytes(r.content)


def handle_callback(callback):
    tg("answerCallbackQuery", callback_query_id=callback.get("id"), text="در حال بررسی...")
    if not ADMIN_ID or not authorized_user(callback):
        return
    data = (callback.get("data") or "").split(":")
    if len(data) != 3 or data[0] != "approval": return
    approval_id, action = data[1], data[2]
    approvals = load_approvals(); item = approvals.get(approval_id)
    message = callback.get("message") or {}; chat_id = (message.get("chat") or {}).get("id")
    if not item: send(chat_id, "⚠️ این درخواست پیدا نشد یا قبلاً پردازش شده است."); return
    if item.get("status") != "pending": send(chat_id, f"این درخواست قبلاً پردازش شده: {item.get('status')}"); return
    if time.time() - float(item.get("created_at", 0)) > EXPIRY_SECONDS:
        item["status"] = "expired"; save_approvals(approvals); send(chat_id, "⚠️ اعتبار این پیش‌نمایش تمام شده است."); return
    if action == "reject":
        item["status"] = "rejected"; save_approvals(approvals); send(chat_id, "❌ انتشار رد شد."); return
    if action != "approve": return
    item["status"] = "publishing"; save_approvals(approvals)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "approved_short.mp4"
            download_telegram_file(item["video_file_id"], video)
            result = publish_approved(str(video), item)
        item["status"] = "published"; item["results"] = result; save_approvals(approvals)
        lines = ["✅ انتشار تأییدشده انجام شد."]
        for platform, info in result.items():
            if isinstance(info, dict) and info.get("url"): lines.append(f"{platform}: {info['url']}")
        if result.get("errors"): lines.append("⚠️ خطای بخشی: " + json.dumps(result["errors"], ensure_ascii=False))
        send(chat_id, "\n".join(lines))
    except Exception as exc:
        item["status"] = "failed"; item["error"] = str(exc); save_approvals(approvals)
        send(chat_id, f"⚠️ انتشار انجام نشد و وضعیت برای بررسی ذخیره شد:\n{exc}")


def main():
    if not BOT_TOKEN: print("TELEGRAM_BOT_TOKEN تنظیم نشده"); sys.exit(1)
    offset = load_offset()
    result = tg("getUpdates", offset=offset + 1 if offset else None, timeout=10, allowed_updates=["message", "callback_query"])
    if not result.get("ok"): raise RuntimeError(result)
    updates = result.get("result") or []; max_id = offset
    for update in updates:
        max_id = max(max_id, update.get("update_id", 0))
        if update.get("callback_query"): handle_callback(update["callback_query"])
        elif update.get("message"): handle_message(update["message"])
    if updates: save_offset(max_id)


if __name__ == "__main__": main()
