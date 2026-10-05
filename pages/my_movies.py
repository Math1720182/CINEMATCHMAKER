import os
import streamlit as st
from IPython.display import Image
import requests
from utils import load_and_transform
from dotenv import load_dotenv
from datetime import date
import psycopg2


st.title("My movies", text_alignment = "center", help = "**Select your favorite movies to personalize your recommendations!**")
st.space()


#Load and transform
df, df_vector_2D = load_and_transform()

#API KEY AND URL_DATABASE
load_dotenv()
try:
    if "API_KEY_TMDB" in st.secrets:
        st.session_state.api_key = st.secrets["API_KEY_TMDB"]
except:
    st.session_state.api_key = os.getenv("API_KEY_TMDB")

parameters = {"api_key": st.session_state.api_key}

try:
    URL_DATABASE = st.secrets['URL_DATABASE_RAILWAY']
except:
    URL_DATABASE = os.getenv("URL_DATABASE_LOCAL")

#------------DEF SQL DATABASE CALL---------------


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

if st.user.is_logged_in:
    user_id = find_user_id(google_sub=st.user["sub"])
else:
    user_id = find_user_id(username=st.session_state["user"]["username"])


def add_movie(user_id, tmdbID, note, date):

    conn = psycopg2.connect(URL_DATABASE)
    cur = conn.cursor()

    cur.execute(
        """
    INSERT INTO user_movies (user_id, tmdb_id, note, date_added)
    VALUES (%s, %s, %s, %s)
    ON CONFLICT (user_id, tmdb_id)
    DO UPDATE SET note = EXCLUDED.note;
        """,
        (user_id, tmdbID, note, date)
    )

    conn.commit()
    cur.close()
    conn.close()


def find_movie(user_id):

    conn = psycopg2.connect(URL_DATABASE)
    cur = conn.cursor()

    cur.execute("""
    SELECT tmdb_id, note, date_added
    FROM user_movies
    WHERE user_id = %s;
    """,
    (str(user_id,)),
    )

    movies = cur.fetchall()
    cur.close()
    conn.close()

    return movies

movies = find_movie(user_id)

def delete_movie(user_id, tmdb_id):

    conn = psycopg2.connect(URL_DATABASE)
    cur = conn.cursor()

    cur.execute(
        """
        DELETE FROM user_movies
        WHERE user_id = %s AND tmdb_id = %s;
        """,
        (user_id, int(tmdb_id)),
    )

    conn.commit()
    cur.close()
    conn.close()


#--------------------------------------

#API CALL for MOVIES
@st.cache_data
def get_tmdb_movie_data(tmdbID, parameters):
    URL = f"https://api.themoviedb.org/3/movie/{tmdbID}?append_to_response=watch/providers,credits,videos"
    response = requests.get(URL, params= parameters)

    if response.status_code == 200:
        return response.json()
    return None


if "tmdbID_dico" not in st.session_state:
    st.session_state["tmdbID_dico"] = {}

if "movie_added" not in st.session_state:
    st.session_state["movie_added"] = False

#Select movies
col1, col2, col3, col4 = st.columns(4, vertical_alignment="center")

with col1:
    recherche = st.text_input("**A movie I liked**", "Dune", width = 300, key ="user_reco")
    df_filtre = df[df['title'].str.contains(recherche, case =False, na = False, regex = False)].head(50)
with col2:
    if not df_filtre.empty:
        movie_user = st.selectbox("**Select the movie from the list**", options = df_filtre['title'], width = 300, key ="user_reco_list")
        st.session_state["selected_movie"] = movie_user
    else:
        st.write("")
        st.write("")
        st.warning("No movies find with this title")
        st.session_state["selected_movie"] = None
with col3:
    note = st.slider("**My notation**", min_value = 0.0, max_value = 5.0, step = 0.5)
with col4:
    st.write("")
    st.write("")
    if st.button("Add the movie"):
            tmdbID = int(df_filtre[df_filtre['title'] == movie_user]['tmdbId'].iloc[0])
            add_movie(user_id, tmdbID, note, date.today())
            if "user_movies" in st.session_state:
                st.session_state["user_movies"].append((tmdbID, note, date.today()))

            st.session_state["movie_added"] = True
            st.session_state["df_sorted_user"] = None
            st.session_state["movie_index_user"] = 0
            st.rerun()


for item in movies:
    tmdbID = item[0] 
    note = item[1] 
    date = item[2]
    st.session_state["tmdbID_dico"][tmdbID] = {"note": note, "date": date}


st.space(50)

if st.session_state["tmdbID_dico"]:
    with st.container():

        NB_COLS = 5
        cols = st.columns(NB_COLS)

        for index, (tmdbID, infos) in enumerate(st.session_state["tmdbID_dico"].items()):

            note = infos["note"]
            date = infos["date"]

            if index > 0 and index % NB_COLS == 0:
                cols = st.columns(NB_COLS)
                
            col = cols[index % NB_COLS]

            data_movie = get_tmdb_movie_data(tmdbID, parameters)
            
            if data_movie:
                chemin_poster = data_movie.get('poster_path')

                if chemin_poster:
                    URL_base_image = "https://image.tmdb.org/t/p/w300/"
                    poster_layout = URL_base_image + chemin_poster
                else:
                    poster_layout = None

                with col:
                    if poster_layout:
                        st.image(poster_layout)
                    else:
                        st.write("Pas d'affiche")

                    col1, col2 = st.columns([0.70, 0.40])

                    with col1:
                        st.markdown(f"#### ⭐️ {note}")
                    with col2:
                        if st.button("❌", key=f"delete_{tmdbID}", type = "tertiary"):
                            delete_movie(user_id, tmdbID)
                            del st.session_state["tmdbID_dico"][tmdbID]

                            st.session_state["movie_added"] = True
                            st.session_state["df_sorted_user"] = None
                            st.session_state["movie_index_user"] = 0
                            st.rerun()



