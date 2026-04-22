import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
import json
import re

# 頁面配置
st.set_page_config(page_title="萬能訂單對轉工具", layout="centered")
st.title("📦 萬能訂單對轉工具")

# API Key 載入
api_key = st.secrets.get("GEMINI_API_KEY", "")
with st.sidebar:
    st.header("1. 系統設定")
    if api_key:
        st.success("✅ 系統已就緒")
    else:
        api_key = st.text_input("輸入 Gemini API Key", type="password")

# --- 2. 智慧載入產品總表 ---
st.header("2. 載入產品總表")
uploaded_db = st.file_uploader("第一步：請上傳產品總表", type=["xlsx", "csv"])

df_db = None
if uploaded_db:
    try:
        if uploaded_db.name.endswith('.csv'):
            temp_df = pd.read_csv(uploaded_db, header=None, dtype=str).fillna("")
        else:
            temp_df = pd.read_excel(uploaded_db, header=None, dtype=str).fillna("")
        
        # 尋找包含「品名」或「貨號」的行作為標題
        header_row = 0
        for i, row in temp_df.iterrows():
            row_str = "".join(row.astype(str))
            if "品名" in row_str or "貨號" in row_str:
                header_row = i
                break
        df_db = temp_df.iloc[header_row:].copy()
        df_db.columns = df_db.iloc[0]
        df_db = df_db[1:].reset_index(drop=True)
        st.success(f"✅ 總表已就緒 ({len(df_db)} 筆資料)")
    except Exception as e:
        st.error(f"讀取總表失敗: {e}")

# --- 3. 圖片貼上區 (直接在這裡按 Ctrl+V) ---
st.header("3. 輸入訂單內容")
st.info("💡 請點擊下方框框後直接按 **Ctrl + V** 貼上截圖")

pasted_file = st.file_uploader("圖片貼上/上傳區", type=["jpg", "jpeg", "png"], key="main_uploader")
text_input = st.text_area("或者：在此貼上訂單文字", placeholder="例：淨透潤 450x12", height=100)

input_content = None
input_type = None

if pasted_file:
    input_content = Image.open(pasted_file)
    input_type = "image"
    st.image(input_content, caption="✅ 已讀取圖片", width=300)
elif text_input:
    input_content = text_input
    input_type = "text"

# --- 4. 辨識與智慧比對 ---
if input_content and df_db is not None and api_key:
    if st.button("🚀 開始自動轉單"):
        with st.spinner("AI 正在分析..."):
            try:
                genai.configure(api_key=api_key)
                model_names = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                target = next((m for m in model_names if 'flash' in m), model_names[0])
                model = genai.GenerativeModel(model_name=target)

                prompt = "提取訂單為 JSON 陣列：[{\"key\":\"品名關鍵字\",\"degree\":\"度數數字\",\"qty\":數量}]。如果是450度請輸出4.50。只需輸出 JSON。"
                
                if input_type == "image":
                    response = model.generate_content([prompt, input_content])
                else:
                    response = model.generate_content([prompt + f"\n內容：{input_content}"])
                
                json_str = re.sub(r'```json|```', '', response.text).strip()
                items = json.loads(json_str)
                
                final_results = []
                for item in items:
                    k = str(item['key']).strip().replace('鹽', '塩')
                    # 智慧處理度數轉換 (修正 Bug 的關鍵)
                    try:
                        d_val = float(str(item['degree']).replace("度", ""))
                        if d_val >= 100: d_val = d_val / 100.0
                        d_s2 = f"{d_val:.2f}"
                        d_s1 = f"{d_val:.1f}"
                        d_raw = str(int(round(d_val * 100))) # 修正：先四捨五入再轉整數
                    except:
                        d_s2 = d_s1 = d_raw = str(item['degree'])

                    # 智慧模糊比對
                    def smart_match(row):
                        row_txt = "".join(row.astype(str)).replace("-","").replace(" ","")
                        if k not in row_txt: return False
                        # 只要度數的任何一種寫法 (4.50, 4.5, 450) 有出現在這一行即可
                        return (d_s2 in row_txt or d_s1 in row_txt or d_raw in row_txt)

                    match = df_db[df_db.apply(smart_match, axis=1)]
                    if not match.empty:
                        res = match.iloc[0].to_dict()
                        res['訂購數量'] = item['qty']
                        final_results.append(res)
                    else:
                        st.warning(f"🔍 辨識出「{k} / {d_s2}」，但在總表中找不到。")

                if final_results:
                    st.subheader("✅ 轉換結果")
                    res_df = pd.DataFrame(final_results)
                    st.table(res_df)
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        res_df.to_excel(writer, index=False)
                    st.download_button("📥 下載轉單 Excel", output.getvalue(), "訂單結果.xlsx")
                
            except Exception as e:
                st.error(f"系統出錯：{e}")
