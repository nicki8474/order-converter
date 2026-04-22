import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
import json
import re

st.set_page_config(page_title="智慧訂單工具", layout="wide")
st.title("📦 智慧訂單轉單 (自動校正版)")

# --- 1. API 設定 ---
api_key = st.secrets.get("GEMINI_API_KEY", "")
if not api_key:
    api_key = st.sidebar.text_input("輸入 API Key", type="password")

# --- 2. 載入總表 ---
uploaded_db = st.file_uploader("上傳總表 (Excel/CSV)", type=["xlsx", "csv"])
df_db = None
all_product_keywords = ""

if uploaded_db:
    try:
        df_db = pd.read_excel(uploaded_db) if uploaded_db.name.endswith('xlsx') else pd.read_csv(uploaded_db)
        # 這裡假設你的總表有 '品名' 這一欄
        all_product_keywords = ", ".join(df_db['品名'].astype(str).unique())
        st.success("✅ 總表已載入，AI 已學習品名清單")
    except:
        st.error("讀取失敗，請檢查格式")

# --- 3. 輸入與按鈕 ---
img_file = st.file_uploader("上傳訂單圖片", type=["jpg", "png", "jpeg"])

if st.button("🚀 開始智慧辨識", use_container_width=True):
    if api_key and df_db is not None and img_file:
        with st.spinner("AI 正在校對手寫字..."):
            try:
                genai.configure(api_key=api_key)
                # 使用最穩定的模型呼叫方式
                model = genai.GenerativeModel('gemini-1.5-flash')
                
                # 將總表品名餵給 AI，讓它做「智慧修正」
                prompt = f"""
                你是一個訂單辨識助手。
                【已知產品清單】：{all_product_keywords}
                
                【任務】：
                1. 辨識圖片中的產品、度數、數量。
                2. 重要：若圖片手寫字模糊，請比對「已知產品清單」，修正為清單中正確的名稱。
                   (例如：可泳棟 -> 可沐棕)
                3. 輸出 JSON：[{"key":"品名","degree":"度數","qty":數量}]。
                """
                
                response = model.generate_content([prompt, Image.open(img_file)])
                
                # 獲取 JSON
                json_str = re.search(r'\[.*\]', response.text, re.DOTALL).group()
                items = json.loads(json_str)
                
                # 顯示結果並提供下載 (保留你之前的比對邏輯)
                st.write("### 辨識結果 (已自動校正)")
                st.table(items)
                
            except Exception as e:
                st.error(f"錯誤: {e}")
    else:
        st.warning("請確保 API Key、總表、圖片都已就緒")
