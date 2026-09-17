#!/usr/bin/env python3
"""
一次性本機工具:跑 Google OAuth2 installed-app flow,拿到 GMAIL_REFRESH_TOKEN。

這支不是給 GitHub Actions 用的,是給你自己電腦跑一次,把印出來的 refresh token
存進 repo secret `GMAIL_REFRESH_TOKEN`(連同 client id / secret 一起,見 README)。

事前準備:
    1. Google Cloud Console 建一個 project,啟用 Gmail API。
    2. OAuth consent screen 設成 External + Testing 模式,把自己的信箱加進
       test users(不需要送審)。
    3. Credentials → Create OAuth client ID → Application type 選 "Desktop app"，
       下載 client_secret.json。

用法:
    pip install google-auth-oauthlib
    python3 gmail_get_refresh_token.py --client-secret client_secret.json
"""
import argparse
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--client-secret",
        required=True,
        help="Google Cloud Console 下載的 client_secret.json 路徑",
    )
    args = ap.parse_args()

    flow = InstalledAppFlow.from_client_secrets_file(args.client_secret, SCOPES)
    creds = flow.run_local_server(port=0)

    print("\n=== 存進 repo secrets ===")
    print(f"GMAIL_CLIENT_ID={creds.client_id}")
    print(f"GMAIL_CLIENT_SECRET={creds.client_secret}")
    print(f"GMAIL_REFRESH_TOKEN={creds.refresh_token}")

    if not creds.refresh_token:
        print(
            "\n警告:沒有拿到 refresh_token,通常是這個帳號之前已經同意過這個 app、"
            "Google 就不會再給。去 https://myaccount.google.com/permissions 撤銷這個"
            "app 的權限後重跑一次。",
            file=sys.stderr,
        )


if __name__ == "__main__":
    sys.exit(main())
