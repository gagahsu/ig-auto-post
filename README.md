# 台股盤前速報 / 盤後統整 → IG 自動發布

兩條獨立 pipeline,共用同一組 Gmail OAuth secrets 跟 render/publish script,差別只在
讀信的主旨前綴、套用的模板、跑的時間。每條 pipeline 都發 2 張圖的輪播(carousel)
貼文,不是單圖 — 資料量每天不一樣,塞單張圖字會被擠得很小,拆兩張手機上才看得清楚：

| | 盤前速報 | 盤後統整 |
|---|---|---|
| workflow | `.github/workflows/post-to-ig.yml` | `.github/workflows/post-closing-to-ig.yml` |
| 讀信主旨前綴 | `IG_BRIEFING_PAYLOAD` | `IG_CLOSING_PAYLOAD` |
| 模板(輪播 2 張) | `templates/card_template_1.html` + `_2.html` | `templates/closing_card_template_1.html` + `_2.html` |
| 排程(台北) | 08:05 | 22:15 |

## 檔案結構
```
.github/workflows/post-to-ig.yml         ← 盤前速報 workflow
.github/workflows/post-closing-to-ig.yml ← 盤後統整 workflow
scripts/render_card.py                   ← 把資料套進模板,依序渲染成輪播 PNG(--template 可重複指定)
scripts/publish_ig.py                    ← 呼叫 Meta Graph API 發布(--image-url 給 1 個發單圖,給多個自動發輪播)
scripts/fetch_briefing_email.py          ← 用 Gmail API 讀當天的 payload 信,解析成 payload.json(--subject-prefix 選主旨)
scripts/gmail_get_refresh_token.py       ← 一次性本機工具,取得 Gmail OAuth2 refresh token
templates/card_template_1.html           ← 盤前速報輪播第1張:期貨與美股(1080x1350)
templates/card_template_2.html           ← 盤前速報輪播第2張:焦點快訊與族群(1080x1350)
templates/closing_card_template_1.html   ← 盤後統整輪播第1張:指數與籌碼(1080x1350)
templates/closing_card_template_2.html   ← 盤後統整輪播第2張:族群與明日觀測(1080x1350)
payload.example.json                     ← 盤前速報測試用範例資料
payload_closing.example.json             ← 盤後統整測試用範例資料
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
python3 scripts/render_card.py --payload payload.example.json --out-dir output \
  --template card_template_1.html --template card_template_2.html
# 打開 output/slide-1.png、output/slide-2.png 看排版對不對
```

確認圖卡沒問題後，測試發布（需要先把圖片放到一個公開網址，例如先手動 push
一次 assets/ 資料夾，或直接用 GitHub Actions 的 `workflow_dispatch` 手動觸發整條
流程）：

Repo → Actions → "Post daily briefing to Instagram" → Run workflow →
把 `payload.example.json` 的內容整個貼進 `payload_json` 欄位 → Run。

盤後統整同理，改用 `payload_closing.example.json`：
```bash
python3 scripts/render_card.py --payload payload_closing.example.json --out-dir output \
  --template closing_card_template_1.html --template closing_card_template_2.html
```
Repo → Actions → "Post closing summary to Instagram" → Run workflow → 貼
`payload_closing.example.json` 的內容 → Run。

## 正式串接：schedule cron 自動拉信

不需要手動做什麼：
- `.github/workflows/post-to-ig.yml` 的 `schedule: cron: "5 0 * * *"`
  （00:05 UTC = 08:05 台北）每天自動觸發，去讀主旨 `IG_BRIEFING_PAYLOAD {日期}`
  的信。
- `.github/workflows/post-closing-to-ig.yml` 的 `schedule: cron: "15 14 * * *"`
  （14:15 UTC = 22:15 台北）每天自動觸發，去讀主旨 `IG_CLOSING_PAYLOAD {日期}`
  的信。

前提是上面「一次性設定」的 Gmail secrets 都設好、且有對應的來源自動把整理好
的 JSON 寄回自己信箱（盤前速報的部分見 `project-scheduled-task-prompt.md`；
盤後統整目前沒有寫在這個 repo 裡的排程任務指令文件，由使用者自行在 Claude
Project 那邊設定，主旨務必是 `IG_CLOSING_PAYLOAD {YYYY-MM-DD}`，內文純文字、
就是照 `payload_closing.example.json` 格式整理好的 JSON，一個字不多不少）。

`repository_dispatch`（`event_type: post_briefing` / `post_closing`）觸發路徑
都還留著，當作緊急補發或測試用；`workflow_dispatch` 手動觸發時如果
`payload_json` 留空，也會走跟 schedule 一樣的「去讀信」路徑，方便直接測整條
讀信流程。

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
- 每張輪播圖裡標 `.fit-text` 的區塊（新聞/焦點族群/盤後重點等長度會變動的內文）,
  `render_card.py` 會在內容太長、超出卡片固定高度時自動等比縮小字級,縮到
  55% 還塞不下就放棄、印警告到 log,圖卡底部可能被裁切 —— 平常應該不會踩到,
  真的遇到記得去 Actions log 看警告,考慮精簡文案或未來拆成 3 張。
