#!/usr/bin/env python3
"""
把 out/<日期>/mail.html 用 Gmail SMTP 寄出，圖片以 inline cid 穿插（雲端版）。

由 .github/workflows/mail.yml 在「Claude 推了 mail.html 上來」時觸發。
掃描所有 out/*/mail.html，凡是還沒有同層 mail.sent 的就寄出，寄完寫下 mail.sent
（mail.sent 會被 workflow commit 回 repo，所以去重狀態是持久的）。

為什麼寄信留在 Actions 而不是交給 Gmail 連接器：連接器要把圖片以 base64
塞進工具參數裡，一張圖大約 5 萬 token，三張就把成本推高 30 倍；SMTP 直接
讀檔案，零成本。Claude 只負責產出 HTML。

環境變數：GMAIL_USER / GMAIL_APP_PASSWORD / MAIL_TO
用法：python send_mail.py            掃描全部未寄的
      python send_mail.py 2026-09-22 只處理指定日期
      python send_mail.py 2026-09-22 --force  忽略 mail.sent 強制重寄
"""
import os, sys, re, time, smtplib, mimetypes, traceback
import datetime as dt
from pathlib import Path
from email.message import EmailMessage
from email.utils import make_msgid
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parent
TPE = ZoneInfo("Asia/Taipei")


def log(msg):
    print(f"{dt.datetime.now(TPE):%Y-%m-%d %H:%M:%S} 台北 | {msg}", flush=True)


def send_one(outdir: Path, user: str, pw: str, to: str, force: bool) -> bool:
    date = outdir.name
    html_path = outdir / "mail.html"
    sent_flag = outdir / "mail.sent"
    if not html_path.exists():
        return True
    if sent_flag.exists() and not force:
        return True

    subj_path = outdir / "mail_subject.txt"
    subject = (subj_path.read_text(encoding="utf-8").strip()
               if subj_path.exists() else f"股癌 {date} 貼文講解")
    html = html_path.read_text(encoding="utf-8")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    msg.set_content("此信為 HTML 格式，請用支援 HTML 的信箱檢視。")

    inline = []

    def repl(m):
        src = m.group(1)
        p = (outdir / src).resolve()
        if not p.exists():
            log(f"WARN | 找不到圖片 {src}，保留原樣")
            return m.group(0)
        cid = make_msgid(domain="gooaye.local")[1:-1]
        inline.append((cid, p))
        return m.group(0).replace(src, f"cid:{cid}")

    html_cid = re.sub(r'<img[^>]*?src="([^"]+)"', repl, html)
    msg.add_alternative(html_cid, subtype="html")

    html_part = msg.get_payload()[-1]
    for cid, p in inline:
        ctype, _ = mimetypes.guess_type(str(p))
        maintype, subtype = (ctype or "image/jpeg").split("/", 1)
        html_part.add_related(p.read_bytes(), maintype=maintype, subtype=subtype,
                              cid=f"<{cid}>", filename=p.name)

    # 587(STARTTLS) 與 465(SSL) 輪流試：某個 port 被擋或閃斷時另一個常常還通
    for attempt in range(1, 5):
        try:
            if attempt % 2 == 1:
                with smtplib.SMTP("smtp.gmail.com", 587, timeout=60) as s:
                    s.ehlo(); s.starttls(); s.ehlo()
                    s.login(user, pw)
                    s.send_message(msg)
            else:
                with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=60) as s:
                    s.login(user, pw)
                    s.send_message(msg)
            break
        except Exception:
            log(f"WARN | {date} 寄信失敗（第 {attempt}/4 次）\n{traceback.format_exc()}")
            if attempt == 4:
                log(f"FAIL | {date} 寄信放棄，等下一輪補寄排程；仍失敗會開 GitHub Issue")
                return False
            time.sleep(15 * attempt)

    sent_flag.write_text(dt.datetime.now(TPE).isoformat(), encoding="utf-8")
    log(f"OK | {date} 已寄出「{subject}」→ {to}，內嵌圖片 {len(inline)} 張")
    return True


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force = "--force" in sys.argv

    user = os.environ.get("GMAIL_USER")
    pw = (os.environ.get("GMAIL_APP_PASSWORD") or "").replace(" ", "")
    to = os.environ.get("MAIL_TO") or user
    if not user or not pw:
        log("FAIL | 缺 GMAIL_USER / GMAIL_APP_PASSWORD")
        return 1

    if args:
        dirs = [BASE / "out" / args[0]]
    else:
        dirs = sorted((BASE / "out").glob("????-??-??"))

    ok = True
    todo = 0
    for d in dirs:
        if (d / "mail.html").exists() and (force or not (d / "mail.sent").exists()):
            todo += 1
            ok &= send_one(d, user, pw, to, force)
    if todo == 0:
        log("沒有待寄的 mail.html，結束")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
