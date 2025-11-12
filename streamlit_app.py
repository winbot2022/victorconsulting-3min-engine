# -*- coding: utf-8 -*-
# =====================================================
# 3分診断エンジン｜Victor Consulting
# =====================================================
# - 複数テーマ統合（製造業診断・資金繰り改善診断）
# - OpenAIによるAIコメント生成
# - PDFレポート出力
# - URLパラメータでテーマ選択（?theme=factory / ?theme=cashflow）
# =====================================================

import os, io, json, time, base64, tempfile, re
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
import qrcode, requests, gspread
from google.oauth2.service_account import Credentials

# =====================================================
# 共通設定
# =====================================================
BRAND_BG   = "#f0f7f7"
LOGO_URL   = "https://victorconsulting.jp/wp-content/uploads/2025/10/CImark.png"
CTA_URL    = "https://victorconsulting.jp/spot-diagnosis/"
OPENAI_MODEL = "gpt-4o-mini"
APP_VERSION  = "v2.5.0"
JST = timezone(timedelta(hours=9))
THEME_SLUGS = {"factory": "製造業診断", "cashflow": "資金繰り改善診断"}
SLUG_BY_NAME = {v: k for k, v in THEME_SLUGS.items()}

st.set_page_config(page_title="3分診断エンジン｜Victor Consulting", page_icon="✅", layout="centered")

# =====================================================
# 汎用関数
# =====================================================
def read_secret(key, default=None):
    try:
        return st.secrets[key]
    except Exception:
        return os.environ.get(key, default)

def setup_font():
    font_path = "NotoSansJP-Regular.ttf"
    if os.path.exists(font_path):
        pdfmetrics.registerFont(TTFont("JP", font_path))
        registerFontFamily("JP", normal="JP", bold="JP", italic="JP", boldItalic="JP")
        font_manager.fontManager.addfont(font_path)
setup_font()

def path_or_download_logo() -> str:
    local = "CImark.png"
    if os.path.exists(local):
        return local
    try:
        r = requests.get(LOGO_URL, timeout=8)
        if r.ok:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
            tmp.write(r.content)
            tmp.flush()
            return tmp.name
    except Exception:
        pass
    return None

def build_qr_png(url: str):
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()

def build_bar_png(df: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(5,2.5), dpi=220)
    df_sorted = df.sort_values("平均スコア", ascending=True)
    ax.barh(df_sorted["カテゴリ"], df_sorted["平均スコア"], color="#0077b6")
    ax.set_xlim(0,5)
    ax.grid(axis="x", linestyle="--", alpha=0.3)
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="PNG")
    plt.close(fig)
    buf.seek(0)
    return buf.read()

def make_pdf_bytes(result: dict, df: pd.DataFrame):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=32, leftMargin=32, topMargin=28, bottomMargin=28)
    styles = getSampleStyleSheet()
    normal = styles["BodyText"]; h3 = styles["Heading3"]
    normal.fontName = h3.fontName = "JP"
    elems = []
    logo_path = path_or_download_logo()
    if logo_path:
        elems.append(Image(logo_path, width=120, height=40))
    elems.append(Spacer(1, 10))
    elems.append(Paragraph(f"3分無料診断レポート｜{result['theme']}", styles["Title"]))
    elems.append(Spacer(1, 6))
    elems.append(Paragraph(f"会社名：{result['company']}　日付：{result['dt']}　信号：{result['signal']}", normal))
    elems.append(Spacer(1, 6))
    elems.append(Paragraph("AIコメント", h3))
    elems.append(Paragraph(result["comment"], normal))
    elems.append(Spacer(1, 6))
    data = [["カテゴリ","平均スコア"]] + [[r["カテゴリ"], f"{r['平均スコア']:.2f}"] for _,r in df.iterrows()]
    t = Table(data, colWidths=[260,100])
    t.setStyle(TableStyle([("GRID",(0,0),(-1,-1),0.5,colors.grey)]))
    elems.append(t)
    elems.append(Spacer(1,8))
    png = build_bar_png(df)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    tmp.write(png); tmp.flush()
    elems.append(Image(tmp.name, width=380, height=180))
    elems.append(Spacer(1,10))
    qr = build_qr_png(CTA_URL)
    qtmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    qtmp.write(qr); qtmp.flush()
    elems.append(Paragraph("次の一手：90分スポット診断のご案内", h3))
    elems.append(Image(qtmp.name, width=60, height=60))
    doc.build(elems)
    buf.seek(0)
    return buf.read()

