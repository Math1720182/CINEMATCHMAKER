import os
import pandas as pd
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from IPython.display import Image
import requests
from dotenv import load_dotenv
import streamlit as st
import streamlit.components.v1 as components
from google.oauth2 import service_account
import io
from google.cloud import storage
import gcsfs
import pyarrow as pa
from scipy.sparse import load_npz
import json

#region Title
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Caveat:wght@600&family=Inter:wght@400;600;700&display=swap');

    .hero-title {
        font-family: 'Inter', sans-serif;
        font-size: 2.8rem;
        font-weight: 700;
        color: #000000;
        margin-top: 0px;
        margin-bottom: 0px;
        margin-left: 180px;
    }
    
    .hero-title-handwritten {
        font-family: 'Caveat', cursive;
        font-size: 3.5rem;
        color: #00D2C8; /* Couleur cyan / turquoise */
        margin-left:10px;
    }
    </style>
    """, unsafe_allow_html=True)

st.markdown("""
    <div style="display: flex; align-items: baseline; margin-bottom: 10px;">
        <span class="hero-title">Welcome to Cine</span>
        <span class="hero-title-handwritten">MatchMaker!</span>
    </div>
""", unsafe_allow_html=True)
#endregion

#Step 1: Load and transform

gcp_key_env = os.getenv("GCP_SERVICE_ACCOUNT_KEY")

if gcp_key_env:
    info_key = json.loads(gcp_key_env)
else:
    info_key = dict(st.secrets["gcp_service_account"])

key_google = (service_account.Credentials.from_service_account_info(info_key)).with_scopes(["https://www.googleapis.com/auth/devstorage.read_only"])

fs = gcsfs.GCSFileSystem(token=key_google,default_fill_target=0)


@st.cache_data(show_spinner=False)
def load_and_transform():
    
    df = pd.read_parquet("gs://cinematchmaker/load_and_transform/df_from_load_and_transform.parquet",filesystem=fs,)

    df_vector_2D = load_npz(fs.open("gs://cinematchmaker/load_and_transform/df_vector_2D_from_load_and_transform.npz"))

    return df, df_vector_2D

df, df_vector_2D = load_and_transform()


#API KEY AND URL_DATABASE
load_dotenv()
try:
    if "API_KEY_TMDB" in st.secrets:
        st.session_state.api_key = st.secrets["API_KEY_TMDB"]
except:
    st.session_state.api_key = os.getenv("API_KEY_TMDB")

parameters = {"api_key": st.session_state.api_key}

#------Trending movies-----------------------
URL = "https://api.themoviedb.org/3/trending/all/week"
URL_base_image = "https://image.tmdb.org/t/p/w300/"

reponse = requests.get(URL, params = parameters)
trend = reponse.json()

st.markdown("### Trending movies")

movie1, movie2, movie3, movie4, movie5 = st.columns(5)
with movie1:
    st.image(URL_base_image + trend["results"][0]["poster_path"])
with movie2:
    st.image(URL_base_image + trend["results"][1]["poster_path"])
with movie3:
    st.image(URL_base_image + trend["results"][2]["poster_path"])
with movie4:
    st.image(URL_base_image + trend["results"][3]["poster_path"])
with movie5:
    st.image(URL_base_image + trend["results"][4]["poster_path"])

st.divider()

#---------------------------------

#region Step 2 : ------ Content engine ----- (similarity by content)

#User profile
if "selected_movie" not in st.session_state:
    st.session_state["selected_movie"] = None

st.markdown("## Movies recommendation")

st.markdown("### Please log-in to save your favorite movies and see your personnal recommendation!")
st.space()

