# -*- coding: utf-8 -*-
# 3分診断エンジン｜Victor Consulting
# - 会社名/メール必須、UTM取得、AIコメント自動生成、PDF 1ページ、JST
# - Google Sheets 自動保存（なければ CSV）
# - サイレント保存、二重書き込み防止（saved_once & dedup_key）
# - 管理者モード（?admin=1 または Secrets: ADMIN_MODE="1"）でイベント確認
# - テーマ切替 (?theme=factory など)
# - テーマごとに保存シートは responses_{theme}

import os, io, re, json, time, base64, tempfile, importlib, importlib.util
from datetime import datetime, timedelta, timezone
from typing import Tuple

import streamlit as st
import pandas as pd
import altair as alt
import matplotlib.pyplot as plt

# PDF
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
)
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

# ========= ポータル（ブランドページ）設定 =========
PORTAL_TITLE = "3分診断ポータル｜Victor Consulting"
PORTAL_HERO  = "会社の “ボトルネック” を、3分で見える化"
PORTAL_LEAD  = "機密数値は不要。Yes/Noや2〜3段階の簡易回答だけで、“次の一手”まで示します。"

# カード定義（順番＝表示順）
DIAG_MENU = [
    {
        "key": "factory",
        "emoji": "🏭",
        "title": "製造現場の隠れたムダ診断",
        "lead": "工程・段取り・仕掛・在庫の“ボトルネック”を明確化し、流れを良くする改善点を特定します",
        "available": True,
    },
    {
        "key": "cashflow",
        "emoji": "💴",
        "title": "資金繰り改善診断",
        "lead": "入金・在庫・回収・支払など、お金の動きを止める“資金ボトルネック”を3分で抽出します",
        "available": True,
    },
    {
        "key": "succession",
        "emoji": "🧭",
        "title": "事業承継準備度診断",
        "lead":  "後継者・資本・ガバナンス・関係者・ライフ設計の視点から“承継のリスク要因”を見える化します",
        "available": True,
    },
    {
        "key": "retention",
        "emoji": "👥",
        "title": "人材定着診断",
        "lead":  "採用・評価・育成・働き方・職場風土から、“離職につながる要因”を早期に発見します",
        "available": True,
    },
    {
        "key": "productivity_office",
        "emoji": "🗂️",
        "title": "オフィス生産性診断",
        "lead":  "会議・情報共有・IT活用・時間配分の乱れから、“生産性を下げる要因”を見える化します",
        "available": True,
    },
    {
        "key": "sales",
        "emoji": "📈",
        "title": "営業力改善診断",
        "lead":  "見込み客づくり・商談・受注・リピートの流れを整理し、営業活動の“停滞ポイント”を特定します",
        "available": True,
    },
]

# ========= クエリ/ルーティング系 =========
def current_query_params() -> dict:
    try:
        q = st.query_params
        return {k: (v[0] if isinstance(v, list) else v) for k, v in q.items()}
    except Exception:
        q = st.experimental_get_query_params()
        return {k: (v[0] if isinstance(v, list) else v) for k, v in q.items()}

def build_theme_url(theme_key: str, keep=("utm_source","utm_medium","utm_campaign")) -> str:
    base = {"theme": theme_key}
    q = current_query_params()
    for k in keep:
        if q.get(k):
            base[k] = q[k]
    return "?" + "&".join(f"{k}={base[k]}" for k in base)

def is_truthy(x) -> bool:
    return str(x).strip() in ("1","true","True","yes","on")

# 日本時間
JST = timezone(timedelta(hours=9))

# 共通ヘッダー
COMMON_HEADER_ORDER = [
    "timestamp","company","email","category_scores","total_score","type_label","ai_comment",
    "utm_source","utm_campaign","pdf_url","app_version","status","ai_comment_len",
    "risk_level","entry_check","report_date","theme"
]

# ========= 画面設定 =========
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

# ========= ルーティング判定 =========
def theme_exists(theme_key: str) -> bool:
    try:
        return importlib.util.find_spec(f"themes.{theme_key}") is not None
    except Exception:
        return False

def get_route() -> dict:
    """
    return {"mode": "portal" | "theme", "theme": <slug or None>}
    """
    q = current_query_params()
    menu_flag = is_truthy(q.get("menu", "0"))
    theme_raw = (q.get("theme", "") or "").strip().lower()

    if menu_flag or theme_raw in ("", "portal"):
        return {"mode": "portal", "theme": None}

    if theme_raw and theme_exists(theme_raw):
        return {"mode": "theme", "theme": theme_raw}

    # 未実装テーマなど → ポータルへ
    return {"mode": "portal", "theme": None}

ROUTE = get_route()
THEME = ROUTE["theme"]  # <- 保存時にも使うグローバル定数

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

