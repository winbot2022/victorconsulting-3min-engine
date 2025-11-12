# -*- coding: utf-8 -*-
# 事業承継準備度診断（準備中ダミー）
THEME_META = {
    "title": "事業承継準備度診断（準備中）",
    "lead": "公開準備中です。近日リリース。"
}

TYPE_TEXT = {"N/A": "公開準備中です。"}

import pandas as pd
import streamlit as st

def render_questions(st):
    st.info("事業承継準備度診断は現在準備中です。")
    company = st.text_input("会社名", "")
    email   = st.text_input("メールアドレス", "")
    df = pd.DataFrame([{"カテゴリ":"準備中","平均スコア":0.0}])
    return company, email, df

def evaluate(df_scores: pd.DataFrame):
    return 0.0, ("準備中","badge-yellow"), "N/A"

def build_ai_prompt(company, main_type, df_scores, overall_avg):
    return "事業承継準備度診断：準備中のためAIコメントは表示されません。"
