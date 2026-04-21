import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
import json

# 設定頁面
st.set_page_config(page_title="訂單自動對轉工具", layout="centered")

st.title("📦 訂單自動對轉工具")
st.markdown("只需上傳圖片，自動比對總表並產出匯入檔。")

# --- 側邊欄設定 ---
with st.sidebar:
    st.header("1. 系統設定")
    api_key = st.text_input("輸入 Gemini API Key", type="password", help="請至 Google AI Studio 申請免費 Key")
    st.info("設定好後，您的同事只需打開網址即可使用。")

# --- 2. 產品總表上傳 ---
st.header("2. 載入資料庫")
uploaded_db = st.file_uploader("請上傳您的「產品總表.xlsx」", type=["xlsx", "csv"])

if uploaded_db:
    try:
        if uploaded_db.name.endswith('.csv'):
            df_db = pd.read_csv(uploaded_db)
        else:
            df_db = pd.read_excel(uploaded_db)
        # 清洗總表資料：移除空白列、設定標題
        df_db.columns = df_db.columns.str.strip()
        st.success(f"成功載入 {len(df_db)} 筆產品資料！")
    except Exception as e:
        st.error(f"讀取總表失敗：{e}")

# --- 3. 圖片上傳與辨識 ---
st.header("3. 上傳訂單圖片")
uploaded_file = st.file_uploader("請上傳或貼上手寫單圖片", type=["jpg", "jpeg", "png"])

if uploaded_file and uploaded_db and api_key:
    img = Image.open(uploaded_file)
    st.image(img, caption="待處理訂單", width=400)
    
    if st.button("🚀 開始自動轉換"):
        with st.spinner("AI 正在辨識並匹配總表貨號..."):
            try:
                # 配置 AI
                genai.configure(api_key=api_key, transport='rest')
model = genai.GenerativeModel(model_name="models/gemini-1.5-flash-latest")
                
                # 圖片辨識
                prompt = """
                你是一個訂單處理專家。請辨識圖片中的內容，輸出成 JSON 陣列。
                格式必須為：[{"key": "品名關鍵字", "degree": "度數", "qty": 數量}]
                例如：[{"key": "塩雪烏龍", "degree": "2.75", "qty": 1}]
                """
                response = model.generate_content([prompt, img])
                
                # 解析 AI 回傳內容
                clean_json = response.text.replace('```json', '').replace('```', '').strip()
                items = json.loads(clean_json)
                
                # --- 自動比對邏輯 ---
                final_results = []
                for item in items:
                    # 在總表中搜尋：品名同時包含「關鍵字」與「度數」
                    match = df_db[
                        (df_db['品名'].str.contains(str(item['key']), na=False)) & 
                        (df_db['品名'].str.contains(str(item['degree']), na=False))
                    ]
                    
                    if not match.empty:
                        res_row = match.iloc[0].to_dict()
                        res_row['數量'] = item['qty']
                        final_results.append(res_row)
                
                # 產出結果表格
                if final_results:
                    res_df = pd.DataFrame(final_results)
                    st.subheader("✅ 轉換結果預覽")
                    st.table(res_df)
                    
                    # 轉為 Excel 下載
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        res_df.to_excel(writer, index=False, sheet_name='訂單匯入')
                    
                    st.download_button(
                        label="📥 下載轉單 Excel",
                        data=output.getvalue(),
                        file_name="訂單匯入結果.xlsx",
                        mime="application/vnd.ms-excel"
                    )
                else:
                    st.error("抱歉，辨識出的產品在總表中找不到對應貨號。")
                    
            except Exception as e:
                st.error(f"執行出錯：{e}")
