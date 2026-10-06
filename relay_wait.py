#!/usr/bin/env python3
"""
Gooaye Fetch 完成後由 workflow_run 觸發：等 Claude 的原稿寄到 Gmail 再往下寄正式信。
- 今天已寄過 / 今天抓取不是 OK / count=0 → 輸出 ready=false，直接結束。
- 否則每 2 分鐘用 IMAP 查一次「[gooaye-src] 股癌 <今天> 貼文講解」，
  找到 → ready=true；超過 DEADLINE（台北時間）仍沒有 → ready=false（cron 仍會補）。
環境變數：GMAIL_USER / GMAIL_APP_PASSWORD；輸出寫到 $GITHUB_OUTPUT。
"""
import os, json, time, imaplib, datetime as dt
from pathlib import Path

BASE = Path(__file__).resolve().parent
TPE = dt.timezone(dt.timedelta(hours=8))
DEADLINE_HHMM = os.environ.get("WAIT_DEADLINE", "14:30")
INTERVAL = 120


def out(ready: bool):
    with open(os.environ.get("GITHUB_OUTPUT", "/dev/null"), "a") as f:
        f.write(f"ready={'true' if ready else 'false'}\n")
    print("ready =", ready)


def draft_exists(day: str) -> bool:
    user = os.environ["GMAIL_USER"]
    pw = os.environ["GMAIL_APP_PASSWORD"].replace(" ", "")
    M = imaplib.IMAP4_SSL("imap.gmail.com")
    try:
        M.login(user, pw)
        M.select("INBOX", readonly=True)
        typ, data = M.search(None, "X-GM-RAW", f'"subject:gooaye-src subject:{day} newer_than:2d"')
        return typ == "OK" and bool(data[0].split())
    finally:
        try: M.logout()
        except Exception: pass


def main():
    now = dt.datetime.now(TPE)
    day = now.strftime("%Y-%m-%d")

    if (BASE / "out" / day / "mail.sent").exists():
        print(f"{day} 已寄過"); return out(False)
    try:
        s = json.load(open(BASE / "status.json"))
    except Exception as e:
        print("讀不到 status.json：", e); return out(False)
    if s.get("date") != day or s.get("status") != "OK" or not s.get("count"):
        print(f"今天不需要寄：date={s.get('date')} status={s.get('status')} count={s.get('count')}")
        return out(False)

    hh, mm = map(int, DEADLINE_HHMM.split(":"))
    deadline = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    while True:
        try:
            if draft_exists(day):
                print(f"{dt.datetime.now(TPE):%H:%M} 找到 {day} 原稿"); return out(True)
        except Exception as e:
            print("IMAP 錯誤（稍後重試）：", e)
        if dt.datetime.now(TPE) >= deadline:
            print(f"到 {DEADLINE_HHMM} 仍沒有原稿，交給 cron 補寄"); return out(False)
        print(f"{dt.datetime.now(TPE):%H:%M} 尚無原稿，{INTERVAL}s 後再查")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
