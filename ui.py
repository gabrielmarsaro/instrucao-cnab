"""Componentes de interface Streamlit."""

from __future__ import annotations

import base64
import html as html_lib
import json
from datetime import datetime

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from supabase import Client

from auth import login, logout, recuperar_senha, sign_up
from bb_api import (
    BbApiError,
    HOMOLOG_AGENCIA,
    HOMOLOG_CARTEIRA,
    HOMOLOG_CONTA,
    HOMOLOG_CONVENIO,
    HOMOLOG_VARIACAO,
    INSTRUCOES_API_LABEL,
    ResultadoConsultaBoleto,
    ambientes_bb_para_usuario,
    ativar_credenciais_bb,
    bb_credenciais_configuradas,
    consultar_boleto,
    consultar_boletos_com_erro,
    dataframe_campos_completos_consultas,
    dataframe_resumo_consultas,
    enviar_lotes_api,
    limpar_cache_token_bb,
    mensagem_credenciais_bb,
    sincronizar_credenciais_bb_sessao,
    testar_conexao_bb,
    usuario_pode_homologar,
)
from cnab import (
    buscar_valor_registrado,
    coletar_nosso_numeros_lotes,
    formatar_real,
    gerar_remessa,
    linhas_para_bytes,
    normalizar_valor_monetario,
)
from config import (
    ABA_API_BB_TAB,
    ABA_CONVENIOS_TAB,
    ABA_HISTORICO_TAB,
    ABA_VALORES_TAB,
    APP_VERSION,
    FONTE_APP,
    INSTRUCOES_CNAB,
    MODOS_REFERENCIA_VALORES,
    NAV_API_BB,
    NAV_CLIENTES,
    NAV_CONVENIOS,
    NAV_GERADOR,
    NAV_HISTORICO,
    NAV_OPCOES,
    NAV_VALORES,
    PREVIEW_LINHAS,
    REF_VALORES_ESCOLHER,
    REF_VALORES_ULTIMA,
    STATUS_REMESSA_ACEITA,
    STATUS_REMESSA_GERADA,
    STATUS_REMESSA_LABELS,
    STATUS_REMESSA_OPCOES,
    STATUS_REMESSA_REJEITADA,
    TITULO_API_BB_HTML,
    TITULO_GESTAO_CLIENTES_HTML,
    TITULO_GESTAO_CONVENIOS_HTML,
    TITULO_HISTORICO_HTML,
    TITULO_VALORES_NOMINAIS_HTML,
)
from db import (
    MENSAGEM_MIGRATION_004,
    MENSAGEM_MIGRATION_007,
    _erro_coluna_status_ausente,
    aceitar_convite,
    atualizar_cliente,
    atualizar_convenio,
    atualizar_status_remessa,
    atualizar_valor_nominal_titulo,
    contar_bb_credenciais_cached,
    contar_remessas_convenio,
    convidar_para_base,
    criar_cliente,
    criar_clientes_lote,
    criar_convenio,
    excluir_bb_credenciais,
    excluir_clientes,
    excluir_convenio,
    excluir_titulo_valor,
    invalidar_cache_workspace,
    listar_bases_compartilhadas,
    listar_bb_credenciais,
    listar_clientes,
    listar_clientes_cached,
    listar_compartilhamentos_dono,
    listar_convenios,
    listar_convenios_cached,
    listar_convites_pendentes,
    listar_remessas,
    listar_remessas_com_valores,
    listar_remessas_por_convenio,
    listar_titulos_valores,
    normalizar_cnpj_credencial,
    obter_arquivo_remessa,
    obter_bb_credenciais,
    obter_ultima_remessa_com_valores,
    obter_valores_referencia,
    remover_compartilhamento,
    salvar_bb_credenciais,
    salvar_remessa,
    salvar_remessa_resiliente,
    salvar_snapshot_valores_remessa,
    secrets_configurados,
    tabela_compartilhamentos_disponivel,
    tabela_remessa_valores_disponivel,
    traduzir_erro_db,
    upsert_titulos_valores,
)
from validation import (
    limpar_nosso_numero,
    mapear_colunas_clientes,
    mapear_colunas_planilha,
    preparar_importacao_clientes,
    validar_cnpj_cpf,
    validar_planilha,
)



def _filtrar_lotes_sem_nns(lotes: list[dict], nns_ok: set[str]) -> list[dict]:
    """Remove do carrinho os boletos cujo nosso numero ja foi enviado com sucesso."""
    if not nns_ok:
        return lotes
    novos: list[dict] = []
    for lote in lotes:
        df = lote["df"].copy()
        df.columns = [str(c).strip().lower() for c in df.columns]
        colunas_map = mapear_colunas_planilha(df)
        col_nn = colunas_map.get("nn")
        if not col_nn or col_nn not in df.columns:
            novos.append(lote)
            continue
        mask = ~df[col_nn].map(lambda x: limpar_nosso_numero(x) in nns_ok)
        df2 = df.loc[mask].copy()
        if df2.empty:
            continue
        novos.append({**lote, "df": df2})
    return novos


def _lotes_so_api(lotes: list[dict]) -> bool:
    from bb_api import INSTRUCOES_API_SUPORTADAS, codigo_instrucao_lote

    return all(codigo_instrucao_lote(l) in INSTRUCOES_API_SUPORTADAS for l in lotes)


def _payload_consulta_json(consultas: list[ResultadoConsultaBoleto]) -> list[dict]:
    return [
        {
            "nosso_numero": c.nosso_numero,
            "boleto_id": c.boleto_id,
            "sucesso": c.sucesso,
            "mensagem": c.mensagem,
            "erro_instrucao": c.erro_instrucao,
            "dados": c.dados,
        }
        for c in consultas
    ]


