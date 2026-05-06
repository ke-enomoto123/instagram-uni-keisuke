import os
import json
import random
import base64
import shutil
import requests
from io import BytesIO
from openai import OpenAI
import anthropic
from config import OPENAI_API_KEY, IMGBB_API_KEY, ANTHROPIC_API_KEY

# アカウント設定
ACCOUNT_HANDLE = "@uni.4534"
BRAND_COLOR_HEX = "#FF0027"

# 画像スタイル（ランダム選択）
IMAGE_STYLES = ["ad_banner", "awareness_infographic"]


def _analyze_caption(caption: str) -> dict:
    """Claudeでキャプションを広告コンセプトに分析"""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=800,
        messages=[{
            "role": "user",
            "content": f"""以下のInstagram投稿テキストを読んで、画像コンセプトをJSONで出力してください。

投稿テキスト:
{caption}

出力形式（JSONのみ。説明不要）:
{{
  "main_headline": "最も目立たせるメインコピー（15文字以内）",
  "sub_headline": "サブコピー（25文字以内）",
  "key_stat": "強調したい数字・特典（例: ポイント3倍、月額0円、5%還元）",
  "featured_service": "メインのサービス名（例: Yahoo!ショッピング, PayPay, LYPプレミアム）",
  "event_trigger": "日付・イベント名があれば（例: 5のつく日。なければ空文字）",
  "visual_objects": "画像内オブジェクト（英語。例: smartphone showing Yahoo Shopping app, red shopping bag, golden coins）",
  "awareness_hook": "気づかせる一言（例: 実はSoftBankユーザーなら月額0円！、この組み合わせで還元率が倍に）",
  "compare_before": "知らない人の損している状態（例: 毎月508円払い続けている）",
  "compare_after": "知った後の得している状態（例: 月額0円で同じサービスが使える）",
  "mood": "雰囲気（excited/warm/premium のどれか）"
}}"""
        }]
    )

    text = response.content[0].text.strip()
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            try:
                return json.loads(part)
            except Exception:
                continue
    return json.loads(text)


def _prompt_ad_banner(c: dict) -> str:
    """広告バナー型プロンプト"""
    main_headline  = c.get("main_headline", "知らないと損！")
    sub_headline   = c.get("sub_headline", "Yahoo!ショッピングでお得にEC節約")
    key_stat       = c.get("key_stat", "")
    featured       = c.get("featured_service", "Yahoo!ショッピング")
    event_trigger  = c.get("event_trigger", "")
    visual_objects = c.get("visual_objects", "smartphone showing shopping app, golden coins, red shopping bag")
    mood           = c.get("mood", "excited")

    event_block    = f'- TOP-RIGHT CORNER: Calendar or badge icon with Japanese text: "{event_trigger}"' if event_trigger else ""
    key_stat_block = f'- Large starburst badge with Japanese text "{key_stat}" in huge bold font' if key_stat else ""

    mood_desc = {
        "excited": "bright and energetic — red/yellow dominant, white background with sunburst lines",
        "warm":    "warm and friendly — orange/yellow palette, soft gradient",
        "premium": "sophisticated — dark navy background with gold accents",
    }.get(mood, "bright and energetic — red/yellow dominant, white background with sunburst lines")

    return f"""
Create a high-quality Japanese promotional banner (1:1 square, 1024x1024px) for Instagram.
Style: professional Japanese SNS advertisement — like a real EC or fintech app promotional graphic.
Mood: {mood_desc}

LAYOUT:
- TOP: Large bold Japanese headline "{main_headline}" in red font. Below: sub-text "{sub_headline}"
{event_block}
- CENTER: Main visuals — {visual_objects}. The smartphone shows {featured} app realistically.
{key_stat_block}
  Golden coin icons (¥/P symbols), sparkle stars, upward arrows as decorative accents.
- BOTTOM: Supporting Japanese benefit text. Footer: "{ACCOUNT_HANDLE}" in small gray.

RULES:
- All Japanese text perfectly rendered and readable
- Primary: {BRAND_COLOR_HEX} red. Secondary: #FFD700 gold/yellow
- NO CTA button. NO photographic faces — flat illustration style
- Scroll-stopping visual impact
"""


