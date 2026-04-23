import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
import json
import re
import time

st.set_page_config(page_title="智慧轉單工具", layout="wide")
st.title("📦 智慧轉單工具 (額度省電版)")

# --- 1. API Key ---
api_key = st.secrets.get("GEMINI_API_KEY", "")
with st.sidebar:
    st.header("⚙️ 設定")
    api_key = st.text_input("輸入 API Key (若額度用完請換一個)", value=api_key, type="password")
    st.info("💡 免費版每日限 20 次。若出現 429 錯誤，請等待 1 分鐘或更換 Key。")

# --- 2. 總表載入 (快取) ---
@st.cache_data
def load_db(file):
    df = pd.read_excel(file, header=None, dtype=str) if file.name.endswith('xlsx') else pd.read_csv(file, header=None, dtype=str)
    h_row = 0
    for i, row in df.iterrows():
        if "品名" in "".join(row.astype(str)):
            h_row = i
            break
    df_clean = df.iloc[h_row:].copy()
    df_clean.columns = df_clean.iloc[0]
    return df_clean[1:].reset_index(drop=True)

uploaded_db = st.file_uploader("📂 1. 載入產品總表", type=["xlsx", "csv"])
df_db = None
product_hint = ""

if uploaded_db:
    df_db = load_db(uploaded_db)
    if df_db is not None:
        unique_names = set()
        for name in df_db.iloc[:, 1].astype(str):
            clean_n = re.sub(r'[\d\.\-]+', '', name).strip()
            if len(clean_n) > 1: unique_names.add(clean_n[:10]) 
        product_hint = ", ".join(list(unique_names)[:80])
        st.success("✅ 總表載入成功")

# --- 3. 輸入內容 ---
st.header("📝 2. 輸入訂單")
col1, col2 = st.columns(2)
with col1:
    img_file = st.file_uploader("🖼️ 圖片", type=["jpg", "png", "jpeg"])
with col2:
    text_input = st.text_area("✍️ 文字", height=150)

# --- 4. 執行轉單 ---
if st.button("🚀 執行辨識 (請勿頻繁點擊)", use_container_width=True):
    if not api_key:
        st.error("請輸入 API Key")
    elif df_db is None:
        st.error("請先載入總表")
    elif not (img_file or text_input):
        st.warning("請先提供內容")
    else:
        with st.spinner("AI 解析中... (若卡住請稍候)"):
            try:
                genai.configure(api_key=api_key)
                
                # 自動偵測模型，防 404
                models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                target = next((m for m in models if 'flash' in m), models[0])
                model = genai.GenerativeModel(model_name=target)

                prompt = f"提取 JSON:[{{'key':'品名','degree':'度數','qty':數量}}]。參考清單:[{product_hint}]。450度轉4.50。只需JSON。"
                
                content = Image.open(img_file) if img_file else text_input
                response = model.generate_content([prompt, content] if img_file else prompt + f"\n{text_input}")
                
                json_match = re.search(r'\[.*\]', response.text, re.DOTALL)
                if json_match:
                    items = json.loads(json_match.group())
                    final_res = []
                    for item in items:
                        k = str(item.get('key','')).strip().replace('鹽', '塩')
                        try:
                            d_f = float(str(item.get('degree','')).replace("度","").replace("-",""))
                            if d_f >= 100: d_f /= 100.0
                            vs = [f"{d_f:.2f}", f"{d_f:.1f}", str(int(round(d_f * 100)))]
                        except: vs = [str(item.get('degree',''))]

                        mask = df_db.apply(lambda r: k in "".join(r.astype(str)) and any(v in "".join(r.astype(str)) for v in vs), axis=1)
                        match = df_db[mask]
                        if not match.empty:
                            r_data = match.iloc[0].to_dict()
                            r_data['訂購數量'] = item.get('qty', 0)
                            final_res.append(r_data)
                    
                    if final_res:
                        st.dataframe(pd.DataFrame(final_res), use_container_width=True)
                        # 下載按鈕...
                    else:
                        st.warning("查無對應產品")
                
            except Exception as e:
                # 專門抓 429 錯誤並翻譯成白話文
                if "429" in str(e):
                    st.error("❌ 額度用完了！請等 1 分鐘後再試，或在左側更換 API Key。")
                else:
                    st.error(f"執行出錯: {e}")
