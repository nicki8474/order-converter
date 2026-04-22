import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
import json
import re

# 1. 網頁基本設定
st.set_page_config(page_title="訂單智慧對轉工具", layout="centered")
st.title("📦 訂單智慧對轉工具 (多功能輸入版)")

# --- 安全讀取 Key ---
api_key = st.secrets.get("GEMINI_API_KEY", "")

with st.sidebar:
    st.header("1. 系統設定")
    if api_key:
        st.success("✅ 系統已就緒")
    else:
        api_key = st.text_input("輸入 Gemini API Key", type="password")

# --- 2. 產品總表上傳 ---
st.header("2. 載入資料庫")
uploaded_db = st.file_uploader("第一步：請上傳「產品總表」", type=["xlsx", "csv"])

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

# --- 3. 混合模式輸入 ---
st.header("3. 輸入訂單內容")
st.info("💡 您可以選擇：(1) 直接貼上圖片檔案到下方 (2) 上傳檔案 (3) 在文字框貼上訂單文字")

# 建立分頁標籤：圖片輸入 或 文字輸入
tab1, tab2 = st.tabs(["🖼️ 圖片/貼上圖片", "✍️ 貼上文字內容"])

input_content = None
input_type = None

with tab1:
    # Streamlit 的 file_uploader 支援直接在選取框上按 Ctrl+V 貼上圖片檔案
    uploaded_file = st.file_uploader("將圖片拖曳至此、點選上傳，或點此處後按 Ctrl+V 貼上", type=["jpg", "jpeg", "png"])
    if uploaded_file:
        input_content = Image.open(uploaded_file)
        input_type = "image"
        st.image(input_content, caption="待處理訂單圖片", width=300)

with tab2:
    text_input = st.text_area("請直接在此貼上訂單文字 (例如：淨透潤 450x12, 烏龍 550x1)", height=150)
    if text_input:
        input_content = text_input
        input_type = "text"

# --- 4. 執行辨識與比對 ---
if input_content and df_db is not None and api_key:
    if st.button("🚀 開始自動轉單"):
        with st.spinner("AI 處理中..."):
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel("gemini-1.5-flash")

                # 根據輸入類型調整 Prompt
                if input_type == "image":
                    prompt = "提取訂單：產品名關鍵字、度數(數字)、數量。只需輸出 JSON 陣列，不需解釋。"
                    source = [prompt, input_content]
                else:
                    prompt = f"請從以下文字提取訂單：{input_content}。格式：[{{\"key\": \"產品關鍵字\", \"degree\": \"度數\", \"qty\": 數量}}]。只需輸出 JSON 陣列。"
                    source = [prompt]

                response = model.generate_content(source)
                json_str = re.sub(r'```json|```', '', response.text).strip()
                items = json.loads(json_str)
                
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
                    st.download_button(label="📥 下載轉單 Excel", data=output.getvalue(), file_name="訂單結果.xlsx")
                else:
                    st.warning("⚠️ 找不到對應產品。")

            except Exception as e:
                if "429" in str(e):
                    st.error("❌ 今日免費額度已用完。")
                else:
                    st.error(f"出錯了：{e}")
