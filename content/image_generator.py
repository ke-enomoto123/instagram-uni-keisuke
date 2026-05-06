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
    """高級ブランドブック風の凝ったTipsインフォグラフィック"""
    main_headline = c.get("main_headline", "大人の余裕の作り方")
    sub_headline = c.get("sub_headline", "")
    tip_items = c.get("tip_items", []) or []
    tip_items = (tip_items + ["項目1", "項目2", "項目3"])[:5]
    mood = c.get("mood", "sophisticated")

    items_text = "\n".join([
        f'  Item {i+1}: large elegant Roman numeral or arabic number "{i+1}" in champagne-gold serif at left, '
        f'matched to Japanese mincho text "{item}" on the right side'
        for i, item in enumerate(tip_items)
    ])

    mood_palette = {
        "calm":          "deep slate-charcoal base with warm ivory and brushed brass-gold accents — like a monogrammed leather notebook",
        "warm":          "rich burgundy/oxblood base with warm ivory and brass-gold accents — like a Park Hyatt brand brochure cover",
        "sophisticated": "deep midnight navy or near-black base with champagne-gold and warm ivory accents — like a luxury watch maison's catalogue cover",
    }.get(mood, "deep midnight navy or near-black base with champagne-gold and warm ivory accents — like a luxury watch maison's catalogue cover")

    return f"""
Create a striking premium editorial infographic (1:1 square, 1024x1024px) for a 40s adult men's lifestyle Instagram account.

AESTHETIC REFERENCE:
High-end luxury magazine cover meets boutique hotel brand book. Think The Rake, Robb Report, Casa BRUTUS, Monocle covers, Aman Resorts brand assets, or a Patek Philippe annual catalogue. Premium, intentional, eye-catching, refined.

COLOR PALETTE:
{mood_palette}
Maximum 3 colors total: dark base + ivory/cream + champagne-gold accent. NO bright red, NO yellow, NO neon, NO bright tones.

LAYOUT (precise, all Japanese text must render perfectly):
- TOP-CENTER: A small ornate decorative element above the headline — thin double-line frame, monogram badge, classical seal, or fine art-deco motif (in champagne gold)
- HEADLINE: "{main_headline}" in large elegant Japanese mincho/serif typography, set in warm ivory or champagne gold. Confident, refined, NOT loud.
- SUBLINE: "{sub_headline}" in smaller mincho italic-feel weight below, slightly tracked, in muted ivory
- A thin horizontal hairline divider (1px, gold) under the header
- BODY (center, vertically stacked): Numbered tip list with strong hierarchy:
{items_text}
  Numbers should be visually DOMINANT (large, champagne-gold serif numerals — like a Roman editorial folio) — they catch the eye first.
  Japanese tip text aligned to the right of each number, in elegant mincho.
  Between each item: a delicate gold hairline divider (very thin).
- BACKGROUND: Subtle texture — fine linen weave, brushed paper grain, or matte fabric — NOT a flat solid color. Slight inner vignette darkening at edges.
- DECORATIVE ACCENTS: Tiny classic line ornaments at the four corners (filigree / fleurons / minimal art-deco motifs), set in thin gold, sized so they frame without competing.
- BOTTOM-CENTER: A small monogram-style seal containing "{ACCOUNT_HANDLE}" in tiny refined lettering, with a thin gold circle around it.

DESIGN RULES:
- Feels expensive, slow, intentional — like print, not screen
- Strong visual hierarchy: ornament → headline → numbered tips → footer
- Japanese text perfectly rendered (mincho/serif weight, accurate kerning, no malformed glyphs)
- NO sales / promotional vibe, NO photographic faces, NO product shots
- Negative space is part of the design — let the typography breathe
- The image should make a 40-something man pause, screenshot, and save it
"""


def _prompt_lifestyle_scene(c: dict) -> str:
    """シネマティック写真 ＋ ダークガラス調オーバーレイ Tips"""
    scene = c.get(
        "scene_keyword",
        "dimly lit luxury hotel lounge at dusk, single tumbler of amber whisky on dark walnut counter, brass detailing, leather Chesterfield in shallow focus background, warm amber lamp glow"
    )
    main_headline = c.get("main_headline", "")
    sub_headline = c.get("sub_headline", "")
    tip_items = c.get("tip_items", []) or []
    short_tips = tip_items[:3]
    mood = c.get("mood", "sophisticated")

    mood_desc = {
        "calm":          "soft natural daylight, refined and peaceful — like an Aman Resorts portfolio shot",
        "warm":          "warm intimate cinematic — golden hour or candlelight, inviting and tasteful — like a Park Hyatt suite at dusk",
        "sophisticated": "moody low-key luxurious — deep shadows, warm pools of light, rich textures — like a Robb Report editorial spread",
    }.get(mood, "moody low-key luxurious — deep shadows, warm pools of light, rich textures — like a Robb Report editorial spread")

    overlay_block = ""
    if main_headline or short_tips:
        items_text = "\n".join([f'    {i+1}. "{item}"' for i, item in enumerate(short_tips)]) if short_tips else ""
        sub_inline = f'\n  - Below the headline, a thin gold hairline divider, then "{sub_headline}" in italicized smaller weight' if sub_headline else ""
        items_inline = f"\n  - Below the divider, numbered tips in warm ivory mincho:\n{items_text}" if items_text else ""
        overlay_block = f"""
TYPOGRAPHY OVERLAY (critical):
- On the LEFT THIRD or BOTTOM of the canvas, place a translucent dark-glass / smoked-obsidian panel (semi-transparent black with subtle inner glow), giving rich legibility for text
- Panel framing: a thin champagne-gold hairline border (1px), with delicate art-deco corner accents
- Inside the panel:
  - Japanese headline "{main_headline}" in elegant mincho/serif, in warm champagne gold{sub_inline}{items_inline}
- Right side / remaining canvas keeps the rich photographic atmosphere fully visible
- Panel must NOT cover the focal subject of the photo — should feel like a typeset caption layered over editorial photography
"""

    return f"""
Create a cinematic editorial lifestyle composition for a 40s adult men's Instagram (1:1 square, 1024x1024px).

AESTHETIC REFERENCE:
Editorial fine-art photography meets premium magazine layout. Think Robb Report / The Rake / Park Hyatt brand book / Aman Resorts portfolio. Atmospheric, intentional, restrained luxury.

PHOTOGRAPHY:
- Subject scene: {scene}
- Lighting and mood: {mood_desc}
- NO PEOPLE / NO FACES (abstract silhouettes from behind only if absolutely necessary)
- Rich material textures: dark walnut, brass, leather, glass, wool, silk, linen
- Shallow depth of field, deliberate composition, deep shadows used as compositional element
- Restrained palette: dominant earth tones (deep brown, charcoal, oxblood, navy) + ONE warm accent (amber, brass-gold, warm ivory)
{overlay_block}
- BOTTOM-RIGHT CORNER: Tiny "{ACCOUNT_HANDLE}" watermark in semi-transparent ivory or gold, never visually dominant

RULES:
- No readable brand names, no logos, no faces
- Japanese typography must be perfectly rendered (proper mincho/serif rendering, accurate kerning)
- Atmosphere over information — image must evoke 余裕 (refined leisure / composure)
- Avoid clichés: no piles of red roses, no cigars, no flashy bachelor-pad vibes
- Final image should make the viewer feel "this is what mature elegance looks like"
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
