#!/usr/bin/env python3
"""
一次性：在本機產生 Telegram StringSession，貼到 GitHub repo secret TG_SESSION。

這是整套流程中唯一還需要在你自己電腦上做的事，而且只做一次
（除非 session 失效，例如你在 Telegram 裡把這個 session 登出）。

用法：
    pip install telethon
    python tools/make_session.py

會問你手機號碼（含國碼，例如 +886912345678）與 Telegram App 收到的驗證碼，
若有開兩步驟驗證還會問密碼。最後印出一長串 session 字串。

安全提醒：那串字串等同於你的 Telegram 登入憑證。只貼到 GitHub 的
Settings > Secrets and variables > Actions > New repository secret，
不要貼到聊天室、issue 或任何會被記錄的地方。用完就把終端機視窗關掉。
"""
import os
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

api_id = os.environ.get("TG_API_ID") or input("TG_API_ID: ").strip()
api_hash = os.environ.get("TG_API_HASH") or input("TG_API_HASH: ").strip()

with TelegramClient(StringSession(), int(api_id), api_hash) as client:
    print("\n" + "=" * 70)
    print("TG_SESSION（整串複製，包含最後可能出現的 '=' 符號）：\n")
    print(client.session.save())
    print("\n" + "=" * 70)
    print("貼到 GitHub: Settings > Secrets and variables > Actions > New repository secret")
