# -*- coding: utf-8 -*-
# ============================================================================
# Victor Consulting ｜3分診断エンジン（Factory & Cashflow版）
#  - Streamlit Multi-theme App
#  - 各テーマ共通：UTM取得、OpenAIコメント、PDF出力、Sheets保存、二重書込防止
#  - 直リンク（?theme=factory / ?theme=cashflow）対応
#  - シートはテーマごとに分割（factory / cashflow）
# ============================================================================
import os, io, re, json, time, base64, tempfile, requests
from datetime import datetime, timedelta, timezone
import streamlit as st
import pandas as pd
import altair as alt
import matplotlib.pyplot as plt
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from matplotlib import font_manager
from PIL import Image as PILImage
import qrcode
import gspread
from google.oauth2.service_account import Credentials

# ========== 共通ブランド設定 ==========
BRAND_BG   = "#f0f7f7"
LOGO_URL   = "https://victorconsulting.jp/wp-content/uploads/2025/10/CImark.png"
CTA_URL    = "https://victorconsulting.jp/spot-diagnosis/"
OPENAI_MODEL = "gpt-4o-mini"
APP_VERSION  = "vc-multi-v1.0.0"
JST = timezone(timedelta(hours=9))

# ========== Streamlit 基本設定 ==========
st.set_page_config(
    page_title="3分診断エンジン｜Victor Consulting",
    page_icon="🧭",
    layout="centered",
    initial_sidebar_state="expanded"
)

# ========== Secrets & Admin ==========
def read_secret(key: str, default=None):
    try:
        return st.secrets[key]
    except Exception:
        return os.environ.get(key, default)

try:
    qp = st.query_params
except Exception:
    qp = st.experimental_get_query_params()
ADMIN_MODE = (str(qp.get("admin", ["0"])[0]) == "1") or (str(read_secret("ADMIN_MODE", "0")) == "1")

# ========== 日本語フォント設定 ==========
def setup_japanese_font():
    candidates = ["NotoSansJP-Regular.ttf", "/mnt/data/NotoSansJP-Regular.ttf"]
    font_path = next((p for p in candidates if os.path.exists(p)), None)
    if font_path:
        pdfmetrics.registerFont(TTFont("JP", font_path))
        registerFontFamily("JP", normal="JP", bold="JP")
        font_manager.fontManager.addfont(font_path)
        import matplotlib as mpl
        mpl.rcParams["font.family"] = "JP"
        mpl.rcParams["axes.unicode_minus"] = False
        return font_path
    return None
FONT_PATH_IN_USE = setup_japanese_font()

# ========== CSS ==========
st.markdown(f"""
<style>
.stApp {{ background: {BRAND_BG}; }}
.block-container {{ padding-top: 2.8rem; }}
.result-card {{
  background: white; border-radius: 14px; padding: 1.0rem;
  box-shadow: 0 6px 20px rgba(0,0,0,.06); border: 1px solid rgba(0,0,0,.06);
}}
.badge {{ padding:.25rem .6rem; border-radius:999px; font-weight:700; }}
.badge-blue  {{ background:#e6f0ff; color:#0b5fff; }}
.badge-yellow{{ background:#fff6d8; color:#8a6d00; }}
.badge-red   {{ background:#ffe6e6; color:#a80000; }}
</style>
""", unsafe_allow_html=True)

# ========== Google Sheets ヘルパ ==========
HEADER_ORDER = ["timestamp","company","email","category_scores","total_score","type_label",
                "ai_comment","utm_source","utm_campaign","pdf_url","app_version","status",
                "ai_comment_len","risk_level","entry_check","report_date"]

def get_gsheet(spreadsheet_id, service_json_str, sheet_name="responses"):
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    info = json.loads(service_json_str)
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(spreadsheet_id)
    try:
        ws = sh.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=sheet_name, rows=1000, cols=len(HEADER_ORDER))
        ws.append_row(HEADER_ORDER)
    return ws

