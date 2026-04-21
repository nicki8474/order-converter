import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
import json
import re

st.set_page_config(page_title="訂單智慧對轉工具", layout="centered")
st.title("🚀 訂單智慧對轉工具 (終極容錯版)")

with st.sidebar:
    st.header("1. 系統設定")
    api_key = st.text_input("輸入 Gemini API Key", type="password")

st.header("2. 載入資料庫")
uploaded_db = st.file_uploader("請上傳您的「產品總表.xlsx」", type=["xlsx", "csv"])

df_db = None
if uploaded_db:
    try:
        if uploaded_db.name.endswith('.csv'):
            temp_df = pd.read_csv(uploaded_db, header=None)
        else:
            temp_df = pd.read_excel(uploaded_db, header=None)
        
        header_row_index = 0
        found_header = False
        for i, row in temp_df.iterrows():
            row_values = [str(val) for val in row.values if pd.notna(val)]
            if any(k in "".join(row_values) for k in ["品名", "貨號", "條碼"]):
                header_row_index = i
                found_header = True
                break
        
        if found_header:
            df_db = temp_df.iloc[header_row_index:].copy()
            df_db.columns = df_db.iloc[0]
            df_db = df_db[1:].reset_index(drop=True)
            df_db.columns = [str(c).strip() for c in df_db.columns]
            st.success("總表載入成功！")
        else:
            st.error("找不到標題列")
    except Exception as e:
        st.error(f"讀取總表失敗：{e}")

st.header("3. 上傳訂單圖片")
uploaded_file = st.file_uploader("請上傳訂單照片", type=["jpg", "jpeg", "png"])

if uploaded_file and df_db is not None and api_key:
    img = Image.open(uploaded_file)
    st.image(img, caption="上傳的訂單", width=400)
    
    if st.button("🚀 開始智慧匹配"):
        with st.spinner("AI 深度比對中..."):
            try:
                genai.configure(api_key=api_key)
                models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                target_model = next((m for m in models if 'flash' in m), models[0])
                model = genai.GenerativeModel(model_name=target_model)

                prompt = """你是一個訂單處理員。請從圖片提取：
                1. 產品名稱 (如: 烏龍, 淨透潤, 白露) -> 只要提取最核心的兩個字即可
                2. 度數 (如: 4.50, 5.50)
                3. 數量
                輸出 JSON 陣列：[{"key": "核心字", "degree": "度數", "qty": 數量}]"""
                
                response = model.generate_content([prompt, img])
                json_str = re.sub(r'```json|```', '', response.text).strip()
                items = json.loads(json_str)
                
                st.write("🔍 AI 原始提取：", items)
                
                final_results = []
                name_col = next((c for c in df_db.columns if "品名" in str(c)), None)
                
                if name_col:
                    for item in items:
                        # --- 核心邏輯升級 ---
                        search_key = str(item['key']).replace('日彩', '').replace(' ', '').strip()
                        # 處理度數的多種可能 (4.5 -> 4.50)
                        try:
                            d_float = float(item['degree'])
                            d_variants = [f"{d_float:.2f}", f"{d_float:.1f}", str(int(d_float)) if d_float.is_integer() else str(d_float)]
                        except:
                            d_variants = [str(item['degree'])]

                        # 模糊比對：只要品名裡有出現產品關鍵字「且」有出現度數
                        # 我們讓搜尋條件變寬鬆：只要包含關鍵字中的「任兩個字」
                        match = df_db[
                            (df_db[name_col].astype(str).str.contains(search_key[:2], na=False, case=False)) & 
                            (df_db[name_col].astype(str).apply(lambda x: any(v in x for v in d_variants)))
                        ]
                        
                        if not match.empty:
                            # 如果有多筆，選字數最接近的（通常是最準確的）
                            res_row = match.iloc[0].to_dict()
                            res_row['訂購數量'] = item['qty']
                            final_results.append(res_row)
                        else:
                            st.warning(f"❌ 找不到：{search_key} 度數 {item['degree']}")
                
                if final_results:
                    res_df = pd.DataFrame(final_results)
                    st.subheader("✅ 智慧比對成果")
                    st.table(res_df)
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        res_df.to_excel(writer, index=False)
                    st.download_button(label="📥 下載 Excel", data=output.getvalue(), file_name="對轉結果.xlsx")
                
            except Exception as e:
                st.error(f"出錯了：{e}")
