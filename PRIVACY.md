# 隱私權政策 / Privacy Policy

最後更新:2026-09-30

## 中文

`ig-auto-post` 是個人自用的自動化工具,只供開發者本人使用,不對外提供服務。

**存取的資料**
- 僅透過 Gmail API 唯讀存取開發者本人 Gmail 信箱中的特定信件(盤前簡報、盤後總結的來源信件,及其自動產生的 JSON 內容信件)。
- 不存取任何其他使用者的資料。

**資料的使用**
- 信件內容僅用於產生 Instagram 圖卡與貼文文案。
- 不會出售、出租、分享給任何第三方,也不用於廣告或訓練任何 AI 模型。

**資料的儲存**
- 除了產生後公開發布的圖卡與文案外,不另行儲存信件內容。
- OAuth 憑證(Client ID、Client Secret、Refresh Token)僅保存於 GitHub Actions Secrets。

**聯絡方式**
如有問題,請透過本 repo 的 GitHub Issues 聯繫。

## English

`ig-auto-post` is a personal automation tool used only by its developer. It is not offered as a service to others.

- **Data accessed:** read-only access, via the Gmail API, to specific emails in the developer's own mailbox. No other user's data is accessed.
- **Data use:** email content is used solely to generate Instagram images and captions. It is never sold, shared with third parties, used for advertising, or used to train AI models.
- **Data storage:** apart from the publicly posted images and captions, email content is not retained. OAuth credentials are stored only in GitHub Actions Secrets.
- **Contact:** please open an issue in this repository.