def _exibir_ficha_consulta_boleto(consulta: ResultadoConsultaBoleto) -> None:
    """Ficha resumida + JSON completo em destaque."""
    if not consulta.sucesso:
        st.error(consulta.mensagem or "Falha na consulta.")
        if consulta.erro_instrucao:
            st.caption(f"Erro da instrucao: {consulta.erro_instrucao}")
        return

    resumo = consulta.para_resumo()
    col1, col2, col3 = st.columns(3)
    col1.metric("Situação", resumo.get("Situação") or "—")
    col2.metric("Vencimento", str(resumo.get("Vencimento") or "—"))
    col3.metric(
        "Valor atual",
        str(resumo.get("Valor atual") if resumo.get("Valor atual") != "" else "—"),
    )
    col_pago, col_rec, col_cred = st.columns(3)
    col_pago.metric(
        "Valor pago",
        str(resumo.get("Valor pago") if resumo.get("Valor pago") != "" else "—"),
    )
    col_rec.metric("Recebimento", str(resumo.get("Recebimento") or "—"))
    col_cred.metric("Crédito", str(resumo.get("Crédito") or "—"))
    col4, col5 = st.columns(2)
    col4.write(f"**Pagador:** {resumo.get('Pagador') or '—'}")
    col5.write(f"**CPF:** {resumo.get('CPF') or '—'}")
    if resumo.get("Erro"):
        st.warning(f"**Erro:** {resumo['Erro']}")
    if resumo.get("Próximo passo"):
        st.info(f"**Próximo passo:** {resumo['Próximo passo']}")

    json_boleto = json.dumps(consulta.dados, ensure_ascii=False, indent=2, default=str)
    with st.expander("JSON completo deste boleto", expanded=False):
        st.code(json_boleto, language="json")
        st.download_button(
            "⬇️ Baixar JSON deste boleto",
            data=json_boleto.encode("utf-8"),
            file_name=f"boleto_{consulta.nosso_numero or 'consulta'}.json",
            mime="application/json",
            key=f"btn_json_boleto_{consulta.boleto_id or consulta.nosso_numero}",
        )

    with st.expander("Tabela de todos os campos", expanded=False):
        df_campos = pd.DataFrame(
            [{"Campo": k, "Valor": v} for k, v in consulta.campos_achatados().items()]
        )
        _tabela_zebra(df_campos, altura_max=420)


def _valor_nominal_da_consulta(consulta: ResultadoConsultaBoleto):
    """Valor atual do titulo no BB; se vier vazio, o valor original."""
    if not consulta.sucesso:
        return None
    valor = consulta._primeiro_valor(
        "valorAtualTituloCobranca", "valorAtual"
    )
    if valor in ("", None):
        valor = consulta._primeiro_valor(
            "valorOriginalTituloCobranca", "valorOriginal"
        )
    try:
        valor_f = round(float(valor), 2)
    except (TypeError, ValueError):
        return None
    if valor_f <= 0:
        return None
    return valor_f


def _gravar_valores_consulta_planilha(consultas: list[ResultadoConsultaBoleto]) -> str:
    """Atualiza titulos_valores com o valor que o BB devolveu na consulta."""
    supabase = st.session_state.get("supabase")
    user_id = str(st.session_state.get("api_consulta_user_id") or "").strip()
    convenio_id = str(st.session_state.get("api_consulta_convenio_id") or "").strip()
    if supabase is None or not user_id or not convenio_id:
        return "Consulta feita, mas a base nao foi atualizada (convenio da sessao ausente)."

    registros = []
    for consulta in consultas:
        valor = _valor_nominal_da_consulta(consulta)
        if valor is None:
            continue
        seu = consulta._primeiro_valor(
            "numeroTituloCedenteCobranca", "numeroTituloBeneficiario"
        )
        registros.append(
            {
                "nosso_numero": consulta.nosso_numero,
                "seu_numero": seu or None,
                "valor_nominal": valor,
            }
        )
    if not registros:
        return "Nenhum boleto consultado trouxe valor para gravar na base."
    try:
        qtd = upsert_titulos_valores(supabase, user_id, convenio_id, registros)
    except Exception as exc:
        return f"Consulta feita, mas falhou ao gravar valores: {traduzir_erro_db(exc)}"
    return f"{qtd} valor(es) atualizado(s) na base com o valor atual do BB."


def _exibir_consulta_erros_bb() -> None:
    consultas: list[ResultadoConsultaBoleto] | None = st.session_state.get(
        "ultima_consulta_erros_bb"
    )
    if not consultas:
        return

    st.subheader("Consulta no BB")
    aviso_valores = st.session_state.get("aviso_valores_consulta_planilha")
    if aviso_valores:
        texto = str(aviso_valores)
        if texto.startswith("Consulta feita, mas") or texto.startswith("Nenhum boleto"):
            st.warning(texto)
        else:
            st.success(texto)
    ok = sum(1 for c in consultas if c.sucesso)
    st.caption(
        f"{ok} consultado(s) com sucesso, {len(consultas) - ok} falha(s) na consulta."
    )
    df_resumo = dataframe_resumo_consultas(consultas)
    _tabela_zebra(df_resumo, altura_max=400)

    payload = _payload_consulta_json(consultas)
    json_completo = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    col_json, col_csv = st.columns(2)
    with col_json:
        st.download_button(
            "⬇️ Baixar JSON completo",
            data=json_completo.encode("utf-8"),
            file_name=f"consulta_bb_{stamp}.json",
            mime="application/json",
            use_container_width=True,
            key="btn_json_consulta_erros_bb",
        )
    with col_csv:
        st.download_button(
            "Baixar resumo (CSV)",
            data=df_resumo.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"consulta_bb_resumo_{stamp}.csv",
            mime="text/csv",
            use_container_width=True,
            key="btn_csv_consulta_resumo_bb",
        )

    with st.expander("Ver JSON completo (todos os boletos)", expanded=False):
        st.code(json_completo, language="json")

    with st.expander("Baixar CSV com todos os campos", expanded=False):
        df_full = dataframe_campos_completos_consultas(consultas)
        st.download_button(
            "Baixar completo (CSV)",
            data=df_full.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"consulta_bb_erros_{stamp}.csv",
            mime="text/csv",
            key="btn_csv_consulta_erros_bb",
        )

    opcoes = {
        f"{c.nosso_numero or '?'} ({'OK' if c.sucesso else 'falha consulta'})": i
        for i, c in enumerate(consultas)
    }
    if opcoes:
        escolha = st.selectbox(
            "Detalhe do boleto",
            options=list(opcoes.keys()),
            key="sel_detalhe_consulta_erro_bb",
        )
        _exibir_ficha_consulta_boleto(consultas[opcoes[escolha]])


def _exibir_resultado_api_tabela():
    """Tabela com nosso numero + status/erro de cada boleto do ultimo envio API."""
    df = st.session_state.get("ultimo_resultado_api_df")
    if df is None or (isinstance(df, pd.DataFrame) and df.empty):
        return
    st.subheader("Resultado por boleto (API BB)")
    st.caption(
        "Cada linha e um nosso numero da remessa. "
        "Erros HTTP 5xx / codigo 4125718 costumam ser falha tecnica do BB "
        "(nao detalham campo invalido)."
    )
    _tabela_zebra(df, altura_max=500)
    csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "Baixar resultado (CSV)",
        data=csv_bytes,
        file_name=f"resultado_api_bb_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
        key="btn_csv_resultado_api",
    )

    _exibir_json_chamada_api()
    _exibir_botao_consultar_planilha()


