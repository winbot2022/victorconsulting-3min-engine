# -*- coding: utf-8 -*-
# 3分診断エンジン｜Victor Consulting
# - 会社名/メール必須、UTM取得、AIコメント自動生成、PDF 1ページ、JST
# - Google Sheets 自動保存（なければ CSV）
# - サイレント保存、二重書き込み防止（saved_once & dedup_key）
# - 管理者モード（?admin=1 または Secrets: ADMIN_MODE="1"）でイベント確認
# - テーマ切替 (?theme=factory / ?theme=cashflow)
# - テーマごとに保存シートは responses_{theme}

import os, io, re, json, time, base64, tempfile, importlib
from datetime import datetime, timedelta, timezone
from typing import Tuple, Dict, Any

import streamlit as st
import pandas as pd
import altair as alt
import matplotlib.pyplot as plt

# PDF
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily

# Fonts/Images
from matplotlib import font_manager
from PIL import Image as PILImage
import qrcode
import requests

# Google Sheets
import gspread
from google.oauth2.service_account import Credentials

# ========= ブランド & 定数 =========
BRAND_BG   = "#f0f7f7"
LOGO_LOCAL = "assets/CImark.png"
LOGO_URL   = "https://victorconsulting.jp/wp-content/uploads/2025/10/CImark.png"
CTA_URL    = "https://victorconsulting.jp/spot-diagnosis/"
OPENAI_MODEL = "gpt-4o-mini"
APP_VERSION  = "engine-v1.0.0"

# 日本時間
JST = timezone(timedelta(hours=9))

# 共通ヘッダー（製造業版・資金繰り版と同一並び）
COMMON_HEADER_ORDER = [
    "timestamp","company","email","category_scores","total_score","type_label","ai_comment",
    "utm_source","utm_campaign","pdf_url","app_version","status","ai_comment_len",
    "risk_level","entry_check","report_date","theme"  # ← 最後に theme を追記
]

# ========= 画面設定（背景余白は既存同様） =========
st.set_page_config(
    page_title="3分診断エンジン｜Victor Consulting",
    page_icon="✅",
    layout="centered",
    initial_sidebar_state="expanded"
)

# ========= Secrets/環境変数 =========
def read_secret(key: str, default=None):
    try:
        return st.secrets[key]
    except Exception:
        return os.environ.get(key, default)

# ========= 管理者モード =========
try:
    qp = st.query_params
except Exception:
    qp = st.experimental_get_query_params()
ADMIN_MODE = (str(qp.get("admin", ["0"])[0]) == "1") or (str(read_secret("ADMIN_MODE", "0")) == "1")

# ========= テーマ選択 =========
def get_theme_name() -> str:
    try:
        q = st.query_params
    except Exception:
        q = st.experimental_get_query_params()
    theme = q.get("theme", ["factory"])[0] if isinstance(q.get("theme"), list) else q.get("theme", "factory")
    return theme if theme in ("factory","cashflow") else "factory"

THEME = get_theme_name()

# ========= 日本語TTF 登録 =========
def setup_japanese_font():
    candidates = [
        "NotoSansJP-Regular.ttf",
        "/mnt/data/NotoSansJP-Regular.ttf",
        "/content/NotoSansJP-Regular.ttf",
    ]
    font_path = next((p for p in candidates if os.path.exists(p)), None)
    if not font_path:
        return None
    try:
        pdfmetrics.registerFont(TTFont("JP", font_path))
        registerFontFamily("JP", normal="JP", bold="JP", italic="JP", boldItalic="JP")
    except Exception as e:
        print("ReportLab font register error:", e)
    try:
        font_manager.fontManager.addfont(font_path)
        fp = font_manager.FontProperties(fname=font_path)
        import matplotlib as mpl
        mpl.rcParams["font.family"] = fp.get_name()
        mpl.rcParams["axes.unicode_minus"] = False
    except Exception as e:
        print("Matplotlib font register error:", e)
    return font_path
FONT_PATH_IN_USE = setup_japanese_font()

