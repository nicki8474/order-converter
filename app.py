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
        # 讀取檔案，先不設標題
        if uploaded_db.name.endswith('.csv'):
            temp_df = pd.read_csv(uploaded_db, header=None)
        else:
            temp_df = pd.read_excel(uploaded_db, header=None)
        
        # 【修正：更強大的標題列搜尋，自動跳過非字串內容】
        header_row_index = 0
        found_header = False
        for i, row in temp_df.iterrows():
            # 將整列轉為字串並過濾掉 'nan'
            row_values = [str(val) for val in row.values if pd.notna(val)]
            if any("品名" in s for s in row_values) or any("貨號" in s for s in row_values):
                header_row_index = i
                found_header = True
                break
        
        if found_header:
            # 重新設定標題
            df_db = temp_df.iloc[header_row_index:].copy()
            df_db.columns = df_db.iloc[0]
            df_db = df_db[1:].reset_index(drop=True)
            # 去除標題前後空格並過濾掉空欄位
            df_db.columns = [str(c).strip() if pd.notna(c) else f"Unnamed_{i}" for i, c in enumerate(df_db.columns)]
            st.success(f"成功載入！偵測到欄位：{', '.join([c for c in df_db.columns if 'Unnamed' not in c])}")
        else:
            st.error("在檔案中找不到包含「品名」或「貨號」的標題列，請檢查 Excel 格式。")

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
                # 找出正確的品名欄位名稱
                name_col = next((c for c in df_db.columns if "品名" in str(c)), None)
                
                if name_col:
                    for item in items:
                        # 在品名欄位搜尋關鍵字與度數
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
                    st.error("總表中找不到對應產品，請確認圖片文字與總表內容是否相符。")
            except Exception as e:
                st.error(f"執行出錯：{e}")
