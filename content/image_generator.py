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

# 画像スタイル（重み付きランダム選択）
# illustration_with_people: 人物イラスト＋会話/気づき調（日常感重視）
# tips_infographic:         上品なTips型インフォグラフィック
# lifestyle_scene:          ライフスタイル写真＋オーバーレイTips
IMAGE_STYLES = [
    ("illustration_with_people", 50),  # 日常感メイン（半分）
    ("tips_infographic", 25),
    ("lifestyle_scene", 25),
]


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

AESTHETIC REFERENCE (highest priority):
Premium adult Tokyo lifestyle magazine — strongly evoke 大人の週末 (Otonano-Shumatsu) and 東京カレンダー (Tokyo Calendar) magazine spreads. Sophisticated Tokyo nightlife/dining culture for refined adult readers. Premium, intentional, modern, eye-catching but warm — never stiff luxury-watch-catalogue feel.

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
    """大人の週末/東京カレンダー風 シーン写真 ＋ ダークガラス調オーバーレイ Tips"""
    scene = c.get(
        "scene_keyword",
        "dimly lit modern Tokyo bar at night, single tumbler of amber whisky on dark walnut counter, brass detailing, leather banquette in shallow focus background, warm amber lamp glow, Ginza vibe"
    )
    main_headline = c.get("main_headline", "")
    sub_headline = c.get("sub_headline", "")
    tip_items = c.get("tip_items", []) or []
    short_tips = tip_items[:3]
    mood = c.get("mood", "sophisticated")

    mood_desc = {
        "calm":          "soft warm light at dusk, refined Tokyo restaurant interior — like a 大人の週末 dining feature",
        "warm":          "warm intimate cinematic — candlelight, brass lamps, inviting Tokyo bar atmosphere — like 東京カレンダー dining feature spread",
        "sophisticated": "moody low-key — deep shadows, warm pools of light, rich textures, modern Tokyo nightlife — like 東京カレンダー mature dating feature illustration",
    }.get(mood, "moody low-key — deep shadows, warm pools of light, rich textures, modern Tokyo nightlife — like 東京カレンダー mature dating feature illustration")

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

AESTHETIC REFERENCE (highest priority):
Premium adult Tokyo lifestyle magazine — strongly evoke 大人の週末 (Otonano-Shumatsu) dining feature spreads and 東京カレンダー (Tokyo Calendar) mature dating editorial. Sophisticated Tokyo nightlife/dining culture for refined adult readers. Atmospheric, intentional, modern.

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


