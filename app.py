import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
import json
import re

st.set_page_config(page_title="萬能訂單對轉工具", layout="centered")
st.title("📦 萬能訂單對轉工具")

# 讀取 Key
api_key = st.secrets.get("GEMINI_API_KEY", "")
with st.sidebar:
    st.header("1. 系統設定")
    if api_key:
        st.success("✅ 系統已就緒")
    else:
        api_key = st.text_input("輸入 Gemini API Key", type="password")

# --- 2. 智慧讀取產品總表 ---
st.header("2. 載入產品總表")
uploaded_db = st.file_uploader("第一步：請上傳任何格式的產品總表", type=["xlsx", "csv"])

df_db = None
if uploaded_db:
    try:
        if uploaded_db.name.endswith('.csv'):
            temp_df = pd.read_csv(uploaded_db, header=None, dtype=str).fillna("")
        else:
            temp_df = pd.read_excel(uploaded_db, header=None, dtype=str).fillna("")
        
        # 智慧尋找標題行：尋找包含「品名」或內容最多的那一行
        header_row_index = 0
        for i, row in temp_df.iterrows():
            row_str = "".join(row.values)
            if "品名" in row_str or "貨號" in row_str:
                header_row_index = i
                break
        
        df_db = temp_df.iloc[header_row_index:].copy()
        df_db.columns = df_db.iloc[0]
        df_db = df_db[1:].reset_index(drop=True)
        st.success(f"✅ 總表載入成功 (共 {len(df_db)} 筆)")
    except Exception as e:
        st.error(f"總表讀取失敗：{e}")

# --- 3. 混合訂單輸入 ---
st.header("3. 輸入訂單內容")
tab1, tab2, tab3 = st.tabs(["📋 直接貼上圖片", "📁 上傳檔案", "✍️ 貼上文字"])
input_content, input_type = None, None

with tab1:
    p_file = st.file_uploader("點此按 Ctrl+V 貼圖", type=["jpg", "jpeg", "png"], key="paste", label_visibility="collapsed")
    if p_file: input_content, input_type = Image.open(p_file), "image"
with tab2:
    u_file = st.file_uploader("選擇檔案", type=["jpg", "jpeg", "png"], key="upload")
    if u_file: input_content, input_type = Image.open(u_file), "image"
with tab3:
    t_input = st.text_area("貼上文字 (例：淨透潤 450 x12)", height=100)
    if t_input: input_content, input_type = t_input, "text"

# --- 4. 智慧比對邏輯 ---
if input_content and df_db is not None and api_key:
    if st.button("🚀 開始自動轉單"):
        with st.spinner("AI 正在解析並比對資料庫..."):
            try:
                genai.configure(api_key=api_key)
                # 自動挑選模型
                model_names = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                target_model = next((m for m in model_names if 'flash' in m), model_names[0])
                model = genai.GenerativeModel(model_name=target_model)

                prompt = "提取訂單為 JSON 陣列：[{\"key\":\"品名關鍵字\",\"degree\":\"度數數字\",\"qty\":數量}]。注意：450度請輸出4.50。只需JSON。"
                
                if input_type == "image":
                    response = model.generate_content([prompt, input_content])
                else:
                    response = model.generate_content([prompt + f"\n內容：{input_content}"])
                
                json_str = re.sub(r'```json|```', '', response.text).strip()
                items = json.loads(json_str)
                
                final_results = []
                for item in items:
                    # 1. 處理品名關鍵字
                    k = str(item['key']).strip().replace('鹽', '塩')
                    # 2. 處理度數 (多重格式相容)
                    try:
                        d = float(item['degree'])
                        if d >= 100: d = d / 100.0
                        d_str_2 = f"{d:.2f}"
                        d_str_1 = f"{d:.1f}"
                        d_str_raw = str(int(d*100)) if d != 0 else "0" # 處理 450 這種格式
                    except:
                        d_str_2 = d_str_1 = d_str_raw = str(item['degree'])

                    # 3. 智慧全行比對
                    def smart_match(row):
                        row_full_text = "".join(row.astype(str)).replace("-", "").replace(" ", "")
                        # 檢查關鍵字
                        if k not in row_full_text: return False
                        # 檢查度數 (滿足任一格式即可)
                        return (d_str_2 in row_full_text or d_str_1 in row_full_text or d_str_raw in row_full_text)

                    match = df_db[df_db.apply(smart_match, axis=1)]
                    
                    if not match.empty:
                        res = match.iloc[0].to_dict()
                        res['訂購數量'] = item['qty']
                        final_results.append(res)
                    else:
                        st.info(f"🔍 AI 辨識出「{k} / {d_str_2}」，但總表比對失敗。")

                if final_results:
                    st.subheader("✅ 轉換結果")
                    res_df = pd.DataFrame(final_results)
                    st.table(res_df)
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        res_df.to_excel(writer, index=False)
                    st.download_button("📥 下載轉單 Excel", output.getvalue(), "訂單結果.xlsx")

            except Exception as e:
                st.error(f"執行出錯：{e}")
