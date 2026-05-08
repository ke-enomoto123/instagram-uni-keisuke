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


def _split_navigation(text: str) -> tuple[str, str]:
    """テキストから navigation 部分（※〜リプ欄系）を分離。返値: (body, navigation)"""
    lines = text.split("\n")
    nav_start = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("※") and ("リプ欄" in stripped or "続き" in stripped or "詳細" in stripped):
            nav_start = i
            break
    if nav_start is None:
        return text, ""
    body = "\n".join(lines[:nav_start]).rstrip()
    navigation = "\n".join(lines[nav_start:]).strip()
    return body, navigation


def _smart_split_first_tweet(text: str, max_weight: int = 270) -> list[str]:
    """Tweet 1 専用 smart split。navigation（※続きはリプ欄系）を必ず Tweet 1 末尾に置く。"""
    if _tweet_weight(text) <= max_weight:
        return [text]

    body, navigation = _split_navigation(text)
    if not navigation:
        return _split_tweet_by_sentence(text, max_weight)

    nav_weight = _tweet_weight(navigation)
    if nav_weight >= max_weight - 30:
        return _split_tweet_by_sentence(text, max_weight)

    body_max = max_weight - nav_weight - 2
    body_pieces = _split_tweet_by_sentence(body, max_weight=body_max)
    if not body_pieces:
        return [navigation]

    tweet1 = (body_pieces[0] + "\n\n" + navigation).strip()
    if _tweet_weight(tweet1) > max_weight:
        return _split_tweet_by_sentence(text, max_weight)

    return [tweet1] + body_pieces[1:]


def _split_tweet_by_sentence(text: str, max_weight: int = 270) -> list[str]:
    """1ツイート分のテキストを、必要なら複数ツイートに分割（文単位優先、最後の手段で文字単位）"""
    if _tweet_weight(text) <= max_weight:
        return [text]

    import re
    # 改行 / 句点 / 感嘆符 / 疑問符 で chunk 化（区切り記号を保持）
    parts = re.split(r"(\n+|。|！|？)", text)
    chunks = []
    cur = ""
    for p in parts:
        if not p:
            continue
        if re.fullmatch(r"\n+|。|！|？", p):
            cur += p
            chunks.append(cur)
            cur = ""
        else:
            cur += p
    if cur:
        chunks.append(cur)

    tweets: list[str] = []
    current = ""
    for chunk in chunks:
        if _tweet_weight(current + chunk) <= max_weight:
            current += chunk
        else:
            if current.strip():
                tweets.append(current.strip())
            current = ""
            # chunk 単体が長すぎる場合のみ、最終手段で文字単位ハード分割
            while _tweet_weight(chunk) > max_weight:
                weight = 0
                idx = len(chunk)
                for i, ch in enumerate(chunk):
                    cp = ord(ch)
                    cw = 1 if (0x0000 <= cp <= 0x10FF) or \
                              (0x2000 <= cp <= 0x200D) or \
                              (0x2010 <= cp <= 0x201F) or \
                              (0x2032 <= cp <= 0x2037) else 2
                    if weight + cw > max_weight:
                        idx = i
                        break
                    weight += cw
                tweets.append(chunk[:idx].rstrip())
                chunk = chunk[idx:]
            current = chunk
    if current.strip():
        tweets.append(current.strip())
    return tweets

# IGの投稿パターン（実体験エピソード型を最重視）
IG_POST_PATTERNS = [
    "体験談型（先日◯◯した時、〜と気づいた）",
    "失敗→学び型（20代の頃◯◯してて、今は◯◯にしてる、と前向きに転換）",
    "気づき型（前は◯◯と思ってたけど、◯◯してから変わった）",
    "シーン描写型（バーで隣の常連が◯◯してて、それを見て）",
    "対話型（後輩に質問されて返答に詰まった話）",
    "ギャップ型（実は苦手なこと／意外な趣味）",
    "Tips型（◯選）",
    "ランキング型（1位〜5位）",
]

# IG パターンの選択重み（実体験系を 70%）
IG_POST_PATTERN_WEIGHTS = [25, 15, 15, 10, 5, 10, 10, 10]

# 冒頭フック（実体験ベース・友人語り口・家族言及NG・紳士的）
HOOK_LINES = [
    "先日のバーで気づいたことなんだけど",
    "30代の頃の自分が知らなかったこと",
    "出張先のホテルラウンジで隣の常連を見て",
    "30代と40代で変わったなと思うこと",
    "後輩に質問されて返答に詰まった話",
    "なんてことない夜の、ちょっとした気づき",
    "若い頃と違って、最近大事にしてること",
    "週末の一人時間で気づいたこと",
    "ある会食で印象的だった話",
    "20代に戻れるなら伝えたいこと",
]

