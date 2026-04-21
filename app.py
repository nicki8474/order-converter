import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
import json
import re

st.set_page_config(page_title="訂單智慧對轉工具", layout="centered")
st.title("🚀 訂單智慧對轉工具 (度數自動修正版)")

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
uploaded_file = st.file_uploader("請上傳照片", type=["jpg", "jpeg", "png"])

if uploaded_file and df_db is not None and api_key:
    img = Image.open(uploaded_file)
    st.image(img, caption="上傳的訂單", width=400)
    
    if st.button("🚀 開始智慧匹配"):
        with st.spinner("AI 正在校正度數並比對中..."):
            try:
                genai.configure(api_key=api_key)
                models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                target_model = next((m for m in models if 'flash' in m), models[0])
                model = genai.GenerativeModel(model_name=target_model)

                prompt = """你是一個訂單處理員。請從圖片提取：
                1. 產品名稱 (如: 烏龍, 淨透潤, 白露, 紅韻, 伯爵)
                2. 度數 (如果是450請直接輸出4.50，如果是550請輸出5.50)
                3. 數量
                輸出 JSON 陣列：[{"key": "名稱", "degree": "度數", "qty": 數量}]"""
                
                response = model.generate_content([prompt, img])
                json_str = re.sub(r'```json|```', '', response.text).strip()
                items = json.loads(json_str)
                
                st.write("🔍 AI 辨識與校正後：", items)
                
                final_results = []
                name_col = next((c for c in df_db.columns if "品名" in str(c)), None)
                
                if name_col:
                    for item in items:
                        raw_key = str(item['key']).strip().replace('鹽', '塩')
                        
                        # --- 強大度數校正邏輯 ---
                        try:
                            d_val = float(item['degree'])
                            # 如果 AI 給的是 450 這種整數，自動除以 100
                            if d_val >= 100:
                                d_val = d_val / 100.0
                            
                            # 產生所有可能的格式去總表撈：4.50, 4.5, 4.500
                            d_search_list = [
                                f"{d_val:.2f}",
                                f"{d_val:.1f}",
                                str(d_val).rstrip('0').rstrip('.')
                            ]
                        except:
                            d_search_list = [str(item['degree'])]

                        # 模糊比對：品名包含關鍵字 且 包含任一種度數格式
                        mask = (df_db[name_col].astype(str).str.contains(raw_key, na=False, case=False)) & \
                               (df_db[name_col].astype(str).apply(lambda x: any(v in x for v in d_search_list)))
                        
                        match = df_db[mask]
                        
                        if not match.empty:
                            res_row = match.iloc[0].to_dict()
                            res_row['訂購數量'] = item['qty']
                            final_results.append(res_row)
                        else:
                            st.warning(f"❌ 找不到：{raw_key} (嘗試度數: {d_search_list})")
                
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
