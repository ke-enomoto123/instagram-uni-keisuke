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

# IGの投稿パターン（多様化）
IG_POST_PATTERNS = [
    "Tips型（◯選）",
    "ランキング型（1位〜5位）",
    "段階型（初心者・中級・上級・モテ級）",
    "年齢型（20代・30代・40代の違い）",
    "気づき型（〜と思ってたけど、実は〜）",
    "体験談型（先日◯◯したら、〜と気づいた）",
    "対比型（〇〇する大人と、〇〇しない大人）",
    "リスト型（大人がやってる小さな習慣）",
]

# 冒頭フックのバリエーション（IG/X両方で使用）
HOOK_LINES = [
    "女性にモテたい既婚者へ",
    "女性と過ごす時の既婚モテポイント",
    "デート慣れしてる40代の話",
    "女性が密かに見ている大人男性の所作",
    "20代・30代女性に好かれる40代の特徴",
    "女性ウケする40代男性の余裕とは",
    "デート上手な大人男性へ",
    "大人のデートを格上げするコツ",
    "女性に「また会いたい」と思わせる男の習慣",
    "イケオジが普通にやってる、女性が気づく所作",
]

# 地名（トレンドの大人スポットがある主要エリア）
LOCATIONS = [
    "渋谷", "銀座", "中目黒", "代官山", "六本木", "麻布", "西麻布",
    "恵比寿", "白金", "丸の内", "表参道", "青山", "神楽坂", "三軒茶屋",
    "京都", "大阪", "福岡",
]

# 地名トピックのテンプレート
LOCATION_TOPIC_TEMPLATES = [
    "モテ既婚者の{location}の飲み方",
    "{location}で大人カップルが選ぶスポット",
    "{location}で女性と過ごす夜の店選び",
    "{location}の隠れた大人バー",
    "{location}でデートが格上がる店",
    "{location}の大人が通う一軒",
    "{location}で女性が喜ぶスポット",
    "{location}デートの正解",
    "{location}でモテる大人の店選び",
]

# 地名トピック向けの構造パターン
LOCATION_FRIENDLY_PATTERNS = [
    "ランキング型（1位〜5位の店紹介）",
    "段階型（初心者・中級・モテ級それぞれの店）",
    "年齢型（20代女性向け・30代女性向け・40代女性向け）",
    "シーン型（一軒目・二軒目・締めの店）",
]

# X用のスレッド投稿パターン（バラエティ重視）
X_THREAD_PATTERNS = [
    "ランキング型（1位〜5位の順位付け）",
    "理由型（理由1〜5で根拠を並べる）",
    "段階型（初級・中級・上級・モテ級など段階分け）",
    "ステップ型（Step 1〜5、順序立てた手順）",
    "BEFORE→AFTER型（やる前 vs やった後の対比）",
    "やりがちNG vs 大人の正解（NG3つ → 正解3つ）",
    "リスト型（〇〇する人がやってる5つの習慣など）",
    "DO/DON'T型（やる方 vs やらない方を5項目）",
    "数字×断言型（40代で品が出る◯◯のコツ7など）",
]

# uni固有の知識ベース（事実として参照可。捏造はNG）
UNI_DOMAIN_KNOWLEDGE = """
- 大人の身だしなみは「過剰でも怠惰でもない」中庸が品の鍵
- 40代以降は「足し算より引き算」のファッションが上品に見える
- 過剰な筋トレや極端なダイエットは品を損なう。日常の歩行・姿勢・呼吸の方が長期的に効く
- 香水は強すぎない方が記憶に残る（パーソナル空間に入って初めて気づく程度）
- 会話で相手を心地よくする最短距離は「先に話を最後まで聞く」
- 食事の場では「店の選び方」「席のリード」「終わり方」が印象を決める
- 余裕とは「暇」ではなく、忙しい中でも女性の前ではセルフコントロールが効き、思いやりを示せる心の余白のこと
- 思いやりは『時間がある時だけ示す』ものじゃない。忙しい時こそ短い連絡や心遣いに表れる
- 「忙しい」と相手に言わないのが大人。忙しさを感じさせず、相手の時間を最優先する方が魅力的
- 40代の身体維持は「走る・上げる」より「整える・休める」の比重を増やす
- お金の使い方は『金額の大小』より『相手と場面に見合っているか』で見られる
- 好きな相手・気になる相手・記念日・特別な日には、お互いの気持ちに見合った金額を迷わず使う
- 出し惜しみして余裕を装うのは逆効果。会う回数を減らして単価を上げる発想は最もセコく見える
- 教養は知識量より「知らないことを知らないと言える誠実さ」に出る
- 一人の時間を楽しめる人ほど、二人の時間も豊かになる
- 持ち物のこだわりは「主張より馴染み」。長く使ったものに品が宿る
- 大人の関係性は『追いかける』より『余白を残して待つ』
"""


