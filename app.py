import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
import json
import re

st.set_page_config(page_title="極速智慧轉單", layout="wide")
st.title("⚡ 極速智慧對轉工具 (修正 404 版)")

# --- 1. API Key ---
api_key = st.secrets.get("GEMINI_API_KEY", "")
if not api_key:
    api_key = st.sidebar.text_input("輸入 API Key", type="password")

# --- 2. 智慧載入總表 (快取機制，提升速度) ---
@st.cache_data
def process_db(file):
    if file.name.endswith('.csv'):
        df = pd.read_csv(file, header=None, dtype=str).fillna("")
    else:
        df = pd.read_excel(file, header=None, dtype=str).fillna("")
    
    h_row = 0
    for i, row in df.iterrows():
        if "品名" in "".join(row.astype(str)):
            h_row = i
            break
    df_clean = df.iloc[h_row:].copy()
    df_clean.columns = df_clean.iloc[0]
    return df_clean[1:].reset_index(drop=True)

uploaded_db = st.file_uploader("上傳總表 (Excel/CSV)", type=["xlsx", "csv"])
df_db = None
product_hint = ""

if uploaded_db:
    df_db = process_db(uploaded_db)
    # 提取品名關鍵字 (加速 AI 校正速度)
    unique_names = set()
    for name in df_db.iloc[:, 1].astype(str):
        clean_n = re.sub(r'[\d\.\-]+', '', name).strip()
        if len(clean_n) > 1: unique_names.add(clean_n[:10]) 
    product_hint = ", ".join(list(unique_names)[:80])
    st.success(f"✅ 總表已載入")

# --- 3. 雙軌輸入 ---
col1, col2 = st.columns(2)
with col1:
    img_file = st.file_uploader("🖼️ 圖片 (點擊或拖曳)", type=["jpg", "png", "jpeg"])
with col2:
    text_input = st.text_area("✍️ 文字 (直接貼上)", height=150)

# --- 4. 執行辨識 ---
if (img_file or text_input) and df_db is not None and api_key:
    if st.button("🚀 開始極速轉單", use_container_width=True):
        with st.spinner("正在自動尋找可用模型並辨識中..."):
            try:
                genai.configure(api_key=api_key)
                
                # --- 【關鍵修正】動態獲取模型名稱，避免 404 ---
                model_list = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                # 優先尋找名稱中包含 'flash' 的最新模型
                target_model_name = next((m for m in model_list if 'flash' in m), model_list[0])
                model = genai.GenerativeModel(model_name=target_model_name)
                # ---------------------------------------------

                prompt = f"""
                你是訂單解析專家。參考品名：[{product_hint}]
                請提取 JSON 陣列，格式如範例：[{{"key":"品名","degree":"度數","qty":數量}}]
                如果手寫模糊（如可泳棟），請修正為最接近的品名（如可沐棕）。
                450度需轉為4.50。只需輸出 JSON。
                """
                
                content = Image.open(img_file) if img_file else text_input
                response = model.generate_content([prompt, content] if img_file else prompt + f"\n{content}")
                
                # 快速解析結果
                json_str = re.search(r'\[.*\]', response.text, re.DOTALL).group()
                items = json.loads(json_str)
                
                final_res = []
                for item in items:
                    k = str(item.get('key','')).strip().replace('鹽', '塩')
                    try:
                        d_f = float(str(item.get('degree','')).replace("度","").replace("-",""))
                        if d_f >= 100: d_f /= 100.0
                        vs = [f"{d_f:.2f}", f"{d_f:.1f}", str(int(round(d_f * 100)))]
                    except:
                        vs = [str(item.get('degree',''))]

                    mask = df_db.apply(lambda r: k in "".join(r.astype(str)) and any(v in "".join(r.astype(str)) for v in vs), axis=1)
                    match = df_db[mask]
                    
                    if not match.empty:
                        r = match.iloc[0].to_dict()
                        r['訂購數量'] = item.get('qty', 0)
                        final_res.append(r)
                    else:
                        st.warning(f"🔍 辨識為「{k} / {vs[0]}」，但總表找不到")

                if final_res:
                    st.subheader("✅ 轉換結果")
                    st.dataframe(pd.DataFrame(final_res), use_container_width=True)
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        pd.DataFrame(final_res).to_excel(writer, index=False)
                    st.download_button("📥 下載 Excel", output.getvalue(), "訂單.xlsx")
                
            except Exception as e:
                st.error(f"系統錯誤: {e}")
