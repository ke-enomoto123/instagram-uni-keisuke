import random
import os
import anthropic
from account_config import ACCOUNT_PERSONA, TOPIC_CATEGORIES, HASHTAGS_JA, POST_LANGUAGE
from config import ANTHROPIC_API_KEY

POST_PATTERNS = [
    "体験談型",
    "比較型",
    "気づき型",
    "ハウツー型",
    "キャンペーン紹介型",
    "質問誘導型",
    "数字で語る型",
]

def _load_campaign_info() -> str:
    """campaigns/active.txtからキャンペーン情報を読み込む"""
    campaign_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "campaigns", "active.txt")
    if os.path.exists(campaign_file):
        with open(campaign_file, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if content:
                return content
    return ""

def _select_post_type() -> str:
    """投稿タイプを選択（時間帯別）"""
    time_of_day = os.getenv("TIME_OF_DAY", "general")
    if time_of_day == "morning":
        return random.choice(["ハウツー型", "気づき型", "数字で語る型"])
    elif time_of_day == "noon":
        return random.choice(["体験談型", "比較型", "キャンペーン紹介型"])
    else:  # evening
        return random.choice(["キャンペーン紹介型", "質問誘導型", "体験談型"])

def _generate_caption(topic: str, pattern: str, campaign_info: str) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    length_type = random.choices(
        ["short", "medium", "long"],
        weights=[30, 40, 30],
        k=1,
    )[0]

    length_instruction = {
        "short": "30〜60文字。一言で刺すような短いキャプション",
        "medium": "80〜150文字。体験や気づきを2〜3文で",
        "long": "150〜250文字。具体的な数字や手順を含めたお得情報",
    }[length_type]

    campaign_section = ""
    if campaign_info and random.random() < 0.4:
        campaign_section = f"""
【今使えるキャンペーン情報（事実のみ使用）】
{campaign_info}
"""

    prompt = f"""あなたは以下のペルソナでInstagramのキャプションを書いてください。

【ペルソナ】
{ACCOUNT_PERSONA}

【投稿トピック】
{topic}

【投稿パターン】
{pattern}

【文字数】
{length_instruction}
{campaign_section}

【SoftBankユーザー向け基礎知識（事実のみ・必要に応じて活用）】
- LYPプレミアム：通常月額508円（税込）→ SoftBankの対象プランユーザーは無料で使える
- LYPプレミアム会員はYahoo!ショッピングでポイント還元率が毎日+2倍になる
- PayPayカードのYahoo!ショッピング利用でさらに+1倍（合計で最大5〜7%還元も可能）
- PayPayカード基本還元率：1.5%（どこで使っても）
- PayPayステップ：月の利用条件を達成すると翌月の還元率が最大+0.5%アップ
- Yahoo!ショッピングは5のつく日・日曜日にポイント倍増キャンペーンが多い
- SoftBankまとめて支払いでPayPayポイントが貯まるサービスもある

【ルール】
- 「SoftBankユーザーなら」「SoftBankユーザーだから」「SoftBankユーザーは」のニュアンスを自然に含める
- 捏造はNG。具体的な数字は上記の基礎知識か、よく知られた事実のみ使用
- 企業の宣伝っぽくならない。あくまで一ユーザーの体験・発見として書く
- 絵文字を1〜2個使う
- 最後に「。」をつけない
- ハッシュタグは含めない（別途追加する）

キャプション本文のみ出力してください。"""

    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )

    text = message.content[0].text.strip()

    # 長さ制限
    max_chars = {"short": 60, "medium": 150, "long": 250}[length_type]
    if len(text) > max_chars * 2:
        for sep in ["。", "\n"]:
            if sep in text[:max_chars + 40]:
                text = text[:text.index(sep, max_chars - 20) + 1] if sep in text[max_chars - 20:] else text
                break
        else:
            text = text[:max_chars]
    text = text.rstrip("。")

    return text

def _score_caption(caption: str, topic: str) -> float:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=10,
        messages=[{
            "role": "user",
            "content": f"""以下のInstagramキャプションを1〜10で採点してください。数字のみ回答。

評価基準：
- SoftBank経済圏ユーザーとして自然か
- 企業っぽくないか（NG）
- 共感・保存されそうか
- 捏造・誇張がないか

トピック：{topic}
キャプション：{caption}

点数（数字のみ）:"""
        }],
    )
    try:
        return float(message.content[0].text.strip().split()[0])
    except:
        return 7.0

def build_caption() -> dict:
    topic = random.choice(TOPIC_CATEGORIES)
    pattern = _select_post_type()
    campaign_info = _load_campaign_info()

    print(f"[Caption] トピック: {topic}")
    print(f"[Caption] パターン: {pattern}")

    caption = _generate_caption(topic, pattern, campaign_info)
    score = _score_caption(caption, topic)
    print(f"[Caption] 品質スコア: {score}/10.0")

    max_retries = 2
    for i in range(max_retries):
        if score >= 7.0:
            break
        print(f"[Caption] スコア不足 → 再生成 ({i+1}/{max_retries})")
        caption = _generate_caption(topic, pattern, campaign_info)
        score = _score_caption(caption, topic)
        print(f"[Caption] 品質スコア: {score}/10.0")

    # ハッシュタグ選択（5〜8個）
    selected_hashtags = random.sample(HASHTAGS_JA, min(7, len(HASHTAGS_JA)))
    hashtag_text = " ".join(selected_hashtags)

    full_caption = f"{caption}\n\n{hashtag_text}"

    return {
        "caption": full_caption,
        "score": score,
        "topic": topic,
        "pattern": pattern,
    }