def _exibir_json_chamada_api() -> None:
    """JSON enviado ao BB, recolhido ate o cliente abrir."""
    chamadas = st.session_state.get("ultimo_chamadas_api") or []
    if not chamadas:
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_chamada = json.dumps(chamadas, ensure_ascii=False, indent=2, default=str)
    with st.expander("Ver JSON da chamada", expanded=False):
        st.caption("Corpo enviado em cada boleto. Nao inclui token nem App Key.")
        st.code(json_chamada, language="json")
        st.download_button(
            "Baixar JSON da chamada",
            data=json_chamada.encode("utf-8"),
            file_name=f"chamada_bb_{stamp}.json",
            mime="application/json",
            key="btn_json_chamada_api",
        )


def _itens_consulta_planilha() -> list[dict]:
    """Todos os nossos numeros da planilha, com o erro da instrucao quando houver."""
    nns = st.session_state.get("api_nns_planilha") or []
    erros = st.session_state.get("ultimo_resultado_api_erros") or []
    por_nn = {}
    for erro in erros:
        chave = limpar_nosso_numero(erro.get("nosso_numero"))
        if chave:
            por_nn[chave] = erro
    itens = []
    for nn in nns:
        erro = por_nn.get(limpar_nosso_numero(nn), {})
        itens.append(
            {
                "nosso_numero": nn,
                "boleto_id": erro.get("boleto_id") or "",
                "mensagem": erro.get("mensagem") or "",
                "status_http": erro.get("status_http"),
                "codigo_bb": erro.get("codigo_bb") or "",
                "providencia": erro.get("providencia") or "",
                "instrucao": erro.get("instrucao") or "",
            }
        )
    return itens


def _exibir_botao_consultar_planilha() -> None:
    """No erro da API, oferece consulta de todos os nossos numeros da planilha."""
    feedback = st.session_state.get("feedback_geracao") or {}
    erros = st.session_state.get("ultimo_resultado_api_erros") or []
    houve_erro = (not feedback.get("sucesso")) or bool(erros)
    itens = _itens_consulta_planilha()
    convenio = st.session_state.get("ultimo_api_convenio") or ""
    if not houve_erro or not itens:
        return

    st.caption(
        f"{len(itens)} nosso(s) numero(s) da planilha. "
        "A consulta traz o estado atual de todos no BB, nao so das linhas que falharam."
    )
    if not convenio:
        st.warning("Convenio sem numero — nao da para consultar os boletos no BB.")
        return
    if st.button(
        "Consultar nossos números da planilha",
        use_container_width=True,
        key="btn_consultar_erros_bb",
    ):
        try:
            if not bb_credenciais_configuradas():
                st.error(mensagem_credenciais_bb())
            else:
                prog = st.progress(0, text="Consultando no BB...")

                def _on_c(feitos, total, nn):
                    prog.progress(
                        min(feitos / total if total else 1.0, 1.0),
                        text=f"Consulta {feitos}/{total} — {nn or '...'}",
                    )

                consultas = consultar_boletos_com_erro(
                    itens, convenio, on_progress=_on_c
                )
                prog.progress(1.0, text="Consulta concluida.")
                st.session_state.ultima_consulta_erros_bb = consultas
                st.session_state.aviso_valores_consulta_planilha = (
                    _gravar_valores_consulta_planilha(consultas)
                )
                st.rerun()
        except BbApiError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"Falha ao consultar boletos no BB: {exc}")


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

    # Resultado API em tabela (melhor para muitos boletos)
    if chave == "feedback_geracao":
        _exibir_resultado_api_tabela()
        if st.session_state.get("ultimo_resultado_api_df") is None or (
            isinstance(st.session_state.get("ultimo_resultado_api_df"), pd.DataFrame)
            and st.session_state.get("ultimo_resultado_api_df").empty
        ):
            _exibir_botao_consultar_planilha()

    if correcoes:
        lista = "\n".join(f"- {item}" for item in correcoes)
        st.warning(
            f"**{len(correcoes)} valor(es) de face corrigido(s) automaticamente** "
            f"para coincidir com o valor nominal registrado no banco:\n\n{lista}"
        )

    if not erros and not avisos:
        return

    # Se ja mostrou tabela API, nao lista erros em texto (evita poluir)
    if chave == "feedback_geracao" and st.session_state.get("ultimo_resultado_api_df") is not None:
        if avisos:
            with st.expander("Avisos"):
                for item in avisos:
                    st.warning(f"• {item}")
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
    """Tabela zebra para poucos registros; st.dataframe para volumes maiores."""
    if df.empty:
        st.info("Nenhum registro para exibir.")
        return

    if len(df) > 80:
        st.dataframe(df, use_container_width=True, height=min(altura_max, 560))
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


def _rotulo_base(meu_id: str, base_id: str, dono_email: str | None) -> str:
    if str(base_id) == str(meu_id):
        return "Minha base"
    email = (dono_email or "").strip() or "outro usuario"
    return f"Base compartilhada: {email}"


def _bases_acessiveis(supabase: Client, user) -> list[dict]:
    bases = [{"id": str(user.id), "label": "Minha base"}]
    df = listar_bases_compartilhadas(supabase, str(user.id))
    if df.empty:
        return bases
    vistos = {str(user.id)}
    for _, row in df.iterrows():
        dono_id = str(row.get("dono_id") or "")
        if not dono_id or dono_id in vistos:
            continue
        vistos.add(dono_id)
        bases.append(
            {
                "id": dono_id,
                "label": _rotulo_base(str(user.id), dono_id, row.get("dono_email")),
            }
        )
    return bases


def _garantir_workspace(user, bases: list[dict]) -> str:
    ids = [b["id"] for b in bases]
    atual = str(st.session_state.get("workspace_user_id") or user.id)
    if atual not in ids:
        atual = str(user.id)
        st.session_state.workspace_user_id = atual
    return atual


