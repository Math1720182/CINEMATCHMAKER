import streamlit as st
import bcrypt
import psycopg2
from google import genai
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta
import time
import requests
import uuid

st.set_page_config(layout="wide", page_icon = "🍿", initial_sidebar_state = "expanded")

#region Personnalisation
#Css to perso homepage
st.markdown("""
<style>
    div[data-testid="stImage"] img {
        border-radius: 12px !important;
        transition: transform 0.3s ease, box-shadow 0.3s ease !important;
        box-shadow: 0 4px 10px rgba(0, 0, 0, 0.5) !important;
    }

    div[data-testid="stImage"] img:hover {
        transform: scale(1.1) !important;
        box-shadow: 0 8px 100px rgba(0, 210, 200, 0.3) !important;
    }

    div.stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 18px rgba(0, 210, 200, 0.5) !important;
    }
</style>
""", unsafe_allow_html=True)

#Reduce head padding
st.markdown(
    """
    <style>
        .block-container {
            padding-top: 0rem;
            padding-bottom: 0rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

#Beautiful st.button :)
st.markdown("""
<style>
    div.stButton > button {
        border-radius: 12px !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        padding: 8px 20px !important;
        font-weight: 600 !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1) !important;
    }
    div.stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 12px rgba(0, 0, 0, 0.2) !important;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<style>
    [data-testid="stMainBlockContainer"] {
        max-width: 1200px;
        margin-left: auto;
        margin-right: auto;
        padding-top: 0;
        padding-bottom: 0;
    }
</style>
""", unsafe_allow_html=True)

st.logo("logo_white_png.png", size = "large")

#endregion

if "user" not in st.session_state:
    st.session_state["user"] = None

if st.session_state["user"] == None:
    pages = {
        "Cine MatchMaker": [
            st.Page("pages/cinematchmaker_xai.py", title="Homepage", default=True),
            st.Page("pages/about.py", title = "About")
        ]
    }
else:
    pages = {
        "Cine MatchMaker": [
            st.Page("pages/cinematchmaker_xai_user.py", title="Homepage", default = True),
            st.Page("pages/my_movies.py", title="My movies"),
            st.Page("pages/about.py", title = "About")
        ]
    }

pg = st.navigation(pages, position="hidden")

#------------------------

load_dotenv()

try:
    URL_DATABASE = st.secrets['URL_DATABASE_RAILWAY']
except:
    URL_DATABASE = os.getenv("URL_DATABASE_LOCAL")


#-------------------------------DB CONNECT---------------------
def create_user(username, password):

    if len(password) < 8:
        return False, "The password must be at least 8 characters long."

    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    conn = psycopg2.connect(URL_DATABASE)
    cur = conn.cursor()

    cur.execute("SELECT id FROM users WHERE username = %s", (username,))
    if cur.fetchone():
        cur.close()
        conn.close()
        return False, "User already exist."

    cur.execute(
        """
        INSERT INTO users (username, password, created_at, created_with)
        VALUES (%s, %s, %s, %s)
        """,
        (username, password_hash, datetime.now(), "classic")
    )

    conn.commit()
    cur.close()
    conn.close()
    return True, "Account created! You can now log in."


DUMMY_HASH = bcrypt.hashpw(b"dummy_password", bcrypt.gensalt()) #Against timming attack

def verify_credentials(username, password):

    conn = psycopg2.connect(URL_DATABASE)
    cur = conn.cursor()

    cur.execute(
        "SELECT id, username, password FROM users WHERE username = %s",
        (username,)
    )
    user = cur.fetchone()
    cur.close()
    conn.close()

    if user:
        hash_to_check = user[2].encode()
    else:
        hash_to_check = DUMMY_HASH

    is_valid = bcrypt.checkpw(password.encode(), hash_to_check)

    if user and is_valid:
        return {
            "id": user[0],
            "username": user[1]
        }
    
    return None

def log_login(user_id, success):

    conn = psycopg2.connect(URL_DATABASE)
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO login_logs (user_id, timestamp, success)
        VALUES (%s, %s, %s)
        """,
        (user_id, datetime.now(), success)
    )

    conn.commit()
    cur.close()
    conn.close()


if "login_attempts" not in st.session_state:
    st.session_state.login_attempts = 0
    st.session_state.last_attempt = None

