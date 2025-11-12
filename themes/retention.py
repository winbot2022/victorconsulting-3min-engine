# -*- coding: utf-8 -*-
# 人材定着 3分診断 v1.1（やさしい日本語版／中小企業向け表現）
import pandas as pd

THEME_META = {
    "title": "3分で分かる 人材定着診断",
    "lead":  "**10問**に答えるだけで、離職の“火種”を5つの視点で可視化します。"
}

# 選択肢（5が良、1が悪）
YN3 = ["Yes", "部分的に", "No"]
FREQ3_SOFT = ["よくある", "ときどきある", "ほとんどない"]

TYPE_TEXT = {
    "採用・受け入れ未整備型": "採用要件や受け入れ体制に隙があり、入社後早期離職の火種を抱えています。採用基準の明確化と入社後3か月の育成フォローを整えましょう。",
    "評価・成長経路不明型": "評価や成長の道筋が見えにくく、やりがいを失いやすい状態です。目標設定と振り返りの仕組みを整え、成長実感を高めましょう。",
    "育成停滞型": "仕事を通じて学ぶ仕組みが弱く、社員が伸び悩む状態です。社内研修や外部講座など、学びの機会を計画的に設けましょう。",
    "働き方ミスマッチ型": "労働時間や待遇、柔軟性への不満が積み重なっています。定期的に意見を聞き、働き方の見直しを進めましょう。",
    "マネジメント・風土課題型": "上司の対応や人間関係に不満が残り、離職リスクを高めています。職場の声を拾い、信頼関係を築くマネジメントが鍵です。",
    "定着良好型": "全体的に良好。今後は要退職層の早期検知とハイパフォーマー育成への投資へ進みましょう。"
}

# --- スコア変換 ---
def to_score_yn3(ans: str, invert: bool = False) -> int:
    base = {"Yes": 5, "部分的に": 3, "No": 1}
    v = base.get(ans, 3)
    return {5: 1, 3: 3, 1: 5}[v] if invert else v

def to_score_freq3(ans: str, invert: bool = False) -> int:
    base = {"よくある": 1, "ときどきある": 3, "ほとんどない": 5}
    v = base.get(ans, 3)
    return {5: 1, 3: 3, 1: 5}[v] if invert else v

# --- UI（設問） ---
def render_questions(st):
    # ① 採用・受け入れ育成
    st.subheader("① 採用・受け入れ育成")
    q1 = st.radio(
        "Q1. 採用要件（スキル・経験・考え方・社風との相性）は文書で整理され、面接で一貫して確認できていますか？",
        YN3, index=1, key="ret_q1"
    )
    q2 = st.radio(
        "Q2. 入社から3か月までの受け入れ・育成（新人教育や担当者によるフォロー体制）が整っていますか？",
        YN3, index=1, key="ret_q2"
    )

    # ② 評価・成長経路
    st.subheader("② 評価・成長経路")
    q3 = st.radio(
        "Q3. 等級・評価基準・賃金の関係がわかりやすく、期初の目標をもとに評価できていますか？",
        YN3, index=1, key="ret_q3"
    )
    q4 = st.radio(
        "Q4. 将来の成長ステップや配置転換の仕組みがあり、本人と方向性を共有できていますか？",
        YN3, index=1, key="ret_q4"
    )

    # ③ 育成・成長実感
    st.subheader("③ 育成・成長実感")
    q5 = st.radio(
        "Q5. 上司との話し合いや仕事の振り返りの時間を、どの程度持つようにしていますか？",
        FREQ3_SOFT, index=1, key="ret_q5"
    )
    q6 = st.radio(
        "Q6. 社員が仕事に役立つ知識やスキルを学ぶ機会（社内研修・外部講座など）を持てていますか？",
        YN3, index=1, key="ret_q6"
    )

    # ④ 働き方・就労条件
    st.subheader("④ 働き方・就労条件")
    q7 = st.radio(
        "Q7. 所定外労働（残業や休日出勤）が多いと感じる声は、社内でどの程度ありますか？",
        FREQ3_SOFT, index=1, key="ret_q7"
    )
    q8 = st.radio(
        "Q8. 給与・働き方・福利厚生などについて、社員の意見を聞いたり見直したりする機会がありますか？",
        YN3, index=1, key="ret_q8"
    )

    # ⑤ マネジメント・職場風土
    st.subheader("⑤ マネジメント・職場風土")
    q9 = st.radio(
        "Q9. 職場で、上司の対応や人間関係に不満を感じている社員がいると感じますか？",
        FREQ3_SOFT, index=1, key="ret_q9"
    )
    q10 = st.radio(
        "Q10. 社員の悩みや退職の兆しを早めに察知し、話し合える仕組みや習慣がありますか？",
        YN3, index=2, key="ret_q10"
    )

    st.markdown("---")
    company = st.text_input("会社名（必須）", value=st.session_state.get("company", ""))
    email   = st.text_input("メールアドレス（必須）", value=st.session_state.get("email", ""))
    st.caption("※ 入力いただいた会社名・メールは診断ログとして保存されます（営業目的以外には利用しません）。")

    # 各カテゴリ（0-5、5が良）
    hire_scores   = [to_score_yn3(q1), to_score_yn3(q2)]
    eval_scores   = [to_score_yn3(q3), to_score_yn3(q4)]
    grow_scores   = [to_score_freq3(q5), to_score_yn3(q6)]
    work_scores   = [to_score_freq3(q7, invert=True), to_score_yn3(q8)]
    mgmt_scores   = [to_score_freq3(q9, invert=True), to_score_yn3(q10)]

    df = pd.DataFrame({
        "カテゴリ": ["採用・受け入れ育成", "評価・成長経路", "育成・成長実感", "働き方・就労条件", "マネジメント・職場風土"],
        "平均スコア": [
            sum(hire_scores) / len(hire_scores),
            sum(eval_scores) / len(eval_scores),
            sum(grow_scores) / len(grow_scores),
            sum(work_scores) / len(work_scores),
            sum(mgmt_scores) / len(mgmt_scores),
        ]
    })
    df["平均スコア"] = df["平均スコア"].round(2)
    return company, email, df

