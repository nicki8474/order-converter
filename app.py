import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
import json
import re

st.set_page_config(page_title="萬能訂單對轉工具", layout="centered")
st.title("📦 萬能訂單對轉工具")

# --- 1. API Key 載入 ---
api_key = st.secrets.get("GEMINI_API_KEY", "")
with st.sidebar:
    st.header("⚙️ 系統設定")
    if api_key:
        st.success("✅ API 已就緒")
    else:
        api_key = st.text_input("輸入 Gemini API Key", type="password")

# --- 2. 智慧載入產品總表 ---
st.header("📂 2. 載入產品總表")
uploaded_db = st.file_uploader("請上傳總表 (Excel/CSV)", type=["xlsx", "csv"], key="db_loader")

df_db = None
if uploaded_db:
    try:
        if uploaded_db.name.endswith('.csv'):
            temp_df = pd.read_csv(uploaded_db, header=None, dtype=str).fillna("")
        else:
            temp_df = pd.read_excel(uploaded_db, header=None, dtype=str).fillna("")
        
        # 尋找包含「品名」的行
        header_row = 0
        for i, row in temp_df.iterrows():
            if "品名" in "".join(row.astype(str)):
                header_row = i
                break
        df_db = temp_df.iloc[header_row:].copy()
        df_db.columns = df_db.iloc[0]
        df_db = df_db[1:].reset_index(drop=True)
        st.success(f"✅ 資料庫載入成功 (共 {len(df_db)} 筆)")
    except Exception as e:
        st.error(f"讀取失敗: {e}")

# --- 3. 修正後的「全能貼圖區」 ---
st.header("📸 3. 輸入訂單圖片")

st.markdown("""
<div style="background-color:#fff3cd; padding:10px; border-radius:5px; border-left:5px solid #ffc107;">
  <strong>💡 如果貼圖沒反應，請嘗試：</strong><br>
  1. 直接把圖片檔案從資料夾「拖曳」進下方的框框。<br>
  2. 使用最下方的「文字輸入框」貼上訂單文字。
</div>
""", unsafe_allow_html=True)

# 這裡使用最穩定的 file_uploader，但我們把它的標籤做得超明顯
pasted_file = st.file_uploader("請點擊此處使框框變藍，再按 Ctrl+V 貼圖，或直接拖曳圖片進來", type=["jpg", "jpeg", "png"], key="main_paster")

input_content = None
input_type = None

if pasted_file:
    input_content = Image.open(pasted_file)
    input_type = "image"
    st.image(input_content, caption="✅ 圖片讀取成功", width=300)
else:
    st.markdown("---")
    text_input = st.text_area("或者：在此貼上訂單文字內容", placeholder="例：淨透潤 450x12", height=100)
    if text_input:
        input_content = text_input
        input_type = "text"

# --- 4. 智慧執行 ---
if input_content and df_db is not None and api_key:
    if st.button("🚀 開始自動轉單", use_container_width=True):
        with st.spinner("AI 正在解析您的訂單..."):
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel('gemini-1.5-flash')

                prompt = "提取訂單為JSON陣列:[{\"key\":\"關鍵字\",\"degree\":\"度數\",\"qty\":數量}]。度數450轉為4.50。只需JSON。"
                
                if input_type == "image":
                    response = model.generate_content([prompt, input_content])
                else:
                    response = model.generate_content([prompt + f"\n內容：{input_content}"])
                
                # 提取 JSON 內容
                match_json = re.search(r'\[.*\]', response.text, re.DOTALL)
                items = json.loads(match_json.group()) if match_json else []
                
                final_list = []
                for item in items:
                    k = str(item.get('key','')).strip().replace('鹽', '塩')
                    try:
                        d_str = str(item.get('degree','')).replace("度", "").replace("-", "")
                        d_float = float(d_str)
                        if d_float >= 100: d_float /= 100.0
                        
                        # 兼容總表的不同寫法 (4.50, 4.5, 450)
                        v2, v1, v0 = f"{d_float:.2f}", f"{d_float:.1f}", str(int(round(d_float * 100)))
                    except:
                        v2 = v1 = v0 = str(item.get('degree',''))

                    def check_match(row):
                        t = "".join(row.astype(str)).replace("-","").replace(" ","")
                        return k in t and (v2 in t or v1 in t or v0 in t)

                    match = df_db[df_db.apply(check_match, axis=1)]
                    if not match.empty:
                        res = match.iloc[0].to_dict()
                        res['訂購數量'] = item.get('qty', 0)
                        final_list.append(res)
                    else:
                        st.warning(f"🔍 辨識出「{k} / {v2}」，但總表無精確匹配項目。")

                if final_list:
                    st.subheader("📋 轉換結果")
                    st.dataframe(pd.DataFrame(final_list), use_container_width=True)
                    # 下載 Excel
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        pd.DataFrame(final_list).to_excel(writer, index=False)
                    st.download_button("📥 下載轉單 Excel", output.getvalue(), "訂單結果.xlsx")
                else:
                    st.error("❌ 找不到匹配產品，請檢查輸入內容是否正確。")
                
            except Exception as e:
                st.error(f"系統出錯: {e}")
