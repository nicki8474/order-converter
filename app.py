with tab1:
    # 加強提示文字，告訴使用者可以直接貼上
    st.markdown("### 📸 圖片處理區")
    st.write("請直接按 **Ctrl + V** 貼上截圖，或將檔案拖到下方：")
    uploaded_file = st.file_uploader("", type=["jpg", "jpeg", "png"], help="點擊此處會開啟視窗，但您可以直接在網頁任何地方按 Ctrl+V 貼上")
    
    if uploaded_file:
        input_content = Image.open(uploaded_file)
        input_type = "image"
        st.image(input_content, caption="✅ 偵測到圖片，準備處理", width=300)