def _prompt_awareness_infographic(c: dict) -> str:
    """自ら気づき系インフォグラフィック型プロンプト"""
    main_headline  = c.get("main_headline", "知ってた？")
    awareness_hook = c.get("awareness_hook", "この組み合わせで還元率が変わる")
    key_stat       = c.get("key_stat", "")
    compare_before = c.get("compare_before", "知らずに損している状態")
    compare_after  = c.get("compare_after", "知った後にお得になった状態")
    featured       = c.get("featured_service", "LYPプレミアム")
    mood           = c.get("mood", "warm")

    key_stat_block = f'- A large highlighted circle or badge showing "{key_stat}" as the KEY DISCOVERY number' if key_stat else ""

    mood_desc = {
        "excited": "clean white background with light blue and yellow accents — feels like a helpful tips article",
        "warm":    "warm cream or light orange background — feels like a friendly magazine spread",
        "premium": "light gray background with clean lines — feels like a quality financial guide",
    }.get(mood, "clean white background with light blue and yellow accents — feels like a helpful tips article")

    return f"""
Create a Japanese "did you know?" awareness infographic (1:1 square, 1024x1024px) for Instagram.
Style: educational and eye-opening — like a helpful tips post from a Japanese lifestyle magazine or SNS influencer.
Mood: {mood_desc}

LAYOUT:

TOP SECTION:
- A thought bubble or lightbulb icon
- Bold Japanese question or hook text: "{main_headline}"
- Below: "{awareness_hook}" — written as a surprising discovery

MIDDLE SECTION (BEFORE vs AFTER comparison):
- LEFT column labeled "知らないと…" with a downward arrow icon
  Content: "{compare_before}" — illustrated with a sad or confused icon/emoji
- RIGHT column labeled "知ってると！" with an upward arrow icon
  Content: "{compare_after}" — illustrated with a happy or celebratory icon/emoji
- Dividing line or VS badge between the two columns
{key_stat_block}

BOTTOM SECTION:
- Summary tip text in Japanese: this is the key insight about {featured}
- Footer: "{ACCOUNT_HANDLE}" in small gray text

DESIGN RULES:
- Clean, minimal, easy-to-read layout — NOT a busy advertisement
- Uses icons and simple illustrations, NOT photographic images
- Primary accent: {BRAND_COLOR_HEX} red for key numbers and highlights
- Gold/yellow (#FFD700) for positive "after" elements
- Gray or light blue for negative "before" elements
- Japanese text must be perfectly rendered
- Feels like a discovery — the reader should think "え、知らなかった！"
"""


def _build_prompt(caption: str) -> str:
    """キャプション分析 → ランダムにスタイル選択してプロンプト生成"""
    try:
        c = _analyze_caption(caption)
        print(f"[Image] 広告コンセプト: {c}")
    except Exception as e:
        print(f"[Image] キャプション分析失敗、デフォルト使用: {e}")
        c = {}

    style = random.choice(IMAGE_STYLES)
    print(f"[Image] スタイル: {style}")

    if style == "ad_banner":
        return _prompt_ad_banner(c)
    else:
        return _prompt_awareness_infographic(c)


def _convert_to_jpeg(image_path: str) -> bytes:
    """画像をJPEGに変換（PNG→JPEG対応）"""
    try:
        from PIL import Image
        img = Image.open(image_path)
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGB')
        buffer = BytesIO()
        img.save(buffer, format='JPEG', quality=95)
        return buffer.getvalue()
    except ImportError:
        with open(image_path, 'rb') as f:
            return f.read()


def _get_user_photo() -> str | None:
    """photos/フォルダから未使用の写真を取得"""
    photos_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "photos")
    used_dir = os.path.join(photos_dir, "used")
    os.makedirs(used_dir, exist_ok=True)

    extensions = ('.jpg', '.jpeg', '.png', '.webp')
    photos = sorted([
        f for f in os.listdir(photos_dir)
        if f.lower().endswith(extensions) and os.path.isfile(os.path.join(photos_dir, f))
    ])

    if not photos:
        return None

    selected = photos[0]
    photo_path = os.path.join(photos_dir, selected)
    used_path = os.path.join(used_dir, selected)
    shutil.move(photo_path, used_path)
    print(f"[Image] ユーザー写真を使用: {selected}")
    return used_path


def _upload_to_imgbb(image_path: str) -> str:
    """JPEG変換してimgbbにアップロード、URLを返す"""
    jpeg_data = _convert_to_jpeg(image_path)
    encoded = base64.b64encode(jpeg_data).decode('utf-8')

    response = requests.post(
        "https://api.imgbb.com/1/upload",
        data={
            "key": IMGBB_API_KEY,
            "image": encoded,
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()["data"]
    return data["display_url"]


def _generate_with_openai(prompt: str, save_path: str) -> str | None:
    """gpt-image-2 → gpt-image-1 の順でフォールバックして生成。imgbb URLを返す"""
    client = OpenAI(api_key=OPENAI_API_KEY)

    for model in ["gpt-image-2", "gpt-image-1"]:
        try:
            print(f"[Image] {model} で画像生成中...")
            response = client.images.generate(
                model=model,
                prompt=prompt,
                size="1024x1024",
                quality="medium",
                n=1,
            )
            image_data = base64.b64decode(response.data[0].b64_json)
            with open(save_path, 'wb') as f:
                f.write(image_data)
            print(f"[Image] {model} 生成完了 → {save_path}")

            try:
                image_url = _upload_to_imgbb(save_path)
                print(f"[Image] imgbbアップロード完了")
                return image_url
            except Exception as e:
                print(f"[Image] imgbbアップロード失敗: {e}")
                return None

        except Exception as e:
            print(f"[Image] {model} 失敗: {e}")
            if model == "gpt-image-1":
                raise
            print(f"[Image] {model} → gpt-image-1 にフォールバック...")

    return None


def generate_image(caption: str, save_path: str):
    """ユーザー写真優先、なければgpt-image-2（→gpt-image-1フォールバック）で生成"""
    # ① ユーザー写真を試す
    user_photo = _get_user_photo()
    if user_photo:
        try:
            image_url = _upload_to_imgbb(user_photo)
            print(f"[Image] ユーザー写真をimgbbにアップロード完了")
            return user_photo, image_url
        except Exception as e:
            print(f"[Image] imgbbアップロード失敗: {e}")

    # ② OpenAI画像生成（gpt-image-2 → gpt-image-1 フォールバック）
    prompt = _build_prompt(caption)
    image_url = _generate_with_openai(prompt, save_path)

    return save_path, image_url
