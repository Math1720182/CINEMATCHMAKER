import os
import pandas as pd
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from IPython.display import Image
import requests
from dotenv import load_dotenv
import streamlit as st
import streamlit.components.v1 as components
import psycopg2
import json
from google.oauth2 import service_account
import io
from google.cloud import storage
import gcsfs
import pyarrow as pa
from scipy.sparse import load_npz

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

#Google Cloud Call

gcp_key_env = os.getenv("GCP_SERVICE_ACCOUNT_KEY")

if gcp_key_env:
    info_key = json.loads(gcp_key_env)
else:
    info_key = dict(st.secrets["gcp_service_account"])

key_google = (service_account.Credentials.from_service_account_info(info_key)).with_scopes(["https://www.googleapis.com/auth/devstorage.read_only"])

fs = gcsfs.GCSFileSystem(token=key_google,default_fill_target=0)

file_path_ratings_augmented = "gs://cinematchmaker/parquet/ratings_augmented.parquet"


#For embedded matrice 
client = storage.Client(credentials=key_google)
bucket = client.bucket("cinematchmaker")
blob = bucket.blob("movie_embeddings.npy")
file_in_memory = io.BytesIO(blob.download_as_bytes())


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

@st.cache_data
def get_trending_movies(api_key, parameters):
    URL = "https://api.themoviedb.org/3/trending/all/week"
    URL_base_image = "https://image.tmdb.org/t/p/w300/"

    reponse = requests.get(URL, params = parameters)
    return reponse.json(), URL_base_image

trend, URL_base_image = get_trending_movies(st.session_state.api_key, parameters)

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

st.header("Your recommendation", text_alignment = "center")


if "movie_index_user" not in st.session_state:
    st.session_state["movie_index_user"] = 1

if "API_KEY" not in st.session_state:
    st.session_state.api_key = None

#Min in hour function
def min_in_hour(movie_duration):
    hour = movie_duration // 60
    minute = movie_duration % 60
    return hour, minute


#-------Recommendation algorithm----------

def find_user_id(username = None, google_sub = None):
    conn = psycopg2.connect(URL_DATABASE)
    cur = conn.cursor()

    if google_sub:
        cur.execute("SELECT id FROM users WHERE google_sub = %s;", (google_sub,))
    else:
        cur.execute("SELECT id FROM users WHERE username = %s;", (username,))

    user = cur.fetchone()
    cur.close()
    conn.close()
    return user[0] if user else None

@st.cache_data
def load_model_and_data():
    movie_embeddings = np.load(file_in_memory)
    return movie_embeddings

def find_movie(user_id, url_database):
    conn = psycopg2.connect(url_database)
    cur = conn.cursor()
    cur.execute("SELECT tmdb_id, note, date_added FROM user_movies WHERE user_id = %s;", (str(user_id),))
    movies = cur.fetchall()
    cur.close()
    conn.close()
    return movies

with st.spinner("We made your personnal recommendation..."):
    movie_embeddings = load_model_and_data()

try:
    URL_DATABASE = st.secrets['URL_DATABASE_RAILWAY']
except:
    URL_DATABASE = os.getenv("URL_DATABASE_LOCAL")


if st.user and st.user.get("is_logged_in", False):
    user_id = find_user_id(google_sub=st.user["sub"])
elif st.session_state.get("user") is not None:
    user_id = find_user_id(username=st.session_state["user"]["username"])


if "df_sorted_user" not in st.session_state:
    st.session_state["df_sorted_user"] = None

if "movie_added" not in st.session_state:
    st.session_state["movie_added"] = False


movies_user = find_movie(user_id, URL_DATABASE)

#Select platforms
platforms = [
    "Netflix", "Disney Plus", "Amazon Prime Video", "Apple TV", 
    "HBO Max", "Canal+", "Paramount Plus", "Hulu", "Sooner"]

if len(movies_user) >= 4:
    selection = st.pills("", options=platforms, selection_mode="multi")

