"""Autenticação de usuários."""

import streamlit as st
from supabase import Client

from db import traduzir_erro_db


def login(supabase: Client, email: str, password: str) -> bool:
    if not email or not password:
        st.error("Informe e-mail e senha para entrar.")
        return False
    try:
        res = supabase.auth.sign_in_with_password({"email": email.strip(), "password": password})
        st.session_state.user = res.user
        if res.session:
            st.session_state.access_token = res.session.access_token
            st.session_state.refresh_token = res.session.refresh_token
        st.success("Login realizado com sucesso!")
        st.rerun()
        return True
    except Exception as exc:
        st.error(traduzir_erro_db(exc))
        with st.expander("Detalhes do erro"):
            st.code(str(exc))
        return False


def sign_up(supabase: Client, email: str, password: str) -> bool:
    if not email or not password:
        st.error("Informe e-mail e senha para cadastrar.")
        return False
    if len(password) < 6:
        st.error("A senha deve ter pelo menos 6 caracteres.")
        return False
    try:
        supabase.auth.sign_up({"email": email.strip(), "password": password})
        st.success("Conta criada! Verifique seu e-mail (se exigido) e faça login.")
        return True
    except Exception as exc:
        st.error(traduzir_erro_db(exc))
        return False


def logout(supabase: Client) -> None:
    try:
        supabase.auth.sign_out()
    except Exception:
        pass
    st.session_state.user = None
    st.session_state.access_token = None
    st.session_state.refresh_token = None
    st.session_state.lotes = []
    st.session_state.remessa_gerada = None
    st.rerun()
