import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
import json

# 1. 網頁基本設定
st.set_page_config(page_title="訂單自動對轉工具", layout="centered")
st.title("📦 訂單自動對轉工具")
st.markdown("只需上傳圖片，自動比對總表並產出匯入檔。")

# --- 側邊欄設定 ---
with st.sidebar:
    st.header("1. 系統設定")
    api_key = st.text_input("輸入 Gemini API Key", type="password")
    st.info("請確保 API Key 正確無誤。")

# --- 2. 產品總表上傳 ---
st.header("2. 載入資料庫")
uploaded_db = st.file_uploader("請上傳您的「產品總表.xlsx」", type=["xlsx", "csv"])

if uploaded_db:
    try:
        if uploaded_db.name.endswith('.csv'):
            df_db = pd.read_csv(uploaded_db)
        else:
            df_db = pd.read_excel(uploaded_db)
        df_db.columns = df_db.columns.str.strip()
        st.success(f"成功載入 {len(df_db)} 筆產品資料！")
    except Exception as e:
        st.error(f"讀取總表失敗：{e}")

# --- 3. 圖片上傳與辨識 ---
st.header("3. 上傳訂單圖片")
uploaded_file = st.file_uploader("請上傳或貼上手寫單圖片", type=["jpg", "jpeg", "png"])

if uploaded_file and uploaded_db and api_key:
    img = Image.open(uploaded_file)
    st.image(img, caption="待處理訂單", width=400)
    
    if st.button("🚀 開始自動轉換"):
        with st.spinner("系統自動偵測可用 AI 模型中..."):
            try:
                # 配置 API
                genai.configure(api_key=api_key)
                
                # 【核心修正：自動偵測可用模型】
                try:
                    models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                    # 優先選 flash，沒 flash 選第一個可用的
                    target_model_name = next((m for m in models if 'flash' in m), models[0])
                    model = genai.GenerativeModel(model_name=target_model_name)
                    st.toast(f"使用模型: {target_model_name}")
                except Exception as m_err:
                    st.error("無法取得可用模型列表，請檢查 API Key 是否正確。")
                    st.stop()
                
                # 向 AI 發出指令
                prompt = """
                你是一個訂單處理專家。請辨識圖片中的產品、度數與數量。
                請輸出成 JSON 陣列格式：[{"key": "品名關鍵字", "degree": "度數", "qty": 數量}]
                例如：[{"key": "塩雪烏龍", "degree": "2.75", "qty": 1}]
                注意：只需輸出純 JSON 內容，不要包含 Markdown 標籤。
                """
                response = model.generate_content([prompt, img])
                
                # 解析 JSON
                raw_text = response.text.replace('```json', '').replace('```', '').strip()
                items = json.loads(raw_text)
                
                final_results = []
                # 在總表中進行智慧比對
                for item in items:
                    # 搜尋：品名同時包含「關鍵字」與「度數」
                    match = df_db[
                        (df_db['品名'].astype(str).str.contains(str(item['key']), na=False)) & 
                        (df_db['品名'].astype(str).str.contains(str(item['degree']), na=False))
                    ]
                    
                    if not match.empty:
                        res_row = match.iloc[0].to_dict()
                        res_row['數量'] = item['qty']
                        final_results.append(res_row)
                
                # 4. 顯示結果並提供下載
                if final_results:
                    res_df = pd.DataFrame(final_results)
                    st.subheader("✅ 轉換結果預覽")
                    st.table(res_df)
                    
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        res_df.to_excel(writer, index=False, sheet_name='訂單匯入')
                    
                    st.download_button(
                        label="📥 下載轉單 Excel",
                        data=output.getvalue(),
                        file_name="訂單結果.xlsx",
                        mime="application/vnd.ms-excel"
                    )
                else:
                    st.error("辨識成功，但總表中找不到對應的產品與度數。")
                    
            except Exception as e:
                st.error(f"執行出錯：{e}")
