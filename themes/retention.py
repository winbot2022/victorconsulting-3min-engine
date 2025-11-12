# -*- coding: utf-8 -*-
# 人材定着 3分診断（改善版：キー付与・初期値安全化・丸め・フォールバック等）
import pandas as pd

THEME_META = {
    "title": "3分で分かる 人材定着診断",
    "lead":  "**10問**に答えるだけで、離職の“火種”を5つの視点で可視化します。"
}

# 選択肢（5が良、1が悪）
YN3 = ["Yes", "部分的に", "No"]
FREQ3 = ["頻繁に", "ときどき", "ほとんどない"]   # “頻繁に”はリスク（反転用で処理）

TYPE_TEXT = {
    "採用・オンボ未整備型": "採用要件やオンボーディングに隙があり、入社後早期離職の温床です。要件定義の再設計、入社後90日のオンボDXを急ぎましょう。",
    "評価・キャリア不満型": "評価やキャリア経路の不明瞭さがモチベーション低下を招いています。等級・評価・育成の連動と1on1運用が有効です。",
    "育成停滞型": "スキル開発とリスキリングが弱く“成長実感”が不足。個別の目標設計と越境学習の仕組み化が必要です。",
    "働き方ミスマッチ型": "賃金/残業/柔軟性など就労条件の不一致が離職要因に。職務・報酬の納得感と柔軟な働き方の設計を進めましょう。",
    "マネジメント/風土課題型": "心理的安全性や上司の支援不足が顕在。1on1・フィードバックと小さな成功体験の設計で風土転換を。",
    "定着良好型": "総合的に良好。要退職層の早期検知とハイパフォーマーの成長投資へ進めましょう。"
}

# --- スコア変換 ---
def to_score_yn3(ans: str, invert: bool = False) -> int:
    base = {"Yes": 5, "部分的に": 3, "No": 1}
    v = base.get(ans, 3)
    return {5: 1, 3: 3, 1: 5}[v] if invert else v

def to_score_freq3(ans: str, invert: bool = False) -> int:
    # FREQ3: 頻繁に/ときどき/ほとんどない
    base = {"頻繁に": 1, "ときどき": 3, "ほとんどない": 5}
    v = base.get(ans, 3)
    return {5: 1, 3: 3, 1: 5}[v] if invert else v

# --- UI（設問） ---
def render_questions(st):
    # ① 採用・オンボーディング
    st.subheader("① 採用・オンボーディング")
    q1 = st.radio("Q1. 採用要件（スキル/マインド/カルチャーフィット）は文書化され、面接で一貫評価できていますか？", YN3, index=1, key="ret_q1")
    q2 = st.radio("Q2. 入社90日までのオンボーディング（育成/メンター/評価）が運用されていますか？", YN3, index=1, key="ret_q2")

    # ② 評価・キャリア
    st.subheader("② 評価・キャリア")
    q3 = st.radio("Q3. 等級・評価基準・賃金の関係が透明で、期初合意された目標で期末評価できていますか？", YN3, index=1, key="ret_q3")
    q4 = st.radio("Q4. キャリアパスや職務ローテーションの仕組みがあり、本人と合意形成できていますか？", YN3, index=1, key="ret_q4")

    # ③ 育成・成長実感
    st.subheader("③ 育成・成長実感")
    q5 = st.radio("Q5. 1on1/フィードバックは月1回以上の頻度で実施されていますか？", YN3, index=2, key="ret_q5")
    q6 = st.radio("Q6. リスキリングや越境学習など“成長実感”を高める機会が十分ですか？", YN3, index=1, key="ret_q6")

    # ④ 働き方・就労条件
    st.subheader("④ 働き方・就労条件")
    q7 = st.radio("Q7. 所定外労働（残業/休日出勤）が“過度”だと感じる声が、社内でどの程度ありますか？（頻繁=リスク）", FREQ3, index=1, key="ret_q7")
    q8 = st.radio("Q8. 報酬/福利厚生/柔軟な働き方（時短・リモート等）への満足度を定点把握できていますか？", YN3, index=1, key="ret_q8")

    # ⑤ マネジメント/風土・離職徴候
    st.subheader("⑤ マネジメント/風土・離職徴候")
    q9  = st.radio("Q9. 上司の支援不足や不公正感など“心理的安全性”を損なう事象が見られますか？（頻繁=リスク）", FREQ3, index=1, key="ret_q9")
    q10 = st.radio("Q10. 退職リスクの早期検知（エンゲージメント/面談ログ/人事データ連動）が運用されていますか？", YN3, index=2, key="ret_q10")

    st.markdown("---")
    company = st.text_input("会社名（必須）", value=st.session_state.get("company", ""))
    email   = st.text_input("メールアドレス（必須）", value=st.session_state.get("email", ""))
    st.caption("※ 入力いただいた会社名・メールは診断ログとして保存されます（営業目的以外には利用しません）。")

    # 各カテゴリ（0-5、5が良）
    hire_scores   = [to_score_yn3(q1), to_score_yn3(q2)]
    eval_scores   = [to_score_yn3(q3), to_score_yn3(q4)]
    grow_scores   = [to_score_yn3(q5), to_score_yn3(q6)]
    work_scores   = [to_score_freq3(q7, invert=True), to_score_yn3(q8)]   # Q7は頻繁=リスク → 反転
    mgmt_scores   = [to_score_freq3(q9, invert=True), to_score_yn3(q10)]  # Q9も反転

    df = pd.DataFrame({
        "カテゴリ": ["採用・オンボーディング", "評価・キャリア", "育成・成長実感", "働き方・就労条件", "マネジメント/風土"],
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
            "採用・オンボーディング": "採用・オンボ未整備型",
            "評価・キャリア":       "評価・キャリア不満型",
            "育成・成長実感":       "育成停滞型",
            "働き方・就労条件":     "働き方ミスマッチ型",
            "マネジメント/風土":     "マネジメント/風土課題型",
        }.get(cat, "マネジメント/風土課題型")  # フォールバック保険
    return overall_avg, signal, main_type

# --- AIコメント用プロンプト ---
def build_ai_prompt(company: str, main_type: str, df_scores: pd.DataFrame, overall_avg: float) -> str:
    worst2 = df_scores.sort_values("平均スコア", ascending=True).head(2)["カテゴリ"].tolist()
    signal = "青" if overall_avg >= 4.0 else ("黄" if overall_avg >= 2.6 else "赤")
    strength = {"赤": "強く推奨", "黄": "推奨", "青": "任意"}.get(signal, "推奨")

    return f"""
あなたは人材定着に精通した経営コンサルタントです。以下の診断結果を受け、経営者向けに約300字（260〜340字）で日本語コメントを1段落で作成。
・前置きや免責は不要、箇条書き禁止、具体策重視。
・最後の1文は信号色に応じた強度（{strength}）で「90分スポット診断」への自然な誘導で締める（赤=強く推奨、黄=推奨、青=任意の精緻化）。

[会社名] {company or "（未入力）"}
[全体平均] {overall_avg:.2f} / 5
[信号] {signal}
[タイプ] {main_type}
[弱点カテゴリTOP2] {", ".join(worst2)}
[5カテゴリ] {", ".join(df_scores["カテゴリ"].tolist())}
""".strip()
