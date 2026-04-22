import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
import json
import re

# 1. 網頁基本設定
st.set_page_config(page_title="訂單智慧對轉工具", layout="centered")
st.title("📦 訂單智慧對轉工具")

# --- 安全讀取 Key (從 Streamlit Secrets) ---
api_key = st.secrets.get("GEMINI_API_KEY", "")

with st.sidebar:
    st.header("1. 系統設定")
    if api_key:
        st.success("✅ 系統已就緒")
    else:
        api_key = st.text_input("輸入 Gemini API Key", type="password")
        st.info("請在 Streamlit 後台設定 Secrets 或在此手動輸入")

# --- 2. 產品總表上傳 ---
st.header("2. 載入資料庫")
uploaded_db = st.file_uploader("第一步：請上傳「產品總表」", type=["xlsx", "csv"])

df_db = None
if uploaded_db:
    try:
        if uploaded_db.name.endswith('.csv'):
            temp_df = pd.read_csv(uploaded_db, header=None, encoding_errors='ignore', dtype=str)
        else:
            temp_df = pd.read_excel(uploaded_db, header=None, dtype=str)
        
        # 自動尋找包含「品名」的那一行作為標題
        header_row_index = 0
        for i, row in temp_df.iterrows():
            row_content = "".join([str(x) for x in row.fillna("").values])
            if "品名" in row_content:
                header_row_index = i
                break
        
        df_db = temp_df.iloc[header_row_index:].copy()
        df_db.columns = df_db.iloc[0]
        df_db = df_db[1:].reset_index(drop=True)
        df_db.columns = [str(c).strip() for c in df_db.columns]
        st.success(f"✅ 總表載入成功，共 {len(df_db)} 筆資料")
    except Exception as e:
        st.error(f"讀取總表失敗：{e}")

# --- 3. 混合模式輸入 (支援貼上圖片、檔案、文字) ---
st.header("3. 輸入訂單內容")
tab1, tab2, tab3 = st.tabs(["📋 直接貼上圖片", "📁 上傳檔案", "✍️ 貼上文字"])

input_content = None
input_type = None

with tab1:
    st.write("💡 **請先截圖**，點擊下方框框後直接按 **Ctrl + V**：")
    pasted_file = st.file_uploader("貼上區", type=["jpg", "jpeg", "png"], label_visibility="collapsed")
    if pasted_file:
        input_content = Image.open(pasted_file)
        input_type = "image"
        st.image(input_content, caption="已偵測到貼上之圖片", width=300)

with tab2:
    uploaded_file = st.file_uploader("選擇訂單圖片檔案", type=["jpg", "jpeg", "png"])
    if uploaded_file:
        input_content = Image.open(uploaded_file)
        input_type = "image"
        st.image(input_content, width=300)

with tab3:
    text_input = st.text_area("在此貼上訂單文字內容 (例如：淨透潤 450度 12盒)", height=150)
    if text_input:
        input_content = text_input
        input_type = "text"

# --- 4. 執行辨識與比對 ---
if input_content and df_db is not None and api_key:
    if st.button("🚀 開始自動轉單"):
        with st.spinner("AI 正在努力辨識中..."):
            try:
                genai.configure(api_key=api_key)
                
                # 自動偵測可用模型，避免 404 錯誤
                available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                target_model_name = next((m for m in available_models if 'flash' in m), available_models[0])
                model = genai.GenerativeModel(model_name=target_model_name)

                if input_type == "image":
                    prompt = "提取訂單：產品名核心關鍵字、度數(數字)、數量。只需輸出 JSON 陣列，不需解釋。"
                    source = [prompt, input_content]
                else:
                    prompt = f"請從以下文字提取訂單：{input_content}。格式：[{{\"key\": \"產品關鍵字\", \"degree\": \"度數\", \"qty\": 數量}}]。只需輸出 JSON。"
                    source = [prompt]

                response = model.generate_content(source)
                # 處理可能的 Markdown 標籤
                json_str = re.sub(r'```json|```', '', response.text).strip()
                items = json.loads(json_str)
                
                final_results = []
                for item in items:
                    # 處理常見異體字：例如將 鹽 轉為 塩 (符合總表)
                    search_key = str(item['key']).strip().replace('鹽', '塩')
                    
                    # 處理度數格式 (將 450 轉為 4.50)
                    try:
                        d_val = float(item['degree'])
                        if d_val >= 100: d_val = d_val / 100.0
                        d_search = f"{d_val:.2f}"
                        d_search_alt = f"{d_val:.1f}"
                    except:
                        d_search = str(item['degree'])
                        d_search_alt = d_search

                    # 比對邏輯：檢查產品總表的每一行是否包含關鍵字與度數
                    def row_match(row):
                        full_row_str = "".join(row.fillna("").astype(str))
                        return search_key in full_row_str and (d_search in full_row_str or d_search_alt in full_row_str)

                    matched_rows = df_db[df_db.apply(row_match, axis=1)]
                    
                    if not matched_rows.empty:
                        res_row = matched_rows.iloc[0].to_dict()
                        res_row['訂購數量'] = item['qty']
                        final_results.append(res_row)
                
                if final_results:
                    res_df = pd.DataFrame(final_results)
                    st.subheader("✅ 轉換結果")
                    st.table(res_df)
                    
                    # 製作 Excel 下載
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        res_df.to_excel(writer, index=False)
                    st.download_button(label="📥 下載轉單 Excel", data=output.getvalue(), file_name="訂單結果.xlsx")
                else:
                    st.warning("⚠️ 辨識完成，但總表中找不到對應的產品。請檢查名稱或度數是否正確。")

            except Exception as e:
                if "429" in str(e):
                    st.error("❌ 今日免費額度已用完！請明天再試，或更換付費 Key。")
                elif "404" in str(e):
                    st.error("❌ 找不到 AI 模型。請檢查 API Key 是否正確或稍後再試。")
                else:
                    st.error(f"系統出錯：{e}")
else:
    if not api_key:
        st.info("💡 請先在側邊欄輸入 API Key")
    elif uploaded_db is None:
        st.info("💡 請先上傳產品總表")
    elif input_content is None:
        st.info("💡 請輸入訂單內容 (圖片或文字)")
