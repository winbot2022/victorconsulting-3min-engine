# -*- coding: utf-8 -*-
# 製造業向け 3分診断（改善版：キー付与・初期値安全化・丸め・フォールバック等）
import pandas as pd

THEME_META = {
    "title": "製造現場の“隠れたムダ”をあぶり出す｜3分無料診断",
    "lead":  "**10問**に回答するだけで、貴社のリスク“構造”を可視化します。"
}

YN3  = ["Yes", "部分的に", "No"]
FIVE = ["5（非常にある）", "4", "3", "2", "1（まったくない）"]

TYPE_TEXT = {
    "在庫滞留型": "過剰在庫やWIP滞留で資金が眠っている可能性が高い状態です。生産量ではなく“流れ”の設計に軸足を移しましょう。",
    "熟練依存型": "属人化により技能がブラックボックス化。ベテラン離職に伴う急落リスクが高い状態です。技能棚卸と多能工化の設計が急務です。",
    "原価ブラックボックス型": "コスト意識・原価の見える化が弱く、利益が目減りする体質です。現場まで“見える原価管理”を展開しましょう。",
    "変動脆弱型": "受注変動・突発に弱く、納期トラブルや残業増に直結しています。変動を“なくす”のではなく“流す”バッファ設計が肝要です。",
    "データ断絶型": "進捗・実績が見えず、意思決定が遅れがちです。まずは“見える化”から。現場と経営のデータ接続を整備しましょう。",
    "バランス良好型": "リスク分散と仕組み成熟が進んでいます。次の一手は“利益を生むデータ活用”と継続的なリードタイム短縮です。"
}

# --- スコア変換 ---
def to_score_yn3(ans: str, invert=False) -> int:
    base = {"Yes": 5, "部分的に": 3, "No": 1}
    val = base.get(ans, 3)
    return {5: 1, 3: 3, 1: 5}[val] if invert else val

def to_score_5scale(ans: str) -> int:
    try:
        return int(ans[0])
    except Exception:
        return 3

# --- UI（設問） ---
def render_questions(st):
    st.subheader("① 在庫・運搬（資金の滞留）")
    q1 = st.radio("Q1. 完成品・仕掛品の在庫基準を数値で管理していますか？", YN3, index=1, key="factory_q1")
    q2 = st.radio("Q2. 在庫削減の責任部署（またはKPI）が明確ですか？", YN3, index=1, key="factory_q2")

    st.subheader("② 人材・技能承継（属人化リスク）")
    q3 = st.radio("Q3. 熟練者しか対応できない作業が3割以上ありますか？（Yesはリスク高）", YN3, index=2, key="factory_q3")
    q4 = st.radio("Q4. 作業標準書・マニュアルを継続更新できる体制がありますか？", YN3, index=1, key="factory_q4")

    st.subheader("③ 原価意識・改善文化（損失体質）")
    q5 = st.radio("Q5. 改善提案や原価削減の目標を数値で追っていますか？", YN3, index=1, key="factory_q5")
    q6 = st.radio("Q6. 現場リーダーがコスト感覚を持って行動していますか？", FIVE, index=2, key="factory_q6")

    st.subheader("④ 生産計画・変動対応（流れの乱れ）")
    q7 = st.radio("Q7. 受注変動や突発対応の標準ルールがありますか？", YN3, index=1, key="factory_q7")
    q8 = st.radio("Q8. リードタイム短縮の取組を定期的に見直していますか？", YN3, index=1, key="factory_q8")

    st.subheader("⑤ DX・情報共有（見える化不足）")
    q9  = st.radio("Q9. 現場の進捗や生産実績をリアルタイムで把握できますか？", YN3, index=2, key="factory_q9")
    q10 = st.radio("Q10. データをもとに経営会議や現場ミーティングを行っていますか？", YN3, index=1, key="factory_q10")

    st.markdown("---")
    company = st.text_input("会社名（必須）", value=st.session_state.get("company", ""))
    email   = st.text_input("メールアドレス（必須）", value=st.session_state.get("email", ""))
    st.caption("※ 入力いただいた会社名・メールは診断ログとして保存されます（営業目的以外には利用しません）。")

    inv_scores    = [to_score_yn3(q1), to_score_yn3(q2)]
    skills_scores = [to_score_yn3(q3, invert=True), to_score_yn3(q4)]
    cost_scores   = [to_score_yn3(q5), to_score_5scale(q6)]
    plan_scores   = [to_score_yn3(q7), to_score_yn3(q8)]
    dx_scores     = [to_score_yn3(q9), to_score_yn3(q10)]

    df = pd.DataFrame({
        "カテゴリ": ["在庫・運搬", "人材・技能承継", "原価意識・改善文化", "生産計画・変動対応", "DX・情報共有"],
        "平均スコア": [
            sum(inv_scores) / len(inv_scores),
            sum(skills_scores) / len(skills_scores),
            sum(cost_scores) / len(cost_scores),
            sum(plan_scores) / len(plan_scores),
            sum(dx_scores) / len(dx_scores)
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
            "在庫・運搬": "在庫滞留型",
            "人材・技能承継": "熟練依存型",
            "原価意識・改善文化": "原価ブラックボックス型",
            "生産計画・変動対応": "変動脆弱型",
            "DX・情報共有": "データ断絶型",
        }.get(cat, "変動脆弱型")  # フォールバック保険
    return overall_avg, signal, main_type

# --- AIコメント生成プロンプト ---
def build_ai_prompt(company: str, main_type: str, df_scores: pd.DataFrame, overall_avg: float) -> str:
    worst2 = df_scores.sort_values("平均スコア", ascending=True).head(2)["カテゴリ"].tolist()
    signal = "青" if overall_avg >= 4.0 else ("黄" if overall_avg >= 2.6 else "赤")
    strength = {"赤": "強く推奨", "黄": "推奨", "青": "任意"}.get(signal, "推奨")

    return f"""
あなたは製造業の現場改善に精通した経営コンサルタントです。以下の診断結果を受け、経営者向けに約300字（260〜340字）で日本語コメントを1段落で作成。
・前置きや免責は不要、箇条書き禁止、具体策重視。
・最後の1文は信号色に応じた強度（{strength}）で「90分スポット診断」への自然な誘導で締める（赤=強く推奨、黄=推奨、青=任意の精緻化）。

[会社名] {company or "（未入力）"}
[全体平均] {overall_avg:.2f} / 5
[信号] {signal}
[タイプ] {main_type}
[弱点カテゴリTOP2] {", ".join(worst2)}
[5カテゴリ] {", ".join(df_scores["カテゴリ"].tolist())}
""".strip()

