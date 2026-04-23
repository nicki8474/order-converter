import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
import json
import re

st.set_page_config(page_title="智慧轉單工具", layout="wide")
st.title("📦 智慧轉單工具")

# --- 1. API Key ---
api_key = st.secrets.get("GEMINI_API_KEY", "")
with st.sidebar:
    st.header("⚙️ 設定")
    api_key = st.text_input("輸入 API Key", value=api_key, type="password")

# --- 2. 總表載入 (快取) ---
@st.cache_data
def load_db(file):
    try:
        df = pd.read_excel(file, header=None, dtype=str) if file.name.endswith('xlsx') else pd.read_csv(file, header=None, dtype=str)
        h_row = 0
        for i, row in df.iterrows():
            if "品名" in "".join(row.astype(str)):
                h_row = i
                break
        df_clean = df.iloc[h_row:].copy()
        df_clean.columns = df_clean.iloc[0]
        return df_clean[1:].reset_index(drop=True)
    except:
        return None

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
st.markdown("---")
if st.button("🚀 開始智慧轉單並比對", use_container_width=True):
    if not api_key:
        st.error("❌ 請先輸入 API Key")
    elif df_db is None:
        st.error("❌ 請先載入產品總表")
    elif not (img_file or text_input):
        st.warning("⚠️ 請先提供圖片或文字內容")
    else:
        with st.spinner("AI 正在分析中..."):
            try:
                genai.configure(api_key=api_key)
                
                # 自動偵測模型名，確保不因版本異動報 404
                models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                target = next((m for m in models if 'flash' in m), models[0])
                model = genai.GenerativeModel(model_name=target)

                prompt = f"""提取訂單為 JSON 陣列：[{{'key':'品名','degree':'度數','qty':數量}}]。
                參考清單：[{product_hint}]。手寫模糊請校正品名。450度轉4.50。只需JSON。"""
                
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
                        except: 
                            vs = [str(item.get('degree',''))]

                        # 使用向量化比對提升搜尋速度
                        mask = df_db.apply(lambda r: k in "".join(r.astype(str)) and any(v in "".join(r.astype(str)) for v in vs), axis=1)
                        match = df_db[mask]
                        if not match.empty:
                            r_data = match.iloc[0].to_dict()
                            r_data['訂購數量'] = item.get('qty', 0)
                            final_res.append(r_data)
                    
                    if final_res:
                        st.subheader("✅ 轉換結果")
                        res_df = pd.DataFrame(final_res)
                        st.dataframe(res_df, use_container_width=True)
                        
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                            res_df.to_excel(writer, index=False)
                        st.download_button("📥 下載轉單 Excel", output.getvalue(), "訂單結果.xlsx", use_container_width=True)
                    else:
                        st.warning("查無對應產品")
                
            except Exception as e:
                if "429" in str(e):
                    st.error("❌ 系統忙碌中或額度暫時用罄，請稍候 1 分鐘再試。")
                else:
                    st.error(f"執行出錯: {e}")
