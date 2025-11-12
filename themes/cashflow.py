# -*- coding: utf-8 -*-
# 資金繰り改善 3分診断（既存と同一UI/スコア/タイプ判定/AIプロンプト）
import pandas as pd

THEME_META = {
    "title": "3分で分かる 資金繰り改善診断",
    "lead":  "**10問**に答えるだけで、資金繰りの“詰まりどころ”を可視化します。"
}

YN3  = ["Yes", "部分的に", "No"]
THREE_USUAL = ["いつも", "ときどき", "ほとんどない"]       # 高頻度がリスク高 → 反転マップで処理
THREE_BANK  = ["ほとんどない", "たまに", "頻繁に"]         # 頻繁が良い → 通常
THREE_STOCK = ["多くある", "少しある", "ほとんどない"]     # 多いがリスク高 → 反転マップで処理

MAP_USUAL = {"いつも":1, "ときどき":3, "ほとんどない":5}
MAP_BANK  = {"ほとんどない":1, "たまに":3, "頻繁に":5}
MAP_STOCK = {"多くある":1, "少しある":3, "ほとんどない":5}

TYPE_TEXT = {
    "売上依存型": "売上・入金管理に弱点。請求〜入金のズレや回収管理の甘さが資金を細らせます。入金管理の定点観測と遅延アラート、与信ルールの整備を優先しましょう。",
    "支払圧迫型": "支払・仕入管理に弱点。期日や条件が自社のキャッシュサイクルに合っていない可能性。仕入先との条件見直しと支払予定の可視化が効果的です。",
    "在庫・固定費過多型": "在庫・固定費管理に弱点。売れ残りや固定費の重さが現金を圧迫。滞留在庫の処分・棚卸頻度の適正化、固定費の弾力化を検討しましょう。",
    "金融連携不足型": "金融機関連携に弱点。日頃の関係構築が薄いと、有事の資金調達が後手に回ります。担当者との定期対話と借入条件の棚卸しが必要です。",
    "体制未整備型": "資金繰りの運用体制に弱点。資金繰り表の未整備や手順不在は“気づいたら足りない”の温床。3ヶ月ローリングの予測運用を開始しましょう。",
    "バランス良好型": "全体バランスは良好。次は資金効率の最大化へ。余剰資金の運用設計、回収・支払条件の最適化でキャッシュ創出力を高めましょう。"
}

def to_score_yn3(ans: str, invert=False) -> int:
    base = {"Yes": 5, "部分的に": 3, "No": 1}
    v = base.get(ans, 3)
    return {5:1,3:3,1:5}[v] if invert else v

def to_score_map(ans: str, mapping: dict, invert=False) -> int:
    v = mapping.get(ans, 3)
    return {5:1,3:3,1:5}[v] if invert else v

def render_questions(st):
    st.subheader("① 売上・入金管理")
    q1 = st.radio("Q1. 得意先からの入金が「少し遅い」と感じることがありますか？", THREE_USUAL, index=1)
    q2 = st.radio("Q2. 請求書発行から入金までの流れを定期的に点検・改善していますか？", YN3, index=1)

    st.subheader("② 支払・仕入管理")
    q3 = st.radio("Q3. 支払条件（サイト）は自社の資金繰りを考慮して設計できていますか？", YN3, index=1)
    q4 = st.radio("Q4. 外注費や仕入先への支払予定を月次で見通せていますか？", YN3, index=1)

    st.subheader("③ 在庫・固定費管理")
    q5 = st.radio("Q5. 倉庫や事業所に「売れ残り在庫」がありますか？", THREE_STOCK, index=1)
    q6 = st.radio("Q6. 固定費（家賃・人件費など）を季節変動を加味して予実管理できていますか？", YN3, index=1)

    st.subheader("④ 借入・金融機関連携")
    q7 = st.radio("Q7. 銀行とは、どの程度の頻度で連絡を取り合いますか？", THREE_BANK, index=1)
    q8 = st.radio("Q8. 借入金の返済計画や金利条件を把握し、必要に応じて見直していますか？", YN3, index=1)

    st.subheader("⑤ 資金繰り管理体制")
    q9  = st.radio("Q9. 短期の資金繰り表（資金予測）を運用していますか？", YN3, index=2)
    q10 = st.radio("Q10. 資金不足が見込まれる場合の社内手順（対応ルール）は定めていますか？", YN3, index=1)

    st.markdown("---")
    company = st.text_input("会社名（必須）", value=st.session_state["company"])
    email   = st.text_input("メールアドレス（必須）", value=st.session_state["email"])
    st.caption("※ 入力いただいた会社名・メールは診断ログとして保存されます（営業目的以外には利用しません）。")

    sales_scores  = [to_score_map(q1, MAP_USUAL, invert=False), to_score_yn3(q2)]
    pay_scores    = [to_score_yn3(q3), to_score_yn3(q4)]
    stock_scores  = [to_score_map(q5, MAP_STOCK, invert=False), to_score_yn3(q6)]
    bank_scores   = [to_score_map(q7, MAP_BANK, invert=False), to_score_yn3(q8)]
    sys_scores    = [to_score_yn3(q9), to_score_yn3(q10)]

    df = pd.DataFrame({
        "カテゴリ": ["売上・入金管理","支払・仕入管理","在庫・固定費管理","借入・金融機関連携","資金繰り管理体制"],
        "平均スコア": [
            sum(sales_scores)/2,
            sum(pay_scores)/2,
            sum(stock_scores)/2,
            sum(bank_scores)/2,
            sum(sys_scores)/2
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
            "売上・入金管理": "売上依存型",
            "支払・仕入管理": "支払圧迫型",
            "在庫・固定費管理": "在庫・固定費過多型",
            "借入・金融機関連携": "金融連携不足型",
            "資金繰り管理体制": "体制未整備型"
        }[cat]
    return overall_avg, signal, main_type

def build_ai_prompt(company: str, main_type: str, df_scores: pd.DataFrame, overall_avg: float) -> str:
    worst2 = df_scores.sort_values("平均スコア", ascending=True).head(2)["カテゴリ"].tolist()
    signal = "青" if overall_avg>=4.0 else ("黄" if overall_avg>=2.6 else "赤")
    return f"""
あなたは資金繰りに強いコンサルタントです。以下の診断結果を受け、経営者向けに約300字（260〜340）で日本語コメントを1段落で作成。
・前置きや免責は不要、箇条書き禁止、具体策重視。
・最後の1文は信号色に応じた強度で「90分スポット診断」への自然な誘導で締める（赤=強く推奨、黄=推奨、青=任意の精緻化）。

[会社名] {company or "（未入力）"}
[全体平均] {overall_avg:.2f} / 5
[信号] {signal}
[タイプ] {main_type}
[弱点カテゴリTOP2] {", ".join(worst2)}
[5カテゴリ] {", ".join(df_scores["カテゴリ"].tolist())}
""".strip()
