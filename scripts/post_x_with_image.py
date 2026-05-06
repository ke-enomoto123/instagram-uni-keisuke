"""
post_x_with_image.py
post_data.json を読み込んで画像付きでXに投稿
"""
import os
import sys
import json
import datetime
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from x.poster import post_tweet_with_image, post_tweet


def download_image(url: str, save_path: str) -> str:
    """imgbb URLから画像をダウンロード"""
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    with open(save_path, "wb") as f:
        f.write(resp.content)
    print(f"[Post X] 画像ダウンロード完了: {save_path}")
    return save_path


def main():
    print("=" * 50)
    print(f"[Post X] 投稿開始: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    with open("post_data.json", "r", encoding="utf-8") as f:
        post_data = json.load(f)

    x_text = post_data["x_text"]
    image_url = post_data["image_url"]
    generated_at = post_data.get("generated_at", "不明")

    print(f"[Post X] 生成日時: {generated_at}")
    print(f"[Post X] 投稿テキスト:\n{x_text}")
    print(f"[Post X] 文字数: {len(x_text)}")
    print(f"[Post X] 画像URL: {image_url[:60]}...")

    # 画像をダウンロード
    image_path = "/tmp/post_image_x.jpg"
    try:
        download_image(image_url, image_path)
        tweet_id = post_tweet_with_image(x_text, image_path, x_username="uni_keisuke")
    except Exception as e:
        print(f"[Post X] 画像付き投稿失敗: {e}")
        print("[Post X] テキストのみで投稿します...")
        tweet_id = post_tweet(x_text, x_username="uni_keisuke")

    print(f"\n[Post X] ✅ X投稿完了! ID: {tweet_id}")


if __name__ == "__main__":
    main()
