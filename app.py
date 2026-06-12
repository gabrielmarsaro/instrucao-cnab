"""Entry point do Gerador CNAB 240 - Banco do Brasil."""

import streamlit as st

from db import init_connection, secrets_configurados, traduzir_erro_db
from ui import render_app, render_login

st.set_page_config(
    page_title="Gerador CNAB 240 - BB",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

if "user" not in st.session_state:
    st.session_state.user = None
if "lotes" not in st.session_state:
    st.session_state.lotes = []
if "remessa_gerada" not in st.session_state:
    st.session_state.remessa_gerada = None
if "access_token" not in st.session_state:
    st.session_state.access_token = None
if "refresh_token" not in st.session_state:
    st.session_state.refresh_token = None

if not secrets_configurados():
    st.error("Credenciais do Supabase não configuradas.")
    st.markdown(
        """
        Edite o arquivo **`.streamlit/secrets.toml`** na pasta do projeto com os dados do seu projeto:

        1. Supabase → **Project Settings** → **API**
        2. Copie **Project URL** e **anon public** key
        3. Cole no arquivo e salve (o app recarrega sozinho)

        ```toml
        SUPABASE_URL = "https://xxxx.supabase.co"
        SUPABASE_KEY = "eyJhbGciOi..."
        ```

        Use as **mesmas credenciais** do Streamlit Cloud.
        """
    )
    st.stop()

def restaurar_sessao(supabase):
    """Mantém login após recarregar a página."""
    if st.session_state.user:
        return
    if not (st.session_state.access_token and st.session_state.refresh_token):
        return
    try:
        supabase.auth.set_session(
            st.session_state.access_token,
            st.session_state.refresh_token,
        )
        res = supabase.auth.get_user()
        if res and res.user:
            st.session_state.user = res.user
    except Exception:
        st.session_state.access_token = None
        st.session_state.refresh_token = None


try:
    supabase = init_connection()
    restaurar_sessao(supabase)
except Exception as exc:
    st.error(
        "Não foi possível conectar ao Supabase. "
        "Configure SUPABASE_URL e SUPABASE_KEY nos Secrets do Streamlit "
        "(ou em `.streamlit/secrets.toml` localmente)."
    )
    st.caption(traduzir_erro_db(exc))
    st.stop()

if not st.session_state.user:
    render_login(supabase)
    st.stop()

render_app(supabase)
