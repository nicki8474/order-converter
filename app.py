import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
import json
import re

st.set_page_config(page_title="訂單轉單工具", layout="wide")
st.title("📦 訂單智慧對轉工具")

# --- 1. API Key (優先從 Secrets 讀取) ---
api_key = st.secrets.get("GEMINI_API_KEY", "")
with st.sidebar:
    st.header("⚙️ 系統設定")
    if not api_key:
        api_key = st.text_input("輸入 API Key", type="password")

# --- 2. 總表上傳 ---
st.header("2. 載入產品總表")
uploaded_db = st.file_uploader("請上傳總表 Excel/CSV", type=["xlsx", "csv"])

df_db = None
if uploaded_db:
    try:
        if uploaded_db.name.endswith('.csv'):
            temp_df = pd.read_csv(uploaded_db, header=None, dtype=str).fillna("")
        else:
            temp_df = pd.read_excel(uploaded_db, header=None, dtype=str).fillna("")
        
        # 智慧尋找標題
        h_row = 0
        for i, row in temp_df.iterrows():
            if "品名" in "".join(row.astype(str)):
                h_row = i
                break
        df_db = temp_df.iloc[h_row:].copy()
        df_db.columns = df_db.iloc[0]
        df_db = df_db[1:].reset_index(drop=True)
        st.success("✅ 總表載入成功")
    except Exception as e:
        st.error(f"讀取失敗: {e}")

# --- 3. 輸入區 ---
st.header("3. 輸入訂單內容")
col1, col2 = st.columns(2)

with col1:
    st.subheader("🖼️ 圖片 (請用『拖曳』進來)")
    img_file = st.file_uploader("直接把圖拖進此框框", type=["jpg", "png", "jpeg"])

with col2:
    st.subheader("✍️ 文字 (直接貼上文字)")
    text_input = st.text_area("在此貼上訂單文字", height=150)

input_content = None
input_type = None

if img_file:
    input_content = Image.open(img_file)
    input_type = "image"
    st.image(input_content, width=300)
elif text_input:
    input_content = text_input
    input_type = "text"

# --- 4. 執行 ---
if input_content and df_db is not None and api_key:
    if st.button("🚀 開始轉單", use_container_width=True):
        with st.spinner("AI 處理中..."):
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel('gemini-1.5-flash')
                prompt = "提取 JSON: [{\"key\":\"品名\",\"degree\":\"度數\",\"qty\":數量}]。450度轉4.50。只需 JSON。"
                
                if input_type == "image":
                    response = model.generate_content([prompt, input_content])
                else:
                    response = model.generate_content(prompt + f"\n內容：{input_content}")
                
                items = json.loads(re.search(r'\[.*\]', response.text, re.DOTALL).group())
                
                final_results = []
                for item in items:
                    k = str(item.get('key','')).strip().replace('鹽', '塩')
                    try:
                        d_f = float(str(item.get('degree','')).replace("度","").replace("-",""))
                        if d_f >= 100: d_f /= 100.0
                        v2, v1, v0 = f"{d_f:.2f}", f"{d_f:.1f}", str(int(round(d_f * 100)))
                    except:
                        v2 = v1 = v0 = str(item.get('degree',''))

                    def match(row):
                        t = "".join(row.astype(str)).replace("-","").replace(" ","")
                        return k in t and (v2 in t or v1 in t or v0 in t)

                    m = df_db[df_db.apply(match, axis=1)]
                    if not m.empty:
                        res = m.iloc[0].to_dict()
                        res['訂購數量'] = item.get('qty', 0)
                        final_results.append(res)
                
                if final_results:
                    st.dataframe(pd.DataFrame(final_results), use_container_width=True)
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        pd.DataFrame(final_results).to_excel(writer, index=False)
                    st.download_button("📥 下載 Excel", output.getvalue(), "訂單.xlsx")
                else:
                    st.warning("查無匹配產品")
            except Exception as e:
                st.error(f"錯誤: {e}")