def login_with_rate_limit(username, password):

    if st.session_state.login_attempts >= 5:
        if st.session_state.last_attempt:
            time_elapsed = (datetime.now() - st.session_state.last_attempt).seconds
            if time_elapsed < 60:
                wait_time = 60 - time_elapsed
                st.error(f"Too much request. Try again in {wait_time} seconds")
                return False
            else:
                st.session_state.login_attempts = 0

    user = verify_credentials(username, password)

    if user:
        st.session_state.login_attempts = 0
        return user
    else:
        st.session_state.login_attempts += 1
        st.session_state.last_attempt = datetime.now()
        return None

def login_with_google(google_sub):

    conn = psycopg2.connect(URL_DATABASE)
    cur =conn.cursor()

    cur.execute(
        """
        INSERT INTO users (username, password, created_at, created_with, google_sub)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (google_sub) DO NOTHING;
        """,
        (str(uuid.uuid4()), str(uuid.uuid4()), datetime.now(), "google", google_sub)
    )

    conn.commit()
    cur.close()
    conn.close()

def is_user_logged_in():
    return st.user is not None and getattr(st.user, "is_logged_in", False)

if "mode_dialog" not in st.session_state:
    st.session_state.mode_dialog = "login"

def get_user_avatar(): #Sometimes, st.user.picture is blocked by Google and no image is loading (CORS)

    if hasattr(st, "user") and getattr(st.user, "is_logged_in", False):
        picture_url = st.user.get("picture") or st.user.get("avatar_url")
        
        if picture_url:
            try:
                response = requests.get(picture_url, timeout=5)
                if response.status_code == 200:
                    return response.content
            except Exception:
                pass
                
    # Fallback par défaut si non connecté ou si la requête échoue
    return "🐻"

user_avatar = get_user_avatar()

if is_user_logged_in():
    login_with_google(st.user["sub"])


@st.dialog("Log in or sign up", width="small")
def login_page():

    if st.session_state.mode_dialog == "login":

        st.button("🚀 Continue with Google", on_click = st.login, width = 600)


        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Connexion", type="primary")

            if submitted:
                user = login_with_rate_limit(username, password)

                if user:
                    st.session_state["user"] = user
                    log_login(user["id"], True)
                    st.success("Connected!")
                    time.sleep(1)
                    st.rerun()

                else:
                    log_login(None, False)
                    st.error("Incorrect password or username. Try again.")

        st.write("**No account?**")
        if st.button("Create an account"):
            st.session_state.mode_dialog = "sign_up"

        with st.expander("Your privacy is (really) my priority.", icon = "🔐"):
            st.write(
            "I only collect essential information required to create your account "
            "and save your movie choices (like your username and an encrypted version of your password)."
            )
            st.markdown("""
            * **No tracking:** I do not collect sensitive personal data.
            * **Security first:** Passwords are salted and hashed using `bcrypt` — no one, not even me, can read them.
            * **Note**: The chat is powered by Gemini AI. Please do not share any personal, sensitive, or confidential information (such as your full name, address, passwords, or financial details) in your messages.
            """)


    elif st.session_state.mode_dialog == "sign_up":

        with st.form("create_account_form"):
            st.write("**Create an account**")
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted_sign_up = st.form_submit_button(
                "Sign-up", type="primary"
            )

            if submitted_sign_up:
                if username != "" and password != "":
                    success, message = create_user(username, password)
                    if success:
                        st.success(message)
                        st.session_state.mode_dialog = "login"
                    else:
                        st.error(message)
                else:
                    st.error("Please fill in all fields.")

        st.write("**Already have an account?**")
        if st.button("Sign-in"):
            st.session_state.mode_dialog = "login"
 

if st.user.is_logged_in and st.session_state["user"] is None:
    st.session_state["user"] = st.user
    st.rerun()
            
with st.sidebar:
    if st.session_state["user"] is None:
        if st.button("**Log in**", type = 'primary', key = "sign_in", width = 300):
            login_page()
    else:
        if not st.user.is_logged_in:
            st.write(f"Welcome **{st.session_state["user"]["username"]}**")
        else:
            st.image(user_avatar, width = 30)
            st.write(f"Welcome **{st.user['name']}**")
    
        if st.button("Sign-out"):
            st.logout()
            st.session_state.clear()

    st.caption("Menu")
    for page in pages["Cine MatchMaker"]:
        st.page_link(page, label=page.title)

