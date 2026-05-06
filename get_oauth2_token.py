"""
X OAuth 2.0 ユーザートークン取得スクリプト（初回のみ実行）
取得したrefresh_tokenをGitHub Secretsに保存してください。

実行方法:
  python get_oauth2_token.py
"""
import tweepy
import os
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("X_OAUTH2_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("X_OAUTH2_CLIENT_SECRET", "")

if not CLIENT_ID or not CLIENT_SECRET:
    print("❌ X_OAUTH2_CLIENT_ID と X_OAUTH2_CLIENT_SECRET を .env に設定してください")
    exit(1)

oauth2_handler = tweepy.OAuth2UserHandler(
    client_id=CLIENT_ID,
    redirect_uri="https://localhost",
    scope=["tweet.read", "tweet.write", "users.read", "offline.access"],
    client_secret=CLIENT_SECRET,
)

auth_url = oauth2_handler.get_authorization_url()
print("\n" + "="*60)
print("以下のURLをブラウザで開いてください：")
print("="*60)
print(auth_url)
print("="*60)
print("\n認証後、ブラウザのアドレスバーに表示されたURLを")
print("（https://localhost?state=...&code=... という形式）")
print("コピーして貼り付けてください：\n")

response_url = input("リダイレクトURL: ").strip()

token = oauth2_handler.fetch_token(response_url)

print("\n" + "="*60)
print("✅ 認証成功！以下をGitHub Secretsに保存してください：")
print("="*60)
print(f"X_OAUTH2_REFRESH_TOKEN = {token.get('refresh_token', 'なし（offline.accessスコープが必要）')}")
print(f"access_token（確認用）= {token.get('access_token', '')[:30]}...")
print("="*60)
