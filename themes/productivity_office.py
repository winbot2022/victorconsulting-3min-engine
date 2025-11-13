# -*- coding: utf-8 -*-
# 生産性診断（オフィス業務向け）3分診断 v1.1
# - 5カテゴリ×各2問=10問
# - やさしい日本語／中小企業向け表現
# - 否定疑問を避ける／頻度項目は「よくある=1 / ときどき=3 / ほとんどない=5」
# - Q7/Q8 は頻度3段階（反転なし）

import pandas as pd

THEME_META = {
    "title": "3分で分かる オフィス生産性ボトルネック診断",
    "lead":  "**10問**に答えるだけで、会議・情報共有・IT活用・時間配分・チーム連携の “オフィスのボトルネック” を、5つの視点から見える化します。"
}

# 選択肢（5が良、1が悪）
YN3 = ["Yes", "部分的に", "No"]   # Yes=5 / 部分的に=3 / No=1
FREQ3_SOFT = ["よくある", "ときどき", "ほとんどない"]  # よくある=1 / ときどき=3 / ほとんどない=5

TYPE_TEXT = {
    "業務属人化型": "業務のやり方が人によって異なり、引き継ぎ・代替が難しい状態です。手順の見える化と標準化から着手しましょう。",
    "会議過多型":   "会議や報告の目的・時間管理が甘く、本来業務に集中できていません。会議の目的明確化・短時間化・非同期化で改善を。",
    "IT停滞型":     "デジタル活用が進まず、手作業・紙中心で非効率です。まずは表計算・クラウド共有の“型”を整え、再利用を前提に。",
    "時間ロス型":   "緊急対応・調整に追われ、優先順位が曖昧です。計画時間の確保と“やらないこと”の合意形成が有効です。",
    "チーム断絶型": "情報が個人に閉じ、助け合いが弱い状態です。共有ルールと強みを生かす役割分担で“チームとしての生産性”を上げましょう。",
    "バランス良好型": "全体バランスは良好。次は“ムダ時間の1割削減”など具体KPIで継続改善へ。"
}

# --- スコア変換 ---
def to_score_yn3(ans: str, invert: bool = False) -> int:
    base = {"Yes": 5, "部分的に": 3, "No": 1}
    v = base.get(ans, 3)
    return {5: 1, 3: 3, 1: 5}[v] if invert else v

def to_score_freq3(ans: str, invert: bool = False) -> int:
    base = {"よくある": 1, "ときどき": 3, "ほとんどない": 5}
    v = base.get(ans, 3)
    return {5: 1, 3: 3, 1: 5}[v] if invert else v

