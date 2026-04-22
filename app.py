import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
import json
import re

st.set_page_config(page_title="訂單智慧對轉工具", layout="centered")
st.title("📦 訂單智慧對轉工具")

# --- 安全讀取 Key ---
api_key = st.secrets.get("GEMINI_API_KEY", "")

with st.sidebar:
    st.header("1. 系統設定")
    if api_key:
        st.success("✅ 系統已就緒")
    else:
        api_key = st.text_input("輸入 Gemini API Key", type="password")

st.header("2. 載入資料庫")
uploaded_db = st.file_uploader("第一步：上傳產品總表", type=["xlsx", "csv"])

df_db = None
if uploaded_db:
    try:
        if uploaded_db.name.endswith('.csv'):
            temp_df = pd.read_csv(uploaded_db, header=None, encoding_errors='ignore', dtype=str)
        else:
            temp_df = pd.read_excel(uploaded_db, header=None, dtype=str)
        header_row_index = 0
        for i, row in temp_df.iterrows():
            row_content = "".join([str(x) for x in row.fillna("").values])
            if "品名" in row_content:
                header_row_index = i
                break
        df_db = temp_df.iloc[header_row_index:].copy()
        df_db.columns = df_db.iloc[0]
        df_db = df_db[1:].reset_index(drop=True)
        df_db.columns = [str(c).strip() for c in df_db.columns]
        st.success("✅ 總表載入成功")
    except Exception as e:
        st.error(f"讀取失敗：{e}")

st.header("3. 上傳訂單圖片")
uploaded_file = st.file_uploader("第二步：上傳訂單照片", type=["jpg", "jpeg", "png"])

if uploaded_file and df_db is not None and api_key:
    img = Image.open(uploaded_file)
    st.image(img, caption="上傳的訂單", width=400)
    
    if st.button("🚀 開始自動轉單"):
        with st.spinner("AI 辨識中..."):
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel("gemini-1.5-flash") # 固定模型名稱減少錯誤

                prompt = "提取訂單：產品名核心字、度數(數字)、數量。只需輸出 JSON 陣列，不需任何解釋。"
                
                response = model.generate_content([prompt, img])
                json_str = re.sub(r'```json|```', '', response.text).strip()
                items = json.loads(json_str)
                
                # --- 這裡絕對沒有 st.write(items) ---
                
                final_results = []
                for item in items:
                    key = str(item['key']).strip().replace('鹽', '塩')
                    try:
                        d_val = float(item['degree'])
                        if d_val >= 100: d_val = d_val / 100.0
                        d_search = f"{d_val:.2f}"
                        d_search_alt = f"{d_val:.1f}"
                    except:
                        d_search = str(item['degree'])
                        d_search_alt = d_search

                    def row_match(row):
                        full_text = "".join(row.fillna("").astype(str))
                        return key in full_text and (d_search in full_text or d_search_alt in full_text)

                    matched_rows = df_db[df_db.apply(row_match, axis=1)]
                    if not matched_rows.empty:
                        res_row = matched_rows.iloc[0].to_dict()
                        res_row['訂購數量'] = item['qty']
                        final_results.append(res_row)
                
                if final_results:
                    res_df = pd.DataFrame(final_results)
                    st.subheader("✅ 轉換結果")
                    st.table(res_df)
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        res_df.to_excel(writer, index=False)
                    st.download_button(label="📥 下載轉單 Excel", data=output.getvalue(), file_name="結果.xlsx")
                else:
                    st.warning("⚠️ 找不到對應產品，請確認總表內容。")

            except Exception as e:
                if "429" in str(e):
                    st.error("❌ 今日免費額度(20次)已用完！請明天再試，或更換 API Key。")
                else:
                    st.error(f"出錯了：{e}")