def render_compartilhamento(supabase: Client, user, workspace_user_id: str):
    st.sidebar.markdown("### Compartilhar base")
    if not tabela_compartilhamentos_disponivel(supabase):
        st.sidebar.warning(MENSAGEM_MIGRATION_007)
        return

    meu_id = str(user.id)
    meu_email = str(getattr(user, "email", "") or "")

    convites = listar_convites_pendentes(supabase, meu_email)
    if not convites.empty:
        st.sidebar.info("Voce recebeu um convite para usar a base de outro usuario.")
        for _, convite in convites.iterrows():
            dono_email = convite.get("dono_email") or "usuario"
            convite_id = str(convite["id"])
            st.sidebar.caption(f"De: {dono_email}")
            c1, c2 = st.sidebar.columns(2)
            if c1.button("Aceitar", key=f"aceitar_{convite_id}", use_container_width=True):
                try:
                    aceitar_convite(supabase, convite_id, meu_id)
                    st.session_state.workspace_user_id = str(convite.get("dono_id") or meu_id)
                    st.session_state.pop("sel_base_dados", None)
                    st.session_state.lotes = []
                    st.session_state.remessa_gerada = None
                    st.sidebar.success("Convite aceito.")
                    st.rerun()
                except Exception as exc:
                    st.sidebar.error(traduzir_erro_db(exc))
            if c2.button("Recusar", key=f"recusar_{convite_id}", use_container_width=True):
                try:
                    remover_compartilhamento(supabase, convite_id)
                    st.rerun()
                except Exception as exc:
                    st.sidebar.error(traduzir_erro_db(exc))

    sou_dono_da_base = workspace_user_id == meu_id
    if not sou_dono_da_base:
        st.sidebar.caption(
            "Voce esta na base de outro usuario. "
            "Somente o dono convida ou remove pessoas."
        )
        if st.sidebar.button("Sair desta base compartilhada", key="sair_base_compartilhada"):
            st.session_state.workspace_user_id = meu_id
            st.session_state.pop("sel_base_dados", None)
            st.session_state.lotes = []
            st.session_state.remessa_gerada = None
            st.rerun()
        return

    email_convite = st.sidebar.text_input(
        "E-mail para compartilhar",
        key="email_compartilhar",
        placeholder="pessoa@empresa.com",
    )
    if st.sidebar.button("Enviar convite", type="primary", use_container_width=True, key="btn_convidar"):
        try:
            convidar_para_base(supabase, meu_id, meu_email, email_convite)
            st.sidebar.success("Convite enviado. A outra pessoa precisa entrar no app e aceitar.")
            st.rerun()
        except ValueError as exc:
            st.sidebar.error(str(exc))
        except Exception as exc:
            st.sidebar.error(traduzir_erro_db(exc))

    df_shares = listar_compartilhamentos_dono(supabase, meu_id)
    if df_shares.empty:
        st.sidebar.caption("Ninguem mais tem acesso a sua base.")
        return

    st.sidebar.caption("Quem tem acesso")
    for _, row in df_shares.iterrows():
        status = str(row.get("status") or "")
        label_status = "Aceito" if status == "aceito" else "Aguardando aceite"
        email = row.get("convidado_email") or ""
        share_id = str(row["id"])
        st.sidebar.write(f"{email} — {label_status}")
        if st.sidebar.button("Revogar", key=f"revogar_{share_id}"):
            try:
                remover_compartilhamento(supabase, share_id)
                st.rerun()
            except Exception as exc:
                st.sidebar.error(traduzir_erro_db(exc))


