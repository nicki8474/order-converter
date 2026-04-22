import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
import json
import re

st.set_page_config(page_title="訂單轉單工具", layout="wide")
st.title("📦 訂單智慧對轉工具")

# --- 1. API Key ---
api_key = st.secrets.get("GEMINI_API_KEY", "")
with st.sidebar:
    st.header("⚙️ 系統設定")
    if not api_key:
        api_key = st.text_input("手動輸入 API Key", type="password")
    else:
        st.success("✅ API 已就緒")

# --- 2. 載入產品總表 ---
st.header("📂 1. 載入產品總表")
uploaded_db = st.file_uploader("上傳總表 Excel/CSV", type=["xlsx", "csv"])

df_db = None
if uploaded_db:
    try:
        if uploaded_db.name.endswith('.csv'):
            temp_df = pd.read_csv(uploaded_db, header=None, dtype=str).fillna("")
        else:
            temp_df = pd.read_excel(uploaded_db, header=None, dtype=str).fillna("")
        
        h_row = 0
        for i, row in temp_df.iterrows():
            if "品名" in "".join(row.astype(str)):
                h_row = i
                break
        df_db = temp_df.iloc[h_row:].copy()
        df_db.columns = df_db.iloc[0]
        df_db = df_db[1:].reset_index(drop=True)
        st.success("✅ 資料庫載入成功")
    except Exception as e:
        st.error(f"讀取失敗: {e}")

# --- 3. 雙軌輸入區 (圖片與文字) ---
st.header("📝 2. 輸入訂單內容")
col1, col2 = st.columns(2)

with col1:
    st.subheader("🖼️ 圖片來源")
    # 如果 Ctrl+V 不行，請試著點 Browse files 直接選檔案
    img_file = st.file_uploader("支援拖曳或點擊選擇圖片", type=["jpg", "png", "jpeg"], key="img_up")

with col2:
    st.subheader("✍️ 文字來源")
    text_input = st.text_area("直接在此貼上 Line 訂單文字", height=150, placeholder="例如：淨透潤 450x12")

input_content = None
input_type = None

if img_file:
    input_content = Image.open(img_file)
    input_type = "image"
    st.image(input_content, width=300)
elif text_input:
    input_content = text_input
    input_type = "text"

# --- 4. 執行辨識 ---
if input_content and df_db is not None and api_key:
    if st.button("🚀 開始自動轉單", use_container_width=True):
        with st.spinner("AI 正在解析訂單並學習總表規律..."):
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel('gemini-1.5-flash')
                prompt = "提取 JSON: [{\"key\":\"品名\",\"degree\":\"度數\",\"qty\":數量}]。450度轉4.50。只需 JSON。"
                
                if input_type == "image":
                    response = model.generate_content([prompt, input_content])
                else:
                    response = model.generate_content(prompt + f"\n內容：{input_content}")
                
                json_match = re.search(r'\[.*\]', response.text, re.DOTALL)
                items = json.loads(json_match.group()) if json_match else []
                
                final_res = []
                for item in items:
                    k = str(item.get('key','')).strip().replace('鹽', '塩')
                    try:
                        # 智慧換算度數 (學習所有總表格式)
                        d_str = str(item.get('degree','')).replace("度","").replace("-","")
                        d_f = float(d_str)
                        if d_f >= 100: d_f /= 100.0
                        v2, v1, v0 = f"{d_f:.2f}", f"{d_f:.1f}", str(int(round(d_f * 100)))
                    except:
                        v2 = v1 = v0 = str(item.get('degree',''))

                    def match_func(row):
                        t = "".join(row.astype(str)).replace("-","").replace(" ","")
                        return k in t and (v2 in t or v1 in t or v0 in t)

                    m = df_db[df_db.apply(match_func, axis=1)]
                    if not m.empty:
                        r = m.iloc[0].to_dict()
                        r['訂購數量'] = item.get('qty', 0)
                        final_res.append(r)
                
                if final_res:
                    st.dataframe(pd.DataFrame(final_res), use_container_width=True)
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        pd.DataFrame(final_res).to_excel(writer, index=False)
                    st.download_button("📥 下載轉單 Excel", output.getvalue(), "訂單結果.xlsx")
                else:
                    st.warning("⚠️ 辨識完成但無法與總表對應")
            except Exception as e:
                st.error(f"出錯了: {e}")
