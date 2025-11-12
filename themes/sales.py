# -*- coding: utf-8 -*-
# 営業力改善 3分診断（既存と同一UI/スコア/タイプ判定/AIプロンプト）
import pandas as pd

THEME_META = {
    "title": "3分で分かる 営業力改善診断",
    "lead":  "**10問**に答えるだけで、営業の“詰まりどころ”を可視化します。"
}

# 選択肢
YN3 = ["Yes", "部分的に", "No"]
FREQ3 = ["よくある", "ときどき", "ほとんどない"]  # “よくある”はリスク高 → invert=True で反転

# スコア化
def to_score_yn3(ans: str, invert=False) -> int:
    base = {"Yes": 5, "部分的に": 3, "No": 1}
    v = base.get(ans, 3)
    return {5:1, 3:3, 1:5}[v] if invert else v

def to_score_freq(ans: str, invert=False) -> int:
    base = {"よくある": 1, "ときどき": 3, "ほとんどない": 5}
    v = base.get(ans, 3)
    return {5:1, 3:3, 1:5}[v] if invert else v

TYPE_TEXT = {
    "見込み客不足型": "新規の出会いが足りず、商談の母数が細っています。紹介づくり・情報発信・電話/訪問など誘因の仕組みを増やしましょう。",
    "提案弱含型": "商談はあるが、提案の深さ・相手理解が不足。課題の言語化と比較表、事例提示、決裁者巻き込みの設計が要点です。",
    "粗利圧迫型": "値引き前提の受注が多く、利益が逃げています。標準見積、条件のすり合わせ手順、代替案提示で防波堤を作りましょう。",
    "継続弱体型": "一度きりの取引が多く、更新・深耕が弱い状態。定期点検の約束、定期便の提案、解約兆候の早期察知を仕組みに。",
    "管理未整備型": "数字と進捗が見えず、重点と手戻りが発生。案件表・週次確認・共有メモなど“見える化”から始めましょう。",
    "バランス良好型": "全体は良好。次は粗利最大化と紹介の連鎖づくりへ。勝ち筋の型化と育成で伸ばしましょう。"
}

def render_questions(st):
    st.subheader("① 見込み客づくり（入口）")
    q1 = st.radio("Q1. 月ごとの新規コンタクト（問い合わせ・紹介・訪問など）の目標と実績を把握できていますか？", YN3, index=1)
    q2 = st.radio("Q2. “紹介が自然と生まれる仕組み”がありますか？（例：お礼・紹介依頼の定型、紹介特典など）", YN3, index=2)

    st.subheader("② 面談・提案（商談の質）")
    q3 = st.radio("Q3. 初回面談で、相手の課題や決裁プロセス、比較候補などの“必要な情報”をしっかり聞けていますか？", YN3, index=1)
    q4 = st.radio("Q4. 提案書や見積は“選べる案（標準/拡張/最小）”で提示できていますか？", YN3, index=1)

    st.subheader("③ 受注・価格（利益）")
    q5 = st.radio("Q5. 値引きの前に、“別案の提示”や“内容の見直し”など、他の方法で調整できていますか？", YN3, index=1)
    q6 = st.radio("Q6. 受注後の追加請求・範囲外工数の精算が曖昧になることがありますか？", FREQ3, index=1)  # よくある=リスク高 → そのまま

    st.subheader("④ 継続・紹介（深耕）")
    q7 = st.radio("Q7. 既存のお客様には、定期点検や更新の案内を“あらかじめ伝える”ようにしていますか？", YN3, index=2)
    q8 = st.radio("Q8. 解約や取引縮小の“前ぶれ”（反応薄・遅れなど）を早めに気づけていますか？", YN3, index=1)

    st.subheader("⑤ 体制・見える化（運用）")
    q9  = st.radio("Q9. 案件表（見込み〜受注）を週次で確認し、優先順位を共有できていますか？", YN3, index=1)
    q10 = st.radio("Q10. 商談メモ・見積・書式の“共通ひな形”を整え、誰でも使えるようにしていますか？", YN3, index=1)

    st.markdown("---")
    company = st.text_input("会社名（必須）", value=st.session_state["company"])
    email   = st.text_input("メールアドレス（必須）", value=st.session_state["email"])
    st.caption("※ 入力いただいた会社名・メールは診断ログとして保存されます（営業目的以外には利用しません）。")

    leads_scores   = [to_score_yn3(q1), to_score_yn3(q2)]
    propose_scores = [to_score_yn3(q3), to_score_yn3(q4)]
    price_scores   = [to_score_yn3(q5), to_score_freq(q6, invert=False)]
    retain_scores  = [to_score_yn3(q7), to_score_yn3(q8)]
    ops_scores     = [to_score_yn3(q9), to_score_yn3(q10)]

    df = pd.DataFrame({
        "カテゴリ": ["見込み客づくり","面談・提案","受注・価格","継続・紹介","体制・見える化"],
        "平均スコア": [
            sum(leads_scores)/2,
            sum(propose_scores)/2,
            sum(price_scores)/2,
            sum(retain_scores)/2,
            sum(ops_scores)/2
        ]
    })
    return company, email, df

def evaluate(df_scores: pd.DataFrame):
    overall_avg = df_scores["平均スコア"].mean()
    if overall_avg >= 4.0:
        signal = ("青信号", "badge-blue")
    elif overall_avg >= 2.6:
        signal = ("黄信号", "badge-yellow")
    else:
        signal = ("赤信号", "badge-red")

    if (df_scores["平均スコア"] >= 4.0).all():
        main_type = "バランス良好型"
    else:
        worst_row = df_scores.sort_values("平均スコア").iloc[0]
        cat = worst_row["カテゴリ"]
        main_type = {
            "見込み客づくり": "見込み客不足型",
            "面談・提案": "提案弱含型",
            "受注・価格": "粗利圧迫型",
            "継続・紹介": "継続弱体型",
            "体制・見える化": "管理未整備型",
        }[cat]
    return overall_avg, signal, main_type

def build_ai_prompt(company: str, main_type: str, df_scores: pd.DataFrame, overall_avg: float) -> str:
    worst2 = df_scores.sort_values("平均スコア", ascending=True).head(2)["カテゴリ"].tolist()
    signal = "青" if overall_avg>=4.0 else ("黄" if overall_avg>=2.6 else "赤")
    return f"""
あなたは中小企業の営業支援に詳しいコンサルタントです。以下の診断結果を受け、経営者向けに約300字（260〜340字）の具体的コメントを日本語で1段落で書いてください。
・前置きや免責は不要、箇条書き禁止。実行策を端的に。
・外来語やカタカナ語はできるだけ使わず、平易な日本語で。
・最後は信号色に応じた強さで「90分スポット診断」への自然な誘導で締める（赤=強く推奨、黄=推奨、青=任意の精緻化）。

[会社名] {company or "（未入力）"}
[全体平均] {overall_avg:.2f} / 5
[信号] {signal}
[タイプ] {main_type}
[弱点カテゴリTOP2] {", ".join(worst2)}
[5カテゴリ] {", ".join(df_scores["カテゴリ"].tolist())}
""".strip()
