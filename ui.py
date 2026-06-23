"""Componentes de interface Streamlit."""

from __future__ import annotations

import html as html_lib
from datetime import datetime

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from supabase import Client

from auth import login, logout, recuperar_senha, sign_up
from cnab import (
    buscar_valor_registrado,
    coletar_nosso_numeros_lotes,
    formatar_real,
    gerar_remessa,
    linhas_para_bytes,
    normalizar_valor_monetario,
)
from config import (
    ABA_CONVENIOS_TAB,
    ABA_HISTORICO_TAB,
    ABA_VALORES_TAB,
    FONTE_APP,
    INSTRUCOES_CNAB,
    MODOS_REFERENCIA_VALORES,
    PREVIEW_LINHAS,
    REF_VALORES_ESCOLHER,
    REF_VALORES_ULTIMA,
    STATUS_REMESSA_ACEITA,
    STATUS_REMESSA_GERADA,
    STATUS_REMESSA_LABELS,
    STATUS_REMESSA_OPCOES,
    STATUS_REMESSA_REJEITADA,
    TITULO_GESTAO_CLIENTES_HTML,
    TITULO_GESTAO_CONVENIOS_HTML,
    TITULO_HISTORICO_HTML,
    TITULO_VALORES_NOMINAIS_HTML,
)
from db import (
    _erro_coluna_status_ausente,
    atualizar_cliente,
    atualizar_convenio,
    atualizar_status_remessa,
    atualizar_valor_nominal_titulo,
    contar_remessas_convenio,
    criar_cliente,
    criar_clientes_lote,
    criar_convenio,
    excluir_clientes,
    excluir_convenio,
    excluir_titulo_valor,
    listar_clientes,
    listar_convenios,
    listar_remessas,
    listar_remessas_com_valores,
    listar_remessas_por_convenio,
    listar_titulos_valores,
    obter_ultima_remessa_com_valores,
    obter_valores_referencia,
    salvar_remessa,
    salvar_snapshot_valores_remessa,
    secrets_configurados,
    tabela_remessa_valores_disponivel,
    traduzir_erro_db,
    upsert_titulos_valores,
    MENSAGEM_MIGRATION_004,
)
from validation import (
    mapear_colunas_clientes,
    preparar_importacao_clientes,
    validar_cnpj_cpf,
    validar_planilha,
)


def _exibir_feedback_lote(chave: str, label_botao: str = "Ver detalhes de erros e avisos"):
    """Mostra resumo e botão opcional para expandir erros/avisos."""
    feedback = st.session_state.get(chave)
    if not feedback:
        return

    erros = feedback.get("erros", [])
    avisos = feedback.get("avisos", [])
    correcoes = feedback.get("correcoes", [])

    if feedback.get("sucesso"):
        st.success(feedback["mensagem"])
    else:
        st.error(feedback["mensagem"])

    if correcoes:
        lista = "\n".join(f"- {item}" for item in correcoes)
        st.warning(
            f"**{len(correcoes)} valor(es) de face corrigido(s) automaticamente** "
            f"para coincidir com o valor nominal registrado no banco:\n\n{lista}"
        )

    if not erros and not avisos:
        return

    toggle_key = f"{chave}_aberto"
    if st.button(label_botao, key=f"btn_{chave}"):
        st.session_state[toggle_key] = not st.session_state.get(toggle_key, False)
        st.rerun()

    if st.session_state.get(toggle_key):
        with st.container(border=True):
            if erros:
                st.markdown("**Erros**")
                for item in erros:
                    st.error(f"• {item}")
            if avisos:
                st.markdown("**Avisos**")
                for item in avisos:
                    st.warning(f"• {item}")


@st.dialog("Salvar arquivo de remessa")
def _dialog_salvar_remessa():
    ultimo = st.session_state.get("ultimo_arquivo_remessa")
    if not ultimo:
        st.warning("Nenhum arquivo disponível.")
        return

    nome = ultimo["nome_arquivo"]
    st.markdown(f"Arquivo **{nome}** gerado com sucesso.")
    st.markdown(
        "Clique no botão abaixo. O navegador abrirá a janela para "
        "**escolher a pasta** e confirmar o nome do arquivo."
    )
    st.caption(
        "Dica: no Chrome/Edge, ative em Configurações → Downloads → "
        "'Perguntar onde salvar cada arquivo antes de baixar'."
    )

    st.download_button(
        label="Escolher onde salvar",
        data=ultimo["bytes"],
        file_name=nome,
        mime="application/octet-stream",
        type="primary",
        use_container_width=True,
        key="dialog_salvar_remessa",
    )


def _render_titulo(html_fragment: str) -> None:
    """Título de seção com entidades HTML (estável no Chrome e Edge)."""
    st.markdown(
        f'<div style="font-family:{FONTE_APP};margin:0 0 1rem 0;">{html_fragment}</div>',
        unsafe_allow_html=True,
    )


