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
        st.success(
            "Se os dados estiverem corretos, sua conta foi criada. "
            "Verifique seu e-mail (se exigido) e faça login. "
            "Se você já tem conta, use **Entrar** ou **Esqueci a senha**."
        )
        return True
    except Exception as exc:
        msg = str(exc).lower()
        if "already registered" in msg or "user already" in msg:
            # Mensagem neutra: evita revelar se o e-mail existe (enumeracao)
            st.info(
                "Se os dados estiverem corretos, sua conta foi criada. "
                "Verifique seu e-mail. Se você já tem conta, use **Entrar** ou **Esqueci a senha**."
            )
            return True
        st.error(traduzir_erro_db(exc))
        return False


def recuperar_senha(supabase: Client, email: str) -> bool:
    if not email or not email.strip():
        st.error("Informe o e-mail cadastrado para recuperar a senha.")
        return False
    try:
        supabase.auth.reset_password_for_email(email.strip())
        st.success(
            "Se o e-mail estiver cadastrado, voce recebera um link para redefinir a senha. "
            "Verifique tambem a caixa de spam."
        )
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