def render_sidebar(supabase: Client, user):
    st.sidebar.markdown("### Menu")
    st.sidebar.write(f"👤 **{user.email}**")
    st.sidebar.divider()

    bases = _bases_acessiveis(supabase, user)
    workspace_user_id = _garantir_workspace(user, bases)
    if len(bases) > 1:
        labels = [b["label"] for b in bases]
        ids = [b["id"] for b in bases]
        indice = ids.index(workspace_user_id) if workspace_user_id in ids else 0
        escolhido = st.sidebar.selectbox("Base de dados", labels, index=indice, key="sel_base_dados")
        novo_id = ids[labels.index(escolhido)]
        if novo_id != workspace_user_id:
            st.session_state.workspace_user_id = novo_id
            st.session_state.lotes = []
            st.session_state.remessa_gerada = None
            limpar_cache_token_bb()
            st.session_state.pop("bb_credenciais_workspace", None)
            st.rerun()
        workspace_user_id = novo_id

    if st.session_state.get("bb_creds_workspace_id") != str(workspace_user_id):
        sincronizar_credenciais_bb_sessao(None)
        st.session_state.bb_creds_workspace_id = str(workspace_user_id)
        limpar_cache_token_bb()

    if st.sidebar.button("Atualizar tela", use_container_width=True, help="Recarrega o app (use isto em vez de Ctrl+F5)"):
        invalidar_cache_workspace(str(workspace_user_id))
        st.cache_data.clear()
        st.cache_resource.clear()
        st.rerun()
    if st.sidebar.button("🚪 Sair", use_container_width=True):
        logout(supabase)
    st.sidebar.markdown("---")
    render_compartilhamento(supabase, user, workspace_user_id)
    st.sidebar.markdown("---")
    st.sidebar.caption("CNAB 240 · Banco do Brasil")
    try:
        qtd_creds = contar_bb_credenciais_cached(supabase, str(workspace_user_id))
    except Exception:
        qtd_creds = 0
    if qtd_creds:
        st.sidebar.caption(f"API BB: {qtd_creds} CNPJ(s) com credencial")
    else:
        st.sidebar.caption("API BB: configure por CNPJ na aba API BB")
    st.sidebar.caption(f"Versao interface: {APP_VERSION}")
    return workspace_user_id


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
                        invalidar_cache_workspace(user_id)
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
                            invalidar_cache_workspace(user_id)
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
                        invalidar_cache_workspace(user_id)
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
                        invalidar_cache_workspace(user_id)
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
                            invalidar_cache_workspace(user_id)
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
                        invalidar_cache_workspace(user_id)
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
    dias_protesto = 3
    if instrucao.startswith("09"):
        dias_protesto = int(
            st.number_input(
                "Dias para protesto (API)",
                min_value=1,
                max_value=99,
                value=3,
                key="dias_protesto_lote",
            )
        )

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
                        "dias_protesto": dias_protesto,
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
        st.caption(
            "Use **CNAB** para o que a API ainda nao cobre. "
            f"API BB agora: **{INSTRUCOES_API_LABEL}**."
        )
        email_user = str(getattr(st.session_state.get("user"), "email", "") or "")
        cfg_sess = st.session_state.get("bb_credenciais_workspace") or {}
        amb_ativo = str(cfg_sess.get("ambiente") or "").lower()
        if usuario_pode_homologar(email_user) and amb_ativo in ("homologacao", "sandbox"):
            st.info(
                f"**Homologacao BB** — convenio `{HOMOLOG_CONVENIO}`, "
                f"ag `{HOMOLOG_AGENCIA}`, cc `{HOMOLOG_CONTA}`, "
                f"carteira `{HOMOLOG_CARTEIRA}/{HOMOLOG_VARIACAO}`. "
                "Nosso numero API: `000` + convenio(7) + controle(10). "
                "Alteracao/baixa so apos **30 minutos** da geracao do boleto."
            )
        elif amb_ativo == "producao":
            st.warning(
                "**Ambiente: PRODUCAO** — as instrucoes enviadas pela API "
                "alteram boletos reais."
            )
        api_ok = _lotes_so_api(st.session_state.lotes)
        if not api_ok:
            st.warning(
                "Algum lote tem instrucao **fora da API**. "
                "Use **CNAB** para esses, ou remova do carrinho. "
                f"API: {INSTRUCOES_API_LABEL}."
            )
        col_cnab, col_api = st.columns(2)
        gerar_cnab = col_cnab.button(
            "📄 Gerar Remessa CNAB",
            type="primary",
            use_container_width=True,
            key="btn_gerar_cnab",
        )
        enviar_api = col_api.button(
            "🌐 Enviar via API BB",
            use_container_width=True,
            key="btn_enviar_api_bb",
            disabled=not api_ok,
        )

        if gerar_cnab:
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
                    "arquivo_b64": base64.b64encode(arquivo_bytes).decode("ascii"),
                }
                avisos_persistencia: list[str] = []
                try:
                    remessa_id_salva = salvar_remessa_resiliente(supabase, user_id, dados_remessa)
                    if not remessa_id_salva:
                        avisos_persistencia.append(
                            "Arquivo gerado, mas a remessa nao foi gravada no historico."
                        )
                except Exception as exc:
                    remessa_id_salva = None
                    avisos_persistencia.append(
                        f"Arquivo gerado, mas falhou ao gravar no historico: {traduzir_erro_db(exc)}"
                    )

                if remessa_id_salva and resultado.valores_enviados:
                    try:
                        salvar_snapshot_valores_remessa(
                            supabase,
                            user_id,
                            convenio_id,
                            remessa_id_salva,
                            resultado.valores_enviados,
                        )
                    except Exception as exc:
                        avisos_persistencia.append(
                            f"Snapshot de valores nao gravado: {traduzir_erro_db(exc)}"
                        )

                if resultado.titulos_atualizar:
                    try:
                        upsert_titulos_valores(
                            supabase,
                            user_id,
                            convenio_id,
                            resultado.titulos_atualizar,
                        )
                    except Exception as exc:
                        avisos_persistencia.append(
                            f"Valores nominais nao gravados: {traduzir_erro_db(exc)}"
                        )

                st.session_state.lotes = []
                st.session_state.feedback_lote = None
                st.session_state.ultimo_arquivo_remessa = {
                    "bytes": arquivo_bytes,
                    "nome_arquivo": nome_arquivo,
                }

                msg_ok = f"Arquivo **{nome_arquivo}** gerado!"
                correcoes = list(resultado.avisos_correcao)
                avisos_geracao: list[str] = list(avisos_persistencia)
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

        if enviar_api:
            try:
                dados_bancarios = dados_conv_sel.to_dict()
                lotes_atuais = list(st.session_state.lotes)
                try:
                    st.session_state.api_nns_planilha = coletar_nosso_numeros_lotes(
                        lotes_atuais
                    )
                except Exception:
                    st.session_state.api_nns_planilha = []
                st.session_state.ultimo_api_convenio = "".join(
                    filter(str.isdigit, str(dados_bancarios.get("convenio", "")))
                )
                st.session_state.api_consulta_user_id = user_id
                st.session_state.api_consulta_convenio_id = convenio_id_sel
                cnpj_conv = normalizar_cnpj_credencial(str(dados_bancarios.get("cnpj") or ""))
                creds_cnpj = obter_bb_credenciais(supabase, user_id, cnpj_conv) if cnpj_conv else None
                ativar_credenciais_bb(creds_cnpj)
                if not bb_credenciais_configuradas():
                    st.session_state.ultimo_resultado_api_df = None
                    st.session_state.ultimo_resultado_api_erros = []
                    st.session_state.feedback_geracao = {
                        "sucesso": False,
                        "mensagem": mensagem_credenciais_bb(
                            cnpj_conv or "(sem CNPJ no convenio)"
                        ),
                        "erros": ["Credenciais da API do BB nao configuradas."],
                        "avisos": [],
                    }
                    st.rerun()
                email_envio = str(
                    getattr(st.session_state.get("user"), "email", "") or ""
                )
                amb_envio = str((creds_cnpj or {}).get("ambiente") or "").lower()
                if (
                    not usuario_pode_homologar(email_envio)
                    and amb_envio
                    and amb_envio != "producao"
                ):
                    st.session_state.ultimo_resultado_api_df = None
                    st.session_state.ultimo_resultado_api_erros = []
                    st.session_state.feedback_geracao = {
                        "sucesso": False,
                        "mensagem": (
                            "Este usuario so pode usar a API em producao. "
                            "Na aba API BB, salve as credenciais de producao deste CNPJ."
                        ),
                        "erros": ["Ambiente da credencial nao e producao."],
                        "avisos": [],
                    }
                    st.rerun()

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

                progress = st.progress(0, text="Enviando via API BB...")
                status_txt = st.empty()

                def _on_prog(feitos, total, nn):
                    frac = (feitos / total) if total else 1.0
                    progress.progress(
                        min(frac, 1.0),
                        text=f"API BB {feitos}/{total} — {nn or '...'}",
                    )
                    status_txt.caption(
                        f"CNPJ {cnpj_conv} · {(creds_cnpj or {}).get('ambiente', '?')}"
                    )

                ja_ok = set(st.session_state.get("api_nn_enviados_ok") or [])
                resultado_api = enviar_lotes_api(
                    lotes_atuais,
                    dados_bancarios,
                    valores_conhecidos=valores_conhecidos,
                    on_progress=_on_prog,
                    pular_nosso_numeros=ja_ok,
                )
                progress.progress(1.0, text="Envio concluido.")

                erros_api = [
                    f"{linha.nosso_numero}: {linha.mensagem}"
                    for linha in resultado_api.linhas
                    if not linha.sucesso
                ]
                avisos_api = list(resultado_api.avisos)
                if descricao_ref:
                    avisos_api.append(f"Referencia de valores: {descricao_ref}.")

                if resultado_api.titulos_atualizar:
                    try:
                        upsert_titulos_valores(
                            supabase,
                            user_id,
                            convenio_id,
                            resultado_api.titulos_atualizar,
                        )
                        avisos_api.append(
                            f"{len(resultado_api.titulos_atualizar)} valor(es) nominal(is) "
                            "registrado(s) apos envio pela API."
                        )
                    except Exception:
                        avisos_api.append(
                            "Envio OK, mas falhou ao gravar valores nominais no Supabase."
                        )

                df_resultado = resultado_api.dataframe_resultado()
                st.session_state.ultimo_resultado_api_df = df_resultado
                st.session_state.ultimo_resultado_api_erros = [
                    {
                        "nosso_numero": linha.nosso_numero,
                        "boleto_id": linha.boleto_id,
                        "mensagem": linha.mensagem,
                        "status_http": linha.status_http,
                        "codigo_bb": linha.codigo_bb,
                        "providencia": linha.providencia,
                        "instrucao": linha.instrucao,
                    }
                    for linha in resultado_api.linhas
                    if not linha.sucesso
                ]
                st.session_state.ultimo_api_convenio = "".join(
                    filter(str.isdigit, str(dados_bancarios.get("convenio", "")))
                )
                st.session_state.ultimo_chamadas_api = [
                    {
                        "nosso_numero": linha.nosso_numero,
                        "boleto_id": linha.boleto_id,
                        "instrucao": linha.instrucao,
                        "http": linha.status_http,
                        "sucesso": linha.sucesso,
                        **(linha.chamada or {}),
                    }
                    for linha in resultado_api.linhas
                    if linha.chamada
                ]
                st.session_state.ultima_consulta_erros_bb = None

                preview = []
                for l in resultado_api.linhas[:PREVIEW_LINHAS]:
                    preview.append(
                        f"{'OK' if l.sucesso else 'ERRO'} | {l.nosso_numero} | "
                        f"HTTP {l.status_http or '-'} | {l.codigo_bb or '-'} | {l.mensagem}"
                    )
                nome_registro = (
                    f"api_bb_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    f"_{resultado_api.sucessos}ok_{resultado_api.falhas}erro"
                )
                try:
                    remessa_id_api = salvar_remessa_resiliente(
                        supabase,
                        user_id,
                        {
                            "convenio_id": convenio_id,
                            "nome_arquivo": nome_registro,
                            "total_lotes": len(lotes_atuais),
                            "total_boletos": resultado_api.total,
                            "instrucoes": [l["instrucao"] for l in lotes_atuais],
                            "preview_linhas": preview,
                            "status": (
                                STATUS_REMESSA_ACEITA
                                if resultado_api.falhas == 0 and resultado_api.sucessos > 0
                                else STATUS_REMESSA_GERADA
                            ),
                        },
                    )
                    if remessa_id_api and resultado_api.valores_enviados:
                        salvar_snapshot_valores_remessa(
                            supabase,
                            user_id,
                            convenio_id,
                            remessa_id_api,
                            resultado_api.valores_enviados,
                        )
                except Exception as exc:
                    avisos_api.append(
                        f"Envio processado, mas falhou ao gravar no historico: "
                        f"{traduzir_erro_db(exc)}"
                    )

                nns_ok_agora = {
                    limpar_nosso_numero(l.nosso_numero)
                    for l in resultado_api.linhas
                    if l.sucesso and l.nosso_numero
                }
                ja_ok |= nns_ok_agora
                st.session_state.api_nn_enviados_ok = list(ja_ok)

                if resultado_api.sucessos and resultado_api.falhas == 0:
                    st.session_state.lotes = []
                    st.session_state.feedback_lote = None
                    st.session_state.api_nn_enviados_ok = []
                    st.session_state.feedback_geracao = {
                        "sucesso": True,
                        "mensagem": (
                            f"API BB: **{resultado_api.sucessos}** boleto(s) enviado(s) com sucesso. "
                            "Veja a tabela abaixo."
                        ),
                        "erros": [],
                        "avisos": avisos_api,
                    }
                elif resultado_api.sucessos:
                    st.session_state.lotes = _filtrar_lotes_sem_nns(
                        list(st.session_state.lotes), nns_ok_agora
                    )
                    st.session_state.feedback_geracao = {
                        "sucesso": True,
                        "mensagem": (
                            f"API BB: **{resultado_api.sucessos}** ok, "
                            f"**{resultado_api.falhas}** com erro. "
                            "Boletos OK sairam do carrinho — reenvie so os erros."
                        ),
                        "erros": erros_api,
                        "avisos": avisos_api,
                    }
                else:
                    st.session_state.feedback_geracao = {
                        "sucesso": False,
                        "mensagem": (
                            f"API BB: nenhum boleto enviado com sucesso "
                            f"({resultado_api.falhas} erro(s)). Veja a tabela abaixo."
                        ),
                        "erros": erros_api,
                        "avisos": avisos_api,
                    }
                st.session_state.feedback_geracao_aberto = False
                st.rerun()
            except BbApiError as exc:
                st.session_state.ultimo_resultado_api_df = None
                st.session_state.ultimo_resultado_api_erros = []
                st.session_state.feedback_geracao = {
                    "sucesso": False,
                    "mensagem": str(exc),
                    "erros": [str(exc)],
                    "avisos": [],
                }
                st.session_state.feedback_geracao_aberto = False
                st.rerun()
            except Exception as exc:
                st.session_state.ultimo_resultado_api_df = None
                st.session_state.ultimo_resultado_api_erros = []
                st.session_state.feedback_geracao = {
                    "sucesso": False,
                    "mensagem": f"Erro ao enviar pela API do BB: {traduzir_erro_db(exc)}",
                    "erros": [traduzir_erro_db(exc)],
                    "avisos": [],
                }
                st.session_state.feedback_geracao_aberto = False
                st.rerun()

    aviso_busca = st.session_state.pop("aviso_busca_valores", None)
    if aviso_busca:
        st.error(aviso_busca)

    _exibir_feedback_lote("feedback_geracao", "Ver outros detalhes")

    msg_avulsa = st.session_state.pop("feedback_consulta_avulsa", None)
    if msg_avulsa:
        if "falhou" in str(msg_avulsa).lower():
            st.error(msg_avulsa)
        else:
            st.success(msg_avulsa)

    # Resultado de consulta (erros do lote OU avulsa) — sempre visivel quando houver
    _exibir_consulta_erros_bb()

    st.divider()
    st.subheader("Consulta avulsa no BB")
    st.caption(
        "Informe o nosso numero do convenio selecionado acima. "
        "O resultado aparece na secao **Consulta no BB** (com Ver/Baixar JSON)."
    )
    nn_avulso = st.text_input("Nosso numero", key="consulta_avulsa_nn")
    if st.button("🔍 Consultar boleto", type="primary", key="btn_consulta_avulsa_bb"):
        try:
            if not (nn_avulso or "").strip():
                st.error("Informe o nosso numero.")
            else:
                dados_b = dados_conv_sel.to_dict()
                cnpj_a = normalizar_cnpj_credencial(str(dados_b.get("cnpj") or ""))
                creds_a = (
                    obter_bb_credenciais(supabase, user_id, cnpj_a) if cnpj_a else None
                )
                ativar_credenciais_bb(creds_a)
                if not bb_credenciais_configuradas():
                    st.error(mensagem_credenciais_bb(cnpj_a or ""))
                else:
                    conv = "".join(
                        filter(str.isdigit, str(dados_b.get("convenio", "")))
                    )
                    from bb_api import montar_numero_titulo_cliente

                    nn_limpo = limpar_nosso_numero(nn_avulso)
                    bid = montar_numero_titulo_cliente(conv, nn_limpo)
                    with st.spinner(f"Consultando {bid}..."):
                        cons = consultar_boleto(
                            bid, conv, nosso_numero=nn_limpo
                        )
                    st.session_state.ultima_consulta_erros_bb = [cons]
                    st.session_state.pop("mostrar_json_consulta_bb", None)
                    if cons.sucesso:
                        st.session_state.feedback_consulta_avulsa = (
                            f"Consulta OK: {nn_limpo}. Veja o resumo abaixo "
                            "(expanda o JSON se quiser)."
                        )
                    else:
                        st.session_state.feedback_consulta_avulsa = (
                            f"Consulta falhou: {cons.mensagem}"
                        )
                    st.rerun()
        except BbApiError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(str(exc))

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
        st.subheader("Baixar / visualizar remessa")
        arquivo_sel = st.selectbox(
            "Selecione a remessa:",
            df_remessas["nome_arquivo"].tolist(),
        )
        registro = df_remessas[df_remessas["nome_arquivo"] == arquivo_sel].iloc[0]

        remessa_id_dl = str(registro.get("id") or "")
        arquivo_b64 = None
        if remessa_id_dl:
            try:
                arquivo_b64 = obter_arquivo_remessa(supabase, user_id, remessa_id_dl)
            except Exception as exc:
                st.warning(f"Nao foi possivel buscar o arquivo: {traduzir_erro_db(exc)}")
        if arquivo_b64:
            try:
                arquivo_bytes = base64.b64decode(str(arquivo_b64))
                st.download_button(
                    label="⬇️ Baixar arquivo completo (.rem)",
                    data=arquivo_bytes,
                    file_name=str(arquivo_sel),
                    mime="application/octet-stream",
                    type="primary",
                    key="btn_redownload_remessa",
                )
            except Exception:
                st.warning("Não foi possível reconstruir o arquivo desta remessa.")
        else:
            canal = "API" if str(arquivo_sel).startswith("api_bb_") else "CNAB"
            if canal == "API":
                st.info(
                    "Remessa gerada via **API BB** (sem arquivo CNAB). "
                    "Use a tabela de resultado / consulta na aba Gerar Remessa."
                )
            else:
                st.info(
                    "Arquivo CNAB nao disponivel nesta remessa "
                    "(gerada antes da migration 006 ou nao gravado)."
                )

        preview = registro.get("preview_linhas") or []
        if preview:
            st.caption("Preview CNAB salvo (primeiras linhas)")
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


