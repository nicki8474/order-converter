import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
import json
import re

# 頁面配置
st.set_page_config(page_title="極速智慧轉單", layout="wide")
st.title("⚡ 極速智慧對轉工具 (穩定維護版)")

# --- 1. API 資源快取 (一勞永逸解決 404 與 慢速) ---
@st.cache_resource
def get_ai_model(api_key):
    try:
        genai.configure(api_key=api_key)
        # 自動偵測可用模型，避免 Google 門牌號碼變動導致 404
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        target = next((m for m in models if 'flash' in m), models[0])
        return genai.GenerativeModel(model_name=target)
    except Exception as e:
        st.error(f"模型初始化失敗: {e}")
        return None

# API Key 載入
api_key = st.secrets.get("GEMINI_API_KEY", "")
with st.sidebar:
    st.header("⚙️ 系統設定")
    if not api_key:
        api_key = st.text_input("輸入 API Key", type="password")
    else:
        st.success("✅ API 已就緒")

# --- 2. 總表快取 (提升比對速度) ---
@st.cache_data
def load_and_process_db(file):
    try:
        if file.name.endswith('.csv'):
            df = pd.read_csv(file, header=None, dtype=str).fillna("")
        else:
            df = pd.read_excel(file, header=None, dtype=str).fillna("")
        
        # 尋找包含「品名」的標題行
        h_row = 0
        for i, row in df.iterrows():
            if "品名" in "".join(row.astype(str)):
                h_row = i
                break
        df_clean = df.iloc[h_row:].copy()
        df_clean.columns = df_clean.iloc[0]
        return df_clean[1:].reset_index(drop=True)
    except Exception as e:
        st.error(f"總表解析失敗: {e}")
        return None

st.header("📂 1. 載入產品總表")
uploaded_db = st.file_uploader("上傳 Excel 或 CSV 總表", type=["xlsx", "csv"])

df_db = None
product_hint = ""

if uploaded_db:
    df_db = load_and_process_db(uploaded_db)
    if df_db is not None:
        # 提取關鍵字給 AI 參考，加速校正 (例：可泳棟 -> 可沐棕)
        unique_names = set()
        for name in df_db.iloc[:, 1].astype(str):
            clean_n = re.sub(r'[\d\.\-]+', '', name).strip()
            if len(clean_n) > 1: unique_names.add(clean_n[:10]) 
        product_hint = ", ".join(list(unique_names)[:80])
        st.success(f"✅ 總表載入成功 (共 {len(df_db)} 筆)")

# --- 3. 雙軌輸入區 ---
st.header("📝 2. 輸入訂單內容")
col1, col2 = st.columns(2)
with col1:
    img_file = st.file_uploader("🖼️ 圖片 (點擊或拖曳)", type=["jpg", "png", "jpeg"])
with col2:
    text_input = st.text_area("✍️ 文字 (Line 直接貼上)", height=150, placeholder="例如：可沐棕 450x12")

# --- 4. 執行轉單 (按鈕現在會永遠顯示) ---
st.markdown("---")
# 這裡加強了按鈕的可見度
if st.button("🚀 開始智慧轉單並比對資料庫", use_container_width=True):
    if not api_key:
        st.error("❌ 請先輸入 API Key")
    elif df_db is None:
        st.error("❌ 請先載入產品總表")
    elif not (img_file or text_input):
        st.error("❌ 請先輸入訂單內容 (圖片或文字)")
    else:
        with st.spinner("AI 快速辨識並與總表比對中..."):
            try:
                # 取得快取模型
                model = get_ai_model(api_key)
                if model:
                    # 智慧 Prompt
                    prompt = f"""
                    你是訂單解析助手。參考品名清單：[{product_hint}]
                    請提取 JSON 陣列：[{{ "key": "品名", "degree": "度數", "qty": 數量 }}]
                    注意：若字跡模糊，請校正為參考清單中的品名。450度需轉為 4.50。只需 JSON。
                    """
                    
                    # 決定輸入內容
                    content = Image.open(img_file) if img_file else text_input
                    response = model.generate_content([prompt, content] if img_file else prompt + f"\n內容：\n{text_input}")
                    
                    # 快速解析與比對
                    json_match = re.search(r'\[.*\]', response.text, re.DOTALL)
                    if json_match:
                        extracted_items = json.loads(json_match.group())
                        
                        final_res = []
                        for item in extracted_items:
                            k = str(item.get('key','')).strip().replace('鹽', '塩')
                            try:
                                # 度數三重比對 (學習 4.50, 4.5, 450)
                                d_f = float(str(item.get('degree','')).replace("度","").replace("-",""))
                                if d_f >= 100: d_f /= 100.0
                                vs = [f"{d_f:.2f}", f"{d_f:.1f}", str(int(round(d_f * 100)))]
                            except:
                                vs = [str(item.get('degree',''))]

                            # 快速搜尋
                            mask = df_db.apply(lambda r: k in "".join(r.astype(str)) and any(v in "".join(r.astype(str)) for v in vs), axis=1)
                            match = df_db[mask]
                            
                            if not match.empty:
                                r_data = match.iloc[0].to_dict()
                                r_data['訂購數量'] = item.get('qty', 0)
                                final_res.append(r_data)
                            else:
                                st.warning(f"🔍 辨識為「{k} / {vs[0]}」，但總表中查無項目。")

                        if final_res:
                            st.subheader("✅ 轉換結果")
                            result_df = pd.DataFrame(final_res)
                            st.dataframe(result_df, use_container_width=True)
                            
                            output = io.BytesIO()
                            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                                result_df.to_excel(writer, index=False)
                            st.download_button("📥 下載轉單 Excel", output.getvalue(), "智慧轉單結果.xlsx", use_container_width=True)
                    else:
                        st.error("AI 回傳格式異常，請再試一次")
                
            except Exception as e:
                st.error(f"執行出錯: {e}")
