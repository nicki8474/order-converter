import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
import json
import re

# 頁面配置
st.set_page_config(page_title="訂單對轉工具", layout="centered")
st.title("📦 訂單智慧對轉工具")

# API Key 載入
api_key = st.secrets.get("GEMINI_API_KEY", "")
with st.sidebar:
    st.header("1. 系統設定")
    if api_key:
        st.success("✅ 系統已就緒")
    else:
        api_key = st.text_input("輸入 Gemini API Key", type="password")

# --- 2. 載入產品總表 ---
st.header("2. 載入資料庫")
uploaded_db = st.file_uploader("第一步：請上傳產品總表", type=["xlsx", "csv"])

df_db = None
if uploaded_db:
    try:
        if uploaded_db.name.endswith('.csv'):
            temp_df = pd.read_csv(uploaded_db, header=None, dtype=str).fillna("")
        else:
            temp_df = pd.read_excel(uploaded_db, header=None, dtype=str).fillna("")
        
        header_row = 0
        for i, row in temp_df.iterrows():
            if "品名" in "".join(row.astype(str)):
                header_row = i
                break
        df_db = temp_df.iloc[header_row:].copy()
        df_db.columns = df_db.iloc[0]
        df_db = df_db[1:].reset_index(drop=True)
        st.success(f"✅ 總表已就緒 ({len(df_db)} 筆)")
    except Exception as e:
        st.error(f"讀取總表失敗: {e}")

# --- 3. 輸入訂單 (這裡就是你要的空間) ---
st.header("3. 輸入訂單內容")

# 這裡我們換個方式，直接把上傳框放出來，不要用頁籤，避免你找不到
st.markdown("---")
st.subheader("🖼️ 圖片輸入區 (支援直接 Ctrl+V 貼上)")
pasted_file = st.file_uploader("點擊此處後按 Ctrl+V 貼上截圖，或拖曳檔案進來", type=["jpg", "jpeg", "png"], key="main_paster")

st.markdown("---")
st.subheader("✍️ 文字輸入區 (選填)")
text_input = st.text_area("如果沒有圖片，請在此貼上文字訂單", placeholder="例：淨透潤 450x12", height=100)

input_content = None
input_type = None

if pasted_file:
    input_content = Image.open(pasted_file)
    input_type = "image"
    st.image(input_content, caption="✅ 偵測到圖片內容", width=300)
elif text_input:
    input_content = text_input
    input_type = "text"

# --- 4. 辨識與執行 ---
if input_content and df_db is not None and api_key:
    if st.button("🚀 開始自動轉單"):
        with st.spinner("AI 處理中..."):
            try:
                genai.configure(api_key=api_key)
                model_names = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                target = next((m for m in model_names if 'flash' in m), model_names[0])
                model = genai.GenerativeModel(model_name=target)

                prompt = "提取訂單為JSON陣列:[{\"key\":\"關鍵字\",\"degree\":\"度數\",\"qty\":數量}]。450度轉4.50。只需JSON。"
                response = model.generate_content([prompt, input_content] if input_type=="image" else [prompt + input_content])
                
                items = json.loads(re.sub(r'```json|```', '', response.text).strip())
                
                final_list = []
                for item in items:
                    k = str(item['key']).strip().replace('鹽', '塩')
                    try:
                        d_val = float(item['degree'])
                        if d_val >= 100: d_val /= 100.0
                        d_s2, d_s1, d_raw = f"{d_val:.2f}", f"{d_val:.1f}", str(int(d_val*100))
                    except:
                        d_s2 = d_s1 = d_raw = str(item['degree'])

                    def smart_match(row):
                        t = "".join(row.astype(str)).replace("-","").replace(" ","")
                        return k in t and (d_s2 in t or d_s1 in t or d_raw in t)

                    m = df_db[df_db.apply(smart_match, axis=1)]
                    if not m.empty:
                        r = m.iloc[0].to_dict()
                        r['訂購數量'] = item['qty']
                        final_list.append(r)
                    else:
                        st.info(f"🔍 AI 辨識出「{k} / {d_s2}」，但總表無精確匹配。")

                if final_list:
                    st.table(pd.DataFrame(final_list))
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        pd.DataFrame(final_list).to_excel(writer, index=False)
                    st.download_button("📥 下載轉單 Excel", output.getvalue(), "訂單結果.xlsx")
            except Exception as e:
                st.error(f"錯誤: {e}")
