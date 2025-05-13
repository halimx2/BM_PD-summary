import streamlit as st
import pandas as pd
import io
from report_extractor import parse_chat_text, extract_report_data

st.set_page_config(page_title="MI 2동 BM,PD 이력 정리", layout="wide")
st.title("📋 MI 2동 BM,PD 이력 정리")

uploaded_files = st.file_uploader(
    "채팅 txt 파일을 업로드해주세요 (여러 파일 선택 가능)",
    type="txt",
    accept_multiple_files=True
)

if uploaded_files:
    all_messages = []
    for uploaded_file in uploaded_files:
        content = uploaded_file.read().decode('utf-8')
        msgs = parse_chat_text(content)
        all_messages.extend(msgs)

    df = extract_report_data(all_messages)
    if df.empty:
        st.warning("유효한 리포트 데이터가 없습니다.")
    else:
        st.dataframe(df)
        # 엑셀 다운로드 준비
        towrite = io.BytesIO()
        with pd.ExcelWriter(towrite, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        towrite.seek(0)
        st.download_button(
            label="엑셀 파일 다운로드",
            data=towrite,
            file_name=f"report_{pd.Timestamp.now().strftime('%y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
else:
    st.info("왼쪽 상단에서 txt 파일을 드래그하거나 선택해주세요.")

# 실행: streamlit run streamlit_app.py
