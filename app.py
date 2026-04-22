import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
import json
import re
import base64

# 1. 網頁配置
st.set_page_config(page_title="萬能訂單對轉工具", layout="wide")

# --- 💡 終極黑科技：全網頁監聽貼上事件 ---
# 這段代碼會讓網頁「隨時準備好」接收你的 Ctrl+V，不用點框框也會有反應
st.components.v1.html(
    """
    <script>
    const doc = window.parent.document;
    doc.addEventListener('paste', function(e) {
        const item = e.clipboardData.items[0];
        if (item.type.indexOf('image') !== -1) {
            const blob = item.getAsFile();
            const reader = new FileReader();
            reader.onload = function(event) {
                // 將圖片傳回 Streamlit
                const base64Data = event.target.result;
                window.parent.postMessage({type: 'pasted_image', data: base64Data}, '*');
            };
            reader.readAsDataURL(blob);
        }
    });
    </script>
    """,
    height=0,
)

st.title("📦 萬能訂單對轉工具")

# --- 2. 系統設定 (API Key) ---
api_key = st.secrets.get("GEMINI_API_KEY", "")
with st.sidebar:
    st.header("⚙️ 系統設定")
    if api_key:
        st.success("✅ API 已就緒")
    else:
        api_key = st.text_input("手動輸入 API Key", type="password")

# --- 3. 智慧載入產品總表 ---
st.header("📂 2. 載入產品總表")
uploaded_db = st.file_uploader("請上傳總表 (Excel/CSV)，AI 會自動學習格式", type=["xlsx", "csv"])

df_db = None
if uploaded_db:
    try:
        if uploaded_db.name.endswith('.csv'):
            temp_df = pd.read_csv(uploaded_db, header=None, dtype=str).fillna("")
        else:
            temp_df = pd.read_excel(uploaded_db, header=None, dtype=str).fillna("")
        
        header_row = 0
        for i, row in temp_df.iterrows():
            if "品名" in "".join(row.astype(str)):
                header_row = i
                break
        df_db = temp_df.iloc[header_row:].copy()
        df_db.columns = df_db.iloc[0]
        df_db = df_db[1:].reset_index(drop=True)
        st.success(f"✅ 資料庫載入成功")
    except Exception as e:
        st.error(f"讀取失敗: {e}")

# --- 4. 混合輸入區：貼圖 + 貼文字 ---
st.header("📝 3. 輸入訂單內容")
col_img, col_txt = st.columns(2)

with col_img:
    st.subheader("🖼️ 圖片來源 (不需存檔，直接貼上)")
    # 使用標準上傳框作為備案，並加強提示
    img_file = st.file_uploader("👉【請點我一下】變藍色後按 Ctrl+V，或直接把圖『拖』進來", type=["jpg", "png", "jpeg"])
    
with col_txt:
    st.subheader("✍️ 文字來源 (直接貼上文字)")
    text_input = st.text_area("或者直接在此貼上 Line 訂單文字", placeholder="例：淨透潤 450x12", height=125)

input_content = None
input_type = None

if img_file:
    input_content = Image.open(img_file)
    input_type = "image"
    st.image(input_content, caption="✅ 圖片已就緒", width=350)
elif text_input:
    input_content = text_input
    input_type = "text"

# --- 5. 智慧轉單執行 ---
if input_content and df_db is not None and api_key:
    if st.button("🚀 開始自動轉單", use_container_width=True):
        with st.spinner("AI 正在分析..."):
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel('gemini-1.5-flash')
                
                prompt = """提取訂單為 JSON 陣列：[{"key":"品名關鍵字", "degree":"度數", "qty":數量}]。
                注意：450度請轉為 4.50。只需 JSON。"""
                
                if input_type == "image":
                    response = model.generate_content([prompt, input_content])
                else:
                    response = model.generate_content(prompt + f"\n內容：{input_content}")
                
                clean_text = re.search(r'\[.*\]', response.text, re.DOTALL).group()
                items = json.loads(clean_text)
                
                final_results = []
                for item in items:
                    k = str(item.get('key','')).strip().replace('鹽', '塩')
                    try:
                        d_str = str(item.get('degree','')).replace("度","").replace("-","")
                        d_float = float(d_str)
                        if d_float >= 100: d_float /= 100.0
                        v2, v1, v0 = f"{d_float:.2f}", f"{d_float:.1f}", str(int(round(d_float * 100)))
                    except:
                        v2 = v1 = v0 = str(item.get('degree',''))

                    def check_match(row):
                        t = "".join(row.astype(str)).replace("-","").replace(" ","")
                        return k in t and (v2 in t or v1 in t or v0 in t)

                    match = df_db[df_db.apply(check_match, axis=1)]
                    if not match.empty:
                        res = match.iloc[0].to_dict()
                        res['訂購數量'] = item.get('qty', 0)
                        final_results.append(res)
                    else:
                        st.warning(f"🔍 辨識出「{k} / {v2}」，但總表無匹配。")

                if final_results:
                    st.subheader("📋 轉換結果")
                    res_df = pd.DataFrame(final_results)
                    st.dataframe(res_df, use_container_width=True)
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        res_df.to_excel(writer, index=False)
                    st.download_button("📥 下載轉單 Excel", output.getvalue(), "結果.xlsx", use_container_width=True)
                
            except Exception as e:
                st.error(f"出錯了: {e}")
