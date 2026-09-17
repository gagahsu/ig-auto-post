# 台股盤前速報 → IG 自動發布

## 檔案結構
```
.github/workflows/post-to-ig.yml   ← GitHub Actions workflow
scripts/render_card.py             ← 把資料套進模板，渲染成 PNG
scripts/publish_ig.py              ← 呼叫 Meta Graph API 發布
scripts/fetch_briefing_email.py    ← 用 Gmail API 讀當天的 payload 信,解析成 payload.json
scripts/gmail_get_refresh_token.py ← 一次性本機工具,取得 Gmail OAuth2 refresh token
templates/card_template.html       ← 圖卡的 HTML/CSS 模板(1080x1350)
payload.example.json               ← 測試用範例資料
requirements.txt
```

## 一次性設定

### 1. 建這個 repo（必須是 public，jsDelivr / raw.githubusercontent 都不支援 private repo）
把這些檔案 push 上去，維持這個資料夾結構。Secrets（token 等）不會因為 repo
公開而外洩，GitHub Secrets 一律加密，跟 repo 可見度無關。

### 2. 設定 GitHub Secrets
Repo → Settings → Secrets and variables → Actions → New repository secret：

| Secret 名稱 | 內容 |
|---|---|
| `IG_ACCESS_TOKEN` | Meta long-lived access token，要有 `instagram_content_publish` 權限 |
| `IG_BUSINESS_ACCOUNT_ID` | 你的 IG 專業帳號 ID |
| `GMAIL_CLIENT_ID` | Google OAuth2 client id(見下方步驟 3) |
| `GMAIL_CLIENT_SECRET` | Google OAuth2 client secret |
| `GMAIL_REFRESH_TOKEN` | 一次性本機授權拿到的 refresh token |
| `GMAIL_SELF_ADDRESS` | 自己的 Gmail 地址(Claude 排程任務寄信的收件者) |

拿 IG token 的步驟：Meta for Developers → 建立 App → 加 Instagram Graph API 產品 →
串接你的 IG 專業帳號（必須是商業/創作者帳號，且連結一個 FB 粉專）→ 產生
long-lived token（約 60 天效期，記得排一個提醒到期前換新）。

### 3. 讓 GitHub Actions 自己能讀 Gmail(取代原本 Claude 主動呼叫 GitHub API 的做法)

因為 Claude 排程任務對外呼叫常常被網路限制擋掉，流程改成「GitHub 主動來拉」：

1. Claude 排程任務讀完 Gmail、整理好 JSON 後，**寄一封信回自己的信箱**（不再
   呼叫 GitHub API，見 `project-scheduled-task-prompt.md`）。
2. GitHub Actions 改成用 `schedule:` cron 每天自己醒來，跑
   `scripts/fetch_briefing_email.py`，用 Gmail API 去讀那封信、解析出 JSON，
   再接續原本渲染圖卡 + 發布 IG 的流程。

個人 Gmail（非 Workspace）沒有 service account + domain-wide delegation 可用，
所以用 OAuth2 refresh token：

1. Google Cloud Console 開一個 project，啟用 **Gmail API**。
2. OAuth consent screen 選 External + Testing 模式，把自己的信箱加進 test
   users（不用送審，測試模式的 refresh token 不會過期，只要別把 App 改成
   Production 就好）。
3. Credentials → Create OAuth client ID → Application type 選 **Desktop app**，
   下載 `client_secret.json`。
4. 本機跑一次：
   ```bash
   pip install google-auth-oauthlib
   python3 scripts/gmail_get_refresh_token.py --client-secret client_secret.json
   ```
   瀏覽器會跳出來要你登入同意，完成後 terminal 會印出
   `GMAIL_CLIENT_ID` / `GMAIL_CLIENT_SECRET` / `GMAIL_REFRESH_TOKEN`，把這三個
   加上 `GMAIL_SELF_ADDRESS`（你的 Gmail 地址）一起存進上面表格的 repo secrets。

## 本機測試（不需要等排程，先確認整條 pipeline 會動）

```bash
pip install -r requirements.txt
playwright install --with-deps chromium
python3 scripts/render_card.py --payload payload.example.json --out output/card.png
# 打開 output/card.png 看排版對不對
```

確認圖卡沒問題後，測試發布（需要先把圖片放到一個公開網址，例如先手動 push
一次 assets/ 資料夾，或直接用 GitHub Actions 的 `workflow_dispatch` 手動觸發整條
流程）：

Repo → Actions → "Post daily briefing to Instagram" → Run workflow →
把 `payload.example.json` 的內容整個貼進 `payload_json` 欄位 → Run。

## 正式串接：schedule cron 自動拉信

不需要手動做什麼，`.github/workflows/post-to-ig.yml` 裡的 `schedule: cron:
"5 0 * * *"`（00:05 UTC = 08:05 台北）每天會自動觸發，自己跑
`fetch_briefing_email.py` 去讀 Claude 排程任務寄的那封信。前提是上面「一次性
設定」的 Gmail secrets 都設好、且 Claude 那邊的排程任務有照
`project-scheduled-task-prompt.md` 的指示把 JSON 寄回自己信箱。

`repository_dispatch`（`event_type: post_briefing`）觸發路徑還留著，當作緊急
補發或測試用；`workflow_dispatch` 手動觸發時如果 `payload_json` 留空，也會走
跟 schedule 一樣的「去讀信」路徑，方便直接測整條讀信流程。

## 已知限制 / 之後可以改進的地方

- 圖片會先 commit 進 repo 的 `assets/` 資料夾讓 jsDelivr 抓到，IG 發布成功後
  workflow 會自動 `git rm` 掉該檔案，避免 `assets/` 一直長大；但每次還是會留下
  一組「新增 + 刪除」的 commit 紀錄，long-term 想要乾淨歷史的話可以考慮改推到
  獨立的 `assets` branch 或 GitHub Release 附件。
- Long-lived token 約 60 天過期，已經有 `refresh-ig-token.yml` 排程（每月 1、16
  號）自動呼叫 refresh 並寫回 `IG_ACCESS_TOKEN` secret，理論上不用再手動換，
  但仍需另外設定一組有 `Secrets: Read and write` 權限的 `GH_PAT_FOR_SECRETS`。
- IG API 沒有編輯貼文的端點，發錯只能刪除重發，所以正式使用前務必先用
  `workflow_dispatch` 手動測過幾次。
- Gmail OAuth consent screen 停留在 Testing 模式的 refresh token 理論上不會過期，
  但如果哪天手動把 App 改成 Production 或撤銷過權限，`GMAIL_REFRESH_TOKEN` 就會
  失效，需要重跑一次 `gmail_get_refresh_token.py`。