def _cnpjs_dos_convenios(df_convenios: pd.DataFrame) -> pd.DataFrame:
    """CNPJs distintos dos convênios, com razão social e qtd de convênios."""
    if df_convenios is None or df_convenios.empty or "cnpj" not in df_convenios.columns:
        return pd.DataFrame(columns=["cnpj", "razao_social", "qtd_convenios"])
    df = df_convenios.copy()
    df["cnpj_norm"] = df["cnpj"].apply(normalizar_cnpj_credencial)
    df = df[df["cnpj_norm"].astype(str).str.len() > 0]
    if df.empty:
        return pd.DataFrame(columns=["cnpj", "razao_social", "qtd_convenios"])
    agrupado = (
        df.groupby("cnpj_norm", as_index=False)
        .agg(
            razao_social=("razao_social", "first"),
            qtd_convenios=("cnpj_norm", "count"),
        )
        .rename(columns={"cnpj_norm": "cnpj"})
    )
    return agrupado.sort_values("razao_social", na_position="last").reset_index(drop=True)


def render_api_bb(supabase: Client, user_id: str, df_convenios: pd.DataFrame, user=None):
    _render_titulo(TITULO_API_BB_HTML)
    st.caption(
        "Cole as credenciais do Portal Developers BB **por CNPJ**. "
        "Todos os convênios do mesmo CNPJ usam a mesma chave."
    )

    df_cnpjs = _cnpjs_dos_convenios(df_convenios)
    try:
        df_creds = listar_bb_credenciais(supabase, user_id)
    except Exception as exc:
        st.warning(
            "Nao foi possivel listar credenciais. Execute "
            "`supabase/migrations/008_bb_credenciais.sql` no Supabase. "
            f"({traduzir_erro_db(exc)})"
        )
        df_creds = pd.DataFrame()

    cnpjs_ok = set()
    if not df_creds.empty and "cnpj" in df_creds.columns:
        cnpjs_ok = set(df_creds["cnpj"].astype(str).tolist())

    if df_cnpjs.empty:
        st.info(
            f"Cadastre ao menos um convenio na aba **{ABA_CONVENIOS_TAB}** "
            "para vincular credenciais ao CNPJ."
        )
        return

    # Status por CNPJ
    linhas_status = []
    for _, row in df_cnpjs.iterrows():
        cnpj = str(row["cnpj"])
        linhas_status.append(
            {
                "CNPJ": cnpj,
                "Razao Social": row.get("razao_social") or "",
                "Convenios": int(row.get("qtd_convenios") or 0),
                "API BB": "Configurado" if cnpj in cnpjs_ok else "Pendente",
            }
        )
    _tabela_zebra(pd.DataFrame(linhas_status), altura_max=320)

    st.divider()
    st.subheader("Colar credenciais do CNPJ")

    opcoes = [
        f"{row['cnpj']} — {row.get('razao_social') or 'S/N'} ({int(row['qtd_convenios'])} convenio(s))"
        for _, row in df_cnpjs.iterrows()
    ]
    escolha = st.selectbox("CNPJ beneficiario", opcoes, key="sel_cnpj_api_bb")
    cnpj_sel = escolha.split(" — ")[0].strip()
    razao_sel = str(
        df_cnpjs[df_cnpjs["cnpj"] == cnpj_sel].iloc[0].get("razao_social") or ""
    )

    atuais = obter_bb_credenciais(supabase, user_id, cnpj_sel) or {}
    email_user = str(getattr(user, "email", "") or "") if user is not None else ""
    pode_dev = usuario_pode_homologar(email_user)
    ambientes = ambientes_bb_para_usuario(email_user)
    ambiente_atual = str(atuais.get("ambiente") or "producao").strip().lower()
    if ambiente_atual not in ambientes:
        ambiente_atual = ambientes[0]

    sou_dono = True
    if user is not None:
        sou_dono = str(getattr(user, "id", "")) == str(user_id)

    if atuais.get("client_id"):
        st.success(f"Este CNPJ ja tem credenciais ({atuais.get('ambiente') or '?'}).")
        if not pode_dev and str(atuais.get("ambiente") or "").lower() != "producao":
            st.error(
                "Estas credenciais nao sao de **producao**. "
                "Clientes so podem usar producao — salve de novo com o App Key de producao."
            )
    else:
        st.warning("Este CNPJ ainda nao tem credenciais da API.")

    if not pode_dev:
        st.caption("Ambiente disponivel: **producao** (homologacao so para desenvolvimento).")

    if not sou_dono:
        st.info(
            "Voce esta em base compartilhada: so o **dono** edita credenciais. "
            "As chaves ja salvas valem para envio/consulta pela API."
        )
        return

    with st.form("form_credenciais_bb_cnpj"):
        client_id = st.text_input(
            "Client ID",
            value=str(atuais.get("client_id") or ""),
            help="Portal Developers BB → aplicacao → Credenciais",
        )
        client_secret = st.text_input(
            "Client Secret",
            value="",
            type="password",
            help="Deixe em branco para manter o secret ja salvo.",
        )
        app_key = st.text_input(
            "App Key (gw-dev-app-key)",
            value=str(atuais.get("app_key") or ""),
        )
        if len(ambientes) == 1:
            ambiente = ambientes[0]
            st.text_input("Ambiente", value=ambiente, disabled=True)
        else:
            ambiente = st.selectbox(
                "Ambiente",
                ambientes,
                index=ambientes.index(ambiente_atual),
            )
        col_salvar, col_testar = st.columns(2)
        salvar = col_salvar.form_submit_button("Salvar neste CNPJ", type="primary")
        testar = col_testar.form_submit_button("Testar conexao")

    if salvar:
        try:
            salvar_bb_credenciais(
                supabase,
                user_id,
                cnpj_sel,
                client_id,
                client_secret,
                app_key,
                ambiente,
                razao_social=razao_sel,
            )
            ativar_credenciais_bb(
                {
                    "cnpj": cnpj_sel,
                    "client_id": client_id.strip(),
                    "client_secret": client_secret.strip(),
                    "app_key": app_key.strip(),
                    "ambiente": ambiente,
                    "scopes": "",
                }
            )
            invalidar_cache_workspace(user_id)
            st.success(f"Credenciais salvas para o CNPJ {cnpj_sel}.")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(traduzir_erro_db(exc))
            st.info(
                "Se a tabela nao existe, execute no SQL Editor: "
                "`supabase/migrations/008_bb_credenciais.sql` "
                "e `009_bb_credenciais_owner_write.sql`."
            )

    if testar:
        secret_teste = client_secret.strip()
        if not secret_teste and atuais.get("client_secret"):
            secret_teste = str(atuais.get("client_secret") or "")
        ativar_credenciais_bb(
            {
                "cnpj": cnpj_sel,
                "client_id": client_id.strip(),
                "client_secret": secret_teste,
                "app_key": app_key.strip(),
                "ambiente": ambiente,
                "scopes": "",
            }
        )
        ok, msg = testar_conexao_bb()
        if ok:
            st.success(msg)
        else:
            st.error(msg)

    if atuais.get("client_id"):
        if st.button("Remover credenciais deste CNPJ", key="btn_remover_bb_creds_cnpj"):
            try:
                excluir_bb_credenciais(supabase, user_id, cnpj_sel)
                sincronizar_credenciais_bb_sessao(None)
                limpar_cache_token_bb()
                invalidar_cache_workspace(user_id)
                st.success("Credenciais removidas deste CNPJ.")
                st.rerun()
            except Exception as exc:
                st.error(traduzir_erro_db(exc))

    if pode_dev:
        with st.expander("Dados de homologacao BB (referencia — so dev)"):
            st.markdown(
                f"""
- Convenio: `{HOMOLOG_CONVENIO}`
- Agencia: `{HOMOLOG_AGENCIA}` | Conta: `{HOMOLOG_CONTA}`
- Carteira: `{HOMOLOG_CARTEIRA}` / variacao `{HOMOLOG_VARIACAO}`
- Nosso numero API: `000` + convenio(7) + controle(10)
- Alteracao/baixa: so apos 30 minutos da geracao do boleto
                """
            )