def aplicar_estilo():
    st.markdown(
        f"""
        <style>
        html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"],
        .stMarkdown, .stText, label, input, textarea, select, button {{
            font-family: {FONTE_APP} !important;
        }}
        h1, h2, h3, .main-header {{
            font-family: {FONTE_APP} !important;
        }}
        .main-header {{ font-size: 1.8rem; font-weight: 700; margin-bottom: 0.2rem; }}
        .sub-header {{ color: #666; margin-bottom: 1.5rem; }}
        .metric-card {{
            background: #f0f4f8; border-radius: 8px; padding: 1rem;
            border-left: 4px solid #1f77b4;
        }}
        div[data-testid="stSidebar"] {{ background-color: #f8fafc; }}
        [data-baseweb="tab-list"] button[data-baseweb="tab"] {{
            font-family: "Segoe UI", Tahoma, Arial, sans-serif !important;
            min-width: max-content !important;
            max-width: none !important;
            flex-shrink: 0 !important;
            -webkit-font-smoothing: antialiased;
            text-rendering: optimizeLegibility;
        }}
        [data-baseweb="tab-list"] button[data-baseweb="tab"] p {{
            white-space: nowrap !important;
            overflow: visible !important;
            text-overflow: clip !important;
            max-width: none !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_login(supabase: Client):
    aplicar_estilo()
    st.markdown(
        f"""
        <style>
        section[data-testid="stSidebar"] {{ display: none; }}
        [data-testid="stAppViewContainer"] .block-container {{
            max-width: 620px;
            padding-top: 3.5rem;
        }}
        .login-titulo {{
            text-align: center;
            font-family: {FONTE_APP};
            font-size: 2.1rem;
            font-weight: 700;
            color: #1f4e79;
            margin: 0 0 0.35rem 0;
        }}
        .login-sub {{
            text-align: center;
            font-family: {FONTE_APP};
            font-size: 1.1rem;
            color: #6b7280;
            margin: 0 0 1.8rem 0;
        }}
        .login-logo {{
            text-align: center;
            font-size: 3.6rem;
            margin-bottom: 0.4rem;
        }}
        [data-testid="stAppViewContainer"] [data-baseweb="tab"] {{
            font-size: 1.05rem;
        }}
        [data-testid="stAppViewContainer"] .stTextInput input {{
            padding-top: 0.6rem;
            padding-bottom: 0.6rem;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="login-logo">🏦</div>', unsafe_allow_html=True)
    st.markdown('<div class="login-titulo">Gerador CNAB 240</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="login-sub">Banco do Brasil — remessas, clientes e convênios</div>',
        unsafe_allow_html=True,
    )

    if not secrets_configurados():
        st.warning(
            "As credenciais do Supabase ainda estão com valores de exemplo. "
            "Edite `.streamlit/secrets.toml` com a URL e a chave **anon public** do seu projeto."
        )

    with st.container(border=True):
        tab_login, tab_cadastro, tab_recuperar = st.tabs(
            ["Entrar", "Criar Conta", "Esqueci a senha"]
        )

        with tab_login:
            with st.form("form_login"):
                email_login = st.text_input("E-mail")
                senha_login = st.text_input("Senha", type="password")
                if st.form_submit_button("Entrar", type="primary", use_container_width=True):
                    login(supabase, email_login, senha_login)

        with tab_cadastro:
            with st.form("form_cadastro"):
                email_cad = st.text_input("E-mail", key="cad_email")
                senha_cad = st.text_input(
                    "Senha (mín. 6 caracteres)", type="password", key="cad_senha"
                )
                if st.form_submit_button("Cadastrar", use_container_width=True):
                    sign_up(supabase, email_cad, senha_cad)

        with tab_recuperar:
            st.caption(
                "Informe seu e-mail cadastrado. Enviaremos um link para você redefinir a senha."
            )
            with st.form("form_recuperar"):
                email_rec = st.text_input("E-mail", key="rec_email")
                if st.form_submit_button("Enviar link de recuperação", use_container_width=True):
                    recuperar_senha(supabase, email_rec)


def _mapa_clientes(df: pd.DataFrame) -> dict[str, str]:
    mapa = {}
    for _, row in df.iterrows():
        texto = f"{row.get('nome', 'Sem Nome')} (Cód: {row.get('id_cliente_planilha', 'S/C')})"
        mapa[texto] = row["id"]
    return mapa


def _preparar_exibicao_clientes(df: pd.DataFrame) -> pd.DataFrame:
    cols_ocultas = [c for c in ["id", "user_id", "created_at"] if c in df.columns]
    df_exibir = df.drop(columns=cols_ocultas).copy()
    renomear = {
        "id_cliente_planilha": "Código do cliente",
        "cnpj_cpf": "CNPJ/CPF",
        "nome": "Nome",
        "endereco": "Endereço",
        "bairro": "Bairro",
        "cep": "CEP",
        "cidade": "Cidade",
        "uf": "UF",
    }
    df_exibir = df_exibir.rename(columns={k: v for k, v in renomear.items() if k in df_exibir.columns})
    return df_exibir.reset_index(drop=True)


def _preparar_exibicao_convenios(df: pd.DataFrame) -> pd.DataFrame:
    cols_ocultas = [c for c in ["id", "user_id", "created_at"] if c in df.columns]
    df_exibir = df.drop(columns=cols_ocultas).copy()
    renomear = {
        "cnpj": "CNPJ",
        "razao_social": "Razão Social",
        "agencia": "Agência",
        "dv_agencia": "DV Agência",
        "conta": "Conta",
        "dv_conta": "DV Conta",
        "convenio": "Convênio",
        "carteira": "Carteira",
        "variacao": "Variação",
    }
    df_exibir = df_exibir.rename(columns={k: v for k, v in renomear.items() if k in df_exibir.columns})
    return df_exibir.reset_index(drop=True)


def _preparar_exibicao_remessas(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        c
        for c in ["created_at", "nome_arquivo", "status", "total_lotes", "total_boletos", "instrucoes"]
        if c in df.columns
    ]
    df_exibir = df[cols].copy() if cols else df.copy()

    if "created_at" in df_exibir.columns:
        df_exibir["created_at"] = pd.to_datetime(df_exibir["created_at"], errors="coerce").dt.strftime(
            "%d/%m/%Y %H:%M"
        )

    if "status" in df_exibir.columns:
        df_exibir["status"] = df_exibir["status"].apply(
            lambda s: STATUS_REMESSA_LABELS.get(str(s), str(s) if pd.notna(s) else "Gerada")
        )

    if "instrucoes" in df_exibir.columns:
        def _fmt_instrucoes(valor):
            if isinstance(valor, list):
                return " | ".join(str(v) for v in valor)
            return str(valor) if pd.notna(valor) else ""

        df_exibir["instrucoes"] = df_exibir["instrucoes"].apply(_fmt_instrucoes)

    renomear = {
        "created_at": "Data/Hora",
        "nome_arquivo": "Arquivo",
        "status": "Status",
        "total_lotes": "Lotes",
        "total_boletos": "Boletos",
        "instrucoes": "Instruções",
    }
    df_exibir = df_exibir.rename(columns={k: v for k, v in renomear.items() if k in df_exibir.columns})
    return df_exibir.reset_index(drop=True)


def _preparar_exibicao_valores(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        c
        for c in ["nosso_numero", "seu_numero", "valor_nominal", "updated_at"]
        if c in df.columns
    ]
    df_exibir = df[cols].copy() if cols else df.copy()

    if "valor_nominal" in df_exibir.columns:
        df_exibir["valor_nominal"] = df_exibir["valor_nominal"].apply(
            lambda v: formatar_real(float(v)) if pd.notna(v) else ""
        )

    if "updated_at" in df_exibir.columns:
        df_exibir["updated_at"] = pd.to_datetime(
            df_exibir["updated_at"], errors="coerce"
        ).dt.strftime("%d/%m/%Y %H:%M")

    renomear = {
        "nosso_numero": "Nosso Número",
        "seu_numero": "Seu Número",
        "valor_nominal": "Valor Nominal",
        "updated_at": "Atualizado em",
    }
    df_exibir = df_exibir.rename(columns={k: v for k, v in renomear.items() if k in df_exibir.columns})
    return df_exibir.reset_index(drop=True)


def _preparar_exibicao_importacao(df: pd.DataFrame) -> pd.DataFrame:
    renomear = {
        "id_cliente_planilha": "Código do cliente",
        "cnpj_cpf": "CNPJ/CPF",
        "nome": "Nome",
        "endereco": "Endereço",
        "bairro": "Bairro",
        "cep": "CEP",
        "cidade": "Cidade",
        "uf": "UF",
    }
    df_exibir = df.copy()
    df_exibir = df_exibir.rename(columns={k: v for k, v in renomear.items() if k in df_exibir.columns})
    return df_exibir.reset_index(drop=True)


def _tabela_zebra(df: pd.DataFrame, altura_max: int = 720) -> None:
    """Tabela com zebra, fonte moderna e sem quebra de linha nas células."""
    if df.empty:
        st.info("Nenhum registro para exibir.")
        return

    estilo_th = (
        f"white-space:nowrap;padding:10px 14px;background:#1f4e79;color:#fff;"
        f"font-weight:600;text-align:left;border:1px solid #d0d7de;"
        f"font-family:{FONTE_APP};font-size:14px;"
    )
    estilo_td = (
        f"white-space:nowrap;padding:10px 14px;text-align:left;"
        f"border-bottom:1px solid #e2e8f0;vertical-align:middle;"
        f"font-family:{FONTE_APP};font-size:14px;"
    )

    cabecalho = "".join(
        f"<th style='{estilo_th}'>{html_lib.escape(str(c))}</th>" for c in df.columns
    )
    linhas = []
    for i, (_, row) in enumerate(df.iterrows()):
        fundo = "#eef3f8" if i % 2 == 0 else "#ffffff"
        celulas = "".join(
            f"<td style='{estilo_td}background:{fundo};'>"
            f"{html_lib.escape(str(v) if pd.notna(v) else '')}</td>"
            for v in row
        )
        linhas.append(f"<tr>{celulas}</tr>")

    html = f"""
    <div style="overflow-x:auto;border:1px solid #e2e8f0;border-radius:8px;
                font-family:{FONTE_APP};">
        <table style="border-collapse:collapse;width:max-content;min-width:100%;
                      font-family:{FONTE_APP};">
            <thead><tr>{cabecalho}</tr></thead>
            <tbody>{"".join(linhas)}</tbody>
        </table>
    </div>
    """
    altura = min(56 + (38 * len(df)), altura_max)
    components.html(html, height=altura, scrolling=True)


def _mapa_convenios(df: pd.DataFrame) -> dict[str, str]:
    mapa = {}
    for _, row in df.iterrows():
        texto = (
            f"{row.get('razao_social', 'S/N')} "
            f"(Ag: {row.get('agencia', '')} | CC: {row.get('conta', '')})"
        )
        mapa[texto] = row["id"]
    return mapa


def render_sidebar(supabase: Client, user):
    st.sidebar.markdown("### Menu")
    st.sidebar.write(f"👤 **{user.email}**")
    st.sidebar.divider()
    if st.sidebar.button("Atualizar tela", use_container_width=True, help="Recarrega o app (use isto em vez de Ctrl+F5)"):
        st.cache_data.clear()
        st.cache_resource.clear()
        st.rerun()
    if st.sidebar.button("🚪 Sair", use_container_width=True):
        logout(supabase)
    st.sidebar.markdown("---")
    st.sidebar.caption("CNAB 240 · Banco do Brasil")
    st.sidebar.caption("Versao interface: 2026.06.11e")


def _render_importacao_clientes(supabase: Client, user_id: str, df_clientes: pd.DataFrame):
    with st.container(border=True):
        st.subheader("Importar clientes por planilha")
        st.caption("Envie um Excel (.xlsx). CNPJs já cadastrados não serão duplicados.")

        with st.expander("Colunas reconhecidas automaticamente"):
            st.markdown(
                """
                - **Código:** Código, Cliente, ID Cliente
                - **CNPJ/CPF:** CNPJ, CPF, Documento
                - **Nome:** Nome, Razão Social
                - **Endereço, Bairro, CEP, Cidade, UF**
                """
            )

        arquivo_clientes = st.file_uploader(
            "Selecione a planilha de clientes",
            type=["xlsx", "xls"],
            key="upload_clientes",
            label_visibility="visible",
        )

        if not arquivo_clientes:
            return

        df_import = pd.read_excel(arquivo_clientes)
        colunas_detectadas = mapear_colunas_clientes(df_import.copy())
        st.caption("Mapeamento detectado:")
        st.json(colunas_detectadas)

        preview = _preparar_exibicao_importacao(df_import.head(10))
        st.caption("Prévia da planilha (10 primeiras linhas)")
        _tabela_zebra(preview)

        resultado = preparar_importacao_clientes(df_import, df_clientes)

        for erro in resultado.erros:
            st.error(f"• {erro}")

        if resultado.ignorados_cnpj:
            st.info(
                f"**{len(resultado.ignorados_cnpj)}** registro(s) ignorado(s) "
                "por CNPJ já existente na base."
            )
            with st.expander("Ver CNPJs ignorados (já cadastrados)"):
                for msg in resultado.ignorados_cnpj[:50]:
                    st.write(f"• {msg}")
                if len(resultado.ignorados_cnpj) > 50:
                    st.write(f"... e mais {len(resultado.ignorados_cnpj) - 50}.")

        if resultado.ignorados_planilha:
            with st.expander("CNPJs repetidos dentro da planilha"):
                for msg in resultado.ignorados_planilha:
                    st.write(f"• {msg}")

        if resultado.registros:
            st.success(f"**{len(resultado.registros)}** cliente(s) prontos para importar.")
            _tabela_zebra(_preparar_exibicao_importacao(pd.DataFrame(resultado.registros)))

            if st.button("Confirmar importação", type="primary", key="btn_import_cli"):
                try:
                    qtd = criar_clientes_lote(supabase, user_id, resultado.registros)
                    st.success(f"{qtd} cliente(s) importado(s) com sucesso!")
                    st.rerun()
                except Exception as exc:
                    st.error(traduzir_erro_db(exc))


def render_clientes(supabase: Client, user_id: str):
    _render_titulo(TITULO_GESTAO_CLIENTES_HTML)

    try:
        df_clientes = listar_clientes(supabase, user_id)
    except Exception as exc:
        st.error(traduzir_erro_db(exc))
        return pd.DataFrame()

    _render_importacao_clientes(supabase, user_id, df_clientes)
    st.divider()

    tab_novo, tab_vis, tab_edit, tab_del = st.tabs(
        ["Novo (manual)", "Visualizar", "Editar", "Excluir em Lote"]
    )

    with tab_novo:
        with st.form("form_novo_cli"):
            col1, col2 = st.columns(2)
            novo_cod = col1.text_input("Código do cliente *")
            novo_cnpj = col2.text_input("CNPJ/CPF")
            novo_nome = st.text_input("Nome / Razão Social *")
            novo_end = st.text_input("Endereço")
            col3, col4, col5, col6 = st.columns(4)
            novo_bairro = col3.text_input("Bairro")
            novo_cep = col4.text_input("CEP")
            novo_cidade = col5.text_input("Cidade")
            novo_uf = col6.text_input("UF", max_chars=2)
            if st.form_submit_button("💾 Cadastrar Cliente", type="primary"):
                if not novo_cod or not novo_nome:
                    st.error("Código do cliente e Nome são obrigatórios.")
                elif novo_cnpj and not validar_cnpj_cpf(novo_cnpj):
                    st.error("CNPJ/CPF inválido. Informe 11 ou 14 dígitos.")
                else:
                    try:
                        criar_cliente(
                            supabase,
                            user_id,
                            {
                                "id_cliente_planilha": novo_cod.strip(),
                                "cnpj_cpf": novo_cnpj,
                                "nome": novo_nome,
                                "endereco": novo_end,
                                "bairro": novo_bairro,
                                "cep": novo_cep,
                                "cidade": novo_cidade,
                                "uf": novo_uf.upper() if novo_uf else "",
                            },
                        )
                        st.success("Cliente cadastrado com sucesso!")
                        st.rerun()
                    except Exception as exc:
                        st.error(traduzir_erro_db(exc))

    mapa_clientes = _mapa_clientes(df_clientes) if not df_clientes.empty else {}
    opcoes = list(mapa_clientes.keys())

    with tab_vis:
        if df_clientes.empty:
            st.info("Nenhum cliente cadastrado. Use a importação acima ou a aba **Novo (manual)**.")
        else:
            df_exibir = _preparar_exibicao_clientes(df_clientes)
            _tabela_zebra(df_exibir)

    with tab_edit:
        if df_clientes.empty:
            st.info("Cadastre clientes antes de editar.")
        else:
            cliente_sel = st.selectbox("Selecione o cliente:", [""] + opcoes, key="edit_cli_sel")
            if cliente_sel:
                dados = df_clientes[df_clientes["id"] == mapa_clientes[cliente_sel]].iloc[0]
                with st.form("form_edit_cli"):
                    col1, col2 = st.columns(2)
                    edit_cod = col1.text_input("Código do cliente", value=str(dados.get("id_cliente_planilha", "")))
                    edit_cnpj = col2.text_input("CNPJ/CPF", value=str(dados.get("cnpj_cpf", "")))
                    edit_nome = st.text_input("Nome / Razão Social", value=str(dados.get("nome", "")))
                    edit_end = st.text_input("Endereço", value=str(dados.get("endereco", "")))
                    col3, col4, col5, col6 = st.columns(4)
                    edit_bairro = col3.text_input("Bairro", value=str(dados.get("bairro", "")))
                    edit_cep = col4.text_input("CEP", value=str(dados.get("cep", "")))
                    edit_cidade = col5.text_input("Cidade", value=str(dados.get("cidade", "")))
                    edit_uf = col6.text_input("UF", value=str(dados.get("uf", "")))
                    if st.form_submit_button("💾 Salvar Alterações", type="primary"):
                        try:
                            atualizar_cliente(
                                supabase,
                                mapa_clientes[cliente_sel],
                                {
                                    "id_cliente_planilha": edit_cod,
                                    "cnpj_cpf": edit_cnpj,
                                    "nome": edit_nome,
                                    "endereco": edit_end,
                                    "bairro": edit_bairro,
                                    "cep": edit_cep,
                                    "cidade": edit_cidade,
                                    "uf": edit_uf,
                                },
                            )
                            st.success("Cliente atualizado!")
                            st.rerun()
                        except Exception as exc:
                            st.error(traduzir_erro_db(exc))

    with tab_del:
        if df_clientes.empty:
            st.info("Nenhum cliente para excluir.")
        else:
            marcar_todos = st.checkbox("☑️ Selecionar TODOS")
            clientes_excluir = st.multiselect(
                "Clientes selecionados:",
                opcoes,
                default=opcoes if marcar_todos else None,
            )
            if clientes_excluir:
                st.warning(f"⚠️ {len(clientes_excluir)} cliente(s) serão excluídos.")
                if st.button("🚨 Confirmar Exclusão", type="primary"):
                    try:
                        excluir_clientes(supabase, [mapa_clientes[c] for c in clientes_excluir])
                        st.success("Clientes excluídos!")
                        st.rerun()
                    except Exception as exc:
                        st.error(traduzir_erro_db(exc))

    return df_clientes


def render_convenios(supabase: Client, user_id: str):
    _render_titulo(TITULO_GESTAO_CONVENIOS_HTML)

    try:
        df_convenios = listar_convenios(supabase, user_id)
    except Exception as exc:
        st.error(traduzir_erro_db(exc))
        return pd.DataFrame()

    tab_vis, tab_novo, tab_edit, tab_del = st.tabs(
        ["Visualizar", "Novo", "Editar", "Excluir"]
    )

    with tab_vis:
        if df_convenios.empty:
            st.info("Nenhum convênio cadastrado. Use a aba **Novo** para começar.")
        else:
            df_conv_exibir = _preparar_exibicao_convenios(df_convenios)
            _tabela_zebra(df_conv_exibir)

    with tab_novo:
        with st.form("form_novo_conv"):
            col1, col2 = st.columns(2)
            novo_cnpj = col1.text_input("CNPJ *")
            novo_razao = col2.text_input("Razão Social *")
            col3, col4, col5, col6 = st.columns(4)
            novo_ag = col3.text_input("Agência *")
            novo_dv_ag = col4.text_input("DV Agência")
            novo_conta = col5.text_input("Conta *")
            novo_dv_conta = col6.text_input("DV Conta")
            col7, col8, col9 = st.columns(3)
            novo_convenio = col7.text_input("Convênio *")
            novo_carteira = col8.text_input("Carteira *")
            novo_variacao = col9.text_input("Variação")
            if st.form_submit_button("💾 Cadastrar Convênio", type="primary"):
                obrigatorios = [novo_cnpj, novo_razao, novo_ag, novo_conta, novo_convenio, novo_carteira]
                if not all(obrigatorios):
                    st.error("Preencha todos os campos marcados com *.")
                elif not validar_cnpj_cpf(novo_cnpj):
                    st.error("CNPJ inválido. Informe 14 dígitos.")
                else:
                    try:
                        criar_convenio(
                            supabase,
                            user_id,
                            {
                                "cnpj": novo_cnpj,
                                "razao_social": novo_razao,
                                "agencia": novo_ag,
                                "dv_agencia": novo_dv_ag,
                                "conta": novo_conta,
                                "dv_conta": novo_dv_conta,
                                "convenio": novo_convenio,
                                "carteira": novo_carteira,
                                "variacao": novo_variacao,
                            },
                        )
                        st.success("Convênio cadastrado!")
                        st.rerun()
                    except Exception as exc:
                        st.error(traduzir_erro_db(exc))

    mapa_convenios = _mapa_convenios(df_convenios) if not df_convenios.empty else {}
    opcoes = list(mapa_convenios.keys())

    with tab_edit:
        if df_convenios.empty:
            st.info("Cadastre um convênio antes de editar.")
        else:
            conv_sel = st.selectbox("Selecione o Convênio:", [""] + opcoes, key="edit_conv_sel")
            if conv_sel:
                dados = df_convenios[df_convenios["id"] == mapa_convenios[conv_sel]].iloc[0]
                with st.form("form_edit_conv"):
                    col1, col2 = st.columns(2)
                    edit_cnpj = col1.text_input("CNPJ", value=str(dados.get("cnpj", "")))
                    edit_razao = col2.text_input("Razão Social", value=str(dados.get("razao_social", "")))
                    col3, col4, col5, col6 = st.columns(4)
                    edit_ag = col3.text_input("Agência", value=str(dados.get("agencia", "")))
                    edit_dv_ag = col4.text_input("DV Agência", value=str(dados.get("dv_agencia", "")))
                    edit_conta = col5.text_input("Conta", value=str(dados.get("conta", "")))
                    edit_dv_conta = col6.text_input("DV Conta", value=str(dados.get("dv_conta", "")))
                    col7, col8, col9 = st.columns(3)
                    edit_convenio = col7.text_input("Convênio", value=str(dados.get("convenio", "")))
                    edit_carteira = col8.text_input("Carteira", value=str(dados.get("carteira", "")))
                    edit_variacao = col9.text_input("Variação", value=str(dados.get("variacao", "")))
                    if st.form_submit_button("💾 Salvar Convênio", type="primary"):
                        try:
                            atualizar_convenio(
                                supabase,
                                mapa_convenios[conv_sel],
                                {
                                    "cnpj": edit_cnpj,
                                    "razao_social": edit_razao,
                                    "agencia": edit_ag,
                                    "dv_agencia": edit_dv_ag,
                                    "conta": edit_conta,
                                    "dv_conta": edit_dv_conta,
                                    "convenio": edit_convenio,
                                    "carteira": edit_carteira,
                                    "variacao": edit_variacao,
                                },
                            )
                            st.success("Convênio atualizado!")
                            st.rerun()
                        except Exception as exc:
                            st.error(traduzir_erro_db(exc))

    with tab_del:
        if df_convenios.empty:
            st.info("Nenhum convênio para excluir.")
        else:
            conv_excluir = st.selectbox("Convênio a excluir", [""] + opcoes, key="del_conv")
            if conv_excluir:
                st.warning(f"⚠️ Excluindo: {conv_excluir}")
                if st.button("🚨 Confirmar Exclusão do Convênio", type="primary"):
                    try:
                        excluir_convenio(supabase, mapa_convenios[conv_excluir])
                        st.success("Convênio excluído!")
                        st.rerun()
                    except Exception as exc:
                        st.error(traduzir_erro_db(exc))

    return df_convenios


def _formatar_rotulo_remessa(row) -> str:
    created = row.get("created_at", "")
    try:
        dt = pd.to_datetime(created).strftime("%d/%m/%Y %H:%M")
    except (ValueError, TypeError):
        dt = str(created)[:16]
    nome = row.get("nome_arquivo", "")
    qtd = row.get("total_boletos", 0)
    status = str(row.get("status") or STATUS_REMESSA_GERADA)
    rotulo = f"{dt} — {nome} ({qtd} boletos)"
    if status == STATUS_REMESSA_REJEITADA:
        rotulo += " [Rejeitada]"
    elif status == STATUS_REMESSA_ACEITA:
        rotulo += " [Aceita]"
    return rotulo


def _selecionar_referencia_valores(
    supabase: Client,
    user_id: str,
    convenio_id: str,
) -> tuple[str, str | None]:
    with st.expander("Referencia de valores nominais", expanded=False):
        st.caption(
            "Se o banco rejeitar uma remessa, escolha de qual geracao usar os valores de face "
            "enviados antes, para corrigir automaticamente a nova remessa."
        )
        modo = st.radio(
            "Fonte dos valores de face:",
            MODOS_REFERENCIA_VALORES,
            key=f"ref_valores_modo_{convenio_id}",
        )
        remessa_id: str | None = None
        precisa_snapshot = modo in (REF_VALORES_ULTIMA, REF_VALORES_ESCOLHER)

        if precisa_snapshot and not tabela_remessa_valores_disponivel(supabase):
            st.error(MENSAGEM_MIGRATION_004)
            st.markdown(
                "1. Abra o [Supabase Dashboard](https://supabase.com/dashboard) → seu projeto\n"
                "2. **SQL Editor** → **New query**\n"
                "3. Cole o conteudo de `supabase/migrations/004_remessa_valores.sql`\n"
                "4. Clique em **Run**\n"
                "5. Volte aqui e clique em **Atualizar tela**"
            )
        elif modo == REF_VALORES_ULTIMA:
            ultima_id = obter_ultima_remessa_com_valores(supabase, user_id, convenio_id)
            if ultima_id:
                df_todas = listar_remessas_por_convenio(supabase, user_id, convenio_id)
                reg = df_todas[df_todas["id"].astype(str) == ultima_id]
                if not reg.empty:
                    st.caption(f"Sera usada: {_formatar_rotulo_remessa(reg.iloc[0])}")
            else:
                st.caption("Nenhuma remessa anterior com valores salvos para este convenio.")

        elif modo == REF_VALORES_ESCOLHER:
            df_rem = listar_remessas_com_valores(supabase, user_id, convenio_id)
            if df_rem.empty:
                st.info(
                    "Nenhuma remessa anterior possui valores salvos. "
                    "Gere ao menos uma remessa apos executar a migration 004."
                )
            else:
                st.caption(
                    "Remessas rejeitadas aparecem marcadas com [Rejeitada] — "
                    "use-as como referencia ao regenerar o arquivo."
                )
                rotulos = [_formatar_rotulo_remessa(row) for _, row in df_rem.iterrows()]
                indice = st.selectbox(
                    "Remessa de referencia:",
                    range(len(rotulos)),
                    format_func=lambda i: rotulos[i],
                    key=f"ref_remessa_sel_{convenio_id}",
                )
                remessa_id = str(df_rem.iloc[indice]["id"])

    return modo, remessa_id


def render_gerador(supabase: Client, user_id: str, df_convenios: pd.DataFrame, df_clientes: pd.DataFrame):
    if df_convenios.empty:
        st.warning(f"Cadastre ao menos um convênio na aba **{ABA_CONVENIOS_TAB}** antes de gerar remessas.")
        return

    col1, col2 = st.columns(2)
    opcoes_conv = df_convenios["razao_social"].tolist()
    convenio_sel = col1.selectbox("Selecione o Convênio", opcoes_conv)
    arquivo_boletos = col2.file_uploader("Planilha de Boletos", type=["xlsx", "xls"])

    dados_conv_sel = df_convenios[df_convenios["razao_social"] == convenio_sel].iloc[0]
    convenio_id_sel = str(dados_conv_sel.get("id") or "").strip()
    modo_ref_valores, remessa_ref_id = _selecionar_referencia_valores(
        supabase, user_id, convenio_id_sel
    )

    st.divider()
    st.subheader("📦 Montar Lotes de Instrução")
    instrucao = st.selectbox("Instrução para este lote:", INSTRUCOES_CNAB)
    nova_data_str = ""
    if instrucao.startswith("06"):
        nova_data_str = st.text_input("Nova Data Vencimento (DD/MM/AAAA):")

    if st.button("➕ Adicionar ao Lote"):
        st.session_state.feedback_geracao = None
        st.session_state.feedback_geracao_aberto = False
        if not arquivo_boletos:
            st.session_state.feedback_lote = {
                "sucesso": False,
                "mensagem": "Anexe a planilha de boletos antes de adicionar ao lote.",
                "erros": [],
                "avisos": [],
            }
            st.session_state.feedback_lote_aberto = False
        else:
            df_lote = pd.read_excel(arquivo_boletos)
            valido, erros, avisos = validar_planilha(
                df_lote, instrucao, nova_data_str, df_clientes
            )
            if not valido:
                st.session_state.feedback_lote = {
                    "sucesso": False,
                    "mensagem": f"Planilha com {len(erros)} erro(s) — corrija antes de continuar.",
                    "erros": erros,
                    "avisos": avisos,
                }
                st.session_state.feedback_lote_aberto = False
            else:
                st.session_state.lotes.append(
                    {
                        "instrucao": instrucao,
                        "nova_data": nova_data_str,
                        "df": df_lote,
                        "nome_arquivo": arquivo_boletos.name,
                    }
                )
                msg = f"Lote adicionado! ({len(df_lote)} boletos)"
                if avisos:
                    msg += f" — {len(avisos)} aviso(s)."
                st.session_state.feedback_lote = {
                    "sucesso": True,
                    "mensagem": msg,
                    "erros": [],
                    "avisos": avisos,
                }
                st.session_state.feedback_lote_aberto = False

    _exibir_feedback_lote("feedback_lote")

    if st.session_state.lotes:
        st.write("### Carrinho de Lotes")
        for i, lote in enumerate(st.session_state.lotes):
            c1, c2 = st.columns([5, 1])
            c1.write(
                f"**Lote {i + 1}:** {lote['instrucao']} — "
                f"{lote['nome_arquivo']} ({len(lote['df'])} boletos)"
            )
            if c2.button("🗑️", key=f"rm_lote_{i}"):
                st.session_state.lotes.pop(i)
                st.rerun()

        if st.button("🧹 Limpar todos os lotes"):
            st.session_state.lotes = []
            st.session_state.feedback_lote = None
            st.session_state.feedback_lote_aberto = False
            st.rerun()

        st.divider()
        if st.button("🚀 Gerar Arquivo Remessa", type="primary"):
            try:
                dados_bancarios = dados_conv_sel.to_dict()
                try:
                    nsa = contar_remessas_convenio(supabase, user_id, convenio_id) + 1
                except Exception:
                    nsa = 1

                lotes_atuais = list(st.session_state.lotes)
                convenio_id = convenio_id_sel
                valores_conhecidos: dict[str, float] = {}
                descricao_ref = ""
                nosso_numeros: list[str] = []
                try:
                    nosso_numeros = coletar_nosso_numeros_lotes(lotes_atuais)
                    valores_conhecidos, descricao_ref = obter_valores_referencia(
                        supabase,
                        user_id,
                        convenio_id,
                        nosso_numeros,
                        modo_ref_valores,
                        remessa_ref_id,
                    )
                except Exception as exc:
                    st.session_state.aviso_busca_valores = (
                        f"Nao foi possivel consultar valores de referencia: {exc}"
                    )

                resultado = gerar_remessa(
                    lotes_atuais,
                    dados_bancarios,
                    df_clientes,
                    nsa=nsa,
                    valores_conhecidos=valores_conhecidos,
                )

                if resultado.erros_linha:
                    st.session_state.feedback_geracao = {
                        "sucesso": False,
                        "mensagem": (
                            f"Arquivo gerado com {len(resultado.erros_linha)} erro(s) em linhas da planilha."
                        ),
                        "erros": resultado.erros_linha,
                        "avisos": list(resultado.avisos_correcao),
                    }
                    st.session_state.feedback_geracao_aberto = False

                if not resultado.linhas:
                    st.session_state.feedback_geracao = {
                        "sucesso": False,
                        "mensagem": "Nenhuma linha foi gerada. Verifique os dados da planilha.",
                        "erros": resultado.erros_linha,
                        "avisos": [],
                    }
                    _exibir_feedback_lote("feedback_geracao", "Ver detalhes dos erros")
                    return

                arquivo_bytes = linhas_para_bytes(resultado.linhas)
                preview = resultado.linhas[:PREVIEW_LINHAS]
                nome_arquivo = f"remessa_bb_{datetime.now().strftime('%Y%m%d_%H%M%S')}.rem"
                instrucoes = [l["instrucao"] for l in lotes_atuais]

                remessa_id_salva: str | None = None
                dados_remessa = {
                    "convenio_id": convenio_id,
                    "nome_arquivo": nome_arquivo,
                    "total_lotes": resultado.total_lotes,
                    "total_boletos": resultado.total_boletos,
                    "instrucoes": instrucoes,
                    "preview_linhas": preview,
                    "status": STATUS_REMESSA_GERADA,
                }
                try:
                    remessa_id_salva = salvar_remessa(supabase, user_id, dados_remessa)
                except Exception as exc:
                    if _erro_coluna_status_ausente(exc):
                        dados_remessa.pop("status", None)
                        try:
                            remessa_id_salva = salvar_remessa(supabase, user_id, dados_remessa)
                        except Exception:
                            pass
                    else:
                        pass

                if remessa_id_salva and resultado.valores_enviados:
                    try:
                        salvar_snapshot_valores_remessa(
                            supabase,
                            user_id,
                            convenio_id,
                            remessa_id_salva,
                            resultado.valores_enviados,
                        )
                    except Exception:
                        pass

                if resultado.titulos_atualizar:
                    try:
                        upsert_titulos_valores(
                            supabase,
                            user_id,
                            convenio_id,
                            resultado.titulos_atualizar,
                        )
                    except Exception:
                        pass

                st.session_state.lotes = []
                st.session_state.feedback_lote = None
                st.session_state.ultimo_arquivo_remessa = {
                    "bytes": arquivo_bytes,
                    "nome_arquivo": nome_arquivo,
                }

                msg_ok = f"Arquivo **{nome_arquivo}** gerado!"
                correcoes = list(resultado.avisos_correcao)
                avisos_geracao: list[str] = []
                if descricao_ref:
                    avisos_geracao.append(f"Referencia de valores: {descricao_ref}.")
                qtd_registrados = sum(
                    1
                    for nn in nosso_numeros
                    if buscar_valor_registrado(valores_conhecidos, nn) is not None
                )
                if qtd_registrados:
                    avisos_geracao.append(
                        f"{qtd_registrados} título(s) com valor nominal registrado no banco."
                    )
                if resultado.titulos_atualizar:
                    avisos_geracao.append(
                        f"{len(resultado.titulos_atualizar)} valor(es) nominal(is) "
                        "registrado(s) para futuras remessas."
                    )
                if correcoes:
                    msg_ok += (
                        f" **{len(correcoes)} valor(es) de face corrigido(s) automaticamente.**"
                    )
                if resultado.erros_linha:
                    st.session_state.feedback_geracao = {
                        "sucesso": True,
                        "mensagem": msg_ok + f" ({len(resultado.erros_linha)} linha(s) com erro.)",
                        "erros": resultado.erros_linha,
                        "avisos": avisos_geracao,
                        "correcoes": correcoes,
                    }
                else:
                    st.session_state.feedback_geracao = {
                        "sucesso": True,
                        "mensagem": msg_ok,
                        "erros": [],
                        "avisos": avisos_geracao,
                        "correcoes": correcoes,
                    }
                st.session_state.feedback_geracao_aberto = False
                st.rerun()

            except Exception as exc:
                st.error(f"Erro ao gerar arquivo: {traduzir_erro_db(exc)}")

    aviso_busca = st.session_state.pop("aviso_busca_valores", None)
    if aviso_busca:
        st.error(aviso_busca)

    _exibir_feedback_lote("feedback_geracao", "Ver outros detalhes")

    ultimo = st.session_state.get("ultimo_arquivo_remessa")
    if ultimo:
        col_salvar, col_baixar = st.columns(2)
        with col_salvar:
            if st.button("Escolher onde salvar", use_container_width=True, key="btn_abrir_dialog_salvar"):
                _dialog_salvar_remessa()
        with col_baixar:
            st.download_button(
                label="Download arquivo remessa",
                data=ultimo["bytes"],
                file_name=ultimo["nome_arquivo"],
                mime="application/octet-stream",
                use_container_width=True,
            )


def render_historico(supabase: Client, user_id: str):
    _render_titulo(TITULO_HISTORICO_HTML)

    try:
        df_remessas = listar_remessas(supabase, user_id)
    except Exception as exc:
        st.error(traduzir_erro_db(exc))
        st.info(
            "Se a tabela `remessas` ainda não existe, execute o script SQL em "
            "`supabase/migrations/` no painel do Supabase."
        )
        return

    if df_remessas.empty:
        st.info("Nenhuma remessa salva ainda. Gere um arquivo na aba **Gerar Remessa**.")
        return

    _tabela_zebra(_preparar_exibicao_remessas(df_remessas), altura_max=900)

    st.divider()
    st.subheader("Atualizar status da remessa")
    st.caption(
        "Marque como **Rejeitada** quando o banco recusar o arquivo — "
        "fica mais facil identifica-la ao escolher referencia de valores."
    )

    if "id" in df_remessas.columns:
        rotulos_hist = [_formatar_rotulo_remessa(row) for _, row in df_remessas.iterrows()]
        indice_hist = st.selectbox(
            "Remessa:",
            range(len(rotulos_hist)),
            format_func=lambda i: rotulos_hist[i],
            key="hist_remessa_status",
        )
        registro_status = df_remessas.iloc[indice_hist]
        status_atual = str(registro_status.get("status") or STATUS_REMESSA_GERADA)
        indice_status = (
            STATUS_REMESSA_OPCOES.index(status_atual)
            if status_atual in STATUS_REMESSA_OPCOES
            else 0
        )
        novo_status = st.selectbox(
            "Status:",
            STATUS_REMESSA_OPCOES,
            index=indice_status,
            format_func=lambda s: STATUS_REMESSA_LABELS.get(s, s),
            key="hist_novo_status",
        )
        if st.button("Salvar status", type="primary", key="btn_salvar_status_remessa"):
            try:
                atualizar_status_remessa(
                    supabase,
                    user_id,
                    str(registro_status["id"]),
                    novo_status,
                )
                st.success("Status atualizado!")
                st.rerun()
            except Exception as exc:
                if _erro_coluna_status_ausente(exc):
                    st.error(
                        "Coluna status ainda nao existe. "
                        "Execute supabase/migrations/005_remessa_status.sql no Supabase."
                    )
                else:
                    st.error(traduzir_erro_db(exc))

    st.divider()

    if "nome_arquivo" in df_remessas.columns:
        arquivo_sel = st.selectbox(
            "Ver preview de uma remessa:",
            df_remessas["nome_arquivo"].tolist(),
        )
        registro = df_remessas[df_remessas["nome_arquivo"] == arquivo_sel].iloc[0]
        preview = registro.get("preview_linhas") or []
        if preview:
            st.caption("Preview CNAB salvo")
            df_preview = pd.DataFrame(
                {
                    "Linha": list(range(1, len(preview) + 1)),
                    "Conteúdo": [str(linha) for linha in preview],
                }
            )
            _tabela_zebra(df_preview)


def render_valores_nominais(
    supabase: Client,
    user_id: str,
    df_convenios: pd.DataFrame,
):
    _render_titulo(TITULO_VALORES_NOMINAIS_HTML)
    st.caption(
        "Valores registrados apos instrucao 47 (alteracao de valor nominal). "
        "Usados para corrigir automaticamente o montante em novas remessas."
    )

    if df_convenios.empty:
        st.warning(f"Cadastre ao menos um convenio na aba **{ABA_CONVENIOS_TAB}**.")
        return

    convenio_sel = st.selectbox(
        "Convênio:",
        df_convenios["razao_social"].tolist(),
        key="valores_convenio_sel",
    )
    convenio_id = str(
        df_convenios[df_convenios["razao_social"] == convenio_sel].iloc[0]["id"]
    )

    try:
        df_valores = listar_titulos_valores(supabase, user_id, convenio_id)
    except Exception as exc:
        st.error(traduzir_erro_db(exc))
        return

    if df_valores.empty:
        st.info(
            "Nenhum valor registrado para este convenio. "
            "Gere uma remessa com **instrucao 47** para registrar valores nominais."
        )
        return

    filtro = st.text_input("Filtrar por Nosso Número:", key="filtro_nosso_numero")
    df_filtrado = df_valores.copy()
    if filtro.strip():
        mask = df_filtrado["nosso_numero"].astype(str).str.contains(
            filtro.strip(), case=False, na=False
        )
        df_filtrado = df_filtrado[mask]

    st.caption(f"{len(df_filtrado)} titulo(s) encontrado(s).")
    _tabela_zebra(_preparar_exibicao_valores(df_filtrado), altura_max=500)

    st.divider()
    st.subheader("Editar ou excluir")
    if "id" in df_valores.columns:
        opcoes = [
            f"{row['nosso_numero']} — {formatar_real(float(row['valor_nominal']))}"
            for _, row in df_valores.iterrows()
        ]
        indice = st.selectbox(
            "Titulo:",
            range(len(opcoes)),
            format_func=lambda i: opcoes[i],
            key="valores_titulo_sel",
        )
        registro = df_valores.iloc[indice]
        valor_atual = float(registro["valor_nominal"])

        col1, col2 = st.columns(2)
        novo_valor_str = col1.text_input(
            "Novo valor nominal (R$):",
            value=f"{valor_atual:.2f}".replace(".", ","),
            key="valores_novo_valor",
        )
        with col2:
            st.write("")
            st.write("")
            if st.button("Salvar valor", type="primary", key="btn_salvar_valor_titulo"):
                valor_parsed = normalizar_valor_monetario(novo_valor_str)
                if valor_parsed is None:
                    st.error("Valor invalido. Use formato como 1500,00 ou 1500.00")
                else:
                    try:
                        atualizar_valor_nominal_titulo(
                            supabase,
                            user_id,
                            str(registro["id"]),
                            valor_parsed,
                        )
                        st.success("Valor atualizado!")
                        st.rerun()
                    except Exception as exc:
                        st.error(traduzir_erro_db(exc))

        if st.button("Excluir registro", key="btn_excluir_valor_titulo"):
            try:
                excluir_titulo_valor(supabase, user_id, str(registro["id"]))
                st.success("Registro excluido.")
                st.rerun()
            except Exception as exc:
                st.error(traduzir_erro_db(exc))


def render_app(supabase: Client):
    aplicar_estilo()
    user = st.session_state.user
    render_sidebar(supabase, user)

    st.markdown('<p class="main-header">🏦 Gerador de Remessa CNAB 240</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Banco do Brasil — instruções em lote</p>', unsafe_allow_html=True)

    user_id = user.id

    try:
        df_clientes = listar_clientes(supabase, user_id)
    except Exception:
        df_clientes = pd.DataFrame()

    try:
        df_convenios = listar_convenios(supabase, user_id)
    except Exception:
        df_convenios = pd.DataFrame()

    aba_gerador, aba_clientes, aba_convenios, aba_valores, aba_historico = st.tabs(
        ["Gerar Remessa", "Meus Clientes", ABA_CONVENIOS_TAB, ABA_VALORES_TAB, ABA_HISTORICO_TAB]
    )

    with aba_gerador:
        render_gerador(supabase, user_id, df_convenios, df_clientes)

    with aba_clientes:
        render_clientes(supabase, user_id)

    with aba_convenios:
        render_convenios(supabase, user_id)

    with aba_valores:
        render_valores_nominais(supabase, user_id, df_convenios)

    with aba_historico:
        render_historico(supabase, user_id)
