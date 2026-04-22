import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
import json
import re

# 網頁配置：擴展寬度，方便左右對照
st.set_page_config(page_title="萬能訂單對轉工具", layout="wide")
st.title("📦 萬能訂單對轉工具")

# --- 1. API Key 設定 ---
api_key = st.secrets.get("GEMINI_API_KEY", "")
with st.sidebar:
    st.header("⚙️ 系統設定")
    if api_key:
        st.success("✅ API 就緒")
    else:
        api_key = st.text_input("手動輸入 API Key", type="password")

# --- 2. 智慧載入總表 ---
st.header("📂 2. 載入產品總表")
uploaded_db = st.file_uploader("請上傳總表 (Excel/CSV)，AI 會自動學習格式", type=["xlsx", "csv"])

df_db = None
if uploaded_db:
    try:
        if uploaded_db.name.endswith('.csv'):
            temp_df = pd.read_csv(uploaded_db, header=None, dtype=str).fillna("")
        else:
            temp_df = pd.read_excel(uploaded_db, header=None, dtype=str).fillna("")
        
        # 智慧定位標題行
        header_row = 0
        for i, row in temp_df.iterrows():
            if "品名" in "".join(row.astype(str)):
                header_row = i
                break
        df_db = temp_df.iloc[header_row:].copy()
        df_db.columns = df_db.iloc[0]
        df_db = df_db[1:].reset_index(drop=True)
        st.success(f"✅ 資料庫載入成功 (共 {len(df_db)} 筆資料)")
    except Exception as e:
        st.error(f"讀取總表失敗: {e}")

# --- 3. 混合輸入區：貼圖 + 貼文字 ---
st.header("📝 3. 輸入訂單內容")
col_img, col_txt = st.columns(2)

with col_img:
    st.subheader("🖼️ 圖片來源 (支援直接貼上/拖曳)")
    st.markdown("""
    <div style="background-color:#e1f5fe; padding:10px; border-radius:5px; border-left:5px solid #00a0ff; font-size:14px;">
      <strong>📸 貼圖教學：</strong> 先截圖，<b>點一下下方框框</b>(變藍色)，按 <b>Ctrl+V</b>。
    </div>
    """, unsafe_allow_html=True)
    img_file = st.file_uploader("點擊後按 Ctrl+V 貼上訂單圖", type=["jpg", "png", "jpeg"], key="img_input")

with col_txt:
    st.subheader("✍️ 文字來源 (直接貼上文字)")
    st.write("") # 對齊用
    text_input = st.text_area("直接在此貼上 Line 訂單文字內容", placeholder="例：淨透潤 450x12", height=125)

# 整合輸入內容
input_content = None
input_type = None

if img_file:
    input_content = Image.open(img_file)
    input_type = "image"
    st.image(input_content, caption="✅ 圖片讀取成功", width=350)
elif text_input:
    input_content = text_input
    input_type = "text"

# --- 4. 執行與智慧比對 ---
if input_content and df_db is not None and api_key:
    if st.button("🚀 開始自動轉單", use_container_width=True):
        with st.spinner("AI 正在解析訂單並對應總表格式..."):
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel('gemini-1.5-flash')
                
                prompt = """
                你是一個專業的訂單提取專家。請從輸入內容中提取產品名、度數、數量。
                1. 度數若為 450度 請轉為 4.50。
                2. 輸出格式必須是 JSON 陣列：[{"key":"產品關鍵字", "degree":"度數", "qty":數量}]。
                3. 只輸出 JSON 內容。
                """
                
                if input_type == "image":
                    response = model.generate_content([prompt, input_content])
                else:
                    response = model.generate_content(prompt + f"\n內容：{input_content}")
                
                # 清洗 JSON 並轉成物件
                clean_text = re.search(r'\[.*\]', response.text, re.DOTALL).group()
                items = json.loads(clean_text)
                
                final_results = []
                for item in items:
                    k = str(item.get('key','')).strip().replace('鹽', '塩')
                    try:
                        # 智慧解析度數：處理 450, 4.5, 4.50 等多種總表寫法
                        d_str = str(item.get('degree','')).replace("度","").replace("-","")
                        d_float = float(d_str)
                        if d_float >= 100: d_float /= 100.0
                        
                        v2, v1, v0 = f"{d_float:.2f}", f"{d_float:.1f}", str(int(round(d_float * 100)))
                    except:
                        v2 = v1 = v0 = str(item.get('degree',''))

                    # 萬能比對：只要品名關鍵字對，且度數符合任何一種寫法 (相容總表1~6)
                    def check_match(row):
                        t = "".join(row.astype(str)).replace("-","").replace(" ","")
                        return k in t and (v2 in t or v1 in t or v0 in t)

                    match = df_db[df_db.apply(check_match, axis=1)]
                    if not match.empty:
                        res = match.iloc[0].to_dict()
                        res['訂購數量'] = item.get('qty', 0)
                        final_results.append(res)
                    else:
                        st.warning(f"🔍 辨識出「{k} / {v2}」，但總表無精確匹配項目。")

                if final_results:
                    st.subheader("📋 轉換結果")
                    res_df = pd.DataFrame(final_results)
                    st.dataframe(res_df, use_container_width=True)
                    
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        res_df.to_excel(writer, index=False)
                    st.download_button("📥 下載轉單 Excel", output.getvalue(), "訂單結果.xlsx", use_container_width=True)
                
            except Exception as e:
                st.error(f"系統出錯: {e}")
