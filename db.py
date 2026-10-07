"""Operações de banco de dados via Supabase."""

from __future__ import annotations

import streamlit as st
import pandas as pd
from supabase import Client, create_client

from config import MENSAGENS_ERRO
from validation import limpar_nosso_numero

MENSAGEM_MIGRATION_004 = (
    "A tabela remessa_valores ainda nao existe no Supabase. "
    "Execute o arquivo supabase/migrations/004_remessa_valores.sql no SQL Editor do projeto."
)

MENSAGEM_MIGRATION_007 = (
    "O compartilhamento ainda nao esta ativo no Supabase. "
    "Execute o arquivo supabase/migrations/007_compartilhamento.sql no SQL Editor do projeto."
)

STATUS_CONVITE_PENDENTE = "pendente"
STATUS_CONVITE_ACEITO = "aceito"


def _erro_tabela_remessa_valores_ausente(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "pgrst205" in msg or (
        "remessa_valores" in msg and ("could not find" in msg or "does not exist" in msg)
    )


def _erro_tabela_ausente(exc: Exception, tabela: str) -> bool:
    msg = str(exc).lower()
    return "pgrst205" in msg or (
        tabela.lower() in msg and ("could not find" in msg or "does not exist" in msg)
    )


def tabela_compartilhamentos_disponivel(supabase: Client) -> bool:
    if "cache_tabela_compartilhamentos" in st.session_state:
        return bool(st.session_state["cache_tabela_compartilhamentos"])
    try:
        supabase.table("compartilhamentos").select("id").limit(1).execute()
        st.session_state["cache_tabela_compartilhamentos"] = True
        return True
    except Exception as exc:
        if _erro_tabela_ausente(exc, "compartilhamentos"):
            st.session_state["cache_tabela_compartilhamentos"] = False
            return False
        raise


def _normalizar_email(email: str) -> str:
    return (email or "").strip().lower()


def listar_convites_pendentes(supabase: Client, email: str) -> pd.DataFrame:
    email_norm = _normalizar_email(email)
    if not email_norm:
        return pd.DataFrame()
    try:
        resposta = (
            supabase.table("compartilhamentos")
            .select("*")
            .eq("status", STATUS_CONVITE_PENDENTE)
            .eq("convidado_email", email_norm)
            .execute()
        )
    except Exception as exc:
        if _erro_tabela_ausente(exc, "compartilhamentos"):
            return pd.DataFrame()
        raise
    return pd.DataFrame(resposta.data or [])


def listar_compartilhamentos_dono(supabase: Client, dono_id: str) -> pd.DataFrame:
    try:
        resposta = (
            supabase.table("compartilhamentos")
            .select("*")
            .eq("dono_id", dono_id)
            .order("created_at", desc=True)
            .execute()
        )
    except Exception as exc:
        if _erro_tabela_ausente(exc, "compartilhamentos"):
            return pd.DataFrame()
        raise
    return pd.DataFrame(resposta.data or [])


def listar_bases_compartilhadas(supabase: Client, convidado_id: str) -> pd.DataFrame:
    try:
        resposta = (
            supabase.table("compartilhamentos")
            .select("*")
            .eq("convidado_id", convidado_id)
            .eq("status", STATUS_CONVITE_ACEITO)
            .execute()
        )
    except Exception as exc:
        if _erro_tabela_ausente(exc, "compartilhamentos"):
            return pd.DataFrame()
        raise
    return pd.DataFrame(resposta.data or [])


def convidar_para_base(
    supabase: Client,
    dono_id: str,
    dono_email: str,
    convidado_email: str,
) -> None:
    email_norm = _normalizar_email(convidado_email)
    dono_email_norm = _normalizar_email(dono_email)
    if not email_norm or "@" not in email_norm:
        raise ValueError("Informe um e-mail valido para compartilhar.")
    if email_norm == dono_email_norm:
        raise ValueError("Voce nao pode compartilhar a base consigo mesmo.")

    existentes = listar_compartilhamentos_dono(supabase, dono_id)
    if not existentes.empty and "convidado_email" in existentes.columns:
        ja = existentes["convidado_email"].astype(str).str.strip().str.lower() == email_norm
        if ja.any():
            raise ValueError("Este e-mail ja foi convidado para a sua base.")

    supabase.table("compartilhamentos").insert(
        {
            "dono_id": dono_id,
            "dono_email": dono_email_norm,
            "convidado_email": email_norm,
            "status": STATUS_CONVITE_PENDENTE,
        }
    ).execute()


def aceitar_convite(supabase: Client, convite_id: str, convidado_id: str) -> None:
    supabase.table("compartilhamentos").update(
        {
            "status": STATUS_CONVITE_ACEITO,
            "convidado_id": convidado_id,
        }
    ).eq("id", convite_id).execute()


def remover_compartilhamento(supabase: Client, convite_id: str) -> None:
    supabase.table("compartilhamentos").delete().eq("id", convite_id).execute()


def normalizar_cnpj_credencial(cnpj: str) -> str:
    """CNPJ só com dígitos (ou alfanumérico de homologação, maiúsculo sem máscara)."""
    texto = str(cnpj or "").strip().upper()
    if not texto or texto.lower() == "nan":
        return ""
    # Homologação alfanumérica (ex.: MHWXJ9YFDPJ217)
    alfanum = "".join(c for c in texto if c.isalnum())
    so_digitos = "".join(c for c in texto if c.isdigit())
    if so_digitos and len(so_digitos) >= 11 and len(so_digitos) == len(alfanum):
        return so_digitos
    return alfanum


def obter_bb_credenciais(supabase: Client, user_id: str, cnpj: str) -> dict | None:
    """Credenciais da API BB do CNPJ (compartilhadas por todos os convênios desse CNPJ)."""
    cnpj_norm = normalizar_cnpj_credencial(cnpj)
    if not cnpj_norm:
        return None
    try:
        resposta = (
            supabase.table("bb_credenciais")
            .select("cnpj, razao_social, client_id, client_secret, app_key, ambiente, updated_at")
            .eq("user_id", user_id)
            .eq("cnpj", cnpj_norm)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        if _erro_tabela_ausente(exc, "bb_credenciais"):
            return None
        raise
    if not resposta.data:
        return None
    row = resposta.data[0]
    return {
        "cnpj": str(row.get("cnpj") or cnpj_norm),
        "razao_social": str(row.get("razao_social") or "").strip(),
        "client_id": str(row.get("client_id") or "").strip(),
        "client_secret": str(row.get("client_secret") or "").strip(),
        "app_key": str(row.get("app_key") or "").strip(),
        "ambiente": str(row.get("ambiente") or "homologacao").strip().lower(),
        "scopes": "",
        "updated_at": row.get("updated_at"),
    }


def listar_bb_credenciais(supabase: Client, user_id: str) -> pd.DataFrame:
    try:
        resposta = (
            supabase.table("bb_credenciais")
            .select("cnpj, razao_social, ambiente, updated_at, client_id, app_key")
            .eq("user_id", user_id)
            .order("cnpj")
            .execute()
        )
    except Exception as exc:
        if _erro_tabela_ausente(exc, "bb_credenciais"):
            return pd.DataFrame()
        raise
    return pd.DataFrame(resposta.data or [])


def salvar_bb_credenciais(
    supabase: Client,
    user_id: str,
    cnpj: str,
    client_id: str,
    client_secret: str,
    app_key: str,
    ambiente: str,
    razao_social: str = "",
) -> None:
    from datetime import datetime, timezone

    cnpj_norm = normalizar_cnpj_credencial(cnpj)
    ambiente = (ambiente or "homologacao").strip().lower()
    if not cnpj_norm:
        raise ValueError("Informe o CNPJ do beneficiario.")
    if ambiente not in ("sandbox", "homologacao", "producao"):
        raise ValueError("Ambiente invalido. Use sandbox, homologacao ou producao.")
    if not client_id.strip() or not app_key.strip():
        raise ValueError("Preencha Client ID e App Key.")
    secret = client_secret.strip()
    if not secret:
        existentes = obter_bb_credenciais(supabase, user_id, cnpj_norm)
        if existentes and existentes.get("client_secret"):
            secret = existentes["client_secret"]
        else:
            raise ValueError(
                "Informe o Client Secret "
                "(ou deixe em branco apenas para manter o ja salvo)."
            )
    payload = {
        "user_id": user_id,
        "cnpj": cnpj_norm,
        "razao_social": (razao_social or "").strip() or None,
        "client_id": client_id.strip(),
        "client_secret": secret,
        "app_key": app_key.strip(),
        "ambiente": ambiente,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    supabase.table("bb_credenciais").upsert(payload, on_conflict="user_id,cnpj").execute()


def excluir_bb_credenciais(supabase: Client, user_id: str, cnpj: str) -> None:
    cnpj_norm = normalizar_cnpj_credencial(cnpj)
    if not cnpj_norm:
        raise ValueError("CNPJ invalido.")
    supabase.table("bb_credenciais").delete().eq("user_id", user_id).eq(
        "cnpj", cnpj_norm
    ).execute()


def tabela_remessa_valores_disponivel(supabase: Client) -> bool:
    if "cache_tabela_remessa_valores" in st.session_state:
        return bool(st.session_state["cache_tabela_remessa_valores"])
    try:
        supabase.table("remessa_valores").select("id").limit(1).execute()
        st.session_state["cache_tabela_remessa_valores"] = True
        return True
    except Exception as exc:
        if _erro_tabela_remessa_valores_ausente(exc):
            st.session_state["cache_tabela_remessa_valores"] = False
            return False
        raise


def secrets_configurados() -> bool:
    url = str(st.secrets.get("SUPABASE_URL", "")).strip()
    key = str(st.secrets.get("SUPABASE_KEY", "")).strip()
    if not url or not key:
        return False
    placeholders = ("SEU_PROJETO", "sua-chave", "eyJhbGciOi...")
    return not any(p in url or p in key for p in placeholders)


def init_connection() -> Client:
    """Uma conexão por sessão Streamlit (evita compartilhar auth entre usuários)."""
    if "supabase" not in st.session_state:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        st.session_state.supabase = create_client(url, key)

    if st.session_state.get("access_token") and st.session_state.get("refresh_token"):
        try:
            st.session_state.supabase.auth.set_session(
                st.session_state.access_token,
                st.session_state.refresh_token,
            )
        except Exception:
            pass

    return st.session_state.supabase


def traduzir_erro_db(exc: Exception) -> str:
    msg = str(exc).lower()
    if "invalid api key" in msg or "apikeyinvalid" in msg:
        return "Chave do Supabase inválida. Use a chave 'anon public' do painel do projeto."
    if "invalid login credentials" in msg or "invalid_credentials" in msg:
        return MENSAGENS_ERRO["invalid_credentials"]
    if "email not confirmed" in msg:
        return MENSAGENS_ERRO["email_not_confirmed"]
    if "already registered" in msg or "user already" in msg:
        return MENSAGENS_ERRO["user_already_registered"]
    if "password" in msg and "6" in msg:
        return MENSAGENS_ERRO["weak_password"]
    if "row-level security" in msg or "permission denied" in msg or "42501" in msg:
        return MENSAGENS_ERRO["rls"]
    if "network" in msg or "connection" in msg or "timeout" in msg:
        return MENSAGENS_ERRO["network"]
    return f"{MENSAGENS_ERRO['default']} Detalhe: {exc}"


def listar_clientes(supabase: Client, user_id: str) -> pd.DataFrame:
    resposta = supabase.table("clientes").select("*").eq("user_id", user_id).execute()
    return pd.DataFrame(resposta.data or [])


def criar_cliente(supabase: Client, user_id: str, dados: dict) -> None:
    supabase.table("clientes").insert({**dados, "user_id": user_id}).execute()


def criar_clientes_lote(supabase: Client, user_id: str, registros: list[dict]) -> int:
    if not registros:
        return 0
    payload = [{**dados, "user_id": user_id} for dados in registros]
    supabase.table("clientes").insert(payload).execute()
    return len(payload)


def atualizar_cliente(supabase: Client, cliente_id: str, dados: dict) -> None:
    supabase.table("clientes").update(dados).eq("id", cliente_id).execute()


def excluir_clientes(supabase: Client, ids: list[str]) -> None:
    ids_limpos = [str(i) for i in ids if i]
    if not ids_limpos:
        return
    supabase.table("clientes").delete().in_("id", ids_limpos).execute()


def listar_convenios(supabase: Client, user_id: str) -> pd.DataFrame:
    resposta = supabase.table("convenios").select("*").eq("user_id", user_id).execute()
    return pd.DataFrame(resposta.data or [])


def criar_convenio(supabase: Client, user_id: str, dados: dict) -> None:
    supabase.table("convenios").insert({**dados, "user_id": user_id}).execute()


def atualizar_convenio(supabase: Client, convenio_id: str, dados: dict) -> None:
    supabase.table("convenios").update(dados).eq("id", convenio_id).execute()


def excluir_convenio(supabase: Client, convenio_id: str) -> None:
    supabase.table("convenios").delete().eq("id", convenio_id).execute()


def contar_remessas(supabase: Client, user_id: str) -> int:
    resposta = (
        supabase.table("remessas")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .execute()
    )
    return resposta.count or 0


def contar_remessas_convenio(supabase: Client, user_id: str, convenio_id: str) -> int:
    """NSA sequencial por convênio (exigência do Banco do Brasil)."""
    convenio_id = str(convenio_id).strip()
    if not convenio_id:
        return contar_remessas(supabase, user_id)

    resposta = (
        supabase.table("remessas")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .eq("convenio_id", convenio_id)
        .execute()
    )
    return resposta.count or 0


def _erro_coluna_status_ausente(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "status" in msg and ("column" in msg or "could not find" in msg or "pgrst204" in msg)


def _erro_coluna_ausente(exc: Exception, coluna: str) -> bool:
    msg = str(exc).lower()
    return coluna.lower() in msg and (
        "column" in msg or "could not find" in msg or "pgrst204" in msg
    )


def atualizar_status_remessa(
    supabase: Client,
    user_id: str,
    remessa_id: str,
    status: str,
) -> None:
    supabase.table("remessas").update({"status": status}).eq("id", remessa_id).eq(
        "user_id", user_id
    ).execute()


def salvar_remessa(supabase: Client, user_id: str, dados: dict) -> str | None:
    resposta = supabase.table("remessas").insert({**dados, "user_id": user_id}).execute()
    if resposta.data:
        return str(resposta.data[0]["id"])
    return None


def salvar_remessa_resiliente(supabase: Client, user_id: str, dados: dict) -> str | None:
    """Salva a remessa; se uma coluna opcional ainda não existe no BD, remove e tenta de novo."""
    dados = dict(dados)
    colunas_opcionais = ["arquivo_b64", "status"]
    for _ in range(len(colunas_opcionais) + 1):
        try:
            return salvar_remessa(supabase, user_id, dados)
        except Exception as exc:
            removeu = False
            for col in colunas_opcionais:
                if col in dados and _erro_coluna_ausente(exc, col):
                    dados.pop(col, None)
                    removeu = True
            if not removeu:
                raise
    return None


COLUNAS_REMESSA_LISTA = (
    "id,user_id,convenio_id,nome_arquivo,total_lotes,total_boletos,"
    "instrucoes,preview_linhas,status,created_at"
)


def listar_remessas(supabase: Client, user_id: str) -> pd.DataFrame:
    """Lista remessas sem arquivo_b64 (payload leve)."""
    try:
        resposta = (
            supabase.table("remessas")
            .select(COLUNAS_REMESSA_LISTA)
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
    except Exception as exc:
        if _erro_coluna_ausente(exc, "status"):
            resposta = (
                supabase.table("remessas")
                .select(
                    "id,user_id,convenio_id,nome_arquivo,total_lotes,"
                    "total_boletos,instrucoes,preview_linhas,created_at"
                )
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .execute()
            )
        else:
            raise
    return pd.DataFrame(resposta.data or [])


def obter_arquivo_remessa(
    supabase: Client, user_id: str, remessa_id: str
) -> str | None:
    """Busca arquivo_b64 sob demanda para download."""
    try:
        resposta = (
            supabase.table("remessas")
            .select("arquivo_b64")
            .eq("user_id", user_id)
            .eq("id", remessa_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        if _erro_coluna_ausente(exc, "arquivo_b64"):
            return None
        raise
    if not resposta.data:
        return None
    valor = resposta.data[0].get("arquivo_b64")
    return str(valor) if valor else None


def buscar_valores_titulos(
    supabase: Client,
    user_id: str,
    convenio_id: str,
    nosso_numeros: list[str],
) -> dict[str, float]:
    """Retorna mapa nosso_numero → valor_nominal registrado (instrução 47)."""
    if not convenio_id or not nosso_numeros:
        return {}

    convenio_id = str(convenio_id).strip()
    unicos = list(dict.fromkeys(n for n in nosso_numeros if n))
    if not unicos:
        return {}

    from cnab import chaves_nosso_numero

    consulta_numeros: list[str] = []
    for nn in unicos:
        consulta_numeros.extend(chaves_nosso_numero(nn))
    consulta_numeros = list(dict.fromkeys(consulta_numeros))

    resposta = (
        supabase.table("titulos_valores")
        .select("nosso_numero, valor_nominal")
        .eq("user_id", user_id)
        .eq("convenio_id", convenio_id)
        .in_("nosso_numero", consulta_numeros)
        .execute()
    )

    valores: dict[str, float] = {}
    for row in resposta.data or []:
        nn = limpar_nosso_numero(row.get("nosso_numero", ""))
        if not nn:
            continue
        try:
            valor = round(float(row["valor_nominal"]), 2)
        except (TypeError, ValueError, KeyError):
            continue
        for chave in chaves_nosso_numero(nn):
            valores[chave] = valor
    return valores


def upsert_titulos_valores(
    supabase: Client,
    user_id: str,
    convenio_id: str,
    registros: list[dict],
) -> int:
    """Grava ou atualiza valor nominal após remessa com instrução 47."""
    if not convenio_id or not registros:
        return 0

    convenio_id = str(convenio_id).strip()
    payload = []
    for reg in registros:
        nn = limpar_nosso_numero(reg.get("nosso_numero", ""))
        valor = reg.get("valor_nominal")
        if not nn or valor is None:
            continue
        try:
            valor_float = round(float(valor), 2)
        except (TypeError, ValueError):
            continue
        payload.append(
            {
                "user_id": user_id,
                "convenio_id": convenio_id,
                "nosso_numero": nn,
                "seu_numero": reg.get("seu_numero") or None,
                "valor_nominal": valor_float,
            }
        )

    if not payload:
        return 0

    supabase.table("titulos_valores").upsert(
        payload,
        on_conflict="user_id,convenio_id,nosso_numero",
    ).execute()
    return len(payload)


def listar_titulos_valores(
    supabase: Client,
    user_id: str,
    convenio_id: str,
) -> pd.DataFrame:
    convenio_id = str(convenio_id).strip()
    if not convenio_id:
        return pd.DataFrame()

    try:
        resposta = (
            supabase.table("titulos_valores")
            .select("*")
            .eq("user_id", user_id)
            .eq("convenio_id", convenio_id)
            .order("updated_at", desc=True)
            .execute()
        )
    except Exception as exc:
        msg = str(exc).lower()
        if "titulos_valores" in msg and ("could not find" in msg or "pgrst205" in msg):
            return pd.DataFrame()
        raise

    return pd.DataFrame(resposta.data or [])


def atualizar_valor_nominal_titulo(
    supabase: Client,
    user_id: str,
    titulo_id: str,
    valor_nominal: float,
) -> None:
    supabase.table("titulos_valores").update(
        {"valor_nominal": round(float(valor_nominal), 2)}
    ).eq("id", titulo_id).eq("user_id", user_id).execute()


def excluir_titulo_valor(supabase: Client, user_id: str, titulo_id: str) -> None:
    supabase.table("titulos_valores").delete().eq("id", titulo_id).eq(
        "user_id", user_id
    ).execute()


def _nosso_numeros_coincidem(nn_a: str, nn_b: str) -> bool:
    from cnab import chaves_nosso_numero

    chaves_a = set(chaves_nosso_numero(nn_a))
    chaves_b = set(chaves_nosso_numero(nn_b))
    return bool(chaves_a & chaves_b)


def _filtrar_linhas_por_nosso_numeros(
    linhas: list[dict],
    nosso_numeros: list[str],
) -> list[dict]:
    filtradas: list[dict] = []
    for row in linhas:
        nn = limpar_nosso_numero(row.get("nosso_numero", ""))
        if not nn:
            continue
        if any(_nosso_numeros_coincidem(nn, planilha_nn) for planilha_nn in nosso_numeros):
            filtradas.append(row)
    return filtradas


def _valores_de_linhas(
    linhas: list[dict],
    nosso_numeros: list[str] | None = None,
) -> dict[str, float]:
    from cnab import chaves_nosso_numero

    if nosso_numeros:
        linhas = _filtrar_linhas_por_nosso_numeros(linhas, nosso_numeros)

    valores: dict[str, float] = {}
    for row in linhas:
        nn = limpar_nosso_numero(row.get("nosso_numero", ""))
        if not nn:
            continue
        try:
            valor = round(float(row["valor_nominal"]), 2)
        except (TypeError, ValueError, KeyError):
            continue
        for chave in chaves_nosso_numero(nn):
            valores[chave] = valor
    return valores


def listar_remessas_por_convenio(
    supabase: Client,
    user_id: str,
    convenio_id: str,
) -> pd.DataFrame:
    convenio_id = str(convenio_id).strip()
    if not convenio_id:
        return pd.DataFrame()

    resposta = (
        supabase.table("remessas")
        .select("id, nome_arquivo, created_at, total_boletos, instrucoes")
        .eq("user_id", user_id)
        .eq("convenio_id", convenio_id)
        .order("created_at", desc=True)
        .execute()
    )
    return pd.DataFrame(resposta.data or [])


def listar_remessas_com_valores(
    supabase: Client,
    user_id: str,
    convenio_id: str,
) -> pd.DataFrame:
    convenio_id = str(convenio_id).strip()
    if not convenio_id:
        return pd.DataFrame()

    try:
        resposta = (
            supabase.table("remessa_valores")
            .select("remessa_id")
            .eq("user_id", user_id)
            .eq("convenio_id", convenio_id)
            .execute()
        )
    except Exception as exc:
        if _erro_tabela_remessa_valores_ausente(exc):
            return pd.DataFrame()
        raise

    ids = list({str(row["remessa_id"]) for row in (resposta.data or []) if row.get("remessa_id")})
    if not ids:
        return pd.DataFrame()

    df = listar_remessas_por_convenio(supabase, user_id, convenio_id)
    if df.empty or "id" not in df.columns:
        return pd.DataFrame()
    return df[df["id"].astype(str).isin(ids)].reset_index(drop=True)


def obter_ultima_remessa_com_valores(
    supabase: Client,
    user_id: str,
    convenio_id: str,
) -> str | None:
    df = listar_remessas_com_valores(supabase, user_id, convenio_id)
    if df.empty:
        return None
    return str(df.iloc[0]["id"])


def buscar_valores_remessa(
    supabase: Client,
    user_id: str,
    remessa_id: str,
    nosso_numeros: list[str],
) -> dict[str, float]:
    remessa_id = str(remessa_id).strip()
    if not remessa_id or not nosso_numeros:
        return {}

    try:
        resposta = (
            supabase.table("remessa_valores")
            .select("nosso_numero, valor_nominal")
            .eq("user_id", user_id)
            .eq("remessa_id", remessa_id)
            .execute()
        )
    except Exception as exc:
        if _erro_tabela_remessa_valores_ausente(exc):
            return {}
        raise

    return _valores_de_linhas(resposta.data or [], nosso_numeros)


def buscar_valores_ultima_remessa(
    supabase: Client,
    user_id: str,
    convenio_id: str,
    nosso_numeros: list[str],
) -> tuple[dict[str, float], str | None]:
    remessa_id = obter_ultima_remessa_com_valores(supabase, user_id, convenio_id)
    if not remessa_id:
        return {}, None
    valores = buscar_valores_remessa(supabase, user_id, remessa_id, nosso_numeros)
    return valores, remessa_id


def salvar_snapshot_valores_remessa(
    supabase: Client,
    user_id: str,
    convenio_id: str,
    remessa_id: str,
    registros: list[dict],
) -> int:
    remessa_id = str(remessa_id).strip()
    convenio_id = str(convenio_id).strip()
    if not remessa_id or not convenio_id or not registros:
        return 0

    payload = []
    for reg in registros:
        nn = limpar_nosso_numero(reg.get("nosso_numero", ""))
        valor = reg.get("valor_nominal")
        if not nn or valor is None:
            continue
        try:
            valor_float = round(float(valor), 2)
        except (TypeError, ValueError):
            continue
        payload.append(
            {
                "remessa_id": remessa_id,
                "user_id": user_id,
                "convenio_id": convenio_id,
                "nosso_numero": nn,
                "seu_numero": reg.get("seu_numero") or None,
                "valor_nominal": valor_float,
                "cod_instrucao": reg.get("cod_instrucao"),
            }
        )

    if not payload:
        return 0

    try:
        supabase.table("remessa_valores").upsert(
            payload,
            on_conflict="remessa_id,nosso_numero",
        ).execute()
    except Exception as exc:
        if _erro_tabela_remessa_valores_ausente(exc):
            return 0
        raise
    return len(payload)


def obter_valores_referencia(
    supabase: Client,
    user_id: str,
    convenio_id: str,
    nosso_numeros: list[str],
    modo: str,
    remessa_id: str | None = None,
) -> tuple[dict[str, float], str]:
    from config import REF_VALORES_ATUAL, REF_VALORES_ESCOLHER, REF_VALORES_ULTIMA

    convenio_id = str(convenio_id).strip()

    if modo == REF_VALORES_ULTIMA:
        valores, ultima_id = buscar_valores_ultima_remessa(
            supabase, user_id, convenio_id, nosso_numeros
        )
        if not ultima_id:
            return {}, "nenhuma remessa anterior com valores salvos"
        df = listar_remessas_por_convenio(supabase, user_id, convenio_id)
        if not df.empty:
            reg = df[df["id"].astype(str) == ultima_id]
            if not reg.empty:
                nome = reg.iloc[0].get("nome_arquivo", "")
                return valores, f"ultima remessa: {nome}"
        return valores, "ultima remessa do convenio"

    if modo == REF_VALORES_ESCOLHER and remessa_id:
        valores = buscar_valores_remessa(supabase, user_id, remessa_id, nosso_numeros)
        df = listar_remessas_por_convenio(supabase, user_id, convenio_id)
        if not df.empty:
            reg = df[df["id"].astype(str) == str(remessa_id)]
            if not reg.empty:
                nome = reg.iloc[0].get("nome_arquivo", "")
                return valores, f"remessa selecionada: {nome}"
        return valores, "remessa selecionada"

    valores = buscar_valores_titulos(supabase, user_id, convenio_id, nosso_numeros)
    return valores, "valores atuais registrados"



def _cache_key(prefix: str, user_id: str) -> str:
    return f"{prefix}_{user_id}"


def invalidar_cache_workspace(user_id: str | None = None) -> None:
    """Limpa caches de listagens apos CRUD."""
    prefixos = (
        "cache_clientes",
        "cache_convenios",
        "cache_bb_creds_count",
    )
    if user_id:
        for p in prefixos:
            st.session_state.pop(_cache_key(p, str(user_id)), None)
    else:
        for k in list(st.session_state.keys()):
            if any(str(k).startswith(p + "_") for p in prefixos):
                st.session_state.pop(k, None)


def listar_clientes_cached(
    supabase: Client, user_id: str, *, force: bool = False
) -> pd.DataFrame:
    key = _cache_key("cache_clientes", str(user_id))
    if not force and key in st.session_state:
        return st.session_state[key]
    df = listar_clientes(supabase, user_id)
    st.session_state[key] = df
    return df


def listar_convenios_cached(
    supabase: Client, user_id: str, *, force: bool = False
) -> pd.DataFrame:
    key = _cache_key("cache_convenios", str(user_id))
    if not force and key in st.session_state:
        return st.session_state[key]
    df = listar_convenios(supabase, user_id)
    st.session_state[key] = df
    return df


def contar_bb_credenciais_cached(supabase: Client, user_id: str) -> int:
    key = _cache_key("cache_bb_creds_count", str(user_id))
    if key in st.session_state:
        return int(st.session_state[key])
    try:
        df = listar_bb_credenciais(supabase, user_id)
        qtd = 0 if df.empty else len(df)
    except Exception:
        qtd = 0
    st.session_state[key] = qtd
    return qtd
