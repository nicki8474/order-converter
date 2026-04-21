import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
import json
import re

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
        if uploaded_db.name.endswith('.csv'):
            temp_df = pd.read_csv(uploaded_db, header=None)
        else:
            temp_df = pd.read_excel(uploaded_db, header=None)
        
        header_row_index = 0
        found_header = False
        for i, row in temp_df.iterrows():
            row_values = [str(val) for val in row.values if pd.notna(val)]
            if any("品名" in s for s in row_values) or any("貨號" in s for s in row_values):
                header_row_index = i
                found_header = True
                break
        
        if found_header:
            df_db = temp_df.iloc[header_row_index:].copy()
            df_db.columns = df_db.iloc[0]
            df_db = df_db[1:].reset_index(drop=True)
            df_db.columns = [str(c).strip() for c in df_db.columns]
            st.success(f"總表載入成功！")
        else:
            st.error("找不到標題列")
    except Exception as e:
        st.error(f"讀取總表失敗：{e}")

st.header("3. 上傳訂單圖片")
uploaded_file = st.file_uploader("請上傳圖片", type=["jpg", "jpeg", "png"])

if uploaded_file and df_db is not None and api_key:
    img = Image.open(uploaded_file)
    st.image(img, caption="待處理訂單", width=400)
    
    if st.button("🚀 開始自動轉換"):
        with st.spinner("AI 辨識與匹配中..."):
            try:
                genai.configure(api_key=api_key)
                models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                target_model_name = next((m for m in models if 'flash' in m), models[0])
                model = genai.GenerativeModel(model_name=target_model_name)
                
                # 強調格式，避免 AI 亂回
                prompt = """請精確辨識圖片中訂單，輸出 JSON 陣列：
                [{"key": "品名關鍵字", "degree": "度數數字", "qty": 數量}]
                例如：[{"key": "塩雪烏龍", "degree": "2.75", "qty": 1}]
                只需輸出純 JSON，不要 Markdown。"""
                
                response = model.generate_content([prompt, img])
                raw_text = re.sub(r'```json|```', '', response.text).strip()
                items = json.loads(raw_text)
                
                # 在網頁上顯示 AI 辨識到的內容，方便除錯
                st.write("🔍 AI 辨識內容：", items)
                
                final_results = []
                name_col = next((c for c in df_db.columns if "品名" in str(c)), None)
                
                if name_col:
                    for item in items:
                        key = str(item['key']).strip()
                        # 將度數轉為浮點數再轉字串，統一 2.75 與 2.750 的問題
                        try:
                            deg_val = f"{float(item['degree']):.2f}"
                        except:
                            deg_val = str(item['degree']).strip()

                        # 模糊比對：品名欄位包含關鍵字 且 包含度數
                        mask = (df_db[name_col].astype(str).str.contains(key, na=False)) & \
                               (df_db[name_col].astype(str).str.contains(deg_val.replace('.00',''), na=False) | 
                                df_db[name_col].astype(str).str.contains(deg_val, na=False))
                        
                        match = df_db[mask]
                        
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
                    st.error("❌ 比對失敗：AI 辨識到了文字，但在總表中找不到完全符合的品名與度數。請檢查總表「品名」欄位是否包含這些字眼。")
            except Exception as e:
                st.error(f"執行出錯：{e}")
