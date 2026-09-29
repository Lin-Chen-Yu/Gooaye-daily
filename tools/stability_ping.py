#!/usr/bin/env python3
"""穩定性測試：每次執行檢查 Telegram session、status.json，並寄一封信回報。
環境變數：TG_API_ID / TG_API_HASH / TG_SESSION / GMAIL_USER / GMAIL_APP_PASSWORD / MAIL_TO
      EXPECTED_UTC（選填，排程原定時間，用來算延遲）"""
import os, json, smtplib, traceback
import datetime as dt
from email.message import EmailMessage
from pathlib import Path

TPE = dt.timezone(dt.timedelta(hours=8))
now = dt.datetime.now(TPE)
lines = [f"執行時間：{now:%Y-%m-%d %H:%M:%S} 台北"]

try:
    from telethon.sync import TelegramClient
    from telethon.sessions import StringSession
    c = TelegramClient(StringSession(os.environ["TG_SESSION"]),
                       int(os.environ["TG_API_ID"]), os.environ["TG_API_HASH"])
    c.connect()
    me = c.get_me() if c.is_user_authorized() else None
    n = len(c.get_messages("Gooaye", limit=3)) if me else 0
    c.disconnect()
    tg = "OK" if me else "FAIL（session 失效）"
    lines.append(f"Telegram：{tg}，讀到最新 {n} 則")
except Exception as e:
    tg = "FAIL"
    lines.append(f"Telegram：FAIL {type(e).__name__}: {e}")

try:
    st = json.loads((Path(__file__).resolve().parent.parent / "status.json").read_text("utf-8"))
    lines.append(f"status.json：{st['status']} date={st['date']} count={st['count']} "
                 f"generated={st['generated_at_taipei']}")
except Exception as e:
    lines.append(f"status.json：讀取失敗 {e}")

exp = os.environ.get("EXPECTED_UTC")
if exp:
    delay = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(exp)).total_seconds() / 60
    lines.append(f"排程延遲：約 {delay:.1f} 分鐘")

user = os.environ["GMAIL_USER"]
pw = os.environ["GMAIL_APP_PASSWORD"].replace(" ", "")
msg = EmailMessage()
msg["Subject"] = f"[穩定性測試] {now:%H:%M} 台北 TG={tg.split('（')[0]}"
msg["From"] = user
msg["To"] = os.environ.get("MAIL_TO") or user
msg.set_content("\n".join(lines))
for i in range(3):
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=60) as s:
            s.starttls(); s.login(user, pw); s.send_message(msg)
        break
    except Exception:
        traceback.print_exc()
        if i == 2: raise
print("\n".join(lines))
