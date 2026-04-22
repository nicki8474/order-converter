import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
import json
import re

# 頁面基本配置
st.set_page_config(page_title="訂單智慧轉單工具", layout="wide")
st.title("📦 訂單智慧轉單工具")

# --- 1. API Key 設定 ---
api_key = st.secrets.get("GEMINI_API_KEY", "")
with st.sidebar:
    st.header("⚙️ 系統設定")
    if not api_key:
        api_key = st.text_input("手動輸入 API Key", type="password")
    else:
        st.success("✅ API 已就緒")

# --- 2. 載入產品總表 ---
st.header("📂 1. 載入產品總表")
uploaded_db = st.file_uploader("請上傳總表 Excel/CSV (AI 會自動學習格式)", type=["xlsx", "csv"])

df_db = None
if uploaded_db:
    try:
        if uploaded_db.name.endswith('.csv'):
            temp_df = pd.read_csv(uploaded_db, header=None, dtype=str).fillna("")
        else:
            temp_df = pd.read_excel(uploaded_db, header=None, dtype=str).fillna("")
        
        # 智慧尋找標題行
        h_row = 0
        for i, row in temp_df.iterrows():
            if "品名" in "".join(row.astype(str)):
                h_row = i
                break
        df_db = temp_df.iloc[h_row:].copy()
        df_db.columns = df_db.iloc[0]
        df_db = df_db[1:].reset_index(drop=True)
        st.success(f"✅ 資料庫載入成功 (共 {len(df_db)} 筆)")
    except Exception as e:
        st.error(f"總表讀取失敗: {e}")

# --- 3. 雙軌輸入區 (圖片與文字) ---
st.header("📝 2. 輸入訂單內容")
col1, col2 = st.columns(2)

with col1:
    st.subheader("🖼️ 圖片來源")
    # 如果 Ctrl+V 貼不上，請點 Browse files 選擇檔案，或直接「拖曳」進來
    img_file = st.file_uploader("點此選擇圖片 / 拖曳圖片進來 / 點此按 Ctrl+V", type=["jpg", "png", "jpeg"])

with col2:
    st.subheader("✍️ 文字來源 (直接貼上)")
    text_input = st.text_area("如果圖片上傳有問題，請直接貼上 Line 訂單文字", height=150, placeholder="例如：淨透潤 450x12")

# 整合輸入內容
input_content = None
input_type = None

if img_file:
    input_content = Image.open(img_file)
    input_type = "image"
    st.image(input_content, width=300, caption="已讀取圖片")
elif text_input:
    input_content = text_input
    input_type = "text"

# --- 4. 執行轉單 (按鈕永遠顯示，沒填內容會提示) ---
st.markdown("---")
if st.button("🚀 開始自動轉單並比對", use_container_width=True):
    if not api_key:
        st.error("❌ 請先輸入 API Key")
    elif df_db is None:
        st.error("❌ 請先載入產品總表")
    elif not input_content:
        st.error("❌ 請先輸入訂單內容 (貼圖或貼文字)")
    else:
        with st.spinner("AI 正在解析並與總表進行智慧比對..."):
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel('gemini-1.5-flash')
                
                # 強化後的 Prompt，自動學習度數格式
                prompt = "提取 JSON 陣列：[{\"key\":\"品名關鍵字\", \"degree\":\"度數\", \"qty\":數量}]。450度轉為 4.50。只需 JSON。"
                
                if input_type == "image":
                    response = model.generate_content([prompt, input_content])
                else:
                    response = model.generate_content(prompt + f"\n內容：{input_content}")
                
                json_match = re.search(r'\[.*\]', response.text, re.DOTALL)
                items = json.loads(json_match.group()) if json_match else []
                
                final_res = []
                for item in items:
                    k = str(item.get('key','')).strip().replace('鹽', '塩')
                    try:
                        # 處理度數 (學習各類總表格式)
                        d_str = str(item.get('degree','')).replace("度","").replace("-","")
                        d_f = float(d_str)
                        if d_f >= 100: d_f /= 100.0
                        v2, v1, v0 = f"{d_f:.2f}", f"{d_f:.1f}", str(int(round(d_f * 100)))
                    except:
                        v2 = v1 = v0 = str(item.get('degree',''))

                    def match_func(row):
                        t = "".join(row.astype(str)).replace("-","").replace(" ","")
                        return k in t and (v2 in t or v1 in t or v0 in t)

                    m = df_db[df_db.apply(match_func, axis=1)]
                    if not m.empty:
                        r = m.iloc[0].to_dict()
                        r['訂購數量'] = item.get('qty', 0)
                        final_res.append(r)
                    else:
                        st.warning(f"🔍 AI 辨識出「{k} / {v2}」，但總表找不到吻合產品。")

                if final_res:
                    st.subheader("✅ 轉換結果")
                    st.dataframe(pd.DataFrame(final_res), use_container_width=True)
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        pd.DataFrame(final_res).to_excel(writer, index=False)
                    st.download_button("📥 下載轉單 Excel", output.getvalue(), "訂單結果.xlsx")
                
            except Exception as e:
                st.error(f"系統出錯: {e}")
