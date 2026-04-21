import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
import json
import re

st.set_page_config(page_title="訂單自動對轉工具", layout="centered")
st.title("📦 訂單智慧對轉工具 (終極聰明版)")

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
            if any(k in "".join(row_values) for k in ["品名", "貨號", "條碼"]):
                header_row_index = i
                found_header = True
                break
        
        if found_header:
            df_db = temp_df.iloc[header_row_index:].copy()
            df_db.columns = df_db.iloc[0]
            df_db = df_db[1:].reset_index(drop=True)
            df_db.columns = [str(c).strip() for c in df_db.columns]
            st.success("總表載入成功！")
        else:
            st.error("找不到標題列")
    except Exception as e:
        st.error(f"讀取總表失敗：{e}")

st.header("3. 上傳訂單圖片")
uploaded_file = st.file_uploader("請上傳訂單照片", type=["jpg", "jpeg", "png"])

if uploaded_file and df_db is not None and api_key:
    img = Image.open(uploaded_file)
    st.image(img, caption="上傳的訂單", width=400)
    
    if st.button("🚀 開始智慧匹配"):
        with st.spinner("AI 思考中..."):
            try:
                genai.configure(api_key=api_key)
                # 自動偵測可用模型
                models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                target_model = next((m for m in models if 'flash' in m), models[0])
                model = genai.GenerativeModel(model_name=target_model)

                prompt = """你是一個專業的訂單小幫手。請辨識圖片中訂購的產品：
                1. 產品名稱 (如: 塩雪烏龍)
                2. 度數 (請轉換成標準格式，如: 2.75, 3.00)
                3. 數量
                輸出 JSON 陣列：[{"key": "名稱", "degree": "度數", "qty": 數量}]
                只需輸出 JSON，不要囉唆。"""
                
                response = model.generate_content([prompt, img])
                json_str = re.sub(r'```json|```', '', response.text).strip()
                items = json.loads(json_str)
                
                st.write("🔍 AI 辨識到了：", items)
                
                final_results = []
                # 找到品名欄位
                name_col = next((c for c in df_db.columns if "品名" in str(c)), None)
                
                if name_col:
                    for item in items:
                        # 1. 處理品名關鍵字 (塩/鹽 容錯)
                        search_key = str(item['key']).replace('鹽', '塩')
                        # 2. 處理度數 (例如 2.75 變成 2.75)
                        try:
                            d_val = float(item['degree'])
                            d_str_standard = f"{d_val:.2f}"
                            d_str_short = str(d_val).rstrip('0').rstrip('.')
                        except:
                            d_str_standard = str(item['degree'])
                            d_str_short = d_str_standard

                        # 3. 寬鬆比對邏輯
                        # 只要 (品名包含產品關鍵字) 且 (品名包含 2.75 或 2.750) 就算中！
                        mask = (df_db[name_col].astype(str).str.contains(search_key, na=False, case=False)) & \
                               (df_db[name_col].astype(str).str.contains(d_str_standard, na=False) | 
                                df_db[name_col].astype(str).str.contains(d_str_short, na=False))
                        
                        match = df_db[mask]
                        if not match.empty:
                            res_row = match.iloc[0].to_dict()
                            res_row['訂購數量'] = item['qty']
                            final_results.append(res_row)
                        else:
                            st.warning(f"❌ 找不到：{search_key} 度數 {d_str_standard}")
                
                if final_results:
                    res_df = pd.DataFrame(final_results)
                    st.table(res_df)
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        res_df.to_excel(writer, index=False)
                    st.download_button(label="📥 下載 Excel", data=output.getvalue(), file_name="訂單結果.xlsx")
                
            except Exception as e:
                st.error(f"出錯了：{e}")
