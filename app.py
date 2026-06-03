import streamlit as st
import fitz  # PyMuPDF
import os
import re

# --- 設定 ---
PDF_FILE = "kyoutsu_shiyousho_r8.pdf"

st.set_page_config(page_title="仕様書高度検索システム", layout="wide")

# 💡【ベース辞書】略称で検索したいものや、特に最優先で出したいものを登録
BASE_SOUSOKU_MAP = {
    "適用": {"code": "1-1-1-1", "name": "第1編 第1章 第1節 第1条 [適用]"},
    "用語": {"code": "1-1-1-2", "name": "第1編 第1章 第1節 第2条 [用語の定義]"},
    "施工計画書": {"code": "1-1-1-6", "name": "第1編 第1章 第1節 第6条 [施工計画書]"},
    "履行報告": {"code": "1-1-1-28", "name": "第1編 第1章 第1節 第28条 [履行報告]"},
    "安全": {"code": "1-1-1-31", "name": "第1編 第1章 第1節 第31条 [工事中の安全確保]"},
    "ダンプ": {"code": "1-1-1-37", "name": "第1編 第1章 第1節 第37条 [交通安全管理]"},
    "コルゲートパイプ": {"code": "2-2-5-15", "name": "第2編 第2章 第5節 第15条 [コルゲートパイプ]"},
    "トンネル工": {"code": "10-16-26", "name": "第10編 第16章 第26節 [トンネル工]"}
}

@st.cache_data
def load_sousoku_map_automatically(file_path):
    """
    第1編〜第10編までの数千項目をPDFの全ページから自動で読み込んで辞書化する最強機能
    """
    auto_map = BASE_SOUSOKU_MAP.copy()
    if not os.path.exists(file_path):
        return auto_map

    try:
        doc = fitz.open(file_path)
        
        # PDFの全ページから「10-16-26-1 トンネル工」のような文字列をすべて探して登録する
        for page_num in range(len(doc)):
            text = doc[page_num].get_text("text")
            # 正規表現で「数字-数字-数字-数字」から始まる行を抽出
            matches = re.findall(r'^(\d{1,2}-\d{1,2}-\d{1,2}-\d{1,3})[\s　]+([^\n]+)', text, re.MULTILINE)
            
            for match in matches:
                code = match[0]
                name = match[1].strip()
                
                # 長すぎる文章や、どの章にもある「一般事項」などの重複を除外してスッキリさせる
                if name and len(name) <= 20 and name not in auto_map and name != "一般事項":
                    auto_map[name] = {"code": code, "name": f"{code} [{name}]"}
                    
        doc.close()
    except Exception as e:
        pass
    
    return auto_map

# アプリ起動時に数千件のハイブリッド辞書を生成（キャッシュされるので読み込みは初回の一瞬だけ）
SOUSOKU_MAP = load_sousoku_map_automatically(PDF_FILE)

PROCEDURE_COLORS = {
    "協議": "#ffcccc", "承諾": "#ffedcc", "指示": "#cce6ff", "提出": "#ccffcc",
    "提示": "#e6ccff", "報告": "#ffffcc", "通知": "#ffccff", "連絡": "#d9d9d9",
}

def highlight_text_html(text):
    if not text:
        return ""
    for word, color in PROCEDURE_COLORS.items():
        if word in text:
            badge = f'<span style="background-color:{color}; padding:2px 6px; border-radius:4px; font-weight:bold; color:black;">{word}</span>'
            text = text.replace(word, badge)
    return text

@st.cache_data
def search_pdf(keyword1, target_sousoku_code, file_path):
    results = []
    if not os.path.exists(file_path):
        return results, f"エラー: `{file_path}` が見つかりません。"

    try:
        doc = fitz.open(file_path)
    except Exception as e:
        return results, str(e)

    # 1. 目次から検索
    toc = doc.get_toc()
    for item in toc:
        lvl, title, page = item
        match1 = keyword1 and (keyword1 in title)
        match_sousoku = target_sousoku_code and (target_sousoku_code in title)
        
        if match1 or match_sousoku:
            score = 100 if match_sousoku else 50
            results.append({"type": "目次", "page": page, "text": title, "score": score})

    # 2. 本文から検索
    for page_num in range(len(doc)):
        page = doc[page_num]
        
        match1 = keyword1 and page.search_for(keyword1)
        match_sousoku = target_sousoku_code and page.search_for(target_sousoku_code)
        
        if match1 or match_sousoku:
            text = page.get_text("text")
            lines = text.split('\n')
            snippet = ""
            
            target_line_kw = keyword1 if match1 else target_sousoku_code
            for line in lines:
                if target_line_kw in line:
                    snippet = line.strip()
                    break
            
            results.append({
                "type": "本文",
                "page": page_num + 1,
                "text": snippet[:80] + "..." if len(snippet) > 80 else snippet,
                "score": 10
            })

    doc.close()
    
    results = sorted(results, key=lambda x: (-x["score"], x["page"]))
    
    unique_results = []
    seen_pages = set()
    for r in results:
        if r["page"] not in seen_pages:
            unique_results.append(r)
            seen_pages.add(r["page"])
            
    return unique_results, None