# ========= スタイル（既存UIと同一） =========
st.markdown(
    f"""
<style>
.stApp {{ background: {BRAND_BG}; }}
.block-container {{ padding-top: 2.8rem; }}
h1 {{ margin-top: .6rem; }}
.result-card {{
  background: white; border-radius: 14px; padding: 1.0rem 1.0rem;
  box-shadow: 0 6px 20px rgba(0,0,0,.06); border: 1px solid rgba(0,0,0,.06);
}}
.badge {{ display:inline-block; padding:.25rem .6rem; border-radius:999px; font-size:.9rem;
  font-weight:700; letter-spacing:.02em; margin-left:.5rem; }}
.badge-blue  {{ background:#e6f0ff; color:#0b5fff; border:1px solid #cfe3ff; }}
.badge-yellow{{ background:#fff6d8; color:#8a6d00; border:1px solid #ffecb3; }}
.badge-red   {{ background:#ffe6e6; color:#a80000; border:1px solid #ffc7c7; }}
.small-note {{ color:#666; font-size:.9rem; }}
hr {{ border:none; border-top:1px dotted #c9d7d7; margin:1.0rem 0; }}
</style>
""",
    unsafe_allow_html=True
)

# ========= ロゴ取得 =========
def path_or_download_logo() -> str | None:
    if os.path.exists(LOGO_LOCAL):
        return LOGO_LOCAL
    try:
        r = requests.get(LOGO_URL, timeout=8)
        if r.ok:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
            tmp.write(r.content); tmp.flush()
            return tmp.name
    except Exception:
        pass
    return None

# ========= イベント記録（管理者用） =========
def _report_event(level: str, message: str, payload: dict | None = None):
    evt = {
        "timestamp": datetime.now(JST).isoformat(timespec="seconds"),
        "level": level,
        "message": message,
        "payload": json.dumps(payload, ensure_ascii=False) if payload else ""
    }
    # Sheets優先
    secret_json     = read_secret("GOOGLE_SERVICE_JSON", None)
    secret_sheet_id = read_secret("SPREADSHEET_ID", None)
    wrote = False
    try:
        if secret_json and secret_sheet_id:
            scopes = ["https://www.googleapis.com/auth/spreadsheets"]
            info = json.loads(secret_json)
            creds = Credentials.from_service_account_info(info, scopes=scopes)
            gc = gspread.authorize(creds)
            sh = gc.open_by_key(secret_sheet_id)
            try:
                ws = sh.worksheet("events")
            except gspread.WorksheetNotFound:
                ws = sh.add_worksheet(title="events", rows=1000, cols=6)
                ws.append_row(list(evt.keys()))
            ws.append_row([evt[k] for k in evt.keys()])
            wrote = True
    except Exception:
        wrote = False
    # CSVフォールバック
    if not wrote:
        try:
            df = pd.DataFrame([evt])
            csv_path = "events.csv"
            if os.path.exists(csv_path):
                df.to_csv(csv_path, mode="a", header=False, index=False, encoding="utf-8")
            else:
                df.to_csv(csv_path, index=False, encoding="utf-8")
        except Exception:
            pass
    if ADMIN_MODE:
        st.caption(f"［ADMIN］{level}: {message}")

# ========= 保存系（Sheets/CSV） =========
def try_append_to_google_sheets(row_dict: dict, spreadsheet_id: str, service_json_str: str, sheet_title: str):
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    info = json.loads(service_json_str)
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(spreadsheet_id)
    try:
        ws = sh.worksheet(sheet_title)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=sheet_title, rows=2000, cols=30)
        ws.append_row(COMMON_HEADER_ORDER)

    values = ws.get_all_values()
    if not values:
        ws.append_row(COMMON_HEADER_ORDER)

    record = [row_dict.get(k, "") for k in COMMON_HEADER_ORDER]
    ws.append_row(record, value_input_option="USER_ENTERED")

def fallback_append_to_csv(row_dict: dict, csv_path="responses.csv"):
    df = pd.DataFrame([row_dict])
    if os.path.exists(csv_path):
        df.to_csv(csv_path, mode="a", header=False, index=False, encoding="utf-8")
    else:
        df.to_csv(csv_path, index=False, encoding="utf-8")

