import streamlit as st
from google.protobuf.json_format import MessageToDict


st.set_page_config(page_title="Simple Frontend", page_icon="📈", layout="wide")

st.title("📈 Simple Trading Frontend")

st.markdown("""
This is a minimal Streamlit frontend for your trading strategy.<br>
You can customize further as needed.
""", unsafe_allow_html=True)

if st.button("Start Trading"):
    st.success("Trading started! (This is a placeholder action)")

if st.button("Stop Trading"):
    st.warning("Trading stopped! (This is a placeholder action)")

st.info("Live trading data and controls would appear here in a real implementation.")

