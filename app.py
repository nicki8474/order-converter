import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
import json
import re

st.set_page_config(page_title="訂單智慧對轉工具", layout="centered")
st.title("📦 訂單智慧對轉工具 (精準欄位修正版)")

with st.sidebar:
    st.header("1. 系統設定")
    api_key = st.text_input("輸入 Gemini API Key", type="password")

st.header("2. 載入資料庫")
uploaded_db = st.file_uploader("請上傳您的「產品總表.xlsx」", type=["xlsx", "csv"])

df_db = None
if uploaded_db:
    try:
        # 強制讀取所有內容為字串，避免 float 錯誤
        if uploaded_db.name.endswith('.csv'):
            temp_df = pd.read_csv(uploaded_db, header=None, encoding_errors='ignore', dtype=str)
        else:
            temp_df = pd.read_excel(uploaded_db, header=None, dtype=str)
        
        # 尋找包含「品名」的那一行作為標題
        header_row_index = 0
        for i, row in temp_df.iterrows():
            row_content = "".join(row.fillna("").astype(str))
            if "品名" in row_content:
                header_row_index = i
                break
        
        df_db = temp_df.iloc[header_row_index:].copy()
        df_db.columns = df_db.iloc[0]
        df_db = df_db[1:].reset_index(drop=True)
        # 清除欄位名稱的空格
        df_db.columns = [str(c).strip() for c in df_db.columns]
        st.success(f"成功載入！搜尋欄位：{', '.join(df_db.columns)}")
    except Exception as e:
        st.error(f"讀取總表失敗：{e}")

st.header("3. 上傳訂單圖片")
uploaded_file = st.file_uploader("請上傳照片", type=["jpg", "jpeg", "png"])

if uploaded_file and df_db is not None and api_key:
    img = Image.open(uploaded_file)
    st.image(img, caption="上傳的訂單", width=400)
    
    if st.button("🚀 開始精準比對"):
        with st.spinner("正在執行全方位比對..."):
            try:
                genai.configure(api_key=api_key)
                models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                target_model = next((m for m in models if 'flash' in m), models[0])
                model = genai.GenerativeModel(model_name=target_model)

                prompt = """提取訂單 JSON：[{"key": "名稱", "degree": "數字", "qty": 數量}]
                注意：淨透潤, 烏龍, 白露, 紅韻, 伯爵 等。度數如 4.50。"""
                
                response = model.generate_content([prompt, img])
                json_str = re.sub(r'```json|```', '', response.text).strip()
                items = json.loads(json_str)
                
                st.write("🔍 AI 提取：", items)
                
                final_results = []
                # 這次不只找單一欄位，我們掃描「每一列」的所有文字
                for item in items:
                    key = str(item['key']).strip().replace('鹽', '塩')
                    try:
                        d_val = float(item['degree'])
                        if d_val >= 100: d_val = d_val / 100.0
                        d_search = f"{d_val:.2f}" # 您的總表通常是 4.50
                    except:
                        d_search = str(item['degree'])

                    # 【全方位掃描邏輯】
                    # 我們檢查這一列 (Row) 的「所有欄位合併起來」是否包含產品名與度數
                    def row_match(row):
                        full_text = "".join(row.astype(str))
                        # 必須包含產品核心字，且包含度數數字
                        return key in full_text and d_search in full_text

                    matched_rows = df_db[df_db.apply(row_match, axis=1)]
                    
                    if not matched_rows.empty:
                        res_row = matched_rows.iloc[0].to_dict()
                        res_row['訂購數量'] = item['qty']
                        final_results.append(res_row)
                    else:
                        st.warning(f"⚠️ 找不到：{key} 度數 {d_search}")
                
                if final_results:
                    res_df = pd.DataFrame(final_results)
                    st.subheader("✅ 轉換成果")
                    st.table(res_df)
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        res_df.to_excel(writer, index=False)
                    st.download_button(label="📥 下載 Excel", data=output.getvalue(), file_name="對轉結果.xlsx")
                
            except Exception as e:
                st.error(f"出錯了：{e}")
       
