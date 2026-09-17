# 台股盤前速報 → IG 自動發布

## 檔案結構
```
.github/workflows/post-to-ig.yml   ← GitHub Actions workflow
scripts/render_card.py             ← 把資料套進模板，渲染成 PNG
scripts/publish_ig.py              ← 呼叫 Meta Graph API 發布
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

拿 token 的步驟：Meta for Developers → 建立 App → 加 Instagram Graph API 產品 →
串接你的 IG 專業帳號（必須是商業/創作者帳號，且連結一個 FB 粉專）→ 產生
long-lived token（約 60 天效期，記得排一個提醒到期前換新）。

### 3. 準備一個能觸發 workflow 的 GitHub Token（給 Project 排程任務用）
在你的 GitHub 帳號設定一個 fine-grained personal access token，權限只給
`Contents: Read and write` + `Actions: Read and write`，範圍限定這個 repo。
這個 token 會被 Project 的排程任務用來呼叫 `repository_dispatch`，**不要**設成
GitHub Secrets（那是給 workflow 內部用的），而是給 Claude Project 那邊的排程
任務使用（設定方式看它的介面，通常是連結一個 Credential 或直接放進任務指令
情境裡，依 Claude 產品當下版本為準）。

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

## 正式串接：用 repository_dispatch 觸發

Project 排程任務讀完 Gmail、整理好資料後，呼叫：

```bash
curl -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer <你的 fine-grained GitHub token>" \
  https://api.github.com/repos/<你的帳號>/<repo名稱>/dispatches \
  -d '{
    "event_type": "post_briefing",
    "client_payload": { ...按照 payload.example.json 的格式帶入當天資料... }
  }'
```

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
