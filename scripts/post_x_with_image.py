"""
post_x_with_image.py
post_data.json を読み込んで、画像付きスレッド形式（main + reply）でXに投稿
"""
import os
import sys
import json
import datetime
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from x.poster import post_thread, post_tweet


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

    x_tweets = post_data.get("x_tweets") or []
    image_url = post_data.get("image_url", "")
    generated_at = post_data.get("generated_at", "不明")

    if not x_tweets:
        # 旧スキーマフォールバック（x_text 単発）
        x_text = post_data.get("x_text", "")
        if x_text:
            x_tweets = [x_text]

    print(f"[Post X] 生成日時: {generated_at}")
    for i, t in enumerate(x_tweets, start=1):
        print(f"[Post X] tweet {i}/{len(x_tweets)} ({len(t)}字):\n{t}\n")

    # 画像をダウンロード（メインツイートに添付）
    image_path = "/tmp/post_image_x.jpg"
    try:
        if image_url:
            download_image(image_url, image_path)
        else:
            image_path = None

        tweet_ids = post_thread(x_tweets, image_path=image_path, x_username="uni_keisuke")
    except Exception as e:
        print(f"[Post X] スレッド投稿失敗: {e}")
        print("[Post X] テキストのみ・スレッドで再試行...")
        tweet_ids = post_thread(x_tweets, image_path=None, x_username="uni_keisuke")

    print(f"\n[Post X] ✅ X投稿完了! {len(tweet_ids)}件、URL: https://x.com/uni_keisuke/status/{tweet_ids[0]}")


if __name__ == "__main__":
    main()
