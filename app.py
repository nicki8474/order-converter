import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
import json
import re

st.set_page_config(page_title="智慧訂單工具", layout="wide")
st.title("📦 萬能訂單對轉 (修正版)")

# --- 1. API Key ---
api_key = st.secrets.get("GEMINI_API_KEY", "")
with st.sidebar:
    st.header("⚙️ 系統設定")
    if not api_key:
        api_key = st.text_input("輸入 API Key", type="password")
    else:
        st.success("✅ API 已就緒")

# --- 2. 智慧載入總表 ---
st.header("📂 1. 載入產品總表")
uploaded_db = st.file_uploader("上傳總表 Excel/CSV", type=["xlsx", "csv"])

df_db = None
product_keywords = ""

if uploaded_db:
    try:
        if uploaded_db.name.endswith('.csv'):
            temp_df = pd.read_csv(uploaded_db, header=None, dtype=str).fillna("")
        else:
            temp_df = pd.read_excel(uploaded_db, header=None, dtype=str).fillna("")
        
        h_row = 0
        for i, row in temp_df.iterrows():
            if "品名" in "".join(row.astype(str)):
                h_row = i
                break
        df_db = temp_df.iloc[h_row:].copy()
        df_db.columns = df_db.iloc[0]
        df_db = df_db[1:].reset_index(drop=True)
        
        # 提取產品清單供 AI 學習，避免認錯字 (如可沐棕)
        # 假設品名在第二欄 (索引1)
        unique_names = df_db.iloc[:, 1].astype(str).unique().tolist()
        product_keywords = ", ".join(unique_names[:150]) 
        
        st.success(f"✅ 資料庫載入成功，AI 已學習品名清單")
    except Exception as e:
        st.error(f"讀取失敗: {e}")

# --- 3. 雙軌輸入區 (文字框已補回) ---
st.header("📝 2. 輸入訂單內容")
col1, col2 = st.columns(2)

with col1:
    st.subheader("🖼️ 圖片來源")
    img_file = st.file_uploader("上傳圖片或拖曳至此", type=["jpg", "png", "jpeg"])

with col2:
    st.subheader("✍️ 文字來源")
    text_input = st.text_area("在此貼上 Line 訂單文字", height=150, placeholder="例如：可沐棕 450x12")

input_content = None
input_type = None

if img_file:
    input_content = Image.open(img_file)
    input_type = "image"
    st.image(input_content, width=300)
elif text_input:
    input_content = text_input
    input_type = "text"

# --- 4. 智慧執行 (修正 Format Specifier 錯誤) ---
st.markdown("---")
if st.button("🚀 開始智慧轉單", use_container_width=True):
    if not api_key:
        st.error("❌ 請先輸入 API Key")
    elif df_db is None:
        st.error("❌ 請先載入產品總表")
    elif not input_content:
        st.error("❌ 請先提供圖片或文字")
    else:
        with st.spinner("AI 正在校對品名並解析中..."):
            try:
                genai.configure(api_key=api_key)
                
                # 自動偵測可用模型
                model_list = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                target_model = next((m for m in model_list if 'flash' in m), model_list[0])
                model = genai.GenerativeModel(model_name=target_model)

                # 使用雙大括號 {{ }} 來避開 Python f-string 錯誤
                prompt = f"""
                你是一個訂單提取專家。
                參考產品清單：[{product_keywords}]
                
                任務：
                1. 提取訂單內容中的產品、度數、數量。
                2. 若字跡模糊，請比對「參考產品清單」找最接近的字修正。(例如：把「可泳棟」修正為「可沐棕」)
                3. 輸出格式必須為 JSON 陣列，範例如下：
                   [{{ "key": "品名關鍵字", "degree": "度數", "qty": 數量 }}]
                4. 度數若為 450 請寫 4.50。
                5. 只輸出 JSON，不需解釋。
                """
                
                if input_type == "image":
                    response = model.generate_content([prompt, input_content])
                else:
                    response = model.generate_content(prompt + f"\n內容如下：\n{input_content}")
                
                # 清洗 JSON 文字
                json_match = re.search(r'\[.*\]', response.text, re.DOTALL)
                if not json_match:
                    st.error("AI 回傳格式有誤，請再試一次。")
                else:
                    items = json.loads(json_match.group())
                    
                    final_res = []
                    for item in items:
                        k = str(item.get('key','')).strip().replace('鹽', '塩')
                        try:
                            # 智慧處理度數
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
                            st.warning(f"🔍 辨識為「{k} / {v2}」，但總表中查無項目。")

                    if final_res:
                        st.subheader("✅ 轉換結果")
                        st.dataframe(pd.DataFrame(final_res), use_container_width=True)
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                            pd.DataFrame(final_res).to_excel(writer, index=False)
                        st.download_button("📥 下載轉單 Excel", output.getvalue(), "訂單結果.xlsx")
                
            except Exception as e:
                st.error(f"系統出錯: {e}")
