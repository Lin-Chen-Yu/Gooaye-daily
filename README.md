# Gooaye 頻道抓取與講解（純雲端版）

把原本綁在筆電上的三段流程搬到雲端。你的電腦關機、沒插電、出國都不影響。

## 架構

| 誰 | 什麼時候 | 做什麼 |
|---|---|---|
| GitHub Actions `Gooaye Fetch` | 每天 03:30 UTC（11:30 台北） | Telethon 抓過去 26 小時貼文與圖片 → commit `out/<日期>/` 與 `status.json` |
| Claude Cowork 雲端排程 | 每天 13:00 台北 | `git clone` 本 repo → 讀 `status.json` 與 `posts.md`、用 Read 看圖 → 查證講解 → 寫 `out/<日期>/mail.html` → push |
| GitHub Actions `Gooaye Mail` | 偵測到 `mail.html` 被 push | Gmail SMTP 寄出，圖片以 inline cid 穿插 → commit `mail.sent` |

中間留 90 分鐘緩衝，因為 GitHub 的 cron 在尖峰時段會延遲數分鐘到數十分鐘。

### 為什麼是這個分工

- **抓取一定要在 Actions**：Claude 的沙盒連不到 Telegram 伺服器（MTProto 與 DNS 皆不通，已實測）。這是整套流程中唯一無法交給 Claude 的環節。
- **講解一定要在 Claude**：需要看圖、查證、寫作。
- **寄信留在 Actions 而不是用 Gmail 連接器**：連接器支援 `inline: true` 內嵌圖片，但要把圖片以 base64 塞進工具參數，一張圖約 5 萬 token，三張就讓每天成本膨脹 30 倍。SMTP 直接讀檔案，零成本。Claude 只負責產出 HTML。

## 一次性設定

### 1. 建立 repo

建一個 **private** repo，把這個資料夾的內容推上去。設 private 是因為 repo 會累積這個頻道的貼文與圖片，沒必要公開轉載別人的內容。

### 2. 產生 Telegram StringSession（唯一需要在本機做的事）

```bash
pip install telethon
python tools/make_session.py
```

輸入 API ID / hash、手機號碼（含國碼）、Telegram App 收到的驗證碼。會印出一長串 session 字串。**那串字串等同於你的 Telegram 登入憑證**，只貼到 GitHub secret，不要貼到別處。

之後除非你在 Telegram 裡主動把這個 session 登出，否則不用再做這一步。

### 3. 設定 repo secrets

Settings > Secrets and variables > Actions > New repository secret：

| Secret | 值 |
|---|---|
| `TG_API_ID` | Telegram API ID |
| `TG_API_HASH` | Telegram API hash |
| `TG_SESSION` | 上一步印出來的字串 |
| `GMAIL_USER` | `henson0328@gmail.com` |
| `GMAIL_APP_PASSWORD` | Google 應用程式密碼（16 碼，可沿用現有那組） |
| `MAIL_TO` | `henson0328@gmail.com` |

### 4. 建立 fine-grained PAT 給 Claude

GitHub Settings > Developer settings > Personal access tokens > Fine-grained tokens：

- Repository access：**Only select repositories** → 只勾這一個 repo
- Permissions：**Contents: Read and write**（只要這一項）
- 有效期：建議 1 年，到期前 GitHub 會寄信提醒

### 5. 設定 Claude 雲端排程

把 `CLAUDE_TASK.md` 的內容貼成一個新的 Cowork 排程任務，每天 13:00 台北執行，並把開頭三個角括號換成你的 repo 與 PAT。

> 這個排程**不能**引用任何本機路徑。Cowork 排程預設跑在雲端，但只要任務需要本機檔案或 App，就會退回只在本機跑 —— 那就失去搬上雲的意義了。

### 6. 驗證

1. Actions 頁面手動觸發 `Gooaye Fetch`（Run workflow，hours 填 26），確認綠燈且 repo 出現 `out/<日期>/`。
2. 手動跑一次 Claude 排程，確認它 clone 得到、看得到圖、push 得回去。
3. 確認 `Gooaye Mail` 被自動觸發且信寄到了。

## 日常維護

| 狀況 | 怎麼辦 |
|---|---|
| 漏抓幾天 | Actions > Gooaye Fetch > Run workflow，hours 填 `130` |
| 想重寄某天 | Actions > Gooaye Mail > Run workflow，date 填日期、force 打勾 |
| 沒收到信 | 先看 Actions 兩個 workflow 的顏色，再看 `status.json` 與 `out/<日期>/mail.sent` 在不在 |
| Telegram session 失效 | `Gooaye Fetch` 會紅燈並在 `status.json` 寫明，重跑步驟 2 更新 `TG_SESSION` |

## 失效訊號

雲端版最大的好處不是「不用開電腦」，是**失敗會變吵**：

- `Gooaye Fetch` 或 `Gooaye Mail` 紅燈 → GitHub 自動寄通知信給你。
- Claude 排程失敗 → Cowork 的任務列表會顯示。

本機版三段都是靜默失敗，這也是 2026-09-17 到 09-21 那次漏信拖了五天才被發現的原因。

## 保留在本機的東西

`../` 底下的本機版（`gooaye_fetch.py`、`send_mail.py`、`run_*.bat`、工作排程器任務）在雲端版驗證通過之前先不要刪，兩邊同時跑會重複寄信。確認雲端穩定後：

```powershell
Unregister-ScheduledTask 'Gooaye Fetch'        -Confirm:$false
Unregister-ScheduledTask 'Gooaye Mail'         -Confirm:$false
Unregister-ScheduledTask 'Gooaye Mail Watcher' -Confirm:$false
```

並停用舊的 `gooaye--telegram-api` Cowork 排程。