def get_page_image_with_highlight(file_path, page_num, kw1, sousoku_code):
    doc = fitz.open(file_path)
    page = doc[page_num - 1]
    
    search_words = [kw1, sousoku_code]
    for kw in search_words:
        if kw:
            rects = page.search_for(kw)
            for rect in rects:
                page.add_highlight_annot(rect)
    
    mat = fitz.Matrix(2, 2)
    pix = page.get_pixmap(matrix=mat)
    img_bytes = pix.tobytes("png")
    doc.close()
    return img_bytes

# --- UI構築 ---
st.title("🚀 共通仕様書 高度検索・閲覧システム（現場DX版）")

if "selected_page" not in st.session_state:
    st.session_state.selected_page = None

col1, col2 = st.columns([1, 1.5])

with col1:
    st.subheader("🔍 条件検索")
    
    kw1 = st.text_input("検索キーワードを入力", placeholder="例: トンネル工、舗装打換え工、コルゲートパイプ")
    
    st.subheader("📚 関連基準・総則")
    target_sousoku_code = ""
    target_sousoku_name = ""
    
    if kw1:
        # 💡【検索の賢さアップ】完全一致を先に探し、無ければ部分一致で探す
        matched_key = None
        if kw1 in SOUSOKU_MAP:
            matched_key = kw1
        else:
            for k in SOUSOKU_MAP.keys():
                if kw1 in k:
                    matched_key = k
                    break
        
        if matched_key:
            target_sousoku_code = SOUSOKU_MAP[matched_key]["code"]
            target_sousoku_name = SOUSOKU_MAP[matched_key]["name"]
            st.info(f"💡 最適な基準: **{target_sousoku_name}**")
        else:
            st.write("特定の基準指定はありません。（仕様書全体から検索します）")
    else:
        st.write("上にキーワードを入力すると、関連する基準・総則がここに表示されます。")
    
    st.caption(f"💡 現在の自動学習済・基準項目数: {len(SOUSOKU_MAP)} 件 / 重要な手続き文言は自動で色分けされます：")
    legend_html = "".join([f'<span style="background-color:{c};padding:2px 5px;margin-right:5px;border-radius:3px;font-size:11px;color:black;font-weight:bold;">{w}</span>' for w, c in PROCEDURE_COLORS.items()])
    st.markdown(legend_html, unsafe_allow_html=True)
    st.divider()

    if kw1:
        with st.spinner("仕様書をスキャン中..."):
            results, error = search_pdf(kw1, target_sousoku_code, PDF_FILE)
        
        if error:
            st.error(error)
        elif not results:
            st.warning("該当項目が見つかりませんでした。")
        else:
            st.success(f"関連箇所が {len(results)} 件見つかりました。")
            
            for i, res in enumerate(results):
                if target_sousoku_code and target_sousoku_code in res['text']:
                    st.markdown(f"🌟 **【基準】 {target_sousoku_name} （P.{res['page']}）**")
                else:
                    st.markdown(f"📁 **[{res['type']}] ページ {res['page']}**")
                
                highlighted_text = highlight_text_html(res['text'])
                st.markdown(f'<p style="font-size:13px; color:#555; margin-left:15px;">{highlighted_text}</p>', unsafe_allow_html=True)
                
                if st.button(f"📖 P.{res['page']} を開く", key=f"btn_{i}"):
                    st.session_state.selected_page = res['page']
                st.divider()

with col2:
    st.subheader("📖 仕様書プレビュー")
    if st.session_state.selected_page is not None:
        st.info(f"表示中: **{st.session_state.selected_page} ページ目** （検索キーワードは黄色くハイライトされています）")
        
        img_bytes = get_page_image_with_highlight(PDF_FILE, st.session_state.selected_page, kw1, target_sousoku_code)
        st.image(img_bytes, use_container_width=True)
    else:
        st.write("左側の検索結果から「開く」ボタンを押すと、ここに蛍光ペンが引かれた仕様書が表示されます。")