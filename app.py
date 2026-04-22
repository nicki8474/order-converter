import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
import json
import re

st.set_page_config(page_title="萬能訂單對轉工具", layout="wide")
st.title("📦 萬能訂單對轉工具")

# --- 側邊欄：API Key ---
api_key = st.secrets.get("GEMINI_API_KEY", "")
with st.sidebar:
    st.header("1. 系統設定")
    if api_key:
        st.success("✅ 系統已就緒")
    else:
        api_key = st.text_input("輸入 Gemini API Key", type="password")

# --- 2. 智慧載入產品總表 ---
st.header("2. 載入產品總表")
uploaded_db = st.file_uploader("請先上傳產品總表 (Excel/CSV)", type=["xlsx", "csv"])

df_db = None
if uploaded_db:
    try:
        if uploaded_db.name.endswith('.csv'):
            temp_df = pd.read_csv(uploaded_db, header=None, dtype=str).fillna("")
        else:
            temp_df = pd.read_excel(uploaded_db, header=None, dtype=str).fillna("")
        
        header_row = 0
        for i, row in temp_df.iterrows():
            row_str = "".join(row.astype(str))
            if "品名" in row_str or "貨號" in row_str:
                header_row = i
                break
        df_db = temp_df.iloc[header_row:].copy()
        df_db.columns = df_db.iloc[0]
        df_db = df_db[1:].reset_index(drop=True)
        st.success(f"✅ 資料庫載入成功！")
    except Exception as e:
        st.error(f"讀取失敗: {e}")

# --- 3. 強化版貼圖空間 ---
st.header("3. 輸入訂單內容")
st.markdown("""
<div style="background-color:#f0f2f6;padding:15px;border-radius:10px;border:2px dashed #ccc">
    <strong>💡 貼圖秘訣：</strong><br>
    1. 在別處截圖 (Ctrl+C)<br>
    2. <strong>點擊下方「輸入訂單...」的長條框</strong><br>
    3. 直接按 <strong>Ctrl + V</strong> (它會自動變成一個小縮圖檔案)
</div>
""", unsafe_allow_html=True)

# 使用 chat_input 或是專門的監聽方式，但為了穩定性，我們用最靈敏的 file_uploader 變體
pasted_file = st.file_uploader("在下方框內按 Ctrl+V 貼上圖片", type=["jpg", "jpeg", "png"], key="new_paster")
text_input = st.text_area("或者：直接在此貼上訂單文字", placeholder="例：淨透潤 450x12", height=80)

input_content = None
input_type = None

if pasted_file:
    input_content = Image.open(pasted_file)
    input_type = "image"
    st.image(input_content, caption="✅ 圖片已成功讀取", width=250)
elif text_input:
    input_content = text_input
    input_type = "text"

# --- 4. 智慧執行 ---
if input_content and df_db is not None and api_key:
    if st.button("🚀 開始自動轉單", use_container_width=True):
        with st.spinner("AI 正在比對中..."):
            try:
                genai.configure(api_key=api_key)
                # 自動搜尋 Flash 模型
                model_list = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                target_model = next((m for m in model_list if 'flash' in m), model_list[0])
                model = genai.GenerativeModel(model_name=target_model)

                prompt = "提取訂單為JSON陣列:[{\"key\":\"關鍵字\",\"degree\":\"度數\",\"qty\":數量}]。450度轉4.50。只需JSON。"
                
                if input_type == "image":
                    response = model.generate_content([prompt, input_content])
                else:
                    response = model.generate_content([prompt + f"\n內容：{input_content}"])
                
                json_str = re.sub(r'```json|```', '', response.text).strip()
                items = json.loads(json_str)
                
                final_list = []
                for item in items:
                    # 處理品名
                    k = str(item['key']).strip().replace('鹽', '塩')
                    # 處理度數
                    try:
                        d_str = str(item['degree']).replace("度", "").replace("-", "")
                        d_val = float(d_str)
                        if d_val >= 100: d_val /= 100.0
                        # 準備各種可能的總表格式
                        v2, v1, raw = f"{d_val:.2f}", f"{d_val:.1f}", str(int(round(d_val * 100)))
                    except:
                        v2 = v1 = raw = str(item['degree'])

                    def match_logic(row):
                        t = "".join(row.astype(str)).replace("-","").replace(" ","")
                        return k in t and (v2 in t or v1 in t or raw in t)

                    match = df_db[df_db.apply(match_logic, axis=1)]
                    if not match.empty:
                        res = match.iloc[0].to_dict()
                        res['訂購數量'] = item['qty']
                        final_list.append(res)
                    else:
                        st.warning(f"🔍 AI 辨識出「{k} / {v2}」，但總表找不到。")

                if final_list:
                    st.subheader("✅ 轉換結果")
                    res_df = pd.DataFrame(final_list)
                    st.dataframe(res_df, use_container_width=True)
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        res_df.to_excel(writer, index=False)
                    st.download_button("📥 下載轉單 Excel", output.getvalue(), "結果.xlsx", use_container_width=True)
                
            except Exception as e:
                st.error(f"系統錯誤: {e}")