if len(movies_user) >= 4:

    if st.session_state["df_sorted_user"] is None or st.session_state["movie_added"]:
        
        with st.spinner("We made your personnal recommendation..."):
            watched_movie_ids = []
            ratings = []


            movies = movies_user


            for item in movies:
                tmdb_id_str = str(item[0])
                tmdb_id = int(item[0])
                note = item[1]

                film_filtre = df[df["tmdbId"] == tmdb_id]

                if not film_filtre.empty and pd.notna(film_filtre.iloc[0]["movie_idx"]):
                    idx = film_filtre.iloc[0]["movie_idx"]
                    watched_movie_ids.append(int(idx))
                    ratings.append(note)
                else: #If the movie is not in the DB (COLD START)
                    #Filter movie user and df by genre to avoid unrelated movies
                    movie_user_index = df[df['tmdbId'] == tmdb_id].index[0]
                    movie_user_index_genre = df.loc[movie_user_index, 'genre']
                    mask_genre = df['genre'].str.contains(movie_user_index_genre, na = False)
                    indices_filtres = df[mask_genre].index
            
                    df_favorite_vector = df_vector_2D[[movie_user_index]]
            
                    df_vector_2D_filtered = df_vector_2D[indices_filtres]
                    
                    #Cosine similarity
                    similarites = cosine_similarity(df_favorite_vector, df_vector_2D_filtered)
                    df['cosine_similarity'] = np.float64(0.0)
                    df.loc[indices_filtres, 'cosine_similarity'] = similarites[0]

                    df_coldstart = df.sort_values(by=['cosine_similarity'], ascending=False)
                    df_coldstart = df_coldstart[df_coldstart['movieId'].notna()]

                    watched_movie_ids.append(int(df_coldstart['movie_idx'].iloc[0]))
                    ratings.append(note)

            if watched_movie_ids:
                ratings_arr = np.array(ratings, dtype=float)
                weights = ratings_arr - 3.0 
                movie_vectors = movie_embeddings[watched_movie_ids]

                user_profile_vector = weights @ movie_vectors 
                user_profile_vector = np.asarray(user_profile_vector).reshape(1, -1)
                
                similarities = cosine_similarity(user_profile_vector, movie_embeddings)[0]

                for idx in watched_movie_ids:
                    similarities[idx] = -np.inf

                indices_tries = np.argsort(similarities)
                top_indices = indices_tries[::-1]

                df_unique = df.drop_duplicates(subset=["movie_idx"]).dropna(subset=["movie_idx"])

                top_movies = df_unique[df_unique["movie_idx"].isin(top_indices)]
                top_movies["movie_idx"] = pd.Categorical(top_movies["movie_idx"], categories=top_indices, ordered=True)

                st.session_state["df_sorted_user"] = top_movies.sort_values("movie_idx").reset_index(drop=True)

                if "movie_index_user" not in st.session_state:
                    st.session_state["movie_index_user"] = 0
                
                st.session_state["movie_added"] = False

else:
    if len(movies_user) == 0:
        col1, col2, col3 = st.columns([1, 10, 1])
        with col2:
            st.markdown("#### Save a few movies you like to unlock your personalized recommendations!")

        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("🍿 **Save movies now**", use_container_width=True):
                st.switch_page("pages/my_movies.py")
    elif len(movies_user) > 0 and len(movies_user) < 4:
        st.markdown("### You need to add at least 4 movies to see your personnal recommendation 🚀")
        if st.button("🍿 **Save movies now**", use_container_width=True):
                        st.switch_page("pages/my_movies.py")

    st.space(300)

#st.write(df_coldstart)
#st.write(watched_movie_ids)
#st.write(ratings)

if st.session_state["df_sorted_user"] is not None and len(movies_user) > 0:
    df_sorted = st.session_state["df_sorted_user"].copy()
    
    if selection:
        df_sorted = df_sorted[df_sorted["provider"].isin(selection)].reset_index(drop=True)
        
    if "movie_index_user" in st.session_state and st.session_state["movie_index_user"] >= len(df_sorted):
        st.session_state["movie_index_user"] = 0


