# -*- coding: utf-8 -*-
import pandas as pd

THEME_META = {
    "title": "3分で分かる 〈テーマ名〉診断",
    "lead":  "〈10問前後〉に答えるだけで、〈課題の要点〉を可視化します。"
}

TYPE_TEXT = {
    "タイプA": "タイプAの説明。次アクションの示唆まで簡潔に。",
    "タイプB": "タイプBの説明。",
    "タイプC": "タイプCの説明。",
    "バランス良好型": "全体バランス良好。更なる最適化に進めます。"
}

# 選択肢定義（必要に応じて増減）
YN3 = ["Yes", "部分的に", "No"]
MAP = {"高い":1, "ふつう":3, "低い":5}  # 例

def to_score_yn3(ans: str, invert=False) -> int:
    base = {"Yes": 5, "部分的に": 3, "No": 1}
    v = base.get(ans, 3)
    return {5:1,3:3,1:5}[v] if invert else v

def to_score_map(ans: str, mapping: dict, invert=False) -> int:
    v = mapping.get(ans, 3)
    return {5:1,3:3,1:5}[v] if invert else v

def render_questions(st):
    st.subheader("① カテゴリA")
    q1 = st.radio("Q1. 〈質問文〉", YN3, index=1, key="q1")
    q2 = st.radio("Q2. 〈質問文〉", YN3, index=1, key="q2")

    st.subheader("② カテゴリB")
    q3 = st.radio("Q3. 〈質問文〉", list(MAP.keys()), index=1, key="q3")
    q4 = st.radio("Q4. 〈質問文〉", YN3, index=1, key="q4")

    st.markdown("---")
    company = st.text_input("会社名（必須）", value=st.session_state.get("company",""))
    email   = st.text_input("メールアドレス（必須）", value=st.session_state.get("email",""))
    st.caption("※ 入力いただいた会社名・メールは診断ログとして保存されます（営業目的以外には利用しません）。")

    catA_scores = [to_score_yn3(q1), to_score_yn3(q2)]
    catB_scores = [to_score_map(q3, MAP), to_score_yn3(q4)]

    df = pd.DataFrame({
        "カテゴリ": ["カテゴリA","カテゴリB"],
        "平均スコア": [
            sum(catA_scores)/len(catA_scores),
            sum(catB_scores)/len(catB_scores),
        ]
    })
    df["平均スコア"] = df["平均スコア"].round(2)
    return company, email, df

def evaluate(df_scores: pd.DataFrame):
    overall_avg = df_scores["平均スコア"].mean()
    signal = ("青信号","badge-blue") if overall_avg>=4.0 else (("黄信号","badge-yellow") if overall_avg>=2.6 else ("赤信号","badge-red"))

    if (df_scores["平均スコア"] >= 4.0).all():
        main_type = "バランス良好型"
    else:
        worst_row = df_scores.sort_values("平均スコア").iloc[0]
        cat = worst_row["カテゴリ"]
        main_type = {"カテゴリA":"タイプA","カテゴリB":"タイプB"}.get(cat, "タイプC")
    return overall_avg, signal, main_type

def build_ai_prompt(company: str, main_type: str, df_scores: pd.DataFrame, overall_avg: float) -> str:
    worst2 = df_scores.sort_values("平均スコア", ascending=True).head(2)["カテゴリ"].tolist()
    signal = "青" if overall_avg>=4.0 else ("黄" if overall_avg>=2.6 else "赤")
    return f"""
あなたは〈テーマ名〉に強いコンサルタントです。以下の診断結果を受け、経営者向けに約300字（260〜340）で日本語コメントを1段落で作成。
・前置きや免責は不要、箇条書き禁止、具体策重視。
・最後の1文は信号色に応じた強度で「90分スポット診断」へ自然に誘導（赤=強く推奨、黄=推奨、青=任意）。

[会社名] {company or "（未入力）"}
[全体平均] {overall_avg:.2f} / 5
[信号] {signal}
[タイプ] {main_type}
[弱点カテゴリTOP2] {", ".join(worst2)}
[カテゴリ一覧] {", ".join(df_scores["カテゴリ"].tolist())}
""".strip()