def openai_generate_comment(theme, company, main_type, df, avg):
    api_key = read_secret("OPENAI_API_KEY")
    if not api_key:
        return "（AIコメント未生成：APIキー未設定）"
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
    except:
        import openai
        openai.api_key = api_key
        client = openai
    worst2 = df.sort_values("平均スコア", ascending=True).head(2)["カテゴリ"].tolist()
    prompt = f"""
あなたはVictor Consultingの経営コンサルタントです。
テーマ：{theme}
会社名：{company or '（未入力）'}
平均スコア：{avg:.2f} / 5
信号：{"青" if avg>=4 else "黄" if avg>=2.6 else "赤"}
弱点カテゴリTOP2：{", ".join(worst2)}

上記を踏まえ、経営者向けに約300字（260〜340字）で日本語のコメントを作成。
- 1段落で、前置き・箇条書きなし。
- 最後の一文は信号色に応じた強度で「90分スポット診断」を勧める。
"""
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role":"system","content":"簡潔かつ実務的に。"},
                      {"role":"user","content":prompt}],
            temperature=0.5,
            max_tokens=400,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"（AIコメント生成エラー: {e}）"

def auto_save_to_sheets(row, sheet_name):
    secret_json = read_secret("GOOGLE_SERVICE_JSON")
    sheet_id = read_secret("SPREADSHEET_ID")
    if not secret_json or not sheet_id: return
    creds = Credentials.from_service_account_info(json.loads(secret_json), scopes=["https://www.googleapis.com/auth/spreadsheets"])
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(sheet_id)
    try:
        ws = sh.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=sheet_name, rows=1000, cols=20)
    if not ws.get_all_values():
        ws.append_row(list(row.keys()))
    ws.append_row(list(row.values()))

# =====================================================
# 製造業診断
# =====================================================
def run_factory():
    st.title("製造現場の“隠れたムダ”をあぶり出す｜3分無料診断")
    st.write("**10問**に回答するだけで、貴社のリスク構造を可視化します。")
    YN3=["Yes","部分的に","No"]
    with st.form("factory_form"):
        q1=st.radio("在庫基準を数値で管理していますか？",YN3)
        q2=st.radio("在庫削減の責任部署が明確ですか？",YN3)
        q3=st.radio("熟練者しか対応できない作業が多いですか？",YN3)
        q4=st.radio("標準書を継続更新していますか？",YN3)
        q5=st.radio("原価削減目標を数値で追っていますか？",YN3)
        q6=st.radio("現場リーダーがコスト感覚を持っていますか？",YN3)
        q7=st.radio("受注変動対応ルールがありますか？",YN3)
        q8=st.radio("リードタイム短縮を定期見直ししていますか？",YN3)
        q9=st.radio("進捗をリアルタイムで把握できますか？",YN3)
        q10=st.radio("データをもとに会議を行っていますか？",YN3)
        company=st.text_input("会社名"); email=st.text_input("メールアドレス")
        submit=st.form_submit_button("診断する")
    if not submit: return
    def s(x):return {"Yes":5,"部分的に":3,"No":1}.get(x,3)
    df=pd.DataFrame({
        "カテゴリ":["在庫・運搬","人材・技能承継","原価意識・改善文化","生産計画・変動対応","DX・情報共有"],
        "平均スコア":[(s(q1)+s(q2))/2,(6-s(q3)+s(q4))/2,(s(q5)+s(q6))/2,(s(q7)+s(q8))/2,(s(q9)+s(q10))/2]
    })
    avg=df["平均スコア"].mean()
    sig="青" if avg>=4 else "黄" if avg>=2.6 else "赤"
    main=df.sort_values("平均スコア").iloc[0]["カテゴリ"]
    comment=openai_generate_comment("製造業診断",company,main,df,avg)
    pdf=make_pdf_bytes({"theme":"製造業診断","company":company,"dt":datetime.now(JST).strftime("%Y-%m-%d %H:%M"),"signal":sig,"comment":comment},df)
    st.download_button("📄 PDFをダウンロード",data=pdf,file_name=f"製造業診断_{company}.pdf")
    row={"timestamp":datetime.now(JST).isoformat(),"company":company,"email":email,"avg":avg,"comment":comment}
    auto_save_to_sheets(row,"製造業診断")
    st.success("診断結果を保存しました。")

