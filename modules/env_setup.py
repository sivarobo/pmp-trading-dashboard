"""
env_setup.py
Shared environment initialization for every page of the app (Streamlit
multipage apps run each page as its own script, so this needs to be called
at the top of app.py AND every file under pages/).
"""

import os
from dotenv import load_dotenv


def init_env():
    load_dotenv()  # picks up .env created by scripts/get_upstox_token.py, if present

    try:
        import streamlit as st
        for key, value in st.secrets.items():
            os.environ.setdefault(key, str(value))
    except Exception:
        pass  # no secrets.toml / Cloud Secrets configured yet -- fine, defaults to mock
