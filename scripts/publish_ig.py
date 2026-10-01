#!/usr/bin/env python3
"""
用 Instagram Content Publishing API 發布貼文。給 1 個 --image-url 就發單圖,
給 2 個以上就自動發輪播(carousel);給 --video-url 就發 Reels。

需要環境變數:
    IG_ACCESS_TOKEN        Meta long-lived access token(要有 instagram_content_publish 權限)
    IG_BUSINESS_ACCOUNT_ID 你的 IG 專業帳號 ID

用法:
    python3 publish_ig.py --image-url https://.../card.png --caption "文案內容"
    python3 publish_ig.py --image-url https://.../slide-1.png --image-url https://.../slide-2.png --caption "文案內容"
    python3 publish_ig.py --video-url https://.../reel.mp4 --caption "文案內容"
"""
import argparse
import os
import sys
import time

import requests

GRAPH_API_VERSION = "v21.0"
GRAPH_BASE = f"https://graph.instagram.com/{GRAPH_API_VERSION}"


def get_env(name: str) -> str:
    val = os.environ.get(name)
    if val:
        val = val.strip()
    if not val:
        print(f"缺少環境變數: {name}", file=sys.stderr)
        sys.exit(1)
    return val


def create_media_container(
    ig_user_id: str, token: str, image_url: str, caption: str = None, is_carousel_item: bool = False
) -> str:
    data = {"image_url": image_url, "access_token": token}
    if caption is not None:
        data["caption"] = caption
    if is_carousel_item:
        data["is_carousel_item"] = "true"
    resp = requests.post(f"{GRAPH_BASE}/{ig_user_id}/media", data=data, timeout=30)
    body = resp.json()
    if "id" not in body:
        raise RuntimeError(f"建立 media container 失敗: {body}")
    return body["id"]


def create_carousel_container(ig_user_id: str, token: str, children_ids: list, caption: str) -> str:
    resp = requests.post(
        f"{GRAPH_BASE}/{ig_user_id}/media",
        data={
            "media_type": "CAROUSEL",
            "children": ",".join(children_ids),
            "caption": caption,
            "access_token": token,
        },
        timeout=30,
    )
    body = resp.json()
    if "id" not in body:
        raise RuntimeError(f"建立 carousel container 失敗: {body}")
    return body["id"]


def create_reel_container(ig_user_id: str, token: str, video_url: str, caption: str) -> str:
    resp = requests.post(
        f"{GRAPH_BASE}/{ig_user_id}/media",
        data={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "share_to_feed": "true",
            "access_token": token,
        },
        timeout=30,
    )
    body = resp.json()
    if "id" not in body:
        raise RuntimeError(f"建立 reel container 失敗: {body}")
    return body["id"]


def wait_until_ready(creation_id: str, token: str, timeout_sec: int = 60, interval: int = 3) -> None:
    """有些情況 container 需要幾秒鐘處理,輪詢 status_code 直到 FINISHED。"""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        resp = requests.get(
            f"{GRAPH_BASE}/{creation_id}",
            params={"fields": "status_code,status", "access_token": token},
            timeout=15,
        )
        status = resp.json().get("status_code")
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise RuntimeError(f"media container 處理失敗: {resp.json()}")
        time.sleep(interval)
    raise TimeoutError("等待 media container 就緒逾時")


def publish(ig_user_id: str, token: str, creation_id: str) -> dict:
    resp = requests.post(
        f"{GRAPH_BASE}/{ig_user_id}/media_publish",
        data={"creation_id": creation_id, "access_token": token},
        timeout=30,
    )
    body = resp.json()
    if "id" not in body:
        raise RuntimeError(f"publish 失敗: {body}")
    return body


def publish_single(ig_user_id: str, token: str, image_url: str, caption: str) -> dict:
    print(f"建立 media container,image_url={image_url}")
    creation_id = create_media_container(ig_user_id, token, image_url, caption=caption)
    print(f"container id: {creation_id},等待處理完成...")
    wait_until_ready(creation_id, token)
    return publish(ig_user_id, token, creation_id)


def publish_carousel(ig_user_id: str, token: str, image_urls: list, caption: str) -> dict:
    children_ids = []
    for image_url in image_urls:
        print(f"建立 carousel child container,image_url={image_url}")
        child_id = create_media_container(ig_user_id, token, image_url, is_carousel_item=True)
        wait_until_ready(child_id, token)
        children_ids.append(child_id)

    print(f"建立 carousel container,children={children_ids}")
    creation_id = create_carousel_container(ig_user_id, token, children_ids, caption)
    print(f"carousel container id: {creation_id},等待處理完成...")
    wait_until_ready(creation_id, token)
    return publish(ig_user_id, token, creation_id)


def publish_reel(ig_user_id: str, token: str, video_url: str, caption: str) -> dict:
    print(f"建立 reel container,video_url={video_url}")
    creation_id = create_reel_container(ig_user_id, token, video_url, caption)
    print(f"reel container id: {creation_id},等待 IG 處理影片(通常數十秒到幾分鐘)...")
    # 影片要讓 IG 下載+轉檔,比圖片久很多
    wait_until_ready(creation_id, token, timeout_sec=600, interval=10)
    return publish(ig_user_id, token, creation_id)


def main():
    ap = argparse.ArgumentParser()
    media = ap.add_mutually_exclusive_group(required=True)
    media.add_argument(
        "--image-url",
        action="append",
        dest="image_urls",
        help="公開可存取的圖片網址,依輪播順序重複指定這個參數(1 個就發單圖)",
    )
    media.add_argument("--video-url", help="公開可存取的 mp4 網址,發布成 Reels")
    ap.add_argument("--caption", required=True, help="貼文文案(含 hashtag)")
    args = ap.parse_args()

    token = get_env("IG_ACCESS_TOKEN")
    ig_user_id = get_env("IG_BUSINESS_ACCOUNT_ID")

    # 不印出完整 token,只印長度跟開頭幾個字,方便判斷是不是貼錯格式
    # (Instagram API with Instagram Login 的 long-lived token 開頭通常是 "IGAA")
    print(f"token 長度={len(token)}, 開頭={token[:6]!r}", file=sys.stderr)
    if token.startswith("{") or token.startswith('"'):
        print(
            "警告:token 開頭是 '{' 或 '\"',看起來像是整包 JSON 或帶了引號被貼進來了,"
            "應該只存 access_token 欄位的純字串值。",
            file=sys.stderr,
        )

    print("開始 publish...")
    if args.video_url:
        result = publish_reel(ig_user_id, token, args.video_url, args.caption)
    elif len(args.image_urls) == 1:
        result = publish_single(ig_user_id, token, args.image_urls[0], args.caption)
    else:
        result = publish_carousel(ig_user_id, token, args.image_urls, args.caption)

    print(f"發布完成: {result}")


if __name__ == "__main__":
    sys.exit(main())
