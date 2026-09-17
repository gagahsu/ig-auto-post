#!/usr/bin/env python3
"""
用 Gmail API 讀取今天的「盤前速報 payload」信件，解析出 JSON，寫成 payload.json。

背景:排程觸發責任從 Claude session 移到 GitHub Actions 自己(schedule trigger)去拉,
Claude 那邊的排程任務只負責讀信、整理 JSON、寄一封信回自己信箱,不再對外呼叫
GitHub API。這支 script 就是接手「讀那封信」的部分。

需要環境變數:
    GMAIL_CLIENT_ID       OAuth2 client id(Desktop app 類型)
    GMAIL_CLIENT_SECRET   OAuth2 client secret
    GMAIL_REFRESH_TOKEN   一次性本機授權拿到的 refresh token(見 gmail_get_refresh_token.py)
    GMAIL_SELF_ADDRESS    自己的信箱(用來限定 from:me 那個 self-sent 的信)

用法:
    python3 fetch_briefing_email.py --out payload.json
"""
import argparse
import base64
import json
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
SUBJECT_PREFIX = "IG_BRIEFING_PAYLOAD"
TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def get_env(name: str) -> str:
    import os

    val = os.environ.get(name)
    if val:
        val = val.strip()
    if not val:
        print(f"缺少環境變數: {name}", file=sys.stderr)
        sys.exit(1)
    return val


def get_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    resp = requests.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    body = resp.json()
    if "access_token" not in body:
        raise RuntimeError(f"換取 access token 失敗: {body}")
    return body["access_token"]


def find_todays_message_id(access_token: str, self_address: str, today: str) -> str | None:
    subject = f"{SUBJECT_PREFIX} {today}"
    query = f'from:me to:{self_address} subject:"{subject}"'
    resp = requests.get(
        f"{GMAIL_API_BASE}/messages",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"q": query, "maxResults": 1},
        timeout=30,
    )
    body = resp.json()
    messages = body.get("messages") or []
    if not messages:
        return None
    return messages[0]["id"]


def extract_json_body(access_token: str, message_id: str) -> dict:
    resp = requests.get(
        f"{GMAIL_API_BASE}/messages/{message_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"format": "full"},
        timeout=30,
    )
    message = resp.json()

    def walk(part) -> str | None:
        mime_type = part.get("mimeType", "")
        data = part.get("body", {}).get("data")
        if data and mime_type.startswith("text/"):
            return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8")
        for sub in part.get("parts", []) or []:
            found = walk(sub)
            if found:
                return found
        return None

    payload_part = message.get("payload", {})
    text = walk(payload_part)
    if not text:
        raise RuntimeError(f"信件裡找不到可解析的文字內容: message_id={message_id}")

    return json.loads(text.strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="payload.json", help="輸出的 payload JSON 路徑")
    args = ap.parse_args()

    client_id = get_env("GMAIL_CLIENT_ID")
    client_secret = get_env("GMAIL_CLIENT_SECRET")
    refresh_token = get_env("GMAIL_REFRESH_TOKEN")
    self_address = get_env("GMAIL_SELF_ADDRESS")

    today = datetime.now(TAIPEI_TZ).strftime("%Y-%m-%d")

    access_token = get_access_token(client_id, client_secret, refresh_token)

    message_id = find_todays_message_id(access_token, self_address, today)
    if not message_id:
        print(
            f"今天({today})沒有找到主旨為「{SUBJECT_PREFIX} {today}」的信,不使用舊資料,直接停止。",
            file=sys.stderr,
        )
        sys.exit(1)

    payload = extract_json_body(access_token, message_id)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"已從信件 {message_id} 解析出 payload,寫入 {args.out}")


if __name__ == "__main__":
    sys.exit(main())