# 地名（重み付き選択。HIGH=頻出、MED=中頻度、LOW=控えめ）
HIGH_FREQ_LOCATIONS = [
    "恵比寿", "銀座", "五反田", "目黒", "渋谷", "代々木上原", "新橋", "大手町",
]
MED_FREQ_LOCATIONS = [
    "中目黒", "代官山", "麻布", "西麻布", "白金", "丸の内", "表参道", "青山", "神楽坂", "三軒茶屋",
]
LOW_FREQ_LOCATIONS = [
    "六本木", "京都", "大阪", "福岡",
]


def _select_location() -> str:
    bucket = random.choices(["high", "med", "low"], weights=[60, 30, 10], k=1)[0]
    if bucket == "high":
        return random.choice(HIGH_FREQ_LOCATIONS)
    if bucket == "med":
        return random.choice(MED_FREQ_LOCATIONS)
    return random.choice(LOW_FREQ_LOCATIONS)


# 地名トピックのテンプレート（高級〜庶民派の使い分けを含む）
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
    "{location}の大人の使い方（高級〜庶民派の使い分け）",
    "{location}で品よく赤提灯を楽しむ大人の作法",
    "{location}の渋い立ち飲み・赤提灯の品ある楽しみ方",
]

# 地名トピック向けの構造パターン
LOCATION_FRIENDLY_PATTERNS = [
    "ランキング型（1位〜5位の店紹介）",
    "段階型（初心者・中級・モテ級それぞれの店）",
    "年齢型（20代女性向け・30代女性向け・40代女性向け）",
    "シーン型（一軒目・二軒目・締めの店）",
]

# X用のスレッド投稿パターン（バズる実体験型・口癖型を中心に）
X_THREAD_PATTERNS = [
    "口癖ランキング型（モテる40代がよく言う言葉ベスト◯）",
    "やめたこと型（30代でやめてよかったこと◯選）",
    "気づき体験型（先日◯◯で気づいた◯つのこと）",
    "失敗から学んだ型（20代の頃やらかして学んだ◯選）",
    "前後変化型（30代と40代で変わったこと◯選）",
    "ランキング型（1位〜5位の順位付け）",
    "DO/DON'T型（やる方 vs やらない方を5項目）",
    "段階型（駆け出し・中堅・大人それぞれの違い）",
]

# uni固有の知識ベース（実体験・気づきベース。捏造はNG）
UNI_DOMAIN_KNOWLEDGE = """
【モテる40代がよく言う口癖（自然に出る言葉）】
- 「いいね」: どんな場面でも肯定的に応答できる包容力
- 「大丈夫」: 大げさでなく自然に言える、相手を安心させる
- 「俺がやるよ」: 困っている人や責任のある仕事に率先して引き受ける
- 「ありがとう」: 呼吸するように自然に感謝を伝える
- 「楽しみだな」: 趣味や生活に喜びを感じている、相手にも前向きなエネルギー
- 「なんとかなるよ」: 辛い状況でも一緒に寄り添う安心感
- 「心配しなくていいよ」: 落ち込んでる相手に自然な励まし

【女性が見ている細かい所作（実体験で語れる小さなディテール）】
- 約束の時間より5〜10分前に到着する、待たせない
- 相手が話してる間スマホを見ない、目を見て聞く
- 「そのときどう感じたの？」と具体的な質問で話を広げる
- 寒そうにしてたら「席変えようか」と先に提案
- 「それも良い考えだね」と肯定してから自分の意見を述べる
- 自慢話の代わりに「この前◯◯あってさ、そこで学んだのが〜」と経験を活かす形で話す
- 愚痴を言わない、「困難があったけど乗り越えた」と転換
- 見返り要求しない、「喜んでくれると嬉しい」で終わらせる

【大人の余裕の正体（実感したこと）】
- 余裕は「暇」じゃない。忙しい中でも相手の前で一拍置ける、それが余裕
- 思いやりは時間がある時だけじゃなく、忙しい時こそ短い連絡や心遣いに表れる
- 「忙しい」と相手に言わないのが大人。忙しさを感じさせず相手の時間を最優先する方が魅力的
- ハプニング発生時に感情的にならず、冷静に対処できると安心感がある
- 焦り・そわそわ・自分の思い通りにならないとイライラ → 余裕がない男の典型

【大人の魅力の核】
- 何かに夢中になってること自体が魅力（軽いトレーニング・本・カフェ巡り・ワインなど）
- ギャップ：シリアスとユーモア、馬鹿な自分も見せられる隙
- 修羅場経験から得た心の余裕（自慢話じゃなく学んだことを語る）
- 教養：知識量より「知らないことを知らないと言える誠実さ」に出る
- 「今に集中」：デート中はデートに集中、過去を後悔しない

【お金の使い方の本質】
- 「金額の大小」より「相手と場面に見合っているか」で見られる
- 好きな相手・記念日・特別な日には、お互いの気持ちに見合った金額を迷わず使う
- 出し惜しみして余裕を装うのは逆効果
- 「会う回数を減らして単価を上げる」発想は最もセコく見える（絶対NG）

【お酒の話題（教養として、語り口は実体験）】
- 白ワインは魚介・前菜、赤は肉・濃い料理、オレンジは香り立つ料理（中華・スパイス系）
- ワインは「ナッツの香りがする」と感じたまま言える方が、専門用語より好印象
- シャンパーニュは祝杯。記念日には1本ボトルで頼む方が品が出る
- ハイボールは薄めの方が食事を邪魔しない
- 日本酒は燗で旨味、冷やで切れ
- ウイスキーはシングルモルトとブレンデッドの違いを知ってるくらい
- バーでは「マスターの一推しは？」と聞ける、それが品

【大人の楽しみ方の幅】
- 高級店だけじゃなく、新橋の立ち飲み・赤提灯にも品よく通える、それが本当の余裕
- 場所で評価を変えない、銀座でも立ち飲みでも同じ自分

【絶対に書かないNG表現】
- 「〜は野暮」「〜は品」「〜の作法」「〜すべき」「絶対〇〇」
- 「〇〇する男 / しない男」のような二項分類・決めつけ
- 「教えてやる」「これが正解」風の上から目線
- 完璧を演じる、自分や仕事を理想化する、自慢する
- ⚠️ 妻・娘・家族・家庭・パートナー・嫁・連れ合いなど家族関連の言及（既婚設定だが投稿には出さない）
- ⚠️ 殴る・蹴る・潰す・叩くなど暴力的・粗野な表現（紳士性を欠く）
- ⚠️ 自虐・自己否定（『自分を殴りたくなる』『恥ずかしい過去』など）。失敗は前向きに転換して書く
"""