def render_app(supabase: Client):
    aplicar_estilo()
    user = st.session_state.user
    user_id = render_sidebar(supabase, user)

    st.markdown('<p class="main-header">🏦 Gerador de Remessa CNAB 240</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Banco do Brasil — instruções em lote</p>', unsafe_allow_html=True)

    if str(user_id) != str(user.id):
        bases = _bases_acessiveis(supabase, user)
        rotulo = next((b["label"] for b in bases if b["id"] == str(user_id)), "base compartilhada")
        st.info(
            f"Voce esta usando a **{rotulo}**. "
            "Clientes, convenios, historico e remessas sao compartilhados. "
            "So o **dono** edita credenciais API; convidados podem usar a API."
        )

    nav = st.radio(
        "Navegacao",
        NAV_OPCOES,
        horizontal=True,
        label_visibility="collapsed",
        key="nav_principal",
    )

    erro_lista = None
    try:
        df_clientes = listar_clientes_cached(supabase, user_id)
    except Exception as exc:
        df_clientes = pd.DataFrame()
        erro_lista = traduzir_erro_db(exc)

    try:
        df_convenios = listar_convenios_cached(supabase, user_id)
    except Exception as exc:
        df_convenios = pd.DataFrame()
        erro_lista = traduzir_erro_db(exc)

    if erro_lista and nav in (NAV_GERADOR, NAV_CLIENTES, NAV_CONVENIOS):
        st.warning(f"Falha ao carregar cadastros: {erro_lista}")

    if nav == NAV_GERADOR:
        render_gerador(supabase, user_id, df_convenios, df_clientes)
    elif nav == NAV_CLIENTES:
        render_clientes(supabase, user_id)
    elif nav == NAV_CONVENIOS:
        render_convenios(supabase, user_id)
    elif nav == NAV_API_BB:
        render_api_bb(supabase, user_id, df_convenios, user=user)
    elif nav == NAV_VALORES:
        render_valores_nominais(supabase, user_id, df_convenios)
    elif nav == NAV_HISTORICO:
        render_historico(supabase, user_id)
