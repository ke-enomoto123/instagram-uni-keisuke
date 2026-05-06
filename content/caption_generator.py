import random
import os
import anthropic
from account_config import ACCOUNT_PERSONA, ACCOUNT_THEME, TOPIC_CATEGORIES, HASHTAGS_JA
from config import ANTHROPIC_API_KEY


def _tweet_weight(text: str) -> int:
    """X (Twitter) の重み付き文字数を計算（CJKは2、Latin系は1）"""
    weight = 0
    for ch in text:
        cp = ord(ch)
        if (0x0000 <= cp <= 0x10FF) or \
           (0x2000 <= cp <= 0x200D) or \
           (0x2010 <= cp <= 0x201F) or \
           (0x2032 <= cp <= 0x2037):
            weight += 1
        else:
            weight += 2
    return weight


def _truncate_to_tweet_weight(text: str, max_weight: int = 270, suffix: str = "…") -> str:
    """重み付き文字数で max_weight 以内に収める（margin 10で安全側）"""
    if _tweet_weight(text) <= max_weight:
        return text
    suffix_weight = _tweet_weight(suffix)
    target = max_weight - suffix_weight
    weight = 0
    for i, ch in enumerate(text):
        cp = ord(ch)
        char_weight = 1 if (0x0000 <= cp <= 0x10FF) or \
                            (0x2000 <= cp <= 0x200D) or \
                            (0x2010 <= cp <= 0x201F) or \
                            (0x2032 <= cp <= 0x2037) else 2
        if weight + char_weight > target:
            return text[:i].rstrip() + suffix
        weight += char_weight
    return text

# IGの投稿パターン（インフォグラフィック向けTips系を中心に）
IG_POST_PATTERNS = [
    "Tips型",       # 大人の余裕の作り方 5選
    "気づき型",      # 〜と思ってたけど、実は〜
    "体験談型",      # 先日◯◯したら、〜と気づいた
    "対比型",        # 〇〇する大人と、〇〇しない大人
    "リスト型",      # 大人がやってる小さな習慣
]

# X用のスレッド投稿パターン（ランキング・リスト形式）
X_THREAD_PATTERNS = [
    "ランキング型",      # 〇〇TOP5
    "リスト型",          # 〇〇する人がやってる5つの習慣
    "対比型",            # 〇〇する大人と、〇〇しない大人
    "数字×断言型",       # 40代で品が出る◯◯のコツ7
]

# uni固有の知識ベース（事実として参照可。捏造はNG）
UNI_DOMAIN_KNOWLEDGE = """
- 大人の身だしなみは「過剰でも怠惰でもない」中庸が品の鍵
- 40代以降は「足し算より引き算」のファッションが上品に見える
- 過剰な筋トレや極端なダイエットは品を損なう。日常の歩行・姿勢・呼吸の方が長期的に効く
- 香水は強すぎない方が記憶に残る（パーソナル空間に入って初めて気づく程度）
- 会話で相手を心地よくする最短距離は「先に話を最後まで聞く」
- 食事の場では「店の選び方」「席のリード」「終わり方」が印象を決める
- 質の良い時間を作る最大のコツは「予定に余白を持つこと」
- 40代の身体維持は「走る・上げる」より「整える・休める」の比重を増やす
- 大人のお金の使い方は「金額」より「対象と頻度の品」で見られる
- 教養は知識量より「知らないことを知らないと言える誠実さ」に出る
- 一人の時間を楽しめる人ほど、二人の時間も豊かになる
- 持ち物のこだわりは「主張より馴染み」。長く使ったものに品が宿る
- 大人の関係性は『追いかける』より『余白を残して待つ』
"""


def _generate_ig_caption(topic: str, pattern: str) -> str:
    """IG用キャプションを生成"""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    length_type = random.choices(
        ["short", "medium", "long"],
        weights=[20, 50, 30],
        k=1,
    )[0]

    length_instruction = {
        "short": "40〜80文字。一言で刺さる短いキャプション",
        "medium": "100〜180文字。気づきや体験を2〜3文で",
        "long": "180〜280文字。具体的なTipsや手順を含めて",
    }[length_type]

    prompt = f"""あなたは以下のペルソナでInstagramのキャプションを書いてください。

【ペルソナ】
{ACCOUNT_PERSONA}

【アカウントテーマ】
{ACCOUNT_THEME}

【投稿トピック】
{topic}

【投稿パターン】
{pattern}

【文字数】
{length_instruction}

【知識ベース（事実として参照可。捏造はNG）】
{UNI_DOMAIN_KNOWLEDGE}

【ルール】
- 押しつけがましくない、実体験のシェアとして書く
- 「〇〇する男が」のような断定や決めつけは避ける
- 軽薄・下品な言い回しはNG（小手先のテクではなく、品の話）
- 過剰な筋トレ・ハードトレーニング・極端なダイエットは話題にしない
- 「教えてやる」風NG。気づきの共有として書く
- 絵文字は0〜1個まで。多用しない
- 文末「。」は付けない
- ハッシュタグは含めない（別途追加する）

キャプション本文のみ出力してください。"""

    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )

    text = message.content[0].text.strip()
    text = text.rstrip("。").rstrip("．")
    return text


