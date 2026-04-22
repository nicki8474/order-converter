import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
import json
import re

st.set_page_config(page_title="萬能訂單對轉工具", layout="wide")
st.title("📦 萬能訂單對轉工具")

# --- 1. API Key ---
api_key = st.secrets.get("GEMINI_API_KEY", "")
with st.sidebar:
    st.header("設定")
    if api_key:
        st.success("✅ API 就緒")
    else:
        api_key = st.text_input("請輸入 API Key", type="password")

# --- 2. 智慧載入總表 ---
st.header("2. 載入產品總表")
uploaded_db = st.file_uploader("上傳任何一份產品總表 (Excel/CSV)", type=["xlsx", "csv"])

df_db = None
if uploaded_db:
    try:
        if uploaded_db.name.endswith('.csv'):
            temp_df = pd.read_csv(uploaded_db, header=None, dtype=str).fillna("")
        else:
            temp_df = pd.read_excel(uploaded_db, header=None, dtype=str).fillna("")
        
        # 智慧尋找標題行
        header_row = 0
        for i, row in temp_df.iterrows():
            row_txt = "".join(row.astype(str))
            if "品名" in row_txt or "貨號" in row_txt:
                header_row = i
                break
        df_db = temp_df.iloc[header_row:].copy()
        df_db.columns = df_db.iloc[0]
        df_db = df_db[1:].reset_index(drop=True)
        st.success(f"✅ 資料庫載入成功，共 {len(df_db)} 筆。")
    except Exception as e:
        st.error(f"讀取失敗: {e}")

# --- 3. 圖片貼上專用區 ---
st.header("3. 輸入訂單內容 (手寫/拍照/文字)")

col1, col2 = st.columns([1, 1.5])

with col1:
    st.subheader("方式 A：選取檔案")
    u_file = st.file_uploader("手動選取檔案", type=["jpg", "png", "jpeg"], label_visibility="collapsed")

with col2:
    st.subheader("方式 B：直接貼上 (推薦)")
    st.markdown("""
    <div style="border:2px dashed #00a0ff; padding:20px; border-radius:10px; background-color:#e1f5fe; text-align:center;">
        先截圖，然後點擊下方 <b>「按 Ctrl+V 貼上訂單圖」</b> 的框框直接貼上。
    </div>
    """, unsafe_allow_html=True)
    # 使用 chat_input 作為接收器，它對 Ctrl+V 貼圖片檔案的反應比 file_uploader 更好
    p_file = st.chat_input("在此按 Ctrl+V 貼上訂單圖片...")

input_content = None
input_type = None

# 判斷輸入源 (優先處理貼上的內容)
if p_file:
    # 這裡 AI 會檢查 p_file 是否包含圖片對象
    # 在 Streamlit chat_input 貼上圖片會被視為上傳
    input_content = p_file
    input_type = "text" # chat_input 預設轉文字，若貼圖失效則改由下方 u_file 承接
    
if u_file:
    input_content = Image.open(u_file)
    input_type = "image"
    st.image(input_content, caption="✅ 圖片已就緒", width=400)
elif p_file:
    st.info(f"已接收內容：{p_file}")
    input_content = p_file
    input_type = "text"

# --- 4. 智慧轉單執行 ---
if input_content and df_db is not None and api_key:
    if st.button("🚀 開始自動轉單", use_container_width=True):
        with st.spinner("AI 正在解析並比對總表..."):
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel('gemini-1.5-flash')
                
                prompt = "你是訂單解析專家。請提取產品名稱、度數、數量。輸出格式：JSON 陣列 [{\"key\":\"品名\",\"degree\":\"度數\",\"qty\":數量}]。度數若為 450 請寫 4.50。只需 JSON。"
                
                if input_type == "image":
                    response = model.generate_content([prompt, input_content])
                else:
                    response = model.generate_content(prompt + f"\n內容：{input_content}")
                
                items = json.loads(re.search(r'\[.*\]', response.text, re.DOTALL).group())
                
                final_results = []
                for item in items:
                    k = str(item.get('key','')).strip().replace('鹽', '塩')
                    try:
                        d_raw = str(item.get('degree','')).replace("度","").replace("-","")
                        d_val = float(d_raw)
                        if d_val >= 100: d_val /= 100.0
                        v2, v1, v0 = f"{d_val:.2f}", f"{d_val:.1f}", str(int(round(d_val * 100)))
                    except:
                        v2 = v1 = v0 = str(item.get('degree',''))

                    def check_row(row):
                        t = "".join(row.astype(str)).replace("-","").replace(" ","")
                        return k in t and (v2 in t or v1 in t or v0 in t)

                    match = df_db[df_db.apply(check_row, axis=1)]
                    if not match.empty:
                        res = match.iloc[0].to_dict()
                        res['訂購數量'] = item.get('qty', 0)
                        final_results.append(res)
                    else:
                        st.warning(f"🔍 辨識出「{k} / {v2}」，但總表找不到。")

                if final_results:
                    st.subheader("✅ 轉換結果")
                    st.dataframe(pd.DataFrame(final_results), use_container_width=True)
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        pd.DataFrame(final_results).to_excel(writer, index=False)
                    st.download_button("📥 下載轉單 Excel", output.getvalue(), "訂單結果.xlsx")
            
            except Exception as e:
                st.error(f"出錯了: {e}")