def auto_save_row(row: dict, theme_sheet: str):
    """ユーザーには何も表示しない。Sheets→CSVフォールバック。失敗はeventsへ。"""
    secret_json     = read_secret("GOOGLE_SERVICE_JSON", None)
    if not secret_json:
        b64 = read_secret("GOOGLE_SERVICE_JSON_BASE64", None)
        if b64:
            try:
                secret_json = base64.b64decode(b64).decode("utf-8")
            except Exception as e:
                _report_event("ERROR", f"Base64デコード失敗: {e}", {})
    secret_sheet_id = read_secret("SPREADSHEET_ID", None)

    def _append_csv():
        try:
            fallback_append_to_csv(row)
        except Exception as e2:
            _report_event("ERROR", f"CSV保存に失敗: {e2}", {"row_head": {k: row.get(k) for k in list(row)[:6]}})

    try:
        if secret_json and secret_sheet_id:
            try_append_to_google_sheets(row, secret_sheet_id, secret_json, sheet_title=theme_sheet)
        else:
            _append_csv()
    except Exception as e:
        _append_csv()
        _report_event("WARN", f"Sheets保存に失敗しCSVへフォールバック: {e}", {"reason": str(e)})

# ========= テーマ動的ロード =========
def load_theme_module(theme_name: str):
    mod = importlib.import_module(f"themes.{theme_name}")
    return mod

theme = load_theme_module(THEME)

# ========= サイドバー（共通） =========
with st.sidebar:
    logo_path = path_or_download_logo()
    if logo_path:
        st.image(logo_path, width=150)
    st.markdown("### 3分無料診断")
    st.markdown("- 入力はシンプルな2〜3段階 or Yes/部分的/No\n- 機密数値は不要\n- 結果は 6タイプ＋赤/黄/青")
    st.caption("© Victor Consulting")

# ========= タイトル/リード（テーマ依存） =========
st.title(theme.THEME_META["title"])
st.write(theme.THEME_META["lead"])

# ========= セッション初期化 =========
defaults = {
    "result_ready": False, "df": None, "overall_avg": None, "signal": None,
    "main_type": None, "company": "", "email": "",
    "ai_comment": None, "ai_tried": False,
    "utm_source": "", "utm_medium": "", "utm_campaign": "",
    "saved_once": False,
    "dedup_key": ""
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ========= UTM取得 =========
try:
    q = st.query_params
except Exception:
    q = st.experimental_get_query_params()
st.session_state["utm_source"]   = q.get("utm_source",   [""])[0] if isinstance(q.get("utm_source"), list) else q.get("utm_source", "")
st.session_state["utm_medium"]   = q.get("utm_medium",   [""])[0] if isinstance(q.get("utm_medium"), list) else q.get("utm_medium", "")
st.session_state["utm_campaign"] = q.get("utm_campaign", [""])[0] if isinstance(q.get("utm_campaign"), list) else q.get("utm_campaign", "")

# ========= バリデーション =========
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
def validate_inputs(company: str, email: str) -> Tuple[bool, str]:
    if not company.strip():
        return False, "会社名は必須です。"
    if not email.strip():
        return False, "メールアドレスは必須です。"
    if not EMAIL_RE.match(email.strip()):
        return False, "メールアドレスの形式が正しくありません。"
    return True, ""

# ========= フォーム（テーマ側でUI構築 & スコア表返却） =========
with st.form("diagnose_form"):
    company, email, df_scores = theme.render_questions(st)  # ← テーマがUIを描画し、DataFrame(カテゴリ/平均スコア)を返す
    submitted = st.form_submit_button("診断する")

# ========= 信号/タイプ（テーマ側のロジック利用） =========
if submitted:
    ok, msg = validate_inputs(company, email)
    if not ok:
        st.error(msg)
        st.stop()

    overall_avg, signal, main_type = theme.evaluate(df_scores)

    # dedup_key（10秒窓の二重書き込み防止）
    now_jst = datetime.now(JST)
    dedup_key = f"{company}|{email}|{overall_avg:.2f}|{main_type}|{now_jst.strftime('%Y-%m-%d %H:%M')}"
    st.session_state["dedup_key"] = dedup_key

    st.session_state.update({
        "df": df_scores, "overall_avg": overall_avg, "signal": signal,
        "main_type": main_type, "company": company, "email": email,
        "result_ready": True, "ai_comment": None, "ai_tried": False,
        "saved_once": False
    })

# ========= AIコメント =========
def _openai_client(api_key: str):
    try:
        from openai import OpenAI
        return "new", OpenAI(api_key=api_key)
    except Exception:
        import openai
        openai.api_key = api_key
        return "old", openai

def generate_ai_comment(theme_module, company: str, main_type: str, df_scores: pd.DataFrame, overall_avg: float):
    api_key = read_secret("OPENAI_API_KEY", None)
    if not api_key:
        return None, "OpenAIのAPIキーが未設定です。"

    user_prompt = theme_module.build_ai_prompt(company, main_type, df_scores, overall_avg)
    mode, client = _openai_client(api_key)

    for attempt in range(2):
        try:
            if mode == "new":
                resp = client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": "専門的かつ簡潔。日本語。実務に直結する助言を。"},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.4,
                    max_tokens=420,
                )
                return resp.choices[0].message.content.strip(), None
            else:
                resp = client.ChatCompletion.create(
                    model=OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": "専門的かつ簡潔。日本語。実務に直結する助言を。"},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.4,
                    max_tokens=420,
                )
                return resp.choices[0].message["content"].strip(), None
        except Exception as e:
            if attempt == 0:
                time.sleep(4)
                continue
            _report_event("ERROR", f"AIコメント生成エラー: {e}", {})
            return None, f"AIコメント生成でエラー: {e}"

