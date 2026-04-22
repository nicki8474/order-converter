import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
import json
import re

st.set_page_config(page_title="萬能訂單對轉工具", layout="wide")

# 強制注入一段 JavaScript，讓頁面在點擊時能自動獲取焦點 (嘗試輔助貼上)
st.markdown("<script>document.addEventListener('paste', function(e){ console.log('Pasted'); });</script>", unsafe_allow_html=True)

st.title("📦 萬能訂單對轉工具")

# --- 1. API Key ---
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
        
        # 尋找包含「品名」的行
        header_row = 0
        for i, row in temp_df.iterrows():
            if "品名" in "".join(row.astype(str)):
                header_row = i
                break
        df_db = temp_df.iloc[header_row:].copy()
        df_db.columns = df_db.iloc[0]
        df_db = df_db[1:].reset_index(drop=True)
        st.success("✅ 資料庫載入成功")
    except Exception as e:
        st.error(f"讀取失敗: {e}")

# --- 3. 修正後的輸入區 ---
st.header("3. 輸入訂單內容")

# 這次我們把兩個輸入框並排，增加成功率
col1, col2 = st.columns(2)

with col1:
    st.subheader("🖼️ 方法 A：上傳/貼上圖片")
    # 這是目前 Streamlit 唯一能接收 Ctrl+V 的官方方式
    pasted_file = st.file_uploader("點擊這裡使框框變藍色，然後按 Ctrl+V", type=["jpg", "jpeg", "png"])

with col2:
    st.subheader("✍️ 方法 B：貼上文字")
    text_input = st.text_area("如果圖片貼不上，請改用文字：直接在此貼上訂單文字", placeholder="例：淨透潤 450x12", height=120)

input_content = None
input_type = None

if pasted_file:
    input_content = Image.open(pasted_file)
    input_type = "image"
    st.image(input_content, caption="✅ 圖片讀取成功", width=300)
elif text_input:
    input_content = text_input
    input_type = "text"

# --- 4. 智慧比對 ---
if input_content and df_db is not None and api_key:
    if st.button("🚀 開始自動轉單 (若沒反應請多點一次)", use_container_width=True):
        with st.spinner("AI 正在分析..."):
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel('gemini-1.5-flash')

                prompt = "提取訂單為JSON陣列:[{\"key\":\"關鍵字\",\"degree\":\"度數\",\"qty\":數量}]。度數若為450請轉為4.50。只需JSON。"
                
                if input_type == "image":
                    response = model.generate_content([prompt, input_content])
                else:
                    response = model.generate_content([prompt + f"\n內容：{input_content}"])
                
                # 提取 JSON
                match_json = re.search(r'\[.*\]', response.text, re.DOTALL)
                if match_json:
                    items = json.loads(match_json.group())
                else:
                    items = []
                
                final_list = []
                for item in items:
                    k = str(item.get('key','')).strip().replace('鹽', '塩')
                    try:
                        # 這裡修正了總表6的 325, 450 等格式匹配
                        d_raw_str = str(item.get('degree','')).replace("度", "").replace("-", "")
                        d_float = float(d_raw_str)
                        if d_float >= 100: d_float /= 100.0
                        
                        # 產生三種可能的字串來搜尋總表
                        v2, v1, v0 = f"{d_float:.2f}", f"{d_float:.1f}", str(int(round(d_float * 100)))
                    except:
                        v2 = v1 = v0 = str(item.get('degree',''))

                    def check_row(row):
                        t = "".join(row.astype(str)).replace("-","").replace(" ","")
                        return k in t and (v2 in t or v1 in t or v0 in t)

                    match = df_db[df_db.apply(check_row, axis=1)]
                    if not match.empty:
                        res = match.iloc[0].to_dict()
                        res['訂購數量'] = item.get('qty', 0)
                        final_list.append(res)
                    else:
                        st.warning(f"🔍 認出「{k} / {v2}」，但總表找不到。")

                if final_list:
                    st.subheader("✅ 轉換結果")
                    st.dataframe(pd.DataFrame(final_list), use_container_width=True)
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        pd.DataFrame(final_list).to_excel(writer, index=False)
                    st.download_button("📥 下載轉單 Excel", output.getvalue(), "訂單結果.xlsx")
                else:
                    st.error("❌ 找不到任何匹配產品，請檢查總表或訂單內容。")
                
            except Exception as e:
                st.error(f"系統出錯: {e}")
