"""
generate_post.py
キャプション生成 → 画像生成 → imgbb保存 → Slack通知（Instagram＋X両方）
"""
import os
import sys
import json
import base64
import datetime
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from content.caption_generator import build_caption, build_x_thread
from content.image_generator import generate_image


ACCOUNT_USERNAME = "@uni.4534"
ACCOUNT_NAME = "uni"


def upload_to_imgbb(image_path: str) -> str:
    """画像をimgbbにアップロードして永続URLを返す"""
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    resp = requests.post(
        "https://api.imgbb.com/1/upload",
        data={"key": os.getenv("IMGBB_API_KEY"), "image": b64, "expiration": 86400},
        timeout=30,
    )
    resp.raise_for_status()
    url = resp.json()["data"]["url"]
    print(f"[imgbb] アップロード完了: {url[:60]}...")
    return url


def notify_slack(caption: str, image_url: str, x_tweets: list, run_url: str):
    """SlackにInstagram＋Xスレッドのプレビューを通知"""
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        print("[Slack] SLACK_WEBHOOK_URL未設定 → スキップ")
        return

    main_tweet = x_tweets[0] if len(x_tweets) >= 1 else ""
    reply_tweet = x_tweets[1] if len(x_tweets) >= 2 else ""

    main_len = len(main_tweet)
    reply_len = len(reply_tweet)
    main_status = "✅" if main_len <= 280 else "⚠️ オーバー"
    reply_status = "✅" if reply_len <= 280 else "⚠️ オーバー"

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"📸🐦 投稿プレビュー｜{ACCOUNT_NAME}（{ACCOUNT_USERNAME}）"}
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*📸 Instagramキャプション:*\n```" + caption + "```"}
        },
        {
            "type": "image",
            "image_url": image_url,
            "alt_text": "投稿画像プレビュー"
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*🐦 Xメインツイート（同じ画像付き）:*\n```{main_tweet}```"}
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Main文字数:* {main_len} / 280　{main_status}"},
            ]
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*🐦 Xリプライ（詳細）:*\n```{reply_tweet}```"}
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Reply文字数:* {reply_len} / 280　{reply_status}"},
            ]
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "👆 内容を確認して、GitHubで承認または却下してください"}
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅ GitHubで承認・却下する"},
                    "style": "primary",
                    "url": run_url
                }
            ]
        }
    ]

    payload = {
        "text": f"📸🐦 Instagram＋X投稿チェック依頼（{ACCOUNT_USERNAME}）",
        "blocks": blocks,
    }

    resp = requests.post(webhook_url, json=payload, timeout=10)
    if resp.ok:
        print("[Slack] 通知送信完了 ✅")
    else:
        print(f"[Slack] 通知エラー: {resp.status_code} {resp.text}")


def main():
    print("=" * 50)
    print(f"[Generate] 開始: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    # Instagramキャプション生成
    result = build_caption()
    caption = result["caption"]
    print(f"\n[Generate] IGキャプション:\n{caption}")
    print(f"[Generate] 文字数: {len(caption)} / スコア: {result['score']}")

    # X用スレッド投稿生成（main + reply）
    x_result = build_x_thread()
    x_tweets = x_result["tweets"]
    print(f"\n[Generate] Xメイン:\n{x_tweets[0]}")
    print(f"\n[Generate] Xリプライ:\n{x_tweets[1]}")

    # 画像生成（Instagram・X共用、メインツイートに添付）
    save_path = "/tmp/post_image.jpg"
    image_local, dalle_url = generate_image(caption, save_path)

    # imgbbにアップロード（Slackプレビュー＋Instagram投稿用URL）
    try:
        image_url = upload_to_imgbb(image_local)
    except Exception as e:
        print(f"[imgbb] アップロード失敗、フォールバックURL使用: {e}")
        image_url = dalle_url

    # post_data.json に保存（post jobで使用）
    post_data = {
        "caption": caption,
        "image_url": image_url,
        "x_tweets": x_tweets,
        "x_topic": x_result.get("topic"),
        "x_pattern": x_result.get("pattern"),
        "generated_at": datetime.datetime.now().isoformat(),
    }
    with open("post_data.json", "w", encoding="utf-8") as f:
        json.dump(post_data, f, ensure_ascii=False, indent=2)
    print("[Generate] post_data.json 保存完了")

    # GitHub Actions URLを構築
    server = os.getenv("GITHUB_SERVER_URL", "https://github.com")
    repo = os.getenv("GITHUB_REPOSITORY", "ke-enomoto123/instagram-uni-keisuke")
    run_id = os.getenv("GITHUB_RUN_ID", "")
    run_url = f"{server}/{repo}/actions/runs/{run_id}"

    # Slack通知
    notify_slack(caption, image_url, x_tweets, run_url)


if __name__ == "__main__":
    main()
