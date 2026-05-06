import base64
import os
import requests
from config import X_OAUTH2_CLIENT_ID, X_OAUTH2_CLIENT_SECRET, X_OAUTH2_REFRESH_TOKEN


def _update_github_secret(new_refresh_token: str):
    """新しいリフレッシュトークンをGitHub Secretsに自動保存"""
    try:
        from nacl import encoding, public

        github_token = os.getenv("GH_PAT")
        repo = os.getenv("GITHUB_REPOSITORY", "ke-enomoto123/instagram-uni-keisuke")

        if not github_token:
            print("[X] GH_PAT なし - Secret更新スキップ")
            return

        headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github.v3+json",
        }

        # 公開鍵を取得
        key_resp = requests.get(
            f"https://api.github.com/repos/{repo}/actions/secrets/public-key",
            headers=headers,
        )
        key_data = key_resp.json()

        # 暗号化
        pub_key = public.PublicKey(key_data["key"].encode("utf-8"), encoding.Base64Encoder())
        encrypted = base64.b64encode(
            public.SealedBox(pub_key).encrypt(new_refresh_token.encode("utf-8"))
        ).decode("utf-8")

        # Secret更新
        resp = requests.put(
            f"https://api.github.com/repos/{repo}/actions/secrets/X_OAUTH2_REFRESH_TOKEN",
            headers=headers,
            json={"encrypted_value": encrypted, "key_id": key_data["key_id"]},
        )
        if resp.ok:
            print("[X] リフレッシュトークンを自動更新しました ✅")
        else:
            print(f"[X] Secret更新失敗: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"[X] Secret更新エラー（続行）: {e}")


def _get_access_token() -> str:
    """リフレッシュトークンを使って新しいアクセストークンを取得"""
    response = requests.post(
        "https://api.x.com/2/oauth2/token",
        auth=(X_OAUTH2_CLIENT_ID, X_OAUTH2_CLIENT_SECRET),
        data={
            "grant_type": "refresh_token",
            "refresh_token": X_OAUTH2_REFRESH_TOKEN,
        },
    )
    if not response.ok:
        print(f"[X] トークン取得エラー: {response.text}")
    response.raise_for_status()

    data = response.json()
    access_token = data["access_token"]

    new_refresh_token = data.get("refresh_token")
    if new_refresh_token:
        print(f"[X] 新しいリフレッシュトークンを取得 → GitHub Secretsに保存中...")
        _update_github_secret(new_refresh_token)

    return access_token


def _upload_media(image_path: str, access_token: str) -> str:
    """画像をX v2 Media Upload APIでアップロードし media_id を返す"""
    print(f"[X] 画像アップロード中: {image_path}")

    with open(image_path, "rb") as f:
        image_data = f.read()

    mime_type = "image/jpeg"
    if image_path.lower().endswith(".png"):
        mime_type = "image/png"
    elif image_path.lower().endswith(".gif"):
        mime_type = "image/gif"

    response = requests.post(
        "https://api.x.com/2/media/upload",
        headers={"Authorization": f"Bearer {access_token}"},
        files={"media": (os.path.basename(image_path), image_data, mime_type)},
        timeout=60,
    )

    if not response.ok:
        print(f"[X] v2アップロードエラー: {response.status_code} {response.text}")
        response.raise_for_status()

    data = response.json()
    media_id = str(data.get("data", {}).get("id") or data.get("media_id") or data["id"])
    print(f"[X] 画像アップロード完了: media_id={media_id}")
    return media_id


def post_tweet(text: str, x_username: str = "uni_keisuke") -> str:
    """X（Twitter）にテキストのみのツイートを投稿する。"""
    print(f"[X] ツイート投稿開始...")
    print(f"[X] 文字数: {len(text)}")
    print(f"[X] 内容: {text[:60]}...")

    access_token = _get_access_token()
    print(f"[X] アクセストークン取得完了")

    response = requests.post(
        "https://api.x.com/2/tweets",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={"text": text},
        timeout=30,
    )

    if not response.ok:
        print(f"[X] 投稿エラー詳細: {response.text}")
    response.raise_for_status()

    tweet_id = str(response.json()["data"]["id"])
    print(f"[X] 投稿完了! Tweet ID: {tweet_id}")
    print(f"[X] URL: https://x.com/{x_username}/status/{tweet_id}")
    return tweet_id


def post_tweet_with_image(text: str, image_path: str, x_username: str = "uni_keisuke") -> str:
    """X（Twitter）に画像付きツイートを投稿する。"""
    print(f"[X] 画像付きツイート投稿開始...")
    print(f"[X] 文字数: {len(text)}")

    access_token = _get_access_token()
    media_id = _upload_media(image_path, access_token)

    response = requests.post(
        "https://api.x.com/2/tweets",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={"text": text, "media": {"media_ids": [media_id]}},
        timeout=30,
    )

    if not response.ok:
        print(f"[X] 投稿エラー詳細: {response.text}")
    response.raise_for_status()

    tweet_id = str(response.json()["data"]["id"])
    print(f"[X] 投稿完了! Tweet ID: {tweet_id}")
    print(f"[X] URL: https://x.com/{x_username}/status/{tweet_id}")
    return tweet_id


def post_thread(
    tweets: list[str],
    image_path: str | None = None,
    x_username: str = "uni_keisuke",
) -> list[str]:
    """X にスレッド投稿する。最初のツイートに画像を付け、以降をリプライで連結する。"""
    if not tweets:
        raise ValueError("tweets が空です")

    print(f"[X] スレッド投稿開始（{len(tweets)}件）")

    access_token = _get_access_token()

    media_id = None
    if image_path:
        try:
            media_id = _upload_media(image_path, access_token)
        except Exception as e:
            print(f"[X] 画像アップロード失敗、テキストのみで継続: {e}")
            media_id = None

    tweet_ids: list[str] = []
    reply_to: str | None = None

    for i, text in enumerate(tweets, start=1):
        payload: dict = {"text": text}
        if i == 1 and media_id:
            payload["media"] = {"media_ids": [media_id]}
        if reply_to:
            payload["reply"] = {"in_reply_to_tweet_id": reply_to}

        print(f"[X] {i}/{len(tweets)} 投稿中（{len(text)}字）...")
        response = requests.post(
            "https://api.x.com/2/tweets",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
        if not response.ok:
            print(f"[X] 投稿エラー詳細: {response.text}")
        response.raise_for_status()

        tweet_id = str(response.json()["data"]["id"])
        tweet_ids.append(tweet_id)
        reply_to = tweet_id
        print(f"[X] {i}/{len(tweets)} 投稿完了: {tweet_id}")

    print(f"[X] スレッド投稿完了")
    print(f"[X] URL: https://x.com/{x_username}/status/{tweet_ids[0]}")
    return tweet_ids