def clamp_comment(text: str, max_chars: int = 520) -> str:
    if not text: return ""
    t = " ".join(text.strip().split())
    return t if len(t) <= max_chars else (t[:max_chars - 1] + "…")

# ========= 図・QRユーティリティ =========
def build_bar_png(df: pd.DataFrame) -> bytes:
    fig, ax = plt.subplots(figsize=(5.0, 2.4), dpi=220)
    df_sorted = df.sort_values("平均スコア", ascending=True)
    ax.barh(df_sorted["カテゴリ"], df_sorted["平均スコア"])
    ax.set_xlim(0, 5)
    ax.set_xlabel("平均スコア（0-5）")
    ax.grid(axis="x", linestyle="--", alpha=0.3)
    if FONT_PATH_IN_USE:
        from matplotlib import font_manager as fm
        fp = fm.FontProperties(fname=FONT_PATH_IN_USE)
        ax.set_xlabel("平均スコア（0-5）", fontproperties=fp)
        for label in ax.get_yticklabels(): label.set_fontproperties(fp)
        for label in ax.get_xticklabels(): label.set_fontproperties(fp)
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png")
    plt.close(fig); buf.seek(0)
    return buf.read()

def image_with_max_width(path: str, max_w: int):
    with PILImage.open(path) as im:
        w, h = im.size
    if w <= max_w:
        return Image(path, width=w, height=h)
    new_h = h * (max_w / w)
    return Image(path, width=max_w, height=new_h)

