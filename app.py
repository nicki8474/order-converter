import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
import json
import re

# 網頁配置
st.set_page_config(page_title="極速智慧轉單工具", layout="wide")
st.title("⚡ 極速智慧對轉工具 (穩定維護版)")

# --- 1. API Key 設定 ---
# 優先讀取 Secrets，若無則顯示側邊欄輸入
api_key = st.secrets.get("GEMINI_API_KEY", "")
with st.sidebar:
    st.header("⚙️ 系統設定")
    if not api_key:
        api_key = st.text_input("輸入 API Key", type="password")
    else:
        st.success("✅ API 已透過 Secrets 就緒")

# --- 2. 智慧載入總表 (使用快取避免重複讀取) ---
@st.cache_data
def process_db(file):
    try:
        if file.name.endswith('.csv'):
            df = pd.read_csv(file, header=None, dtype=str).fillna("")
        else:
            df = pd.read_excel(file, header=None, dtype=str).fillna("")
        
        # 尋找包含「品名」或「貨號」的標題行
        h_row = 0
        for i, row in df.iterrows():
            row_str = "".join(row.astype(str))
            if "品名" in row_str or "貨號" in row_str:
                h_row = i
                break
        df_clean = df.iloc[h_row:].copy()
        df_clean.columns = df_clean.iloc[0]
        return df_clean[1:].reset_index(drop=True)
    except Exception as e:
        st.error(f"總表解析失敗: {e}")
        return None

st.header("📂 1. 載入產品總表")
uploaded_db = st.file_uploader("上傳 Excel 或 CSV 總表", type=["xlsx", "csv"])

df_db = None
product_hint = ""

if uploaded_db:
    df_db = process_db(uploaded_db)
    if df_db is not None:
        # 提取獨特品名片段，縮短提示詞以加速 AI 反應
        unique_names = set()
        for name in df_db.iloc[:, 1].astype(str): # 假設品名在第二欄
            clean_n = re.sub(r'[\d\.\-]+', '', name).strip()
            if len(clean_n) > 1: unique_names.add(clean_n[:10]) 
        product_hint = ", ".join(list(unique_names)[:80])
        st.success(f"✅ 總表載入成功 (共 {len(df_db)} 筆)")

# --- 3. 輸入區 (圖片與文字並行) ---
st.header("📝 2. 輸入訂單內容")
col1, col2 = st.columns(2)

with col1:
    st.subheader("🖼️ 圖片 (手寫單/截圖)")
    img_file = st.file_uploader("拖曳圖片進來或點擊上傳", type=["jpg", "png", "jpeg"])

with col2:
    st.subheader("✍️ 文字 (Line 貼上)")
    text_input = st.text_area("直接貼上訂單文字內容", height=150, placeholder="例：可沐棕 4.50 x 12")

# --- 4. 執行轉單 ---
st.markdown("---")
if st.button("🚀 開始智慧辨識與比對", use_container_width=True):
    if not api_key:
        st.error("❌ 請先輸入 API Key")
    elif df_db is None:
        st.error("❌ 請先載入產品總表")
    elif not (img_file or text_input):
        st.error("❌ 請提供圖片或文字內容")
    else:
        with st.spinner("AI 正在尋找最佳模型並解析中..."):
            try:
                genai.configure(api_key=api_key)
                
                # --- 自動偵測模型 (防 404 關鍵邏輯) ---
                all_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                # 優先抓取包含 flash 的模型，若無則抓第一個
                active_model_name = next((m for m in all_models if 'flash' in m), all_models[0])
                model = genai.GenerativeModel(model_name=active_model_name)
                
                # 智慧校正 Prompt
                prompt = f"""
                你是一個專業的訂單提取專家。
                參考品名清單：[{product_hint}]
                
                任務：
                1. 提取產品、度數、數量。
                2. 若字跡模糊（如：可泳棟），請根據「參考品名清單」修正為正確名稱（如：可沐棕）。
                3. 輸出 JSON 陣列範例：[{{ "key": "產品名", "degree": "度數", "qty": 數量 }}]
                4. 度數規範：450 轉為 4.50。只需輸出 JSON。
                """
                
                # 判斷輸入源
                if img_file:
                    content = [prompt, Image.open(img_file)]
                else:
                    content = prompt + f"\n內容如下：\n{text_input}"
                
                response = model.generate_content(content)
                
                # 解析結果
                json_str = re.search(r'\[.*\]', response.text, re.DOTALL).group()
                extracted_items = json.loads(json_str)
                
                final_res = []
                for item in extracted_items:
                    k = str(item.get('key','')).strip().replace('鹽', '塩')
                    try:
                        # 智慧度數換算 (支援 4.50, 4.5, 450 三種格式比對)
                        d_val = float(str(item.get('degree','')).replace("度","").replace("-",""))
                        if d_val >= 100: d_val /= 100.0
                        vs = [f"{d_val:.2f}", f"{d_val:.1f}", str(int(round(d_val * 100)))]
                    except:
                        vs = [str(item.get('degree',''))]

                    # 快速矩陣搜尋比對
                    mask = df_db.apply(lambda r: k in "".join(r.astype(str)) and any(v in "".join(r.astype(str)) for v in vs), axis=1)
                    match = df_db[mask]
                    
                    if not match.empty:
                        row_data = match.iloc[0].to_dict()
                        row_data['訂購數量'] = item.get('qty', 0)
                        final_res.append(row_data)
                    else:
                        st.warning(f"🔍 辨識為「{k} / {vs[0]}」，但總表中找不到吻合項目。")

                if final_res:
                    st.subheader("✅ 轉換結果")
                    result_df = pd.DataFrame(final_res)
                    st.dataframe(result_df, use_container_width=True)
                    
                    # 下載區
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        result_df.to_excel(writer, index=False)
                    st.download_button("📥 下載轉單 Excel", output.getvalue(), "智慧轉單結果.xlsx")
                
            except Exception as e:
                st.error(f"執行出錯 (可能為格式問題或 API 限制): {e}")
