import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
import json
import re

st.set_page_config(page_title="訂單智慧對轉工具", layout="centered")
st.title("📦 訂單智慧對轉工具 (格式對應強化版)")

with st.sidebar:
    st.header("1. 系統設定")
    api_key = st.text_input("輸入 Gemini API Key", type="password")

st.header("2. 載入資料庫")
uploaded_db = st.file_uploader("請上傳您的「產品總表.xlsx」", type=["xlsx", "csv"])

df_db = None
if uploaded_db:
    try:
        # 強制讀取並處理空值
        if uploaded_db.name.endswith('.csv'):
            temp_df = pd.read_csv(uploaded_db, header=None, encoding_errors='ignore')
        else:
            temp_df = pd.read_excel(uploaded_db, header=None)
        
        # 修正尋找標題列的邏輯，避免 float 報錯
        header_row_index = 0
        for i, row in temp_df.iterrows():
            row_str = "".join([str(x) for x in row.values if pd.notna(x)])
            if "品名" in row_str:
                header_row_index = i
                break
        
        df_db = temp_df.iloc[header_row_index:].copy()
        df_db.columns = df_db.iloc[0]
        df_db = df_db[1:].reset_index(drop=True)
        df_db.columns = [str(c).strip() for c in df_db.columns]
        st.success(f"總表載入成功！偵測到欄位：{', '.join(df_db.columns)}")
    except Exception as e:
        st.error(f"讀取總表失敗：{e}")

st.header("3. 上傳訂單圖片")
uploaded_file = st.file_uploader("請上傳訂單照片", type=["jpg", "jpeg", "png"])

if uploaded_file and df_db is not None and api_key:
    img = Image.open(uploaded_file)
    st.image(img, caption="上傳的訂單", width=400)
    
    if st.button("🚀 開始精準匹配"):
        with st.spinner("正在對照總表品名結構..."):
            try:
                genai.configure(api_key=api_key)
                models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                target_model = next((m for m in models if 'flash' in m), models[0])
                model = genai.GenerativeModel(model_name=target_model)

                prompt = """你是一個訂單專家。請從圖中提取：
                1. 產品核心名 (如: 淨透潤, 烏龍, 伯爵, 白露, 紅韻)
                2. 度數 (如果是450請輸出4.50)
                3. 數量
                輸出 JSON：[{"key": "產品名", "degree": "度數", "qty": 數量}]"""
                
                response = model.generate_content([prompt, img])
                json_str = re.sub(r'```json|```', '', response.text).strip()
                items = json.loads(json_str)
                
                st.write("🔍 AI 提取內容：", items)
                
                final_results = []
                # 您的總表品名欄位名稱通常叫 '品名'
                name_col = next((c for c in df_db.columns if "品名" == str(c) or "品名" in str(c)), None)
                
                if name_col:
                    for item in items:
                        key = str(item['key']).strip().replace('鹽', '塩')
                        try:
                            d_val = float(item['degree'])
                            if d_val >= 100: d_val = d_val / 100.0
                            # 針對您的總表格式：度數通常在最前面且帶兩位小數 (如 4.50)
                            d_search = f"{d_val:.2f}"
                        except:
                            d_search = str(item['degree'])

                        # 【最終暴力比對邏輯】
                        # 您的格式是 "4.50 OPT PURE淨透潤..."
                        # 所以我們找：品名開頭是度數，且中間包含產品關鍵字
                        mask = (df_db[name_col].astype(str).str.contains(d_search, na=False)) & \
                               (df_db[name_col].astype(str).str.contains(key, na=False, case=False))
                        
                        match = df_db[mask]
                        
                        if not match.empty:
                            res_row = match.iloc[0].to_dict()
                            res_row['訂購數量'] = item['qty']
                            final_results.append(res_row)
                        else:
                            st.warning(f"⚠️ 找不到：度數 {d_search} 產品 {key}")
                
                if final_results:
                    res_df = pd.DataFrame(final_results)
                    st.subheader("✅ 轉換成功")
                    st.table(res_df)
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        res_df.to_excel(writer, index=False)
                    st.download_button(label="📥 下載 Excel", data=output.getvalue(), file_name="對轉結果.xlsx")
                
            except Exception as e:
                st.error(f"出錯了：{e}")