# ========= 共通スタイル =========
# ========= スタイル（ポータル＋診断結果） =========
st.markdown(
    f"""
<style>
.stApp {{ background: {BRAND_BG}; }}
.block-container {{ padding-top: 2.8rem; }}
h1 {{ margin-top: .6rem; }}

/* 診断結果カード（既存） */
.result-card {{
  background: white; border-radius: 14px; padding: 1.0rem 1.0rem;
  box-shadow: 0 6px 20px rgba(0,0,0,.06); border: 1px solid rgba(0,0,0,.06);
}}
.badge {{
  display:inline-block; padding:.25rem .6rem; border-radius:999px; font-size:.9rem;
  font-weight:700; letter-spacing:.02em; margin-left:.5rem;
}}
.badge-blue  {{ background:#e6f0ff; color:#0b5fff; border:1px solid #cfe3ff; }}
.badge-yellow{{ background:#fff6d8; color:#8a6d00; border:1px solid #ffecb3; }}
.badge-red   {{ background:#ffe6e6; color:#a80000; border:1px solid #ffc7c7; }}
.small-note {{ color:#666; font-size:.9rem; }}
hr {{ border:none; border-top:1px dotted #c9d7d7; margin:1.0rem 0; }}

/* ポータル：ヒーロー */
.portal-hero {{
  text-align:center; padding: 1.2rem 0 0.6rem 0;
}}

/* ポータル：グリッド ＋ カード全体リンク */
.portal-grid {{
  display:grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 18px;
  margin-top: 18px;
}}
.portal-card-link {{
  text-decoration:none;
  color:inherit;
  display:block;
  height:100%;
}}

/* ポータル：カード本体（3Dボタン風） */
.portal-card {{
  position:relative;
  display:flex;
  flex-direction:column;
  justify-content:flex-start;
  height:100%;
  min-height:240px;
  padding:16px 18px;
  border-radius:18px;
  background:#ffffff;
  box-shadow:0 10px 24px rgba(15,23,42,.06);
  border:1px solid rgba(15,23,42,.06);
  transition: transform .12s ease, box-shadow .12s ease, border-color .12s ease;
}}
.portal-card:hover {{
  transform: translateY(-4px);
  box-shadow:0 18px 36px rgba(15,23,42,.10);
  border-color:#2563eb;
}}

/* 1行目：アイコン */
.portal-icon {{
  font-size:1.8rem;
  margin-bottom:.3rem;
}}

/* 2〜3行目：タイトル */
.portal-title {{
  font-weight:800;
  font-size:1.1rem;
  margin:0 0 .35rem 0;
  line-height:1.4;
}}

/* 本文（リード） */
.portal-lead {{
  margin:.25rem 0 .9rem;
  line-height:1.6;
  color:#374151;
  font-size:.95rem;
  flex:1;
}}

/* フッター（「この診断を開く →」表示） */
.card-footer {{
  display:flex;
  justify-content:flex-end;
  margin-top:auto;
}}
.portal-cta {{
  font-size:.9rem;
  font-weight:700;
  color:#0b5fff;
}}

/* 準備中バッジ */
.badge-soon {{
  display:inline-block; padding:.2rem .6rem; border-radius:999px;
  background:#fff6d8; color:#8a6d00; border:1px solid #ffecb3; font-weight:700;
}}
</style>
""",
    unsafe_allow_html=True,
)

# ========= ロゴ取得 =========
def path_or_download_logo() -> str | None:
    if os.path.exists(LOGO_LOCAL):
        return LOGO_LOCAL
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

