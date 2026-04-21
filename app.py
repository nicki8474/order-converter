import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
import json
import re

st.set_page_config(page_title="訂單自動對轉工具", layout="centered")
st.title("📦 訂單自動對轉工具 (精準匹配版)")

with st.sidebar:
    st.header("1. 系統設定")
    api_key = st.text_input("輸入 Gemini API Key", type="password")
    st.info("建議使用 Gemini 1.5 Flash")

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
            st.success(f"總表載入成功！")
        else:
            st.error("找不到標題列，請確認 Excel 中有『品名』欄位")
    except Exception as e:
        st.error(f"讀取總表失敗：{e}")

st.header("3. 上傳訂單圖片")
uploaded_file = st.file_uploader("請上傳訂單照片", type=["jpg", "jpeg", "png"])

def clean_degree(d):
    """將各種度數寫法統一化 (例如 275 -> 2.75, 300 -> 3.00)"""
    d_str = str(d).replace(' ', '').replace('-', '')
    nums = re.findall(r"\d+\.?\d*", d_str)
    if not nums: return d_str
    val = float(nums[0])
    if val >= 100: val = val / 100.0 # 處理 275 變 2.75
    return f"{val:.2f}"

if uploaded_file and df_db is not None and api_key:
    img = Image.open(uploaded_file)
    st.image(img, caption="上傳的訂單", width=400)
    
    if st.button("🚀 開始智慧匹配"):
        with st.spinner("AI 深度辨識中..."):
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel("gemini-1.5-flash")
                
                prompt = """請辨識圖片訂單：
                1. 產品名稱 (如: 塩雪烏龍, 淨透潤)
                2. 度數 (如: 2.75, 3.00)
                3. 數量
                輸出 JSON 格式：[{"key": "產品名", "degree": "度數", "qty": 數量}]
                只需輸出 JSON，不要加標籤。"""
                
                response = model.generate_content([prompt, img])
                json_str = re.sub(r'```json|```', '', response.text).strip()
                items = json.loads(json_str)
                
                st.write("📝 AI 原始辨識結果：", items)
                
                final_results = []
                name_col = next((c for c in df_db.columns if "品名" in str(c)), None)
                
                if name_col:
                    for item in items:
                        # 關鍵字容錯 (處理常見異體字)
                        search_key = str(item['key']).replace('鹽', '塩')
                        target_deg = clean_degree(item['degree'])
                        
                        # 智慧比對：品名欄位包含關鍵字 且 (包含 2.75 或 2.750)
                        mask = (df_db[name_col].astype(str).str.contains(search_key, na=False, case=False)) & \
                               (df_db[name_col].astype(str).str.contains(target_deg, na=False) | 
                                df_db[name_col].astype(str).str.contains(target_deg.rstrip('0').rstrip('.'), na=False))
                        
                        match = df_db[mask]
                        
                        if not match.empty:
                            res_row = match.iloc[0].to_dict()
                            res_row['訂購數量'] = item['qty']
                            final_results.append(res_row)
                        else:
                            st.warning(f"⚠️ 無法在總表中找到：{search_key} 度數 {target_deg}")
                
                if final_results:
                    res_df = pd.DataFrame(final_results)
                    st.subheader("✅ 匹配成功")
                    st.table(res_df)
                    
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        res_df.to_excel(writer, index=False)
                    st.download_button(label="📥 下載 Excel", data=output.getvalue(), file_name="對轉結果.xlsx")
                else:
                    st.error("❌ 匹配失敗：請檢查總表品名是否與 AI 辨識出的文字一致。")
            except Exception as e:
                st.error(f"執行出錯：{e}")