# =====================================================
# 資金繰り改善診断
# =====================================================
def run_cashflow():
    st.title("3分で分かる 資金繰り改善診断")
    OPT3=["多くある","少しある","ほとんどない"]
    FREQ=["ほとんどない","たまに","頻繁に"]
    with st.form("cash_form"):
        q1=st.radio("得意先からの入金が少し遅いと感じますか？",["いつも","ときどき","ほとんどない"])
        q2=st.radio("支払い条件が厳しいと感じますか？",["Yes","No"])
        q3=st.radio("在庫が増えていますか？",["Yes","No"])
        q4=st.radio("固定費の負担が重いですか？",["Yes","No"])
        q5=st.radio("倉庫に売れ残り在庫がありますか？",OPT3)
        q6=st.radio("借入金の返済負担が重いと感じますか？",["Yes","No"])
        q7=st.radio("銀行とはどの程度連絡を取りますか？",FREQ)
        q8=st.radio("資金繰り表を定期的に更新していますか？",["Yes","No"])
        q9=st.radio("キャッシュフローを数値で把握していますか？",["Yes","No"])
        q10=st.radio("資金繰り管理を担当する人が明確ですか？",["Yes","No"])
        company=st.text_input("会社名"); email=st.text_input("メールアドレス")
        submit=st.form_submit_button("診断する")
    if not submit:return
    def yn(x):return {"Yes":5,"No":1,"いつも":5,"ときどき":3,"ほとんどない":1,"多くある":1,"少しある":3}.get(x,3)
    df=pd.DataFrame({
        "カテゴリ":["売上・入金管理","支払・仕入管理","在庫・固定費管理","借入・金融機関連携","資金繰り管理体制"],
        "平均スコア":[(yn(q1)+yn(q2))/2,(yn(q2)+yn(q4))/2,(yn(q3)+yn(q5))/2,(yn(q6)+yn(q7))/2,(yn(q8)+yn(q9))/2]
    })
    avg=df["平均スコア"].mean()
    sig="青" if avg>=4 else "黄" if avg>=2.6 else "赤"
    main=df.sort_values("平均スコア").iloc[0]["カテゴリ"]
    comment=openai_generate_comment("資金繰り改善診断",company,main,df,avg)
    pdf=make_pdf_bytes({"theme":"資金繰り改善診断","company":company,"dt":datetime.now(JST).strftime("%Y-%m-%d %H:%M"),"signal":sig,"comment":comment},df)
    st.download_button("📄 PDFをダウンロード",data=pdf,file_name=f"資金繰り診断_{company}.pdf")
    row={"timestamp":datetime.now(JST).isoformat(),"company":company,"email":email,"avg":avg,"comment":comment}
    auto_save_to_sheets(row,"資金繰り改善診断")
    st.success("診断結果を保存しました。")

# =====================================================
# ルーティング制御
# =====================================================
try:
    qp=st.query_params
except:
    qp=st.experimental_get_query_params()
param=(qp.get("theme") or [""])[0].lower()
if param=="factory":
    run_factory()
elif param=="cashflow":
    run_cashflow()
else:
    st.title("3分診断エンジン｜Victor Consulting")
    st.markdown("""
    経営課題を“瞬間で見える化”する自己診断ツール。  
    以下のテーマを選んでください。
    - 🏭 [製造業診断](?theme=factory)
    - 💴 [資金繰り改善診断](?theme=cashflow)
    """)