def _generate_x_thread(topic: str, pattern: str) -> dict:
    """X用ランキング/リスト形式のスレッド投稿を生成（main + reply）"""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    prompt = f"""あなたは以下のペルソナでX（Twitter）のスレッド投稿を作ります。

【ペルソナ】
{ACCOUNT_PERSONA}

【アカウントテーマ】
{ACCOUNT_THEME}

【トピック】
{topic}

【投稿パターン】
{pattern}

【知識ベース（事実として参照可。捏造はNG）】
{UNI_DOMAIN_KNOWLEDGE}

【⚠️ X の文字数仕様（厳守）】
- X は日本語1文字を「重み2」、英数字を「重み1」でカウントし、合計280まで
- つまり日本語のみだと **実質135字が上限**
- 各ツイート（メインもリプライも）は **日本語135字以内、できれば120字程度** を厳守
- 超えるとエラー（403 Forbidden）になる

【スレッド構成（必ず守る）】
1. メインツイート（日本語110〜130字）
   - キャッチーなタイトル（1行目で目を止める）
   - その後にランキング/リスト項目を5つ短く列挙（1項目10〜15字）
   - 末尾に「※詳しくはリプ欄👇」を入れる
   - ハッシュタグは **メイン末尾に最大1個** まで（容量を圧迫するので慎重に）
   - 例（日本語121字）:
     40代で色気が出る男の習慣5選

     1. 行きつけの店を持つ
     2. 朝の余白を作る
     3. 香りで主張しない
     4. 先に質問しない
     5. 別れ際を急がない

     ※詳しくはリプ欄👇

2. リプライ（日本語110〜130字）
   - 各項目の補足を1行ずつ。1項目18〜22字程度に収める
   - ハッシュタグは入れない
   - 押しつけがましくなく、実体験ベース
   - 例（日本語120字）:
     1. 馴染みの一人で過ごせる店が一本ある
     2. 朝5分の余白が日中の余裕を作る
     3. 香水は近距離で気づく程度に
     4. 質問より先に最後まで聞く
     5. 別れ際の3秒で印象が決まる

【出力フォーマット（厳守）】
==MAIN==
（メインツイート本文。改行を使ってOK）
==REPLY==
（リプライ本文。改行を使ってOK）

【ルール】
- 軽薄・下品な言い回しNG。年相応の品を保つ
- 過剰な筋トレ・ハードトレーニングは話題にしない
- ハッシュタグはメインの末尾に1〜2個まで
- 絵文字は最小限（0〜2個、👇程度）
- 文末「。」は付けない"""

    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=900,
        messages=[{"role": "user", "content": prompt}],
    )
    text = message.content[0].text.strip()

    # ==MAIN== / ==REPLY== でパース
    main_text = ""
    reply_text = ""
    if "==MAIN==" in text and "==REPLY==" in text:
        parts = text.split("==REPLY==")
        main_text = parts[0].split("==MAIN==", 1)[1].strip()
        reply_text = parts[1].strip()
    else:
        # フォールバック: 半分割
        midpoint = len(text) // 2
        main_text = text[:midpoint].strip()
        reply_text = text[midpoint:].strip()

    # 重み付き文字数で安全側 270 重み（< 280）にtruncate
    main_text = _truncate_to_tweet_weight(main_text, max_weight=270)
    reply_text = _truncate_to_tweet_weight(reply_text, max_weight=270)

    return {
        "tweets": [main_text, reply_text],
        "topic": topic,
        "pattern": pattern,
    }


def _score_caption(caption: str, topic: str) -> float:
    """品質採点（uni基準）"""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=10,
        messages=[{
            "role": "user",
            "content": f"""以下のInstagramキャプションを1〜10で採点してください。数字のみ回答。

評価基準：
- 40代イケオジの品と落ち着きが出ているか
- 押しつけがましくないか（NGワード: 「〇〇すべき」「絶対に」）
- 軽薄/下品でないか（NG）
- 共感・保存されそうか（具体性があるか）
- 過剰な筋トレ・ダイエット話題が含まれていないか

トピック：{topic}
キャプション：{caption}

点数（数字のみ）:"""
        }],
    )
    try:
        return float(message.content[0].text.strip().split()[0])
    except Exception:
        return 7.0


def build_caption() -> dict:
    """IG用キャプション生成（既存インターフェース維持）"""
    topic = random.choice(TOPIC_CATEGORIES)
    pattern = random.choice(IG_POST_PATTERNS)

    print(f"[Caption] トピック: {topic}")
    print(f"[Caption] パターン: {pattern}")

    caption = _generate_ig_caption(topic, pattern)
    score = _score_caption(caption, topic)
    print(f"[Caption] 品質スコア: {score}/10.0")

    max_retries = 2
    for i in range(max_retries):
        if score >= 7.0:
            break
        print(f"[Caption] スコア不足 → 再生成 ({i+1}/{max_retries})")
        caption = _generate_ig_caption(topic, pattern)
        score = _score_caption(caption, topic)
        print(f"[Caption] 品質スコア: {score}/10.0")

    selected_hashtags = random.sample(HASHTAGS_JA, min(7, len(HASHTAGS_JA)))
    full_caption = f"{caption}\n\n{' '.join(selected_hashtags)}"

    return {
        "caption": full_caption,
        "score": score,
        "topic": topic,
        "pattern": pattern,
    }


def build_x_thread() -> dict:
    """X用ランキング/リストスレッド投稿（main + reply）"""
    topic = random.choice(TOPIC_CATEGORIES)
    pattern = random.choice(X_THREAD_PATTERNS)
    print(f"[X Caption] トピック: {topic}")
    print(f"[X Caption] パターン: {pattern}")

    result = _generate_x_thread(topic, pattern)
    main_text, reply_text = result["tweets"][0], result["tweets"][1]
    print(
        f"[X Caption] Main: {len(main_text)}字 (重み{_tweet_weight(main_text)}/280) / "
        f"Reply: {len(reply_text)}字 (重み{_tweet_weight(reply_text)}/280)"
    )

    return result
