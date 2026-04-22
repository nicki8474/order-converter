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

# --- 3. 混合模式輸入 (改進版) ---
st.header("3. 輸入訂單內容")

tab1, tab2, tab3 = st.tabs(["📋 直接貼上圖片", "📁 上傳檔案", "✍️ 貼上文字"])

input_content = None
input_type = None

with tab1:
    st.write("請點擊下方框框後，直接按 **Ctrl + V**：")
    # 使用 paste_buffer 邏輯或簡單提示
    paste_img = st.chat_input("在這一列按 Ctrl+V 貼上圖片 (或是輸入文字也可)")
    # 這裡我們用一個小技巧：雖然 chat_input 是輸入文字，但有些瀏覽器支援直接貼圖
    # 如果 chat_input 不行，我們回歸最穩定的：
    uploaded_paste = st.file_uploader("點一下這裡再按 Ctrl + V", type=["jpg", "jpeg", "png"], label_visibility="collapsed")
    if uploaded_paste:
        input_content = Image.open(uploaded_paste)
        input_type = "image"
        st.image(input_content, caption="已偵測到貼上的圖片", width=300)

with tab2:
    uploaded_file = st.file_uploader("選擇訂單檔案", type=["jpg", "jpeg", "png"])
    if uploaded_file:
        input_content = Image.open(uploaded_file)
        input_type = "image"
        st.image(input_content, width=300)

with tab3:
    text_input = st.text_area("直接貼上訂單文字", height=150)
    if text_input:
        input_content = text_input
        input_type = "text"

# --- 4. 執行與比對 ---
if input_content and df_db is not None and api_key:
    if st.button("🚀 開始自動轉單"):
        with st.spinner("AI 處理中..."):
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel("gemini-1.5-flash")

                if input_type == "image":
                    prompt = "提取訂單：產品名核心字、度數(數字)、數量。只需輸出 JSON 陣列。"
                    source = [prompt, input_content]
                else:
                    prompt = f"從文字提取訂單：{input_content}。只需輸出 JSON 陣列。"
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
                    st.download_button(label="📥 下載轉單 Excel", data=output.getvalue(), file_name="結果.xlsx")
            except Exception as e:
                st.error(f"出錯了：{e}")