def _select_topic_and_pattern() -> tuple[str, str, bool]:
    """トピックとパターンを選定。30%の確率で地名トピックに切り替える。"""
    use_location = random.random() < 0.3
    if use_location:
        location = random.choice(LOCATIONS)
        template = random.choice(LOCATION_TOPIC_TEMPLATES)
        topic = template.format(location=location)
        pattern = random.choice(LOCATION_FRIENDLY_PATTERNS)
        return topic, pattern, True
    return random.choice(TOPIC_CATEGORIES), random.choice(IG_POST_PATTERNS), False


def _generate_ig_caption(topic: str, pattern: str, is_location: bool) -> str:
    """IG用キャプションを生成"""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    length_type = random.choices(
        ["short", "medium", "long"],
        weights=[15, 45, 40],
        k=1,
    )[0]

    length_instruction = {
        "short": "60〜100文字。一言で刺さる短いキャプション",
        "medium": "120〜200文字。気づきや体験を2〜3文で",
        "long": "200〜320文字。具体的なTipsや手順を含めて",
    }[length_type]

    # 65%の確率で冒頭フックを入れる
    use_hook = random.random() < 0.65
    if use_hook:
        hook = random.choice(HOOK_LINES)
        hook_instruction = f"""
【冒頭フック（必須）】
1行目に「{hook}」のような短い誘導フレーズを入れる。
この通りでなくてOK、似た意図の自然な変形可（例：「{hook[:8]}…」「{hook}向け」）。
1行目はフックのみ、2行目から空行を1つ空けて本文。
"""
    else:
        hook_instruction = "【冒頭フック】今回は使わず、本文から自然に始める。"

    # 地名トピックなら、実在する店をいくつか出すよう指示
    location_instruction = ""
    if is_location:
        location_instruction = """
【地名トピックの追加ルール】
- その地名にある実在する大人向けバー・レストラン・ラウンジなどを2〜3軒、自然に登場させる
- 大人男性が女性をエスコートするのに使える店選び（落ち着いた雰囲気・上質な内装・大人向け）
- 嘘の店名は捏造禁止。確信が持てない場合は店名を出さず「青山の隠れたフレンチ」「西麻布の老舗バー」など総称・特徴で表現
- ランキング・段階・年齢別・シーン別など、構造を持たせて並べる
"""

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

{hook_instruction}
{location_instruction}

【知識ベース（事実として参照可。捏造はNG）】
{UNI_DOMAIN_KNOWLEDGE}

【ルール】
- 押しつけがましくない、実体験のシェアとして書く
- 「〇〇する男が」のような断定や決めつけは避ける
- 軽薄・下品な言い回しはNG（小手先のテクではなく、大人の品と余裕の話）
- 過剰な筋トレ・ハードトレーニング・極端なダイエットは話題にしない
- 【セコい表現は絶対NG】会う回数を減らす・出費を抑える・1回の単価で勝負する・コスパ重視の節約デート、などの計算高い発想や表現は厳禁
- 余裕は『暇』ではなく『忙しい中での思いやり・心の余白』として書く
- お金の話は『出し惜しみせず、相手と場面に見合った金額を迷わず使う』方向で
- 「教えてやる」風NG。気づきの共有として書く
- 絵文字は0〜2個まで。多用しない
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


def _parse_thread_tweets(text: str) -> list[str]:
    """==TWEET N== 区切りでスレッドをパース"""
    import re
    parts = re.split(r"==\s*TWEET\s*\d+\s*==", text)
    return [p.strip() for p in parts if p.strip()]


def _generate_x_thread(topic: str, pattern: str, is_location: bool) -> dict:
    """X用スレッド投稿を生成（2〜5件、内容の質に応じて構成可変）"""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # 内容の量に応じて2-5件のツイート数を方針として渡す
    target_count = random.choices([2, 3, 4, 5], weights=[35, 35, 20, 10])[0]

    # 65%の確率で1件目に冒頭フックを入れる
    use_hook = random.random() < 0.65
    if use_hook:
        hook = random.choice(HOOK_LINES)
        hook_instruction = f'1件目の冒頭1行目に「{hook}」のような短い誘導を入れる（変形可）。空行を空けて本文。'
    else:
        hook_instruction = '冒頭フックは使わず、タイトルから始める。'

    # 地名トピックなら、実在する店をいくつか出すよう指示
    location_instruction = ""
    if is_location:
        location_instruction = """
【地名トピックの追加ルール】
- その地名にある実在する大人向けバー・レストラン・ラウンジを2〜3軒、自然に登場させる
- 大人男性が女性をエスコートする店選び（落ち着いた・上質・大人向け）
- 嘘の店名は捏造禁止。確信が持てない場合は「青山の隠れたフレンチ」「西麻布の老舗バー」など総称・特徴で表現
- ランキング・段階・年齢別・シーン別など構造を持たせる
"""

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
- 各ツイート（1件目もリプライも）は **日本語135字以内、目安120字程度** を厳守
- 超えるとエラー（403 Forbidden）になる