def _select_topic_and_pattern() -> tuple[str, str, bool]:
    """トピックとパターンを選定。20%の確率で地名トピックに切り替える（頻度を下げて実体験系を増やす）。"""
    use_location = random.random() < 0.2
    if use_location:
        location = _select_location()
        template = random.choice(LOCATION_TOPIC_TEMPLATES)
        topic = template.format(location=location)
        pattern = random.choice(LOCATION_FRIENDLY_PATTERNS)
        return topic, pattern, True
    pattern = random.choices(IG_POST_PATTERNS, weights=IG_POST_PATTERN_WEIGHTS, k=1)[0]
    return random.choice(TOPIC_CATEGORIES), pattern, False


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
- ⚠️ **必ず実体験ベース**: 「先日◯◯した時」「あるバーで」「出張先で」「20代の頃◯◯してて」など具体シーンから始める
- ⚠️ **家族関連の言及は絶対NG**: 妻・娘・家族・家庭・パートナー・嫁・連れ合いなどの単語は投稿に一切出さない（既婚設定だが投稿では触れない）
- ⚠️ **暴力的・粗野な表現は絶対NG**: 殴る・蹴る・潰す・叩く等は紳士性を欠くため禁止
- ⚠️ **自虐・後ろ向きNG**: 「自分を殴りたくなる」「恥ずかしい過去」などの自己否定はNG。失敗は『前向きに学んだこと』として書く
- ⚠️ **教科書・先生口調はNG**: 「〜は野暮」「〜の作法」「〜すべき」「絶対〇〇」「〇〇する男/しない男」のような決めつけは禁止。ただし自信を持って言える信念は『俺はこう思う』形でOK
- ⚠️ **完璧を演じない**: 苦手なこと・想定外の出来事は混ぜてOK（家族関連シーン以外）
- 自慢話・愚痴・見返り要求は絶対NG
- 軽薄・下品な言い回しNG
- 過剰な筋トレ・ハードトレーニング・極端なダイエットは話題にしない
- 【セコい表現は絶対NG】会う回数を減らす・出費を抑える・1回の単価で勝負する、などの計算高い発想は厳禁
- 余裕は『暇』ではなく『忙しい中での思いやり・心の余白』として書く
- お金は『出し惜しみせず、相手と場面に見合った金額を迷わず使う』方向で
- モテる40代の口癖（「いいね」「楽しみだな」「俺がやるよ」「ありがとう」等）を1つ自然に混ぜると◎
- 絵文字は0〜2個まで。多用しない
- 文末「。」は付けない
- ハッシュタグは含めない（別途追加する）

