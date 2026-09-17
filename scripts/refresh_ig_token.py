#!/usr/bin/env python3
"""
刷新 Instagram long-lived access token,並把新 token 寫回 GitHub repo 的
Secret(IG_ACCESS_TOKEN),做到不用人工每 60 天手動換一次。

流程(Instagram API with Instagram Login 專用,不需要 App Secret):
    1. 用現有的 IG_ACCESS_TOKEN 呼叫 /refresh_access_token 換一組新 token
       (新 token 效期重新算 60 天)
    2. 用一組有 "Secrets: Read and write" 權限的 GitHub token,呼叫 GitHub
       API 把新 token 加密後寫回這個 repo 的 IG_ACCESS_TOKEN secret

需要環境變數:
    IG_ACCESS_TOKEN     目前使用中的 long-lived token(至少要發出 24 小時)
    GH_PAT_FOR_SECRETS  有這個 repo "Secrets: Read and write" 權限的
                        fine-grained GitHub token(跟一般 GITHUB_TOKEN 不同,
                        要另外申請)
    GITHUB_REPOSITORY   GitHub Actions 會自動帶入,格式 "owner/repo"
"""
import os
import sys
from base64 import b64encode

import requests
from nacl import encoding, public

GITHUB_API = "https://api.github.com"


def get_env(name: str) -> str:
    val = os.environ.get(name)
    if val:
        val = val.strip()
    if not val:
        print(f"缺少環境變數: {name}", file=sys.stderr)
        sys.exit(1)
    return val


def refresh_ig_token(current_token: str) -> tuple[str, int]:
    resp = requests.get(
        "https://graph.instagram.com/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": current_token},
        timeout=30,
    )
    body = resp.json()
    if "access_token" not in body:
        raise RuntimeError(f"refresh token 失敗: {body}")
    return body["access_token"], body.get("expires_in", 0)


def encrypt_secret(public_key_b64: str, secret_value: str) -> str:
    """依 GitHub 文件規定的 libsodium sealed box 加密方式"""
    pk = public.PublicKey(public_key_b64.encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(pk)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return b64encode(encrypted).decode("utf-8")


def get_repo_public_key(repo: str, gh_token: str) -> dict:
    resp = requests.get(
        f"{GITHUB_API}/repos/{repo}/actions/secrets/public-key",
        headers={
            "Authorization": f"Bearer {gh_token}",
            "Accept": "application/vnd.github+json",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def update_github_secret(repo: str, gh_token: str, secret_name: str, secret_value: str):
    key_info = get_repo_public_key(repo, gh_token)
    encrypted_value = encrypt_secret(key_info["key"], secret_value)

    resp = requests.put(
        f"{GITHUB_API}/repos/{repo}/actions/secrets/{secret_name}",
        headers={
            "Authorization": f"Bearer {gh_token}",
            "Accept": "application/vnd.github+json",
        },
        json={"encrypted_value": encrypted_value, "key_id": key_info["key_id"]},
        timeout=15,
    )
    if resp.status_code not in (201, 204):
        raise RuntimeError(f"寫回 GitHub secret 失敗: {resp.status_code} {resp.text}")


def main():
    current_token = get_env("IG_ACCESS_TOKEN")
    gh_token = get_env("GH_PAT_FOR_SECRETS")
    repo = get_env("GITHUB_REPOSITORY")

    print("呼叫 refresh_access_token...")
    new_token, expires_in = refresh_ig_token(current_token)
    days = round(expires_in / 86400, 1) if expires_in else "未知"
    print(f"換到新 token,效期約 {days} 天")

    print(f"寫回 repo {repo} 的 IG_ACCESS_TOKEN secret...")
    update_github_secret(repo, gh_token, "IG_ACCESS_TOKEN", new_token)
    print("完成,GitHub Secret 已更新。")


if __name__ == "__main__":
    sys.exit(main())