# --- UI（設問） ---
def render_questions(st):
    # ① 業務の見える化・標準化
    st.subheader("① 業務の見える化・標準化")
    q1 = st.radio(
        "Q1. 日々の業務内容や進捗を共有できる仕組み（タスク管理・日報など）が整っていますか？",
        YN3, index=1, key="prod_off_q1"
    )
    q2 = st.radio(
        "Q2. 同じ業務を複数人が行う場合、やり方が統一されていますか？",
        YN3, index=1, key="prod_off_q2"
    )

    # ② 会議・報告・連絡
    st.subheader("② 会議・報告・連絡")
    q3 = st.radio(
        "Q3. 定例会議や報告の目的が明確で、時間どおりに終わることが多いですか？",
        YN3, index=1, key="prod_off_q3"
    )
    q4 = st.radio(
        "Q4. チャットやメールでの情報共有が、重複や抜け漏れなく行えていますか？",
        YN3, index=1, key="prod_off_q4"
    )

    # ③ IT・ツール活用
    st.subheader("③ IT・ツール活用")
    q5 = st.radio(
        "Q5. 表計算やクラウドツールなど、ITを使って業務を効率化する取り組みがありますか？",
        YN3, index=1, key="prod_off_q5"
    )
    q6 = st.radio(
        "Q6. 社員が便利なツールを試したり共有したりする雰囲気がありますか？",
        YN3, index=1, key="prod_off_q6"
    )

    # ④ 時間の使い方・優先順位
    st.subheader("④ 時間の使い方・優先順位")
    q7 = st.radio(
        "Q7. 会議・報告・調整に時間を取られて、本来業務が後回しになることはどの程度ありますか？",
        FREQ3_SOFT, index=1, key="prod_off_q7"
    )
    q8 = st.radio(
        "Q8. 緊急対応に追われて、計画的に仕事を進められないことがありますか？",
        FREQ3_SOFT, index=1, key="prod_off_q8"
    )

    # ⑤ チーム連携・人材活用
    st.subheader("⑤ チーム連携・人材活用")
    q9 = st.radio(
        "Q9. チーム内で助け合い・情報共有が自然に行われていますか？",
        YN3, index=1, key="prod_off_q9"
    )
    q10 = st.radio(
        "Q10. 社員一人ひとりの強みを生かした役割分担ができていますか？",
        YN3, index=1, key="prod_off_q10"
    )

    st.markdown("---")
    company = st.text_input("会社名（必須）", value=st.session_state.get("company", ""))
    email   = st.text_input("メールアドレス（必須）", value=st.session_state.get("email", ""))
    st.caption("※ 入力いただいた会社名・メールは診断ログとして保存されます（営業目的以外には利用しません）。")

    # 各カテゴリ（0-5、5が良）
    vis_scores   = [to_score_yn3(q1), to_score_yn3(q2)]
    meet_scores  = [to_score_yn3(q3), to_score_yn3(q4)]
    it_scores    = [to_score_yn3(q5), to_score_yn3(q6)]
    time_scores  = [to_score_freq3(q7), to_score_freq3(q8)]  # ← 反転なし
    team_scores  = [to_score_yn3(q9), to_score_yn3(q10)]

    df = pd.DataFrame({
        "カテゴリ": ["業務の見える化・標準化", "会議・報告・連絡", "IT・ツール活用", "時間の使い方・優先順位", "チーム連携・人材活用"],
        "平均スコア": [
            sum(vis_scores)  / len(vis_scores),
            sum(meet_scores) / len(meet_scores),
            sum(it_scores)   / len(it_scores),
            sum(time_scores) / len(time_scores),
            sum(team_scores) / len(team_scores),
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
        main_type = "バランス良好型"
    else:
        worst_row = df_scores.sort_values("平均スコア").iloc[0]
        cat = worst_row["カテゴリ"]
        main_type = {
            "業務の見える化・標準化": "業務属人化型",
            "会議・報告・連絡":     "会議過多型",
            "IT・ツール活用":       "IT停滞型",
            "時間の使い方・優先順位": "時間ロス型",
            "チーム連携・人材活用":   "チーム断絶型",
        }.get(cat, "時間ロス型")
    return overall_avg, signal, main_type

# --- AIコメント用プロンプト ---
def build_ai_prompt(company: str, main_type: str, df_scores: pd.DataFrame, overall_avg: float) -> str:
    worst2 = df_scores.sort_values("平均スコア", ascending=True).head(2)["カテゴリ"].tolist()
    signal = "青" if overall_avg >= 4.0 else ("黄" if overall_avg >= 2.6 else "赤")
    strength = {"赤": "強く推奨", "黄": "推奨", "青": "任意"}.get(signal, "推奨")

    return f"""
あなたはオフィス業務の生産性向上に精通した経営コンサルタントです。以下の診断結果を受け、経営者向けに約300字（260〜340字）で日本語コメントを1段落で作成。
・前置きや免責は不要、箇条書き禁止、具体策重視。
・外来語やカタカナ語（例：キャリアパス、エンゲージメント、モチベーション等）は使わず、現場の人にも伝わる日本語で具体的に書いてください。
・最後の1文は信号色に応じた強度（{strength}）で「90分スポット診断」への自然な誘導で締める（赤=強く推奨、黄=推奨、青=任意の精緻化）。

[会社名] {company or "（未入力）"}
[全体平均] {overall_avg:.2f} / 5
[信号] {signal}
[タイプ] {main_type}
[弱点カテゴリTOP2] {", ".join(worst2)}
[5カテゴリ] {", ".join(df_scores["カテゴリ"].tolist())}
""".strip()

