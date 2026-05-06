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

# 落ち着いた大人カラー（赤・黄・ネオン禁止）
PRIMARY_COLOR_HEX = "#1a1a1a"      # 黒に近いダークグレー
ACCENT_COLOR_HEX = "#a08e5e"        # ゴールドベージュ

# 画像スタイル（ランダム選択）
# tips_infographic: Tips型インフォグラフィック（A・C系トピック向け）
# lifestyle_scene:  ライフスタイル雰囲気写真（B系トピック向け）
IMAGE_STYLES = ["tips_infographic", "lifestyle_scene"]


def _analyze_caption(caption: str) -> dict:
    """Claudeでキャプションを画像コンセプトに分析"""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=800,
        messages=[{
            "role": "user",
            "content": f"""以下のInstagram投稿テキストを読んで、画像コンセプトをJSONで出力してください。
40代男性向け大人ライフスタイル系アカウント用の、上品で落ち着いた画像です。

投稿テキスト:
{caption}

出力形式（JSONのみ。説明不要）:
{{
  "main_headline": "最も目立たせるメインコピー（15文字以内）",
  "sub_headline": "サブコピー（25文字以内、補足）",
  "tip_items": ["Tipsの項目1（15文字以内）", "Tipsの項目2", "Tipsの項目3", "Tipsの項目4", "Tipsの項目5"],
  "scene_keyword": "ライフスタイル写真のシーン描写（英語。例: dimly lit hotel bar with whisky glass on dark wood, leather notebook on walnut desk with soft warm lamp, evening cityscape from a high-floor lounge）",
  "mood": "雰囲気（calm/warm/sophisticated のどれか）"
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


def _prompt_tips_infographic(c: dict) -> str:
    """Tips型インフォグラフィック（落ち着いた編集デザイン）"""
    main_headline = c.get("main_headline", "大人の余裕の作り方")
    sub_headline = c.get("sub_headline", "")
    tip_items = c.get("tip_items", []) or []
    if len(tip_items) < 3:
        tip_items = (tip_items + ["項目1", "項目2", "項目3"])[:3]
    tip_items = tip_items[:5]
    mood = c.get("mood", "sophisticated")

    items_text = "\n".join([f'  {i+1}. "{item}"' for i, item in enumerate(tip_items)])

    mood_palette = {
        "calm":          "muted beige and soft gray on warm cream off-white background — minimal, serene",
        "warm":          "warm taupe and soft amber on warm cream background — like a tasteful lifestyle magazine",
        "sophisticated": "deep navy and warm gold on warm cream background — like a high-end editorial spread",
    }.get(mood, "deep navy and warm gold on warm cream background — like a high-end editorial spread")

    sub_block = f"""- Below: smaller sub-text "{sub_headline}" in lighter weight""" if sub_headline else ""

    return f"""
Create a sophisticated Japanese editorial tips infographic (1:1 square, 1024x1024px) for Instagram.
Style: high-end men's lifestyle magazine aesthetic — feels premium, calm, refined. Like Casa BRUTUS / Monocle / OCEANS magazine layout.
Mood and palette: {mood_palette}

LAYOUT:
- TOP: Bold Japanese headline "{main_headline}" in elegant serif typography (mincho-style)
{sub_block}
- THIN HORIZONTAL DIVIDING LINE
- CENTER: Numbered list of {len(tip_items)} tips, vertically arranged with thin dividing lines:
{items_text}
  Each item: number on left in a thin circular frame, Japanese text on right
  Use minimalist line icons (ultra-simple, geometric) beside or near each item — no photographic elements
- BOTTOM: Footer with "{ACCOUNT_HANDLE}" in small light gray text

DESIGN RULES:
- Editorial / minimalist Japanese aesthetic — looks like a curated lifestyle magazine spread
- Ample white space, refined typography hierarchy
- Color palette: muted, sophisticated — NO bright red, NO yellow, NO neon, NO loud colors
- All Japanese text perfectly rendered, readable, with proper kerning
- NO photographic faces, NO photographic objects — only minimal line illustrations
- Feels like an adult, well-bred audience would save it
- Avoid sales/advertisement vibe entirely
"""


def _prompt_lifestyle_scene(c: dict) -> str:
    """ライフスタイル雰囲気写真（人物なし）"""
    scene = c.get(
        "scene_keyword",
        "dimly lit hotel bar with a glass of whisky on dark walnut counter, warm amber lighting, leather chair in soft focus background"
    )
    main_headline = c.get("main_headline", "")
    mood = c.get("mood", "sophisticated")

    mood_desc = {
        "calm":          "soft, muted, peaceful — natural daylight, simple composition, calm atmosphere",
        "warm":          "warm tones, intimate, cinematic — golden hour or candlelight, inviting feel",
        "sophisticated": "moody, refined, luxurious — low key lighting, rich textures, restrained elegance",
    }.get(mood, "moody, refined, luxurious — low key lighting, rich textures, restrained elegance")

    headline_block = f"""
- Optional small Japanese text overlay "{main_headline}" placed tastefully (top-left or bottom) in refined thin typography (semi-transparent or muted color, never dominating the image)""" if main_headline else ""

    return f"""
Create a cinematic editorial lifestyle photograph for an Instagram post (1:1 square, 1024x1024px).
Subject: {scene}
Mood: {mood_desc}

COMPOSITION:
- Photographic style: editorial fine-art photography for a high-end men's lifestyle magazine
- NO PEOPLE in the frame (no faces, no full bodies; abstract silhouettes from behind only if absolutely needed)
- Rich textures: leather, dark wood, brass, glass, fabric, paper
- Shallow depth of field, professional lighting
- Composition is intentional and uncluttered{headline_block}
- BOTTOM: Tiny "{ACCOUNT_HANDLE}" watermark in semi-transparent type

RULES:
- No faces, no logos, no readable brand names
- Japanese typography (if any) must be perfectly rendered
- Atmospheric, calm, refined — feels like the personal space of a tasteful 40-something man
- Avoid clichés (no excessive cigars, no flashy luxury brands, no over-styled bachelor-pad vibes)
- No bright/loud colors — earth tones, deep neutrals, soft warm light only
"""


def _build_prompt(caption: str) -> str:
    """キャプション分析 → ランダムにスタイル選択してプロンプト生成"""
    try:
        c = _analyze_caption(caption)
        print(f"[Image] 画像コンセプト: {c}")
    except Exception as e:
        print(f"[Image] キャプション分析失敗、デフォルト使用: {e}")
        c = {}

    style = random.choice(IMAGE_STYLES)
    print(f"[Image] スタイル: {style}")

    if style == "tips_infographic":
        return _prompt_tips_infographic(c)
    else:
        return _prompt_lifestyle_scene(c)


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