【スレッドの分量】
- 今回は **{target_count}件** のツイートで構成してください
- 内容の質を最優先。文字数を埋めるための水増しは禁止
- 各ツイートは独立して読めるよう配慮

【スレッド構成パターン例（{target_count}件構成のとき）】
- 2件: 1=タイトル＋全項目見出し / 2=各項目の詳細をまとめて
- 3件: 1=タイトル＋全項目見出し / 2=詳細前半 / 3=詳細後半
- 4件: 1=フック＋全項目見出し / 2=上位3項目の詳細 / 3=残り2項目の詳細 / 4=まとめ
- 5件: 1=タイトル＋全項目見出し / 2-5=各項目1ツイートずつ深掘り

【投稿パターン】
{pattern}

→ 「ランキング型」なら1位〜5位、「段階型」なら初級・中級・上級・モテ級、
  「BEFORE→AFTER型」なら変化の前後、「DO/DON'T型」ならOK例とNG例、
  というように、選んだパターンに合った構造で組み立ててください。

【1件目（先頭ツイート）の必須要素】
- {hook_instruction}
- 目を止めるキャッチーなタイトル
- 全項目（5つ前後）の見出しだけを短く列挙（1項目10〜15字）
- 末尾に「※続きはリプ欄👇」のような誘導を入れる
- ハッシュタグはメイン末尾に **最大1個** まで
{location_instruction}

【2件目以降の必須要素】
- 各項目の補足を1行ずつ
- ハッシュタグは入れない
- 押しつけがましくなく、実体験ベース

【出力フォーマット（厳守）】
==TWEET 1==
（1件目本文。改行使用OK）
==TWEET 2==
（2件目本文）
...（合計{target_count}件分繰り返す）

【絶対ルール】
- 軽薄・下品NG。年相応の品を保つ
- 過剰な筋トレ・ハードトレーニング・極端なダイエットは話題にしない
- 【セコい表現は絶対NG】会う回数を減らす・出費を抑える・1回の単価で勝負する・コスパ重視の節約デート、などの計算高い発想や表現は厳禁
- 余裕は『暇』ではなく『忙しい中での思いやり・心の余白』として書く
- お金の話は『出し惜しみせず、相手と場面に見合った金額を迷わず使う』方向で
- 絵文字は最小限（0〜2個、👇程度）
- 文末「。」は付けない
- 各ツイートは日本語135字以内（重み280以内）"""

    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = message.content[0].text.strip()

    tweets = _parse_thread_tweets(text)

    # フォールバック: パース失敗で2件未満なら半分割
    if len(tweets) < 2:
        midpoint = len(text) // 2
        tweets = [text[:midpoint].strip(), text[midpoint:].strip()]

    # 重みベースで各ツイートをtruncate（margin 10）
    tweets = [_truncate_to_tweet_weight(t, max_weight=270) for t in tweets]

    return {
        "tweets": tweets,
        "topic": topic,
        "pattern": pattern,
        "target_count": target_count,
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
    """IG用キャプション生成（地名トピック・冒頭フック対応）"""
    topic, pattern, is_location = _select_topic_and_pattern()

    print(f"[Caption] トピック: {topic} {'(地名)' if is_location else ''}")
    print(f"[Caption] パターン: {pattern}")

    caption = _generate_ig_caption(topic, pattern, is_location)
    score = _score_caption(caption, topic)
    print(f"[Caption] 品質スコア: {score}/10.0")

    max_retries = 2
    for i in range(max_retries):
        if score >= 7.0:
            break
        print(f"[Caption] スコア不足 → 再生成 ({i+1}/{max_retries})")
        caption = _generate_ig_caption(topic, pattern, is_location)
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
    """X用スレッド投稿（地名トピック・冒頭フック対応、可変2-5件）"""
    use_location = random.random() < 0.3
    if use_location:
        location = random.choice(LOCATIONS)
        topic = random.choice(LOCATION_TOPIC_TEMPLATES).format(location=location)
        pattern = random.choice(LOCATION_FRIENDLY_PATTERNS)
    else:
        topic = random.choice(TOPIC_CATEGORIES)
        pattern = random.choice(X_THREAD_PATTERNS)

    print(f"[X Caption] トピック: {topic} {'(地名)' if use_location else ''}")
    print(f"[X Caption] パターン: {pattern}")

    result = _generate_x_thread(topic, pattern, use_location)
    print(f"[X Caption] {len(result['tweets'])}件構成（目標{result.get('target_count','?')}件）")
    for i, t in enumerate(result["tweets"], 1):
        label = "Main " if i == 1 else f"Tw{i:>2}"
        print(f"[X Caption] {label}: {len(t)}字 (重み{_tweet_weight(t)}/280)")

    return result
