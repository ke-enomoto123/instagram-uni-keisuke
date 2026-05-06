import requests
import time
from config import INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_BUSINESS_ACCOUNT_ID

def create_media_container(image_url: str, caption: str) -> str:
    url = f"https://graph.facebook.com/v19.0/{INSTAGRAM_BUSINESS_ACCOUNT_ID}/media"
    params = {
        "image_url": image_url,
        "caption": caption,
        "access_token": INSTAGRAM_ACCESS_TOKEN,
    }
    response = requests.post(url, params=params)
    if not response.ok:
        print(f"[Post] メディアコンテナエラー: {response.text}")
    response.raise_for_status()
    return response.json()["id"]

def publish_instagram_post(container_id: str) -> str:
    url = f"https://graph.facebook.com/v19.0/{INSTAGRAM_BUSINESS_ACCOUNT_ID}/media_publish"
    params = {
        "creation_id": container_id,
        "access_token": INSTAGRAM_ACCESS_TOKEN,
    }
    response = requests.post(url, params=params)
    if not response.ok:
        print(f"[Post] 公開エラー詳細: {response.text}")
    response.raise_for_status()
    return response.json()["id"]

def post_to_instagram(image_url: str, caption: str) -> str:
    print("[Post] Instagramへ投稿中...")
    container_id = create_media_container(image_url, caption)
    print(f"[Post] コンテナID: {container_id}")
    time.sleep(5)
    post_id = publish_instagram_post(container_id)
    print(f"[Post] 投稿成功! Post ID: {post_id}")
    return post_id