def append_to_sheet(row_dict, sheet_name="responses"):
    secret_json = read_secret("GOOGLE_SERVICE_JSON", None)
    if not secret_json:
        b64 = read_secret("GOOGLE_SERVICE_JSON_BASE64", None)
        if b64: secret_json = base64.b64decode(b64).decode("utf-8")
    secret_sheet_id = read_secret("SPREADSHEET_ID", None)
    if not secret_json or not secret_sheet_id: return False
    try:
        ws = get_gsheet(secret_sheet_id, secret_json, sheet_name)
        record = [row_dict.get(k,"") for k in HEADER_ORDER]
        ws.append_row(record, value_input_option="USER_ENTERED")
        return True
    except Exception:
        return False

# ========== OpenAIクライアント ==========
def _openai_client(api_key: str):
    try:
        from openai import OpenAI
        return "new", OpenAI(api_key=api_key)
    except Exception:
        import openai
        openai.api_key = api_key
        return "old", openai

# ========== 共通PDF作成 ==========
def make_pdf_bytes(result, df_scores, brand_hex=BRAND_BG):
    from reportlab.lib.units import mm
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
        rightMargin=30,leftMargin=30,topMargin=25,bottomMargin=25)
    styles = getSampleStyleSheet(); normal=styles["BodyText"]; title=styles["Title"]
    if FONT_PATH_IN_USE:
        title.fontName = normal.fontName = "JP"
    normal.fontSize = 10
    elems = []
    try:
        resp = requests.get(LOGO_URL,timeout=6)
        tmp = tempfile.NamedTemporaryFile(delete=False,suffix=".png")
        tmp.write(resp.content); tmp.flush()
        elems.append(Image(tmp.name,width=120))
    except: pass
    elems.append(Paragraph("3分無料診断レポート", title))
    elems.append(Spacer(1,8))
    meta = f"会社名：{result['company']} ／ 日時：{result['dt']} ／ 信号：{result['signal']} ／ タイプ：{result['main_type']}"
    elems.append(Paragraph(meta, normal)); elems.append(Spacer(1,6))
    elems.append(Paragraph("診断コメント", styles["Heading3"]))
    elems.append(Paragraph(result["comment"], normal))
    elems.append(Spacer(1,6))
    data = [["カテゴリ","平均スコア"]] + [[r["カテゴリ"], f"{r['平均スコア']:.2f}"] for _,r in df_scores.iterrows()]
    t=Table(data, colWidths=[220,120])
    t.setStyle(TableStyle([("GRID",(0,0),(-1,-1),0.3,colors.grey)]))
    elems.append(t)
    doc.build(elems); buf.seek(0)
    return buf.read()

