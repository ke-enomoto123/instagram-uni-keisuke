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

from content.caption_generator import build_caption
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


def notify_slack(caption: str, image_url: str, x_text: str, run_url: str):
    """SlackにInstagram＋X両方のプレビューを通知"""
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        print("[Slack] SLACK_WEBHOOK_URL未設定 → スキップ")
        return

    x_char = len(x_text)
    x_status = "✅" if x_char <= 280 else "⚠️ 文字数オーバー"

    payload = {
        "text": f"📸🐦 Instagram＋X投稿チェック依頼（{ACCOUNT_USERNAME}）",
        "blocks": [
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
            {
                "type": "divider"
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*🐦 X投稿テキスト:*\n```{x_text}```"}
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*X文字数:* {x_char} / 280　{x_status}"},
                    {"type": "mrkdwn", "text": "*(同じ画像をXにも投稿します)*"}
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
    print(f"\n[Generate] キャプション:\n{caption}")
    print(f"[Generate] 文字数: {len(caption)} / スコア: {result['score']}")

    # X用テキスト生成（別途短めに生成）
    x_result = build_caption()
    x_text_raw = x_result["caption"]
    x_text = x_text_raw[:270] + "…" if len(x_text_raw) > 270 else x_text_raw
    print(f"\n[Generate] X用テキスト:\n{x_text}")

    # 画像生成（Instagram・X共用）
    save_path = "/tmp/post_image.jpg"
    image_local, dalle_url = generate_image(caption, save_path)

    # imgbbにアップロード
    try:
        image_url = upload_to_imgbb(image_local)
    except Exception as e:
        print(f"[imgbb] アップロード失敗、DALL-E URLを使用: {e}")
        image_url = dalle_url

    # post_data.json に保存（post jobで使用）
    post_data = {
        "caption": caption,
        "image_url": image_url,
        "x_text": x_text,
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

    # Slack通知（Instagram＋X両方）
    notify_slack(caption, image_url, x_text, run_url)


if __name__ == "__main__":
    main()
