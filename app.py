import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
import json
import re

st.set_page_config(page_title="極速智慧轉單", layout="wide")
st.title("⚡ 極速智慧對轉工具 (穩定效能版)")

# --- 1. API 資源快取 (解決 404 與 慢速的主因) ---
@st.cache_resource
def get_ai_model(api_key):
    genai.configure(api_key=api_key)
    # 自動偵測可用模型，避免門牌號碼變動
    models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    target = next((m for m in models if 'flash' in m), models[0])
    return genai.GenerativeModel(model_name=target)

api_key = st.secrets.get("GEMINI_API_KEY", "")
if not api_key:
    api_key = st.sidebar.text_input("輸入 API Key", type="password")

# --- 2. 總表快取 ---
@st.cache_data
def load_and_process_db(file):
    try:
        df = pd.read_excel(file, header=None, dtype=str) if file.name.endswith('xlsx') else pd.read_csv(file, header=None, dtype=str)
        # 尋找品名行
        h_row = 0
        for i, row in df.iterrows():
            if "品名" in "".join(row.astype(str)):
                h_row = i
                break
        df_clean = df.iloc[h_row:].copy()
        df_clean.columns = df_clean.iloc[0]
        return df_clean[1:].reset_index(drop=True)
    except: return None

uploaded_db = st.file_uploader("📂 1. 載入產品總表", type=["xlsx", "csv"])
df_db = None
product_list_text = ""

if uploaded_db:
    df_db = load_and_process_db(uploaded_db)
    if df_db is not None:
        # 只提取前 100 名稱做關鍵字參考，減少 AI 閱讀壓力
        product_list_text = ", ".join(df_db.iloc[:, 1].astype(str).unique()[:100])
        st.success("✅ 總表已快取")

# --- 3. 輸入區 ---
st.header("📝 2. 輸入訂單內容")
col1, col2 = st.columns(2)
with col1:
    img_file = st.file_uploader("🖼️ 圖片 (點擊或拖曳)", type=["jpg", "png", "jpeg"])
with col2:
    text_input = st.text_area("✍️ 文字 (Line 直接貼上)", height=150)

# --- 4. 執行轉單 ---
if (img_file or text_input) and df_db is not None and api_key:
    if st.button("🚀 開始極速轉單", use_container_width=True):
        with st.spinner("AI 快速辨識中..."):
            try:
                # 取得快取好的模型
                model = get_ai_model(api_key)

                # 精簡 Prompt：讓 AI 專心認字，不要廢話
                prompt = f"""
                你是訂單助手。參考清單：[{product_list_text}]
                提取 JSON 陣列：[{{"key":"品名","degree":"度數","qty":數量}}]
                手寫草字校正（例：可泳棟 -> 可沐棕）。
                450度轉4.50。只需 JSON。
                """
                
                content = Image.open(img_file) if img_file else text_input
                response = model.generate_content([prompt, content] if img_file else prompt + f"\n{content}")
                
                # 快速比對邏輯 (Python 比對比 AI 比對快 100 倍)
                json_str = re.search(r'\[.*\]', response.text, re.DOTALL).group()
                items = json.loads(json_str)
                
                final_res = []
                for item in items:
                    k = str(item.get('key','')).strip()
                    try:
                        d_f = float(str(item.get('degree','')).replace("度","").replace("-",""))
                        if d_f >= 100: d_f /= 100.0
                        vs = [f"{d_f:.2f}", f"{d_f:.1f}", str(int(round(d_f * 100)))]
                    except: vs = [str(item.get('degree',''))]

                    # 向量化比對搜尋
                    mask = df_db.apply(lambda r: k in "".join(r.astype(str)) and any(v in "".join(r.astype(str)) for v in vs), axis=1)
                    match = df_db[mask]
                    
                    if not match.empty:
                        r_data = match.iloc[0].to_dict()
                        r_data['訂購數量'] = item.get('qty', 0)
                        final_res.append(r_data)
                
                if final_res:
                    st.dataframe(pd.DataFrame(final_res), use_container_width=True)
                    # 下載 Excel 邏輯...
                else:
                    st.warning("辨識完成，但總表中查無對應產品")

            except Exception as e:
                st.error(f"系統錯誤: {e}")