#region --------API CALL & LAYOUT---------

#API CALL for MOVIES
@st.cache_data
def get_tmdb_movie_data(tmdbID, parameters):
    URL = f"https://api.themoviedb.org/3/movie/{tmdbID}?append_to_response=watch/providers,credits,videos"
    response = requests.get(URL, params= parameters)

    if response.status_code == 200:
        return response.json()
    return None

#Extract from response

def next_movie(max_index):
    current = st.session_state["movie_index_user"]
    st.session_state["movie_index_user"] = min(current + 1, max_index)

def previous_movie():
    current = st.session_state["movie_index_user"]
    st.session_state["movie_index_user"] = max(current - 1, 0)

def reset_movie():
    st.session_state["movie_index_user"] = 1

if "movie_index_user" not in st.session_state:
    st.session_state["movie_index_user"] = 0

if len(movies_user) > 0:
    if st.session_state["df_sorted_user"] is not None:


        movie_index = st.session_state["movie_index_user"]
        tmdbID = df_sorted.iloc[movie_index]['tmdbId']

        data_movie = get_tmdb_movie_data(tmdbID, parameters)

        if data_movie:
            chemin_poster = data_movie.get('poster_path')

            #Poster
            if chemin_poster:
                URL_base_image = "https://image.tmdb.org/t/p/w300/"
                poster_layout = URL_base_image + chemin_poster
            else:
                poster_layout = None

            #Provider image
            try:
                provider_path = data_movie['watch/providers']['results']['FR']['flatrate'][0]['logo_path']
                provider_layout = URL_base_image + provider_path
            except (KeyError, IndexError):
                provider_layout = None

            #Overview
            overview_layout = data_movie['overview']
            
            #Runtime
            runtime = data_movie['runtime']

            #Genre
            genre_list = []
            for genre in data_movie['genres']:
                genre_list.append(genre["name"])

            genre_sentence = ", ".join(genre_list)


            #Notation
            notation = int(data_movie['vote_average']*10)

            # Director
            data_credits = data_movie['credits']

            if data_credits != None:
                director = 'No director'
                for credit in range(0, len(data_credits['crew'])):
                    if data_credits['crew'][credit]["job"] == "Director":
                        director = data_credits['crew'][credit]["original_name"]
                        break
            else:
                director = "Error accessing cast and crew"

            # Acting
            if data_credits != None:
                cast = []
                for actor in data_credits['cast'][:4]:
                    if actor["known_for_department"] == "Acting":
                        dico = {}
                        dico['name'] = actor['original_name']
                        dico['role'] = actor['character']
                    
                        if actor['profile_path']:
                            dico['image'] = "https://image.tmdb.org/t/p/w300" + actor['profile_path']
                        else:
                            dico['image'] = ""

                        cast.append(dico)
            else:
                st.warning("No cast")

            # Trailer
            YT_path = "https://www.youtube.com/watch?v="
            data_trailer = data_movie['videos']

            if data_trailer != None:
                trailer_path = None
                for key in range(0, len(data_trailer['results'])):
                    if data_trailer['results'][key]['type'] == "Trailer":
                        trailer_path = data_trailer['results'][key]['key']
                        trailer_name = data_trailer['results'][key]['name']
                        trailer_path = YT_path + trailer_path
                        break
            else:
                st.write("No trailer available")


            #LAYOUT
            st.space(30)

            #region Score circle function
            if notation >= 75:
                couleur = "#2ed573"
            elif notation >= 50:
                couleur = "#ffa502"
            else:
                couleur = "#ff4757"

            cercle_html = f"""
            <div style="
                display: flex;
                align-items: center;
                gap: 15px; 
            ">
                <span style="
                    font-weight: bold;
                    font-size: 16px;
                    color: #000000;
                "
                >
                    User notation (TMDB)
                </span>
                <!-- OUTER CIRCLE -->
                <div style="
                    width: 70px;
                    aspect-ratio: 1 / 1; 
                    flex-shrink: 0;      
                    border-radius: 50%;
                    background: conic-gradient({couleur} {notation}%, #e0e0e0 {notation}% 100%);
                    display: flex;
                    justify-content: center;
                    align-items: center;
                ">
                    <!-- INNER CIRCLE -->
                    <div style="
                        width: 55px;
                        aspect-ratio: 1 / 1;
                        flex-shrink: 0;
                        border-radius: 50%;
                        background-color: #FFFFFF; 
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        color: #000000;
                        font-size: 19px;
                        font-weight: bold;
                    ">
                        {notation}%
                    </div>
                </div>
            </div>
            """

            col1, col2 = st.columns([1, 1.5])

            with col1:
                if poster_layout != "Not found":
                    st.image(poster_layout)
                else:
                    st.warning("No poster available")

                provider_col1, provider_col2, provider_col3 = st.columns([1.5, 3.5, 3], gap = "small", vertical_alignment="center")
                if provider_layout != None:
                    with provider_col2:

                        st.write("##### Watch it on")
                    with provider_col3:
                        st.image(provider_layout, width=50)
                else:
                    with provider_col2:
                        st.write("**No provider**")
                #Button
                st.write("")
                col_prev, col_next, col_reset = st.columns([1.2,1,1.5], gap = "small", vertical_alignment="center")


                with col_next:
                    st.button(
                        "**Next**",
                        on_click=next_movie,
                        args=(len(df_sorted) - 1,),
                        disabled=st.session_state["movie_index_user"] >= len(df_sorted) - 1,
                    )

                with col_prev:
                    st.button(
                        "**Previous**",
                        on_click=previous_movie,
                        disabled=st.session_state["movie_index_user"] == 1,
                    )

                with col_reset:
                    st.button("**Reset**", on_click=reset_movie)


            with col2:
                title = df_sorted.iloc[movie_index]['title']
                st.subheader(title)

                col2_1, col2_2 = st.columns([9,3], gap="small", vertical_alignment="center")
                with col2_1:
                    hour, minute = min_in_hour(runtime)
                    st.write(f"##### {genre_sentence} - {hour}h{minute}min")
                with col2_2:
                    st.markdown(cercle_html, unsafe_allow_html=True)

                if overview_layout:
                    st.write("")
                    st.write(overview_layout)
                    st.write("")
                    st.write(f"Director : **{director}**")

                    st.html("""
                        <style>
                            .actor-card {
                                border: 0px solid #e0e0e0;
                                border-radius: 10px;
                                overflow: hidden;
                                background-color: #FFFFFF;
                                box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                                margin-bottom: 10px;
                                height: auto; 
                                display: flex;
                                flex-direction: column;
                            }
                            .actor-card img {
                                width: 100%;
                                height: auto;
                                display: block;
                            }
                            .actor-info {
                                padding: 10px;
                            }
                            .actor-name {
                                font-weight: bold;
                                font-size: 14px;
                                color: #0FAFAFA;
                                margin: 0;
                            }
                            .actor-role {
                                font-size: 12px;
                                color: #4D4D4D;
                                margin-top: 4px;
                            }
                        </style>
                    """)

                    cols = st.columns(5)

                    for col, actor in zip(cols, cast):
                        with col:
                            carte_html = f"""
                            <div class="actor-card">
                                <img src="{actor['image']}" alt="{actor['name']}">
                                <div class="actor-info">
                                    <p class="actor-name">{actor['name']}</p>
                                    <p class="actor-role">{actor['role']}</p>
                                </div>
                            </div>
                            """
                            st.html(carte_html)
                else:
                    st.warning("No overview found")

                #Trailer
                @st.dialog(f"Trailer of {title}", width = 'large')
                def afficher_pop_up_video(url):
                    st.video(url)

                if st.button("Watch the trailer", type = "primary"):
                    afficher_pop_up_video(trailer_path)

                st.space()


        else:
            st.warning("Error accessing tmdb API, please try later or pass to the next movie")
            data_movie = None
            poster_layout = "Not found"












                    
                        