#--------------AI CHAT-------------------

#Popover
st.markdown(
    """
<style>
    div[data-testid="stPopover"] {
        position: fixed;
        bottom: 25px;
        right: 25px;
        z-index: 999999;
        width: auto !important; 
    }

    div[data-testid="stPopover"] button {
        width: auto !important;
        height: auto !important;
        border-radius: 30px !important;
        padding: 8px 16px !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15) !important;
        background-color: #133C55 !important; 
        color: white !important; 
        border: none !important;

        transition: transform 0.2s ease-in-out !important;
    }

    div[data-testid="stPopover"] button:hover {
        background-color: #1FA5BA !important;
        color: white !important;
        
        transform: scale(1.2) !important;
    }
</style>
""",
    unsafe_allow_html=True,
)

#Key
try:
    GEMINI_KEY_API = st.secrets['GEMINI_KEY_API']
except:
    GEMINI_KEY_API = os.getenv("GEMINI_KEY_API")

if "messages" not in st.session_state:
    st.session_state.messages = []

#AI API
def ai_response(prompt):

    client = genai.Client(api_key = GEMINI_KEY_API)

    gemini_history = []
    for msg in st.session_state.messages:
        role = "model" if msg["role"] == "assistant" else "user"
        gemini_history.append({"role" : role, "parts": [{"text": msg["content"]}]}) #Parts because we can send different type of message (image, video etc.)

    last_user_message = gemini_history.pop()["parts"][0]["text"]

    chat = client.chats.create(
        model="gemini-3.5-flash-lite",
        history=gemini_history,
        config = {
            "system_instruction" : "Tu es un assistant spécialisé exclusivement dans le domaine du cinéma et des films. Ton rôle est d'aider l'utilisateur uniquement sur ce sujet (recommandations, informations sur les films, acteurs, réalisateurs, histoires du cinéma, etc.). Règle stricte : Toutes les demandes doivent obligatoirement porter sur le cinéma. Si l'utilisateur te pose une question ou te fait une demande qui ne concerne pas le cinéma, tu dois refuser d'y répondre et indiquer poliment que tu ne peux répondre qu'aux sujets liés au cinéma. Tu réponds en anglais si le prompt est en anglais et inversement si c'est en français. Ne fait pas des réponses trop longues et complexes, reste synthétique."
        }
    )

    response = chat.send_message(last_user_message)

    return response.text

#Chat
with st.popover("💬 Ask AI"):
    chat = st.container(height = 400, width = 400)  
    with chat:
        for message in st.session_state.messages:
            st.chat_message(message["role"], avatar = user_avatar if message["role"] == "user" else ("💬" if message["role"] == "assistant" else "🐻")).write(message["content"])
    MAX_CHARA = 500
    if prompt := st.chat_input("Ask me something! Please do not share any personal, sensitive, or confidential information in your messages."):
        if len(prompt) > MAX_CHARA:
            st.error(f'The prompt is too long. Max: {MAX_CHARA} characters')
        else:
            with chat:
                st.chat_message("user", avatar = user_avatar if st.user.is_logged_in else "🐻").write(prompt)
            st.session_state.messages.append({"role" : "user", "content": prompt})

            with st.spinner("The answer is coming!..."):
                answer = ai_response(prompt)

            with chat:
                st.chat_message("assistant", avatar = "💬").write(answer)
            st.session_state.messages.append({"role" : "assistant", "content": answer})


pg.run()


with st.sidebar:
    st.markdown("""
    <style>
        .sidebar-footer {
            position: fixed;
            left: 1rem;
            bottom: 1rem;
            width: 12rem;
            z-index: 1000;
        }

        .sidebar-footer a {
            display: block;
            padding: 0.5rem 0.75rem;
            border-radius: 8px;
            background: #133C55;
            color: white !important;
            text-align: center;
            text-decoration: none;
        }

        .sidebar-footer a:hover {
            background: #1FA5BA;
        }
    </style>

    <div class="sidebar-footer">
        <p><strong>Made with ❤️ by Thomas</strong></p>
        <a href="https://github.com/Math1720182/MathSim/"
           target="_blank" rel="noopener noreferrer">
            Code on GitHub 👾
        </a>
    </div>
    """, unsafe_allow_html=True)