# ========== 共通関数 ==========
def validate_inputs(company,email):
    if not company.strip(): return False,"会社名は必須です。"
    if not re.match(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$",email): return False,"メール形式が正しくありません。"
    return True,""

def to_risk_level(total: float):
    if total<2.0: return "高リスク"
    elif total<3.5: return "中リスク"
    else: return "低リスク"

# =============================================================================
# ▼▼▼ メイン：テーマ切替（製造業・資金繰り） ▼▼▼
# =============================================================================
theme = qp.get("theme", [""])[0] if isinstance(qp.get("theme"), list) else qp.get("theme","")

if not theme:
    st.title("3分診断エンジン｜Victor Consulting")
    st.write("気になるテーマを選択してください。")
    st.markdown("### 🔧 診断メニュー")
    st.markdown("- [🏭 製造業向け 経営診断](?theme=factory)")
    st.markdown("- [💴 資金繰り改善診断](?theme=cashflow)")
    st.info("URL直アクセスも可能です。例：`...?theme=cashflow`")
    st.stop()

# =============================================================================
# テーマ1️⃣ 製造業向け
# =============================================================================
if theme=="factory":
    st.title("🏭 3分で分かる 製造業経営診断")
    st.write("10問に答えるだけで、工場経営の重点改善ポイントを可視化します。")

    YN3 = ["Yes","部分的に","No"]
    with st.form("factory_form"):
        st.subheader("① 生産・在庫管理")
        q1=st.radio("Q1. 生産計画と実績を毎月確認していますか？", YN3, index=1)
        q2=st.radio("Q2. 在庫量を定量的に管理していますか？", YN3, index=1)
        st.subheader("② 原価・収益管理")
        q3=st.radio("Q3. 製品ごとの利益率を把握していますか？", YN3, index=1)
        q4=st.radio("Q4. 価格改定の検討を定期的に行っていますか？", YN3, index=1)
        st.subheader("③ 設備・人材")
        q5=st.radio("Q5. 設備稼働率を把握していますか？", YN3, index=1)
        q6=st.radio("Q6. 技能承継や多能工化の仕組みがありますか？", YN3, index=1)
        st.subheader("④ 取引・顧客関係")
        q7=st.radio("Q7. 主要取引先との依存度を把握していますか？", YN3, index=1)
        q8=st.radio("Q8. 新規顧客の開拓活動を行っていますか？", YN3, index=1)
        st.subheader("⑤ 経営基盤")
        q9=st.radio("Q9. 中期経営計画を策定していますか？", YN3, index=2)
        q10=st.radio("Q10. 経営会議でデータを活用した議論を行っていますか？", YN3, index=2)
        company=st.text_input("会社名（必須）")
        email=st.text_input("メールアドレス（必須）")
        submitted=st.form_submit_button("診断する")

    if submitted:
        ok,msg=validate_inputs(company,email)
        if not ok: st.error(msg); st.stop()
        mapper={"Yes":5,"部分的に":3,"No":1}
        scores=[mapper[q] for q in [q1,q2,q3,q4,q5,q6,q7,q8,q9,q10]]
        df=pd.DataFrame({"カテゴリ":[
            "生産・在庫","原価・収益","設備・人材","取引・顧客","経営基盤"],
            "平均スコア":[sum(scores[0:2])/2,sum(scores[2:4])/2,sum(scores[4:6])/2,sum(scores[6:8])/2,sum(scores[8:10])/2]})
        overall=df["平均スコア"].mean()
        signal="青" if overall>=4 else("黄" if overall>=2.6 else "赤")
        main_type="生産効率型" if df["平均スコア"].idxmin()==0 else "営業・原価改善型"
        comment=f"全体平均{overall:.2f}点。{main_type}の傾向です。"
        result={"company":company,"dt":datetime.now(JST).strftime("%Y-%m-%d %H:%M"),
                "signal":signal,"main_type":main_type,"comment":comment}
        st.markdown(f"### タイプ判定：{main_type}　({signal}信号)")
        st.dataframe(df)
        st.download_button("📄 PDFをダウンロード",
            data=make_pdf_bytes(result,df),file_name="factory.pdf",mime="application/pdf")
        row={"timestamp":datetime.now(JST).isoformat(),"company":company,"email":email,
             "category_scores":json.dumps(df.to_dict(),ensure_ascii=False),"total_score":f"{overall:.2f}",
             "type_label":main_type,"ai_comment":comment,"utm_source":"","utm_campaign":"",
             "pdf_url":"","app_version":APP_VERSION,"status":"ok","ai_comment_len":len(comment),
             "risk_level":to_risk_level(overall),"entry_check":"OK","report_date":datetime.now(JST).strftime("%Y-%m-%d")}
        append_to_sheet(row,"factory")

# =============================================================================
# テーマ2️⃣ 資金繰り改善診断
# =============================================================================
elif theme=="cashflow":
    st.title("💴 3分で分かる 資金繰り改善診断")
    st.write("10問に答えるだけで、資金繰りの“詰まりどころ”を可視化します。")

    YN3=["Yes","部分的に","No"]
    THREE_USUAL=["いつも","ときどき","ほとんどない"]
    THREE_BANK=["ほとんどない","たまに","頻繁に"]
    THREE_STOCK=["多くある","少しある","ほとんどない"]

    def to_score(ans,mapping,invert=False):
        v=mapping.get(ans,3); return {5:1,3:3,1:5}[v] if invert else v

    MAP_USUAL={"いつも":1,"ときどき":3,"ほとんどない":5}
    MAP_BANK={"ほとんどない":1,"たまに":3,"頻繁に":5}
    MAP_STOCK={"多くある":1,"少しある":3,"ほとんどない":5}
    MAP_YN3={"Yes":5,"部分的に":3,"No":1}

    with st.form("cash_form"):
        st.subheader("① 売上・入金管理")
        q1=st.radio("Q1. 得意先からの入金が「少し遅い」と感じることがありますか？",THREE_USUAL,index=1)
        q2=st.radio("Q2. 請求書発行から入金までの流れを定期的に点検・改善していますか？",YN3,index=1)
        st.subheader("② 支払・仕入管理")
        q3=st.radio("Q3. 支払条件（サイト）は自社の資金繰りを考慮して設計できていますか？",YN3,index=1)
        q4=st.radio("Q4. 外注費や仕入先への支払予定を月次で見通せていますか？",YN3,index=1)
        st.subheader("③ 在庫・固定費管理")
        q5=st.radio("Q5. 倉庫や事業所に「売れ残り在庫」がありますか？",THREE_STOCK,index=1)
        q6=st.radio("Q6. 固定費を季節変動を加味して予実管理できていますか？",YN3,index=1)
        st.subheader("④ 借入・金融機関連携")
        q7=st.radio("Q7. 銀行とはどの程度の頻度で連絡を取り合いますか？",THREE_BANK,index=1)
        q8=st.radio("Q8. 借入金の返済計画や金利条件を把握し見直していますか？",YN3,index=1)
        st.subheader("⑤ 資金繰り管理体制")
        q9=st.radio("Q9. 短期の資金繰り表を運用していますか？",YN3,index=2)
        q10=st.radio("Q10. 資金不足が見込まれる場合の対応ルールは定めていますか？",YN3,index=1)
        company=st.text_input("会社名（必須）")
        email=st.text_input("メールアドレス（必須）")
        submitted=st.form_submit_button("診断する")

    if submitted:
        ok,msg=validate_inputs(company,email)
        if not ok: st.error(msg); st.stop()
        df=pd.DataFrame({
            "カテゴリ":["売上・入金管理","支払・仕入管理","在庫・固定費管理","借入・金融機関連携","資金繰り管理体制"],
            "平均スコア":[
                (to_score(q1,MAP_USUAL)+to_score(q2,MAP_YN3))/2,
                (to_score(q3,MAP_YN3)+to_score(q4,MAP_YN3))/2,
                (to_score(q5,MAP_STOCK)+to_score(q6,MAP_YN3))/2,
                (to_score(q7,MAP_BANK)+to_score(q8,MAP_YN3))/2,
                (to_score(q9,MAP_YN3)+to_score(q10,MAP_YN3))/2
            ]})
        overall=df["平均スコア"].mean()
        signal="青" if overall>=4 else("黄" if overall>=2.6 else "赤")
        worst=df.sort_values("平均スコア").iloc[0]["カテゴリ"]
        main_type={"売上・入金管理":"売上依存型","支払・仕入管理":"支払圧迫型",
                   "在庫・固定費管理":"在庫・固定費過多型","借入・金融機関連携":"金融連携不足型",
                   "資金繰り管理体制":"体制未整備型"}[worst]
        comment=f"{main_type}傾向。平均{overall:.2f}点。"

        st.markdown(f"### タイプ判定：{main_type}（{signal}信号）")
        st.dataframe(df)

        pdf_bytes=make_pdf_bytes(
            {"company":company,"dt":datetime.now(JST).strftime('%Y-%m-%d %H:%M'),
             "signal":signal,"main_type":main_type,"comment":comment},df)
        st.download_button("📄 PDFをダウンロード",data=pdf_bytes,file_name="cashflow.pdf",mime="application/pdf")

        row={"timestamp":datetime.now(JST).isoformat(),"company":company,"email":email,
             "category_scores":json.dumps(df.to_dict(),ensure_ascii=False),"total_score":f"{overall:.2f}",
             "type_label":main_type,"ai_comment":comment,"utm_source":"","utm_campaign":"",
             "pdf_url":"","app_version":APP_VERSION,"status":"ok","ai_comment_len":len(comment),
             "risk_level":to_risk_level(overall),"entry_check":"OK","report_date":datetime.now(JST).strftime("%Y-%m-%d")}
        append_to_sheet(row,"cashflow")















