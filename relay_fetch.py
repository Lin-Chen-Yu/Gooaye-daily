#!/usr/bin/env python3
"""
從 Gmail（IMAP）收 Claude 排程寄來的「講解原稿」，轉成 out/<日期>/mail.html，
接著由 send_mail.py 用 SMTP 寄出（圖片以 inline cid 內嵌）。

原因：Claude 的雲端沙盒不能 git push，Gmail 連接器又會拿掉 <img>。
所以 Claude 只寄一封主旨為「[gooaye-src] 股癌 <日期> 貼文講解」的原稿給自己，
圖片位置用文字標記 [[IMG:media/xxxx.jpg]]；本腳本把標記換回 <img>。
處理完的原稿會移到垃圾桶（只動主旨含 [gooaye-src] 的信）。

環境變數：GMAIL_USER / GMAIL_APP_PASSWORD
"""
import os, re, sys, imaplib, email, html as htmllib, urllib.parse
from email.header import decode_header, make_header
from pathlib import Path

BASE = Path(__file__).resolve().parent
TAG = "[gooaye-src]"


def unwrap_google_links(h: str) -> str:
    # 連接器會把連結改成 https://www.google.com/url?q=<原網址>&...，還原成原網址
    def repl(m):
        u = htmllib.unescape(m.group(1))
        q = urllib.parse.parse_qs(urllib.parse.urlparse(u).query).get("q")
        return f'href="{htmllib.escape(q[0], quote=True)}"' if q else m.group(0)
    return re.sub(r'href="(https://www\.google\.com/url\?[^"]+)"', repl, h)


def main():
    user = os.environ.get("GMAIL_USER")
    pw = (os.environ.get("GMAIL_APP_PASSWORD") or "").replace(" ", "")
    if not user or not pw:
        print("缺 GMAIL_USER / GMAIL_APP_PASSWORD")
        return 1

    M = imaplib.IMAP4_SSL("imap.gmail.com")
    M.login(user, pw)
    M.select("INBOX")
    typ, data = M.search(None, "X-GM-RAW", '"subject:gooaye-src newer_than:3d"')
    ids = data[0].split() if typ == "OK" and data[0] else []
    print(f"找到 {len(ids)} 封原稿")

    for i in ids:
        typ, msgdata = M.fetch(i, "(RFC822)")
        msg = email.message_from_bytes(msgdata[0][1])
        subject = str(make_header(decode_header(msg.get("Subject", "")))).strip()
        if TAG not in subject:
            continue
        m = re.search(r"(\d{4}-\d{2}-\d{2})", subject)
        if not m:
            print(f"主旨沒有日期，略過：{subject}")
            continue
        date = m.group(1)
        outdir = BASE / "out" / date
        outdir.mkdir(parents=True, exist_ok=True)

        if not (outdir / "mail.sent").exists():
            body = None
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    body = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace")
                    break
            if body is None:
                print(f"{date} 原稿沒有 HTML，略過")
                continue
            body = unwrap_google_links(body)
            body = re.sub(r"\[\[IMG:\s*(media/[\w.\-]+)\s*\]\]",
                          r'<img src="\1" style="max-width:100%;height:auto;">', body)
            missing = [p for p in re.findall(r'<img src="(media/[^"]+)"', body)
                       if not (outdir / p).exists()]
            if missing:
                print(f"WARN {date} 找不到圖片：{missing}")
            (outdir / "mail.html").write_text(body, encoding="utf-8")
            (outdir / "mail_subject.txt").write_text(
                subject.replace(TAG, "").strip() + "\n", encoding="utf-8")
            print(f"{date} 已轉出 mail.html")
        else:
            print(f"{date} 已寄過，只清掉原稿")

        M.store(i, "+X-GM-LABELS", "\\Trash")

    M.expunge()
    M.logout()
    return 0


if __name__ == "__main__":
    sys.exit(main())
