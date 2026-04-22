import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
import json
import re

st.set_page_config(page_title="萬能訂單對轉工具", layout="wide")
st.title("📦 萬能訂單對轉工具")

# --- 1. API Key ---
api_key = st.secrets.get("GEMINI_API_KEY", "")
with st.sidebar:
    st.header("設定")
    if api_key:
        st.success("✅ API 已就緒")
    else:
        api_key = st.text_input("請輸入 API Key", type="password")

# --- 2. 智慧載入總表 ---
st.header("2. 載入產品總表")
uploaded_db = st.file_uploader("上傳總表 (Excel/CSV)", type=["xlsx", "csv"], key="db_loader")

df_db = None
if uploaded_db:
    try:
        if uploaded_db.name.endswith('.csv'):
            temp_df = pd.read_csv(uploaded_db, header=None, dtype=str).fillna("")
        else:
            temp_df = pd.read_excel(uploaded_db, header=None, dtype=str).fillna("")
        
        # 智慧尋找標題行
        header_row = 0
        for i, row in temp_df.iterrows():
            row_txt = "".join(row.astype(str))
            if "品名" in row_txt or "貨號" in row_txt:
                header_row = i
                break
        df_db = temp_df.iloc[header_row:].copy()
        df_db.columns = df_db.iloc[0]
        df_db = df_db[1:].reset_index(drop=True)
        st.success(f"✅ 資料庫載入成功")
    except Exception as e:
        st.error(f"讀取失敗: {e}")

# --- 3. 混合輸入區 ---
st.header("3. 輸入訂單內容")

# 這裡設計三合一介面
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("🖼️ 圖片輸入 (支援直接貼上)")
    st.markdown("""
    <div style="border:2px dashed #00a0ff; padding:15px; border-radius:10px; background-color:#e1f5fe; margin-bottom:10px;">
        <strong>快速貼圖說明：</strong><br>
        1. 截圖客戶手寫單或 Line 畫面<br>
        2. 點擊下方 <b>「在此按 Ctrl+V」</b> 框框<br>
        3. 直接按 <b>Ctrl + V</b>
    </div>
    """, unsafe_allow_html=True)
    # 使用 chat_input 作為最強力貼圖接收器
    img_paste = st.chat_input("在此按 Ctrl+V 貼上訂單截圖...")
    
    # 保留手動上傳
    img_manual = st.file_uploader("或手動選擇圖片檔案", type=["jpg", "png", "jpeg"], label_visibility="collapsed")

with col2:
    st.subheader("✍️ 文字輸入")
    text_input = st.text_area("直接在此貼上訂單文字內容", placeholder="例如：\n淨透潤 450*12\n茉莉暮灰 325*1", height=215)

# --- 整合輸入源 ---
input_content = None
input_type = None

if img_manual:
    input_content = Image.open(img_manual)
    input_type = "image"
elif img_paste:
    # 在某些 Streamlit 版本，chat_input 貼圖會直接變成文字描述或物件
    # 我們讓 AI 去嘗試解析這個輸入
    input_content = img_paste
    input_type = "text" 
elif text_input:
    input_content = text_input
    input_type = "text"

# 如果是有圖片，顯示縮圖確認
if input_type == "image":
    st.image(input_content, caption="✅ 圖片讀取成功", width=300)

# --- 4. 智慧執行 ---
if input_content and df_db is not None and api_key:
    if st.button("🚀 開始自動轉單", use_container_width=True):
        with st.spinner("AI 正在解析您的訂單並學習總表格式..."):
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel('gemini-1.5-flash')
                
                # 提示詞強化：要求 AI 自動識別度數格式 (不管是 4.50 還是 450)
                prompt = """
                你是一個訂單提取專家。請從訂單內容（圖片或文字）中提取產品名稱、度數、數量。
                注意：
                1. 產品名稱請抓取關鍵字。
                2. 度數請統一轉換為「數字」，若看到450度請寫4.50。
                3. 請輸出 JSON 陣列格式：[{"key":"產品關鍵字", "degree":"度數", "qty":數量}]。
                4. 只輸出 JSON，不要有其他文字。
                """
                
                if input_type == "image":
                    response = model.generate_content([prompt, input_content])
                else:
                    response = model.generate_content(prompt + f"\n內容：{input_content}")
                
                # 清洗 JSON
                clean_json = re.search(r'\[.*\]', response.text, re.DOTALL).group()
                items = json.loads(clean_json)
                
                final_results = []
                for item in items:
                    k = str(item.get('key','')).strip().replace('鹽', '塩')
                    try:
                        # 智慧換算度數：相容 4.50, 4.5, 450
                        d_str = str(item.get('degree','')).replace("度","").replace("-","")
                        d_val = float(d_str)
                        if d_val >= 100: d_val /= 100.0
                        
                        v2 = f"{d_val:.2f}"
                        v1 = f"{d_val:.1f}"
                        v0 = str(int(round(d_val * 100)))
                    except:
                        v2 = v1 = v0 = str(item.get('degree',''))

                    def match_row(row):
                        t = "".join(row.astype(str)).replace("-","").replace(" ","")
                        # 只要品名對，且度數符合任何一種寫法就中
                        return k in t and (v2 in t or v1 in t or v0 in t)

                    match = df_db[df_db.apply(match_row, axis=1)]
                    if not match.empty:
                        res = match.iloc[0].to_dict()
                        res['訂購數量'] = item.get('qty', 0)
                        final_results.append(res)
                    else:
                        st.warning(f"🔍 AI 辨識出「{k} / {v2}」，但目前的總表中找不到吻合項。")

                if final_results:
                    st.subheader("✅ 轉換結果")
                    res_df = pd.DataFrame(final_results)
                    st.dataframe(res_df, use_container_width=True)
                    
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        res_df.to_excel(writer, index=False)
                    st.download_button("📥 下載轉單 Excel", output.getvalue(), "轉單結果.xlsx", use_container_width=True)
                
            except Exception as e:
                st.error(f"執行出錯: {e}")
