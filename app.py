import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
import json
import re

# 1. 網頁基本設定
st.set_page_config(page_title="訂單自動對轉工具", layout="centered")
st.title("📦 訂單自動對轉工具 (穩定修正版)")

# --- 側邊欄設定 ---
with st.sidebar:
    st.header("1. 系統設定")
    api_key = st.text_input("輸入 Gemini API Key", type="password")
    st.info("💡 提示：若出現 404，系統會自動嘗試搜尋可用模型。")

# --- 2. 產品總表上傳 ---
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
            st.error("找不到標題列，請確認 Excel 中有『品名』欄位")
    except Exception as e:
        st.error(f"讀取總表失敗：{e}")

# --- 3. 圖片上傳與辨識 ---
st.header("3. 上傳訂單圖片")
uploaded_file = st.file_uploader("請上傳訂單照片", type=["jpg", "jpeg", "png"])

def clean_degree(d):
    d_str = str(d).replace(' ', '').replace('-', '')
    nums = re.findall(r"\d+\.?\d*", d_str)
    if not nums: return d_str
    val = float(nums[0])
    if val >= 100: val = val / 100.0
    return f"{val:.2f}"

if uploaded_file and df_db is not None and api_key:
    img = Image.open(uploaded_file)
    st.image(img, caption="上傳的訂單", width=400)
    
    if st.button("🚀 開始智慧匹配"):
        with st.spinner("AI 正在偵測模型並辨識中..."):
            try:
                # 配置 API
                genai.configure(api_key=api_key)
                
                # 【核心修正：自動偵測可用模型名】
                available_models = []
                for m in genai.list_models():
                    if 'generateContent' in m.supported_generation_methods:
                        available_models.append(m.name)
                
                # 優先權：1.5-flash > 1.0-pro > 第一個可用的
                target_model = None
                for m_name in available_models:
                    if "gemini-1.5-flash" in m_name:
                        target_model = m_name
                        break
                if not target_model:
                    target_model = available_models[0]
                
                model = genai.GenerativeModel(model_name=target_model)
                st.toast(f"成功連線模型: {target_model}")

                prompt = """請辨識圖片訂單，輸出 JSON：
                [{"key": "產品名", "degree": "度數", "qty": 數量}]
                例如：[{"key": "塩雪烏龍", "degree": "2.75", "qty": 1}]
                只需輸出 JSON，不要加任何標籤或文字。"""
                
                response = model.generate_content([prompt, img])
                json_str = re.sub(r'```json|```', '', response.text).strip()
                items = json.loads(json_str)
                
                st.write("📝 AI 辨識到的內容：", items)
                
                final_results = []
                name_col = next((c for c in df_db.columns if "品名" in str(c)), None)
                
                if name_col:
                    for item in items:
                        search_key = str(item['key']).replace('鹽', '塩')
                        target_deg = clean_degree(item['degree'])
                        
                        mask = (df_db[name_col].astype(str).str.contains(search_key, na=False, case=False)) & \
                               (df_db[name_col].astype(str).str.contains(target_deg, na=False) | 
                                df_db[name_col].astype(str).str.contains(target_deg.rstrip('0').rstrip('.'), na=False))
                        
                        match = df_db[mask]
                        if not match.empty:
                            res_row = match.iloc[0].to_dict()
                            res_row['訂購數量'] = item['qty']
                            final_results.append(res_row)
                        else:
                            st.warning(f"⚠️ 總表中找不到：{search_key} ({target_deg})")
                
                if final_results:
                    res_df = pd.DataFrame(final_results)
                    st.table(res_df)
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        res_df.to_excel(writer, index=False)
                    st.download_button(label="📥 下載 Excel", data=output.getvalue(), file_name="對轉結果.xlsx")
                else:
                    st.error("❌ 比對失敗：AI 有認到字，但總表品名對不起來。")
            except Exception as e:
                st.error(f"執行出錯：{e}")
