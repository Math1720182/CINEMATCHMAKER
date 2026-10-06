import os
import subprocess

os.makedirs(".streamlit", exist_ok=True)

redirect_uri = os.environ.get("redirect_uri", "")
cookie_secret = os.environ.get("cookie_secret", "")
client_id = os.environ.get("client_id", "")
client_secret = os.environ.get("client_secret", "")
server_metadata_url = os.environ.get("server_metadata_url", "")

secrets_content = f"""
[auth]
redirect_uri = "{redirect_uri}"
cookie_secret = "{cookie_secret}"

[auth.google]
client_id = "{client_id}"
client_secret = "{client_secret}"
server_metadata_url = "{server_metadata_url}"
"""

with open(".streamlit/secrets.toml", "w") as f:
    f.write(secrets_content)

port = os.environ.get("PORT", "8501")

import sys

cmd = [
    sys.executable, "-m", "streamlit", "run", "run_app.py",
    "--server.address=0.0.0.0",
    f"--server.port={port}",
    "--server.headless=true"
]

subprocess.run(cmd)