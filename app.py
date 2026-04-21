import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
import json
import re

st.set_page_config(page_title="訂單智慧對轉工具", layout="centered")
st.title("📦 訂單智慧對轉工具 (地毯式搜索版)")

with st.sidebar:
    st.header("1. 系統設定")
    api_key = st.text_input("輸入 Gemini API Key", type="password")

st.header("2. 載入資料庫")
uploaded_db = st.file_uploader("請上傳您的「產品總表.xlsx」", type=["xlsx", "csv"])

df_db = None
if uploaded_db:
    try:
        # 自動偵測編碼讀取 CSV
        if uploaded_db.name.endswith('.csv'):
            temp_df = pd.read_csv(uploaded_db, header=None, encoding_errors='ignore')
        else:
            temp_df = pd.read_excel(uploaded_db, header=None)
        
        # 尋找標題列
        header_row_index = 0
        for i, row in temp_df.iterrows():
            row_str = "".join(row.astype(str).values)
            if "品名" in row_str or "貨號" in row_str:
                header_row_index = i
                break
        
        df_db = temp_df.iloc[header_row_index:].copy()
        df_db.columns = df_db.iloc[0]
        df_db = df_db[1:].reset_index(drop=True)
        df_db.columns = [str(c).strip() for c in df_db.columns]
        st.success("總表載入成功！")
    except Exception as e:
        st.error(f"讀取總表失敗：{e}")

st.header("3. 上傳訂單圖片")
uploaded_file = st.file_uploader("請上傳訂單照片", type=["jpg", "jpeg", "png"])

if uploaded_file and df_db is not None and api_key:
    img = Image.open(uploaded_file)
    st.image(img, caption="上傳的訂單", width=400)
    
    if st.button("🚀 開始地毯式搜索"):
        with st.spinner("正在逐行比對總表資料..."):
            try:
                genai.configure(api_key=api_key)
                models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                target_model = next((m for m in models if 'flash' in m), models[0])
                model = genai.GenerativeModel(model_name=target_model)

                prompt = """你是一個訂單專家。提取：產品名(如: 淨透潤, 烏龍, 伯爵)、度數(數字)、數量。
                注意：450 視為 4.50, 600 視為 6.00。
                輸出 JSON：[{"key": "產品名", "degree": "度數數字", "qty": 數量}]"""
                
                response = model.generate_content([prompt, img])
                json_str = re.sub(r'```json|```', '', response.text).strip()
                items = json.loads(json_str)
                
                st.write("🔍 AI 提取內容：", items)
                
                final_results = []
                # 取得品名欄位名稱
                name_col = next((c for c in df_db.columns if "品名" in str(c)), None)
                
                if name_col:
                    for item in items:
                        # --- 暴力匹配邏輯 ---
                        raw_key = str(item['key']).strip().replace('鹽', '塩')
                        # 處理度數：統一成 4.50 這種格式
                        try:
                            d_val = float(item['degree'])
                            if d_val >= 100: d_val = d_val / 100.0
                            d_search = f"{d_val:.2f}"
                            d_search_alt = f"{d_val:.1f}"
                        except:
                            d_search = str(item['degree'])
                            d_search_alt = d_search

                        # 這裡是「地毯式搜索」：直接對每一列品名進行全文掃描
                        # 只要 (品名包含關鍵字) 且 (品名包含 4.50 或 4.5)
                        matched_rows = df_db[
                            (df_db[name_col].astype(str).str.contains(raw_key, na=False, case=False)) & 
                            (df_db[name_col].astype(str).str.contains(d_search, na=False) | 
                             df_db[name_col].astype(str).str.contains(d_search_alt, na=False))
                        ]
                        
                        if not matched_rows.empty:
                            # 抓到後，保留總表所有欄位
                            res_row = matched_rows.iloc[0].to_dict()
                            res_row['訂購數量'] = item['qty']
                            final_results.append(res_row)
                        else:
                            # 如果真的找不到，試試看只用「度數」找
                            st.warning(f"⚠️ 找不到「{raw_key} {d_search}」，請確認總表是否有這款產品。")
                
                if final_results:
                    res_df = pd.DataFrame(final_results)
                    st.subheader("✅ 轉換成功")
                    st.table(res_df)
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        res_df.to_excel(writer, index=False)
                    st.download_button(label="📥 下載 Excel", data=output.getvalue(), file_name="對轉結果.xlsx")
                
            except Exception as e:
                st.error(f"出錯了：{e}")
