#!/usr/bin/env python3
"""
抓取 Telegram 公開頻道 Gooaye 股癌 過去 N 小時的貼文（GitHub Actions 雲端版）。

與本機版 gooaye_fetch.py 的差異：
  - session 改用 StringSession，從環境變數 TG_SESSION 讀，不需要 .session 檔。
  - 拿掉「等 Wi-Fi 就緒」的迴圈：Actions runner 一開機網路就是通的。
  - 拿掉 run_log.txt：改寫 status.json（機器可讀），執行全文交給 Actions log。
  - 一律 exit 0，成敗寫在 status.json 裡，由 workflow 的最後一步判斷，
    確保「失敗」這件事也會被 commit 上去讓下游看得到。

環境變數：TG_API_ID / TG_API_HASH / TG_SESSION
用法：python fetch.py [hours]   預設 26
"""
import os, sys, json, traceback, shutil
import datetime as dt
from pathlib import Path

BASE = Path(__file__).resolve().parent
CHANNEL = "Gooaye"
TAIPEI = dt.timezone(dt.timedelta(hours=8))
KEEP_DAYS = 30          # 工作目錄只留最近 30 天，更早的靠 git 歷史
STATUS = BASE / "status.json"

hours = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 26
now_tpe = dt.datetime.now(TAIPEI)
today = now_tpe.strftime("%Y-%m-%d")

state = {
    "status": "FAIL",
    "date": today,
    "hours": hours,
    "count": None,
    "dir": f"out/{today}",
    "generated_at_taipei": now_tpe.strftime("%Y-%m-%d %H:%M:%S"),
    "generated_at_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    "posts": [],
    "error": "執行被中斷，沒有走完流程",
}


def save_status():
    STATUS.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")


def main():
    api_id = int(os.environ["TG_API_ID"])
    api_hash = os.environ["TG_API_HASH"]
    session = os.environ["TG_SESSION"]

    from telethon.sync import TelegramClient
    from telethon.sessions import StringSession
    from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument

    outdir = BASE / "out" / today
    mediadir = outdir / "media"
    mediadir.mkdir(parents=True, exist_ok=True)

    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)

    client = TelegramClient(StringSession(session), api_id, api_hash)
    client.connect()
    if not client.is_user_authorized():
        client.disconnect()
        raise RuntimeError(
            "TG_SESSION 已失效或未登入。請在本機重跑 tools/make_session.py "
            "產生新的 StringSession，更新 repo secret TG_SESSION。")

    # 真的能跟伺服器講到話才算連線成功（防「連上了但其實抓不到」的假成功）
    if client.get_me() is None:
        client.disconnect()
        raise RuntimeError("已連線但 get_me() 回傳 None")

    rows = []
    for msg in client.iter_messages(CHANNEL, limit=200):
        if msg.date < cutoff:
            break

        media_note = ""
        if msg.media:
            try:
                if isinstance(msg.media, MessageMediaPhoto):
                    p = msg.download_media(file=str(mediadir / f"{msg.id}"))
                    media_note = f"圖片: media/{Path(p).name}"
                elif isinstance(msg.media, MessageMediaDocument):
                    mime = getattr(msg.media.document, "mime_type", "") or ""
                    if mime.startswith("video"):
                        p = msg.download_media(file=str(mediadir / f"{msg.id}_thumb"),
                                               thumb=-1)
                        media_note = f"影片（僅縮圖）: media/{Path(p).name}"
                    else:
                        p = msg.download_media(file=str(mediadir / f"{msg.id}"))
                        media_note = f"檔案: media/{Path(p).name}"
                else:
                    media_note = f"其他媒體: {type(msg.media).__name__}"
            except Exception as e:
                media_note = f"媒體下載失敗: {e}"

        links = []
        wp = (getattr(msg, "web_preview", None)
              or getattr(getattr(msg, "media", None), "webpage", None))
        if wp is not None and getattr(wp, "url", None):
            links.append(wp.url)

        rows.append({
            "id": msg.id,
            "utc": msg.date.astimezone(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "tpe": msg.date.astimezone(TAIPEI).strftime("%Y-%m-%d %H:%M 台北"),
            "text": (msg.message or "").strip(),
            "media": media_note,
            "links": links,
            "url": f"https://t.me/{CHANNEL}/{msg.id}",
        })

    client.disconnect()
    rows.reverse()

    lines = [f"# Gooaye 股癌 — 過去 {hours} 小時（共 {len(rows)} 則）\n"]
    for r in rows:
        lines.append(f"\n## #{r['id']}　{r['tpe']}（{r['utc']}）")
        lines.append(f"{r['url']}\n")
        lines.append(r["text"] if r["text"] else "_（無文字）_")
        if r["media"]:
            lines.append(f"\n> {r['media']}")
        for l in r["links"]:
            lines.append(f"\n> 外部連結: {l}")
        lines.append("")

    (outdir / "posts.md").write_text("\n".join(lines), encoding="utf-8")
    (outdir / "posts.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    state.update(
        status="OK",
        count=len(rows),
        error=None,
        posts=[{"id": r["id"], "tpe": r["tpe"],
                "has_text": bool(r["text"]), "media": r["media"]} for r in rows],
    )

    print(f"抓到 {len(rows)} 則 -> out/{today}/posts.md")
    for r in rows:
        flag = "文字" if r["text"] else "純媒體"
        print(f"  #{r['id']}  {r['tpe']}  [{flag}] {r['media']}")

    # 工作目錄保留最近 KEEP_DAYS 天；更早的版本 git 歷史裡還在
    cut = now_tpe.date() - dt.timedelta(days=KEEP_DAYS)
    for d in sorted((BASE / "out").glob("????-??-??")):
        try:
            if d.is_dir() and dt.date.fromisoformat(d.name) < cut:
                shutil.rmtree(d)
                print(f"[清理] 已刪除 {d.name}")
        except ValueError:
            pass


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        state["error"] = f"{type(e).__name__}: {e}"
        traceback.print_exc()
        print(f"\n[FATAL] {state['error']}")
    save_status()
    sys.exit(0)   # 一律 0，好讓 status.json 被 commit；成敗由 workflow 最後一步判斷