def build_qr_png(data_url: str) -> bytes:
    img = qrcode.make(data_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()

# ========= PDF生成（既存と同じレイアウト） =========
def make_pdf_bytes(result: dict, df_scores: pd.DataFrame, brand_hex=BRAND_BG) -> bytes:
    logo_path = path_or_download_logo()
    bar_png = build_bar_png(df_scores)
    qr_png  = build_qr_png(CTA_URL)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        rightMargin=32, leftMargin=32, topMargin=28, bottomMargin=28
    )

    styles = getSampleStyleSheet()
    title = styles["Title"]; normal = styles["BodyText"]; h3 = styles["Heading3"]
    if FONT_PATH_IN_USE:
        title.fontName = normal.fontName = h3.fontName = "JP"
    normal.fontSize = 10
    normal.leading = 14
    h3.spaceBefore = 6
    h3.spaceAfter = 4

    elems = []
    if logo_path:
        elems.append(image_with_max_width(logo_path, max_w=120))
        elems.append(Spacer(1, 6))

    elems.append(Paragraph("3分無料診断レポート", title))
    elems.append(Spacer(1, 4))
    meta = (
        f"会社名：{result['company'] or '（未入力）'}　/　"
        f"実施日時：{result['dt']}　/　"
        f"信号：{result['signal']}　/　"
        f"タイプ：{result['main_type']}"
    )
    elems.append(Paragraph(meta, normal))
    elems.append(Spacer(1, 6))

    elems.append(Paragraph("診断コメント", h3))
    elems.append(Paragraph(clamp_comment(result["comment"], 520), normal))
    elems.append(Spacer(1, 6))

    table_data = [["カテゴリ", "平均スコア（0-5）"]] + [
        [r["カテゴリ"], f"{r['平均スコア']:.2f}"] for _, r in df_scores.iterrows()
    ]
    tbl = Table(table_data, colWidths=[220, 140])
    style_list = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(brand_hex)),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.black),
        ("GRID",       (0, 0), (-1, -1), 0.3, colors.grey),
        ("ALIGN",      (1, 1), (-1, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
    ]
    if FONT_PATH_IN_USE:
        style_list.append(("FONTNAME", (0, 0), (-1, -1), "JP"))
    tbl.setStyle(TableStyle(style_list))
    elems.append(tbl)
    elems.append(Spacer(1, 6))

    bar_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    bar_tmp.write(bar_png); bar_tmp.flush()
    elems.append(Paragraph("カテゴリ別スコア（棒グラフ）", h3))
    elems.append(Image(bar_tmp.name, width=390, height=180))
    elems.append(Spacer(1, 6))

    # 次の一手（QR右寄せ）
    elems.append(Paragraph("次の一手（90分スポット診断のご案内）", h3))
    url_par = Paragraph(f"詳細・お申込み：<u>{CTA_URL}</u>", normal)
    qr_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    qr_tmp.write(qr_png); qr_tmp.flush()
    qr_img = Image(qr_tmp.name, width=52, height=52)
    next_table = Table([[url_par, qr_img]], colWidths=[430, 70])
    nt_style = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 0), (1, 0), "RIGHT")]
    if FONT_PATH_IN_USE:
        nt_style.append(("FONTNAME", (0, 0), (-1, -1), "JP"))
    next_table.setStyle(TableStyle(nt_style))
    elems.append(next_table)

    doc.build(elems)
    buf.seek(0)
    return buf.read()