# ========= ポータル描画 =========
def render_portal():
    # サイドバー
    with st.sidebar:
        logo_path = path_or_download_logo()
        if logo_path:
            st.image(logo_path, width=150)
        st.markdown("### 診断メニュー")
        st.markdown("- 3分・無料・数値非公開\n- PDF出力・AIコメント")
        st.caption("© Victor Consulting")

    # ヒーロー
    title_html = "3分診断ポータル<br/>Victor Consulting"
    st.markdown(
        f"<div class='portal-hero'><h1 style='line-height:1.25'>{title_html}</h1></div>",
        unsafe_allow_html=True,
    )
    st.caption(PORTAL_HERO)
    st.write(PORTAL_LEAD)

    # JSON-LD（SEO）
    st.markdown(
        f"""
<script type="application/ld+json">
{json.dumps({
  "@context":"https://schema.org",
  "@type":"WebSite",
  "name":"Victor Consulting 3分診断ポータル",
  "url":"https://victorconsulting.jp/",
  "publisher": {
    "@type":"Organization",
    "name":"Victor Consulting",
    "logo": {"@type":"ImageObject","url": LOGO_URL}
  },
  "potentialAction": {
    "@type":"SearchAction",
    "target":"https://victorconsulting.jp/?s={{query}}",
    "query-input":"required name=query"
  }
}, ensure_ascii=False)}
</script>
""",
        unsafe_allow_html=True,
    )

    # 追加説明（そのまま）
    with st.expander("Victor Consultingについて / なぜ“3分診断”なのか？"):
        st.markdown("""
**Victor Consulting** は、中小製造業・サービス業の現場実装に強みを持つ経営コンサルティング・ファームです。  
**瞬間経営管理®** の考え方に基づき、「今、どこを直せば成果に最短でつながるか」を**3分**で示します。

- **Factory Physics / TOC / Lean** をベースに、工程・在庫・仕掛・キャッシュの流れを総合評価  
- 数値入力は不要、Yes/Noや2〜3段階で**型**に当てはめるだけ  
- 診断結果は**PDF**＋**AIコメント**で即時出力。社内共有と次アクション設計がスムーズ

ご相談は **90分スポット診断** から。継続支援・研修メニューもご用意しています。
""")

    # ▼ カードグリッド（全部 HTML で出力）
    cards_html = []
    for item in DIAG_MENU:
        if item["available"]:
            href = build_theme_url(item["key"])
            safe_href = href.replace("&", "&amp;")
            card_html = f"""
<a class="portal-card-link" href="{safe_href}">
  <div class="portal-card">
    <div class="portal-icon">{item['emoji']}</div>
    <h3 class="portal-title">{item['title']}</h3>
    <div class="portal-lead">{item['lead']}</div>
    <div class="card-footer">
      <span class="portal-cta">この診断を開く →</span>
    </div>
  </div>
</a>
"""
        else:
            card_html = f"""
<div class="portal-card">
  <div class="portal-icon">{item['emoji']}</div>
  <h3 class="portal-title">{item['title']}</h3>
  <div class="portal-lead">{item['lead']}</div>
  <div class="card-footer">
    <span class="badge-soon">準備中</span>
  </div>
</div>
"""
        cards_html.append(card_html)

    st.markdown(
        "<div class='portal-grid'>" + "\n".join(cards_html) + "</div>",
        unsafe_allow_html=True,
    )

# ========= イベント記録 =========
def _report_event(level: str, message: str, payload: dict | None = None):
    evt = {
        "timestamp": datetime.now(JST).isoformat(timespec="seconds"),
        "level": level,
        "message": message,
        "payload": json.dumps(payload, ensure_ascii=False) if payload else "",
    }
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
    """ユーザーには何も表示しない。Sheets→CSVフォールバック。"""
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
            _report_event("ERROR", f"CSV保存に失敗: {e2}", {
                "row_head": {k: row.get(k) for k in list(row)[:6]}
            })

    try:
        if secret_json and secret_sheet_id:
            try_append_to_google_sheets(row, secret_sheet_id, secret_json, sheet_title=theme_sheet)
        else:
            _append_csv()
    except Exception as e:
        _append_csv()
        _report_event("WARN", f"Sheets保存に失敗しCSVへフォールバック: {e}", {"reason": str(e)})

# ========= ルーティング：ポータル or テーマ =========
if ROUTE["mode"] == "portal":
    render_portal()
    st.stop()

# ========= テーマ動的ロード =========
def load_theme_module(theme_name: str):
    return importlib.import_module(f"themes.{theme_name}")

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
    company, email, df_scores = theme.render_questions(st)
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
    if not text:
        return ""
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
        for label in ax.get_yticklabels():
            label.set_fontproperties(fp)
        for label in ax.get_xticklabels():
            label.set_fontproperties(fp)
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
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

# ========= PDF生成 =========
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
    bar_tmp.write(bar_png)
    bar_tmp.flush()
    elems.append(Paragraph("カテゴリ別スコア（棒グラフ）", h3))
    elems.append(Image(bar_tmp.name, width=390, height=180))
    elems.append(Spacer(1, 6))

    # 次の一手（QR右寄せ）
    elems.append(Paragraph("次の一手（90分スポット診断のご案内）", h3))
    url_par = Paragraph(f"詳細・お申込み：<u>{CTA_URL}</u>", normal)
    qr_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    qr_tmp.write(qr_png)
    qr_tmp.flush()
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

    # UI
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

    # 棒グラフ・表
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
    category_scores = {
        cat: float(df.loc[df["カテゴリ"] == cat, "平均スコア"].values[0])
        for cat in df["カテゴリ"].tolist()
    }
    category_scores_str = json.dumps(category_scores, ensure_ascii=False)

    def to_risk_level(total: float) -> str:
        if total < 2.0:
            return "高リスク"
        elif total < 3.5:
            return "中リスク"
        else:
            return "低リスク"

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

    # ▼▼ 二重書き込み防止 ▼▼
    if st.session_state.get("ai_tried") and not st.session_state.get("saved_once"):
        if st.session_state.get("dedup_key"):
            auto_save_row(row, theme_sheet=f"responses_{THEME}")
            st.session_state["saved_once"] = True
else:
    st.caption("フォームに回答し、「診断する」を押してください。")

# ========= 管理者UI =========
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


















