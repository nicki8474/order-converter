import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
import json

st.set_page_config(page_title="訂單自動對轉工具", layout="centered")
st.title("📦 訂單自動對轉工具")

with st.sidebar:
    st.header("1. 系統設定")
    api_key = st.text_input("輸入 Gemini API Key", type="password")

st.header("2. 載入資料庫")
uploaded_db = st.file_uploader("請上傳您的「產品總表.xlsx」", type=["xlsx", "csv"])

df_db = None
if uploaded_db:
    try:
        # 讀取檔案
        if uploaded_db.name.endswith('.csv'):
            temp_df = pd.read_csv(uploaded_db, header=None)
        else:
            temp_df = pd.read_excel(uploaded_db, header=None)
        
        # 【修正：自動尋找正確的標題列】
        header_row_index = 0
        for i, row in temp_df.iterrows():
            row_str = row.astype(str).values
            if any("品名" in s for s in row_str) or any("貨號" in s for s in row_str):
                header_row_index = i
                break
        
        # 重新設定正確的標題
        df_db = temp_df.iloc[header_row_index:].copy()
        df_db.columns = df_db.iloc[0]
        df_db = df_db[1:].reset_index(drop=True)
        df_db.columns = df_db.columns.str.strip() # 去除空白
        
        st.success(f"成功載入！偵測到標題欄位：{', '.join(df_db.columns.astype(str))}")
    except Exception as e:
        st.error(f"讀取總表失敗：{e}")

st.header("3. 上傳訂單圖片")
uploaded_file = st.file_uploader("請上傳或貼上手寫單圖片", type=["jpg", "jpeg", "png"])

if uploaded_file and df_db is not None and api_key:
    img = Image.open(uploaded_file)
    st.image(img, caption="待處理訂單", width=400)
    
    if st.button("🚀 開始自動轉換"):
        with st.spinner("AI 辨識中..."):
            try:
                genai.configure(api_key=api_key)
                models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                target_model_name = next((m for m in models if 'flash' in m), models[0])
                model = genai.GenerativeModel(model_name=target_model_name)
                
                prompt = """辨識圖片產品、度數、數量。
                輸出純 JSON 陣列：[{"key": "品名關鍵字", "degree": "度數", "qty": 數量}]
                例如：[{"key": "塩雪烏龍", "degree": "2.75", "qty": 1}]"""
                
                response = model.generate_content([prompt, img])
                raw_text = response.text.replace('```json', '').replace('```', '').strip()
                items = json.loads(raw_text)
                
                final_results = []
                for item in items:
                    # 智慧搜尋：不分大小寫，且同時包含品名關鍵字與度數
                    # 這裡自動偵測欄位名稱，防止又是 KeyError
                    name_col = next((c for c in df_db.columns if "品名" in str(c)), None)
                    
                    if name_col:
                        match = df_db[
                            (df_db[name_col].astype(str).str.contains(str(item['key']), na=False)) & 
                            (df_db[name_col].astype(str).str.contains(str(item['degree']), na=False))
                        ]
                        
                        if not match.empty:
                            res_row = match.iloc[0].to_dict()
                            res_row['訂購數量'] = item['qty']
                            final_results.append(res_row)
                
                if final_results:
                    res_df = pd.DataFrame(final_results)
                    st.subheader("✅ 轉換結果")
                    st.table(res_df)
                    
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        res_df.to_excel(writer, index=False)
                    st.download_button(label="📥 下載轉單 Excel", data=output.getvalue(), file_name="訂單結果.xlsx")
                else:
                    st.error("總表中找不到對應產品。")
            except Exception as e:
                st.error(f"執行出錯：{e}")
