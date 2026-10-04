
#----------LOAD AND TRANSFORM--------------

import streamlit as st
import pandas as pd
import numpy as np
from sklearn.preprocessing import MaxAbsScaler
from sklearn.feature_extraction.text import TfidfVectorizer
from scipy.sparse import csr_matrix
import os
from dotenv import load_dotenv
import json
from google.oauth2 import service_account
import gcsfs


#Google Cloud Call

gcp_key_env = os.getenv("GCP_SERVICE_ACCOUNT_KEY")

if gcp_key_env:
    info_key = json.loads(gcp_key_env)
else:
    info_key = dict(st.secrets["gcp_service_account"])

key_google = (service_account.Credentials.from_service_account_info(info_key)).with_scopes(["https://www.googleapis.com/auth/devstorage.read_write"])

fs = gcsfs.GCSFileSystem(
    token=key_google,
    default_fill_target=0
)

file_path_df_merged_scrapped = "gs://cinematchmaker/parquet/df_merged_scrapped.parquet"
file_path_tags = "gs://cinematchmaker/parquet/tags.parquet"
file_path_df_tags_tmdb = "gs://cinematchmaker/parquet/df_tags_tmdb.parquet"


@st.cache_data(show_spinner=False)
def load_and_transform():

    #Import data
    df_movie = pd.read_parquet(file_path_df_merged_scrapped,filesystem=fs)
    df_tags = pd.read_parquet(file_path_tags,filesystem=fs)
    df_tags_tmdb = pd.read_parquet(file_path_df_tags_tmdb,filesystem=fs)

    #1. Filter movies
    df_movie = df_movie[
        (df_movie['release'] == "Released") & 
        (df_movie['runtime'] > 70) & 
        (df_movie['vote_count'] > 500)
    ].reset_index(drop=True)

    #2. MovieLens tags
    tag_counts = df_tags['tag'].value_counts()
    tags_populaires = tag_counts[tag_counts >= 30].index
    df_tags_filtre = df_tags[df_tags['tag'].isin(tags_populaires)]

    matrix_ml = pd.crosstab(df_tags_filtre['movieId'], df_tags_filtre['tag'])
    matrix_ml = np.log10(matrix_ml + 1) #Log = less weight for cosine similarity
    matrix_ml = matrix_ml.merge(df_movie[['movieId', 'tmdbId']], on='movieId', how='inner') #adding TMDBID
    matrix_ml = matrix_ml.drop(columns=['movieId'])
    matrix_ml = matrix_ml.drop_duplicates(subset=['tmdbId'])
    matrix_ml = matrix_ml.set_index('tmdbId')
    matrix_ml.columns = matrix_ml.columns.str.lower().str.strip()

    # 3.TMDb Tags (TF-IDF)
    df_tags_tmdb['tags_text'] = df_tags_tmdb['tags'].fillna("").str.replace('|', ' ', regex = False).str.lower().str.strip()

    vectorizer = TfidfVectorizer(min_df = 40)
    tfid_matrix = vectorizer.fit_transform(df_tags_tmdb['tags_text'])

    matrix_tmdb = pd.DataFrame(
        tfid_matrix.toarray(),
        index = df_tags_tmdb['tmdbId'],
        columns = vectorizer.get_feature_names_out()
    )

    matrix_tmdb.columns = matrix_tmdb.columns.str.lower().str.strip()

    #4. ML genres
    df_genre = df_movie['genres'].str.get_dummies(sep='|')
    if "(no genres listed)" in df_genre.columns:
        df_genre = df_genre.drop(columns="(no genres listed)")
        
    df_genre['tmdbId'] = df_movie['tmdbId'].values

    #5. Combining 2 tags matrices
    df_tags_matrix = matrix_ml.add(matrix_tmdb, fill_value = 0)

    #6.Normalized data tags
    scaler = MaxAbsScaler()
    tags_scaled = scaler.fit_transform(df_tags_matrix)
    df_tags_matrix = pd.DataFrame(tags_scaled, index=df_tags_matrix.index, columns=df_tags_matrix.columns)

    #7. Final fusion
    df_vector = pd.merge(df_genre, df_tags_matrix, on = 'tmdbId', how='left').fillna(0)
    df_vector = df_vector.drop_duplicates(subset=['tmdbId'])
    df_vector = df_vector.set_index('tmdbId').reindex(df_movie['tmdbId']).fillna(0)
    
    df_vector_2D = df_vector.values.astype('float32')
    df_vector_2D = csr_matrix(df_vector_2D)

    df = df_movie.copy()
    df['title'] = df['title'].astype('category')

    return df, df_vector_2D

