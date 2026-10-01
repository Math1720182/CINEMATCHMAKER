import streamlit as st

with open("README.md", "r", encoding="utf-8") as fichier:
    contenu = fichier.read()

st.image("logo_white_png.png", width = 300)

with st.container(width = 800):
    st.markdown(contenu)
    
st.space(200)
