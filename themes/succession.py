# -*- coding: utf-8 -*-
# 事業承継準備度 3分診断（改善版：キー付与・初期値安全化・丸め・フォールバック等）
import pandas as pd

THEME_META = {
    "title": "事業承継リスクのボトルネック診断｜3分無料診断",
    "lead":  "10問**に答えるだけで、後継者・資本・ガバナンス・関係者・ライフの5つの視点から、事業承継のどこにボトルネックが潜んでいるかを見える化します。"
}

# 選択肢（5が良、1が悪）
YN3 = ["Yes", "部分的に", "No"]

TYPE_TEXT = {
    "後継者未整備型":     "後継者の特定や育成が遅れており、引き継ぎ期日に間に合わないリスクが高い状態。候補の明確化と計画的OJT・権限移譲の設計を急ぎましょう。",
    "支配構造不透明型":   "意思決定権や責任分担が曖昧で、社内外の不安を招きやすい状態。ガバナンス文書化・権限表整備・移行マイルストーンを明確にしましょう。",
    "資本リスク型":       "株式・相続・保証・借入の整理が不足。税負担や承継後の資金繰り悪化に直結します。株式評価・納税資金計画・保証整理を優先度高で着手。",
    "関係断絶型":         "主要取引先・金融機関・社内キーパーソンへの共有が不十分。信用低下や離反を招きます。キーマップ作成と関係者説明の計画化が必要です。",
    "心理的未準備型":     "現経営者の役割設計やライフプランが未整理で、移譲の遅延を招く恐れ。退任後の役割・関与範囲を先に描き、合意形成を進めましょう。",
    "承継準備良好型":     "全体整備は概ね良好。承継を“守り”で終わらせず、成長投資・デジタル活用・次世代体制のKPI設計へ進めましょう。"
}

# --- スコア変換 ---
def to_score_yn3(ans: str, invert: bool = False) -> int:
    base = {"Yes": 5, "部分的に": 3, "No": 1}
    v = base.get(ans, 3)
    return {5: 1, 3: 3, 1: 5}[v] if invert else v

# --- UI（設問） ---
def render_questions(st):
    # ① 後継者候補
    st.subheader("① 後継者候補（選定・育成）")
    q1 = st.radio("Q1. 後継者候補（親族・社員・外部問わず）は、すでに明確に決まっていますか？", YN3, index=1, key="succ_q1")
    q2 = st.radio("Q2. 後継者候補に対し、経営判断や財務理解を習得させる育成プランを運用していますか？", YN3, index=1, key="succ_q2")

    # ② 経営権・意思決定
    st.subheader("② 経営権・意思決定（支配構造）")
    q3 = st.radio("Q3. 現経営者と後継者の間で、意思決定権や責任範囲を明文化していますか？", YN3, index=1, key="succ_q3")
    q4 = st.radio("Q4. 経営陣・幹部社員の間に、後継体制への不安や温度差はありますか？（Yesはリスク高）", YN3, index=2, key="succ_q4")

    # ③ 財務・株式・相続
    st.subheader("③ 財務・株式・相続（資本構造）")
    q5 = st.radio("Q5. 自社株の保有構成や評価額を把握し、承継後の税負担を試算していますか？", YN3, index=2, key="succ_q5")
    q6 = st.radio("Q6. 不動産・個人保証・借入等の承継後リスクを整理し、対応方針を持っていますか？", YN3, index=1, key="succ_q6")

    # ④ 組織・社員・取引先
    st.subheader("④ 組織・社員・取引先（関係構築）")
    q7 = st.radio("Q7. 主要取引先・金融機関に、事業承継方針と移行スケジュールを共有済みですか？", YN3, index=1, key="succ_q7")
    q8 = st.radio("Q8. 社内リーダー層は、後継者を“次期経営者”として受け入れる体制が整っていますか？", YN3, index=1, key="succ_q8")

    # ⑤ 経営者本人・ライフプラン
    st.subheader("⑤ 経営者本人・ライフプラン（心理・引退設計）")
    q9  = st.radio("Q9. 経営者自身の退任後の役割・関与範囲・生活設計を具体的に描いていますか？", YN3, index=2, key="succ_q9")
    q10 = st.radio("Q10. 「いつ・誰に・どのように」を明文化した事業承継計画書がありますか？", YN3, index=1, key="succ_q10")

    st.markdown("---")
    company = st.text_input("会社名（必須）", value=st.session_state.get("company", ""))
    email   = st.text_input("メールアドレス（必須）", value=st.session_state.get("email", ""))
    st.caption("※ 入力いただいた会社名・メールは診断ログとして保存されます（営業目的以外には利用しません）。")

    # 各カテゴリの平均スコア
    successor_scores = [to_score_yn3(q1), to_score_yn3(q2)]
    control_scores   = [to_score_yn3(q3), to_score_yn3(q4, invert=True)]  # Q4はYes=リスク → 反転
    capital_scores   = [to_score_yn3(q5), to_score_yn3(q6)]
    relation_scores  = [to_score_yn3(q7), to_score_yn3(q8)]
    owner_scores     = [to_score_yn3(q9), to_score_yn3(q10)]

    df = pd.DataFrame({
        "カテゴリ": ["後継者候補", "経営権・意思決定", "財務・株式・相続", "組織・社員・取引先", "経営者本人・ライフプラン"],
        "平均スコア": [
            sum(successor_scores) / len(successor_scores),
            sum(control_scores)   / len(control_scores),
            sum(capital_scores)   / len(capital_scores),
            sum(relation_scores)  / len(relation_scores),
            sum(owner_scores)     / len(owner_scores),
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
        main_type = "承継準備良好型"
    else:
        worst_row = df_scores.sort_values("平均スコア").iloc[0]
        cat = worst_row["カテゴリ"]
        main_type = {
            "後継者候補":       "後継者未整備型",
            "経営権・意思決定": "支配構造不透明型",
            "財務・株式・相続": "資本リスク型",
            "組織・社員・取引先": "関係断絶型",
            "経営者本人・ライフプラン": "心理的未準備型",
        }.get(cat, "支配構造不透明型")  # フォールバック保険
    return overall_avg, signal, main_type

# --- AIコメント用プロンプト ---
def build_ai_prompt(company: str, main_type: str, df_scores: pd.DataFrame, overall_avg: float) -> str:
    worst2 = df_scores.sort_values("平均スコア", ascending=True).head(2)["カテゴリ"].tolist()
    signal = "青" if overall_avg >= 4.0 else ("黄" if overall_avg >= 2.6 else "赤")
    strength = {"赤": "強く推奨", "黄": "推奨", "青": "任意"}.get(signal, "推奨")

    return f"""
あなたは事業承継に精通した経営コンサルタントです。以下の診断結果を受け、経営者または後継者向けに約300字（260〜340字）で日本語コメントを1段落で作成。
・前置きや免責は不要、箇条書き禁止、具体策重視。
・最後の1文は信号色に応じた強度（{strength}）で「90分スポット診断」への自然な誘導で締める（赤=強く推奨、黄=推奨、青=任意の精緻化）。

[会社名] {company or "（未入力）"}
[全体平均] {overall_avg:.2f} / 5
[信号] {signal}
[タイプ] {main_type}
[弱点カテゴリTOP2] {", ".join(worst2)}
[5カテゴリ] {", ".join(df_scores["カテゴリ"].tolist())}
""".strip()