# --- 集計・タイプ判定 ---
def evaluate(df_scores: pd.DataFrame):
    overall_avg = df_scores["平均スコア"].mean()

    if overall_avg >= 4.0:
        signal = ("青信号", "badge-blue")
    elif overall_avg >= 2.6:
        signal = ("黄信号", "badge-yellow")
    else:
        signal = ("赤信号", "badge-red")

    if (df_scores["平均スコア"] >= 4.0).all():
        main_type = "定着良好型"
    else:
        worst_row = df_scores.sort_values("平均スコア").iloc[0]
        cat = worst_row["カテゴリ"]
        main_type = {
            "採用・受け入れ育成": "採用・受け入れ未整備型",
            "評価・成長経路":     "評価・成長経路不明型",
            "育成・成長実感":     "育成停滞型",
            "働き方・就労条件":   "働き方ミスマッチ型",
            "マネジメント・職場風土": "マネジメント・風土課題型",
        }.get(cat, "マネジメント・風土課題型")
    return overall_avg, signal, main_type

# --- AIコメント用プロンプト ---
def build_ai_prompt(company: str, main_type: str, df_scores: pd.DataFrame, overall_avg: float) -> str:
    worst2 = df_scores.sort_values("平均スコア", ascending=True).head(2)["カテゴリ"].tolist()
    signal = "青" if overall_avg >= 4.0 else ("黄" if overall_avg >= 2.6 else "赤")
    strength = {"赤": "強く推奨", "黄": "推奨", "青": "任意"}.get(signal, "推奨")

    return f"""
あなたは人材定着に精通した経営コンサルタントです。以下の診断結果を受け、経営者向けに約300字（260〜340字）で日本語コメントを1段落で作成。
・前置きや免責は不要、箇条書き禁止、具体策重視。
・外来語やカタカナ語（例：メンター、エンゲージメント、モチベーション等）は使わず、現場の人にも伝わる日本語で具体的に書いてください。
・最後の1文は信号色に応じた強度（{strength}）で「90分スポット診断」への自然な誘導で締める（赤=強く推奨、黄=推奨、青=任意の精緻化）。
・外来語やカタカナ語（例：メンター、キャリアパス、エンゲージメント、モチベーションなど）は使わず、「先輩の支援」「将来の成長の道筋」「職場への愛着」「働く意欲」など日本語に言い換えてください。

[会社名] {company or "（未入力）"}
[全体平均] {overall_avg:.2f} / 5
[信号] {signal}
[タイプ] {main_type}
[弱点カテゴリTOP2] {", ".join(worst2)}
[5カテゴリ] {", ".join(df_scores["カテゴリ"].tolist())}
""".strip()