def _prompt_illustration_with_people(c: dict) -> str:
    """モダンTokyo・デート慣れの大人男性イラスト（女性ウケを狙う）"""
    main_headline = c.get("main_headline", "")
    sub_headline = c.get("sub_headline", "")
    tip_items = c.get("tip_items", []) or []
    short_tips = tip_items[:5]
    mood = c.get("mood", "sophisticated")

    items_block = ""
    if short_tips:
        nums = "\n".join([f'    {i+1}. "{t}"' for i, t in enumerate(short_tips)])
        items_block = f"""
- RIGHT-SIDE TRANSLUCENT PANEL: A clean modern panel with numbered tips:
{nums}
  Modern Japanese sans-serif or thin elegant serif typography, in deep ink or warm gold.
"""

    palette = {
        "calm":          "soft cream background with deep navy and dusty rose accents — modern Tokyo lifestyle magazine like Hanako",
        "warm":          "warm ivory background with deep brown, amber, and brass accents — premium izakaya/bar at golden hour, like Pen magazine",
        "sophisticated": "deep charcoal/midnight blue base with brass-gold and warm ivory accents — sophisticated Tokyo nightlife, like GINZA magazine cover",
    }.get(mood, "deep charcoal/midnight blue base with brass-gold and warm ivory accents — sophisticated Tokyo nightlife, like GINZA magazine cover")

    return f"""
Create a chic MODERN editorial illustration (1:1 square, 1024x1024px) for a stylish 40s "kakkoii older man" Instagram account aimed at female audience (cute/pretty 20s-30s women who love gourmet and good drinks).

AESTHETIC REFERENCE (highest priority):
Premium adult Tokyo lifestyle magazine illustration. Strongly evoke 大人の週末 (Otonano-Shumatsu) and 東京カレンダー (Tokyo Calendar) magazine — sophisticated Tokyo nightlife/dining culture aimed at refined adult readers. Think Tokyo Calendar's romance feature illustrations, mature urban-dating editorial spreads, refined-but-warm color treatment.

ABSOLUTELY DO NOT USE (critical constraints):
- NO sepia tones, NO faded yellow vintage filter, NO Showa-era retro
- NO 暮しの手帖 / NO literary watercolor wash style
- NO melancholic / contemplative / quiet folksy vibe
- NO casual hand-lettered child-like typography

SCENE:
A stylish 40s adult man in a sophisticated MODERN Tokyo setting, captured in a moment that women would screenshot and dream about. The man is composed, kakkoii, refined, dating-savvy.

Setting examples (pick one fitting the topic):
- Modern Shibuya / Ginza / Naka-Meguro / Daikanyama bar at night with soft accent lighting and brass detailing
- Trendy Aoyama / Roppongi / Nishi-Azabu izakaya with refined dark wood interior
- A rooftop bar with Tokyo night view (neon, blue hour)
- A sleek modern restaurant with intimate seating and candlelight
- A specialty cocktail bar with marble counter
- A premium hotel lounge at dusk with city view

CHARACTER (critical nuance — busy yet composed):
- The 40s man: handsome, refined, well-tailored smart-casual (well-fit knit, blazer, crisp tailored shirt, or refined turtleneck). Modern haircut. Holds a glass of wine/whisky/highball with care.
- He looks BUSY-BUT-FULLY-PRESENT. Subtle clues he came from work and is generously making time for her: a closed leather notebook on the corner of the table, a smartphone placed face-down (NOT being looked at), a coat draped on the chair behind him. But all his attention is on the woman.
- Posture: composed, slightly leaning toward her — undivided attention, never rushed. The "余裕" is in his thoughtfulness toward her, NOT in idleness.
- Optional: a 20s-30s woman across from him in genuine conversation — modern, attractive, fashionable (one-piece dress, blouse, refined earrings). Real interaction (laughing, listening intently). She visibly feels valued and unhurried by him. NEVER objectified.
- Faces: clean modern features, attractive and dating-savvy. Confident expressions with warmth. NOT cartoonish, NOT melancholic, NOT retro.
- DRAWING STYLE: clean modern lineart with confident strokes, soft modern color blocks, slight cinematic atmosphere, crisp shadows. Editorial illustration in the spirit of 東京カレンダー magazine spreads.

LAYOUT:
- TOP or TOP-LEFT: Headline "{main_headline}" in clean modern Japanese typography (sans-serif or thin elegant serif), in deep ink, warm gold, or dusty rose. NEVER hand-lettered casual.
- {f'Below in lighter weight: "{sub_headline}"' if sub_headline else ''}
- CENTER: The main illustrated scene (largest visual element)
{items_block}
- BOTTOM or BOTTOM-RIGHT: Small "{ACCOUNT_HANDLE}" in modern thin type

PALETTE:
{palette}
- Modern slightly cinematic lighting — Tokyo evening, blue hour, neon accent, candlelight, brass
- AVOID at all costs: sepia, faded yellow, dusty muted retro, watercolor wash, sentimental literary

TONE:
- "I want to date a man like this" / "そのバーに連れて行ってほしい" — appealing to 20s-30s women who love gourmet and drinks
- Confident, refined, kakkoii, scrollable-by-women
- Slightly romantic, modern, urban Tokyo nightlife
- Viewer should imagine being IN this scene with him

RULES:
- Modern, NOT retro
- Japanese text perfectly rendered in MODERN type weight
- No real-brand logos
- Faces illustrated, attractive, modern fashion
- The vibe is confident dating-savvy adult, not literary/nostalgic
"""


def _build_prompt(caption: str) -> str:
    """キャプション分析 → 重み付きランダムでスタイル選択してプロンプト生成"""
    try:
        c = _analyze_caption(caption)
        print(f"[Image] 画像コンセプト: {c}")
    except Exception as e:
        print(f"[Image] キャプション分析失敗、デフォルト使用: {e}")
        c = {}

    styles, weights = zip(*IMAGE_STYLES)
    style = random.choices(styles, weights=weights, k=1)[0]
    print(f"[Image] スタイル: {style}")

    if style == "tips_infographic":
        return _prompt_tips_infographic(c)
    elif style == "illustration_with_people":
        return _prompt_illustration_with_people(c)
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