【出力前に自己チェック】
- 妻・娘・家族・家庭・パートナーなど家族を匂わせる単語が混ざっていないか（混ざってたら書き直し）
- 殴る・蹴るなどの暴力的・粗野な表現がないか
- 自虐・自己否定で締めていないか（失敗は前向きに転換できているか）
- 「〜は野暮」「〜の作法」「〜すべき」「絶対」のような押しつけ口調が混ざっていないか
- 実体験エピソード（先日／前に／あるバーで）から始まっているか

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
- 日本語のみだと **実質135字が上限**、ハッシュタグや記号も含むので余裕を見て120字
- 各ツイート（1件目もリプライも）は **日本語120字以内、目安110字** で書く
- ハッシュタグや「※続きはリプ欄👇」も文字数に含めて計算する
- 超えるとエラー（403 Forbidden）になる

【⚠️ 1ツイートに押し込まないこと】
- 内容を1ツイートに無理に詰め込まない
- 120字を超えそうになったら、文の終わりで切って **次のツイートに送る**
- 「続きはリプ欄」「次に続く」など、自然な流れで次ツイートにつなぐ
- 最終的なツイート数は当初の目標を超えてOK（質を優先）

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

【1件目（先頭ツイート）の必須要素・厳守】
- {hook_instruction}
- 目を止めるキャッチーなタイトル
- 全項目（5つ前後）の見出しだけを短く列挙（1項目10〜13字）
- **末尾に必ず「※続きはリプ欄👇」を1件目の中に入れる**（絶対に2件目以降に切り離さない）
- ハッシュタグはメイン末尾に **最大1個** まで
- 上記すべてを含めて **1件目は日本語110字以内** に収める（フック・タイトル・見出し・誘導・ハッシュタグの合計）
- 入りきらなければ、見出し数を3〜4個に減らすか、タイトルを短くする
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
- ⚠️ **家族関連の言及は絶対NG**: 妻・娘・家族・家庭・パートナー・嫁・連れ合いの単語は一切出さない（既婚設定だが投稿には触れない）
- ⚠️ **暴力的・粗野な表現は絶対NG**: 殴る・蹴る・潰す・叩く等は紳士性を欠くため禁止
- ⚠️ **自虐・後ろ向きNG**: 「自分を殴りたい」「恥ずかしい過去」など。失敗は前向きに転換して書く
- ⚠️ **教科書・先生口調はNG**: 「〜は野暮」「〜の作法」「〜すべき」「絶対〇〇」「〇〇する男/しない男」のような決めつけは禁止。ただし自信を持って言える信念は『俺はこう思う』形でOK
- 必ず実体験ベース・気づき型・口癖／失敗から学んだこと（前向きに）など
- ランキング型でも、項目は「マスターに〜と言うようにしてる」「先日〜してて気づいた」など実体験寄りに
- モテる40代の口癖（「いいね」「楽しみだな」「俺がやるよ」「ありがとう」等）を活かす
- 軽薄・下品NG。年相応の品を保つ
- 過剰な筋トレ・ハードトレーニング・極端なダイエットは話題にしない
- 【セコい表現は絶対NG】会う回数を減らす・出費を抑える・1回の単価で勝負する、などの計算高い発想は厳禁
- 自慢話・愚痴・見返り要求NG
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

    # Tweet 1 は navigation を必ず保持、それ以降は通常 split
    expanded: list[str] = []
    for i, t in enumerate(tweets):
        if i == 0:
            expanded.extend(_smart_split_first_tweet(t, max_weight=270))
        else:
            expanded.extend(_split_tweet_by_sentence(t, max_weight=270))
    tweets = expanded

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

評価基準（厳しめに）：
- ⚠️ 実体験エピソードから始まっているか（「先日」「前に」「あるバーで」等）→ ない場合-3点
- ⚠️ 妻・娘・家族・家庭・パートナーなど家族関連の単語が混ざってないか → あれば-5点（即落第レベル）
- ⚠️ 殴る・蹴る・潰すなど暴力的・粗野な表現がないか → あれば-5点（即落第レベル）
- ⚠️ 自虐・自己否定（『自分を殴りたい』『恥ずかしい過去』等）で締めてないか → あれば-3点
- ⚠️ 教科書・先生口調が混ざってないか（「〜は野暮」「〜の作法」「〜すべき」等）→ あれば-3点
- ⚠️ 「〇〇する男/しない男」のような二項分類・決めつけがないか → あれば-2点
- 完璧を演じてないか（自分や仕事を理想化していないか）
- 40代の口癖・人間味が自然に出ているか
- 共感・保存されそうか（具体シーン・固有性があるか）
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
        location = _select_location()
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