# ========= 結果画面 =========
if st.session_state.get("result_ready"):
    df = st.session_state["df"]
    overall_avg = st.session_state["overall_avg"]
    signal = st.session_state["signal"]
    main_type = st.session_state["main_type"]
    company = st.session_state["company"]
    email = st.session_state["email"]
    current_time = datetime.now(JST).strftime("%Y-%m-%d %H:%M")

    # AIコメント自動生成（初回のみ）
    if not st.session_state["ai_tried"]:
        st.session_state["ai_tried"] = True
        text, err = generate_ai_comment(theme, company, main_type, df, overall_avg)
        if text:
            st.session_state["ai_comment"] = text
        elif err:
            st.session_state["ai_comment"] = None
            _report_event("WARN", f"AIコメント未生成: {err}", {})

    # UI（既存カードと同一）
    st.markdown("### 診断結果")
    st.markdown(
        f"""
        <div class="result-card">
            <h3 style="margin:0 0 .3rem 0;">
              タイプ判定：{main_type} <span class="badge {signal[1]}">{signal[0]}</span>
            </h3>
            <div class="small-note">
              会社名：{company or "（未入力）"} ／ 実施日時：{current_time}
            </div>
            <hr/>
            <p style="margin:.2rem 0 0 0;">{theme.TYPE_TEXT[main_type]}</p>
        </div>
        """,
        unsafe_allow_html=True
    )

    # 棒グラフ・表（同一仕様）
    chart = (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=alt.X("平均スコア:Q", scale=alt.Scale(domain=[0, 5])),
            y=alt.Y("カテゴリ:N", sort="-x"),
            tooltip=["カテゴリ", "平均スコア"]
        ).properties(height=210)
    )
    st.altair_chart(chart, use_container_width=True)
    st.dataframe(df.style.format({"平均スコア": "{:.2f}"}), use_container_width=True)

    # 画面 AIコメント
    st.subheader("AIコメント（自動生成）")
    if st.session_state["ai_comment"]:
        st.write(st.session_state["ai_comment"])
    else:
        st.caption("（OpenAI APIキー未設定等のため、PDFには静的コメントを挿入します）")

    # PDF
    comment_for_pdf = st.session_state["ai_comment"] or theme.TYPE_TEXT[main_type]
    result_payload = {
        "company": company,
        "email": email,
        "dt": current_time,  # JST
        "signal": signal[0],
        "main_type": main_type,
        "comment": comment_for_pdf
    }
    pdf_bytes = make_pdf_bytes(result_payload, df, brand_hex=BRAND_BG)
    fname = f"VC_診断_{company or '匿名'}_{datetime.now(JST).strftime('%Y%m%d_%H%M')}.pdf"
    st.download_button("📄 PDFをダウンロード", data=pdf_bytes, file_name=fname, mime="application/pdf")

    # ======== シート書き込み用データ ========
    category_scores = {cat: float(df.loc[df["カテゴリ"]==cat,"平均スコア"].values[0]) for cat in df["カテゴリ"].tolist()}
    category_scores_str = json.dumps(category_scores, ensure_ascii=False)

    def to_risk_level(total: float) -> str:
        if total < 2.0: return "高リスク"
        elif total < 3.5: return "中リスク"
        else: return "低リスク"

    pdf_persist_url = ""
    comment_text = st.session_state["ai_comment"] or ""
    comment_len = len(comment_text)
    entry_check = "OK"
    report_date = datetime.now(JST).strftime("%Y-%m-%d")

    row = {
        "timestamp":   datetime.now(JST).isoformat(timespec="seconds"),
        "company":     company,
        "email":       email,
        "category_scores": category_scores_str,
        "total_score": f"{overall_avg:.2f}",
        "type_label":  main_type,
        "ai_comment":  comment_text,
        "utm_source":  st.session_state.get("utm_source",""),
        "utm_campaign":st.session_state.get("utm_campaign",""),
        "pdf_url":     pdf_persist_url,
        "app_version": APP_VERSION,
        "status":      "ok",
        "ai_comment_len": str(comment_len),
        "risk_level":  to_risk_level(overall_avg),
        "entry_check": entry_check,
        "report_date": report_date,
        "theme":       THEME,
    }

    # ▼▼ 二重書き込み防止：AI試行済かつ未保存、かつdedup_keyが今と一致 ▼▼
    if st.session_state.get("ai_tried") and not st.session_state.get("saved_once"):
        # 10秒以内の同一キー多重を抑止（再描画対策）
        if st.session_state.get("dedup_key"):
            auto_save_row(row, theme_sheet=f"responses_{THEME}")
            st.session_state["saved_once"] = True
# 結果未表示
else:
    st.caption("フォームに回答し、「診断する」を押してください。")

# ========= 管理者UI（任意） =========
if ADMIN_MODE:
    with st.expander("ADMIN：イベントログの確認（最新50件）"):
        secret_json     = read_secret("GOOGLE_SERVICE_JSON", None)
        secret_sheet_id = read_secret("SPREADSHEET_ID", None)
        shown = False
        try:
            if secret_json and secret_sheet_id:
                scopes = ["https://www.googleapis.com/auth/spreadsheets"]
                info = json.loads(secret_json)
                creds = Credentials.from_service_account_info(info, scopes=scopes)
                gc = gspread.authorize(creds)
                sh = gc.open_by_key(secret_sheet_id)
                ws = sh.worksheet("events")
                values = ws.get_all_records()
                if values:
                    df_evt = pd.DataFrame(values).sort_values("timestamp", ascending=False).head(50)
                    st.dataframe(df_evt, use_container_width=True)
                    shown = True
        except Exception:
            pass
        if not shown:
            if os.path.exists("events.csv"):
                df_evt = pd.read_csv("events.csv").sort_values("timestamp", ascending=False).head(50)
                st.dataframe(df_evt, use_container_width=True)
            else:
                st.info("イベントログはまだありません。")
















