"""Cliente da API Cobranças v2 do Banco do Brasil (sem gerar CNAB)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import httpx
import pandas as pd
import streamlit as st

from cnab import (
    buscar_valor_registrado,
    normalizar_valor_monetario,
    valores_monetarios_diferem,
)
from validation import limpar_nosso_numero, mapear_colunas_planilha

AMBIENTES = {
    "sandbox": {
        "token_url": "https://oauth.sandbox.bb.com.br/oauth/token",
        "api_url": "https://api.sandbox.bb.com.br/cobrancas/v2",
    },
    "homologacao": {
        "token_url": "https://oauth.hm.bb.com.br/oauth/token",
        "api_url": "https://api.hm.bb.com.br/cobrancas/v2",
    },
    "producao": {
        "token_url": "https://oauth.bb.com.br/oauth/token",
        "api_url": "https://api.bb.com.br/cobrancas/v2",
    },
}

# Escopos preferidos. Sem convenio-requisicao (app atual nao tem esse escopo).
SCOPES_PREFERIDOS = [
    "cobrancas.boletos-info cobrancas.boletos-requisicao",
    "cobrancas.boletos-requisicao",
    "cobrancas.boletos-info",
]

INDICADORES_ALTERACAO = [
    "indicadorAlterarAbatimento",
    "indicadorAlterarDataDesconto",
    "indicadorAlterarDesconto",
    "indicadorAlterarEnderecoPagador",
    "indicadorAlterarPrazoBoletoVencido",
    "indicadorAlterarSeuNumero",
    "indicadorAtribuirDesconto",
    "indicadorCancelarProtesto",
    "indicadorCobrarJuros",
    "indicadorCobrarMulta",
    "indicadorDispensarJuros",
    "indicadorDispensarMulta",
    "indicadorIncluirAbatimento",
    "indicadorNegativar",
    "indicadorNovaDataVencimento",
    "indicadorProtestar",
    "indicadorSustacaoProtesto",
    "indicadorNovoValorNominal",
]

# Instruções suportadas via API: apenas alterar (PATCH) e baixa — sem POST /boletos
INSTRUCOES_API_SUPORTADAS = {
    "02",  # baixa
    "06",  # alteração de vencimento
    "09",  # protestar (PATCH)
    "10",  # cancela protesto (PATCH)
    "47",  # alteração valor nominal
}

INSTRUCOES_API_LABEL = "baixa (02) e alteracoes via PATCH (06, 09, 10, 47) — sem registro de boleto"

# ---------------------------------------------------------------------------
# Dados fictícios oficiais do BB para homologação (Portal Developers)
# ---------------------------------------------------------------------------
HOMOLOG_CONVENIO = "3128557"
HOMOLOG_CARTEIRA = "17"
HOMOLOG_VARIACAO = "35"
HOMOLOG_AGENCIA = "452"
HOMOLOG_CONTA = "123873"

# CNPJs/CPFs liberados pelo BB para POST /boletos em homologação
HOMOLOG_PAGADORES_PJ = [
    {"nome": "TECIDOS FARIA DUARTE", "cnpj": "74910037000193"},
    {"nome": "LIVRARIA CUNHA DA CUNHA", "cnpj": "98959112000179"},
    {"nome": "DOCERIA BARBOSA DE ALMEIDA", "cnpj": "92862701000158"},
    {"nome": "DEPOSITO ALVES BRAGA", "cnpj": "94491202000127"},
    {"nome": "PAPELARIA FILARDES GARRIDO", "cnpj": "97257206000133"},
]
HOMOLOG_PAGADORES_PF = [
    {"nome": "VALERIO DE AGUIAR ZORZATO", "cpf": "96050176876"},
    {"nome": "JOAO DA COSTA ANTUNES", "cpf": "88398158808"},
    {"nome": "VALERIO ALVES BARROS", "cpf": "71943984190"},
    {"nome": "JOÃO DA COSTA ANTUNES", "cpf": "97965940132"},
    {"nome": "JOÃO DA COSTA ANTUNES", "cpf": "75069056123"},
]
HOMOLOG_PAGADORES_PJ_ALFA = [
    {"nome": "LIVRARIA CUNHA FERNANDES", "cnpj": "CNPJJOAO180280"},
    {"nome": "CINE PESSOA AMORIM", "cnpj": "MHWXJ9YFDPJ217"},
    {"nome": "ACOUGUE LEITE MANASSES", "cnpj": "X6JSIZ13MI0V80"},
]

AVISO_PRAZO_30_MIN = (
    "Na homologacao do BB, alteracao e baixa so sao aceitas "
    "a partir de 30 minutos apos a geracao do boleto."
)


@dataclass
class ResultadoLinhaApi:
    nosso_numero: str
    sucesso: bool
    mensagem: str
    status_http: int | None = None


@dataclass
class ResultadoEnvioApi:
    total: int = 0
    sucessos: int = 0
    falhas: int = 0
    linhas: list[ResultadoLinhaApi] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    titulos_atualizar: list[dict] = field(default_factory=list)
    valores_enviados: list[dict] = field(default_factory=list)


class BbApiError(Exception):
    """Erro de configuração ou autenticação com a API do BB."""


def _cfg_vazia() -> dict:
    return {
        "client_id": "",
        "client_secret": "",
        "app_key": "",
        "ambiente": "homologacao",
        "scopes": "",
    }


def _secrets_bb() -> dict:
    """Credenciais por base/cliente (aba API BB no Supabase). Sem chave global compartilhada."""
    salvas = st.session_state.get("bb_credenciais_workspace") or {}
    return {
        "client_id": str(salvas.get("client_id") or "").strip(),
        "client_secret": str(salvas.get("client_secret") or "").strip(),
        "app_key": str(salvas.get("app_key") or "").strip(),
        "ambiente": str(salvas.get("ambiente") or "homologacao").strip().lower(),
        "scopes": str(salvas.get("scopes") or "").strip(),
    }


def sincronizar_credenciais_bb_sessao(cfg: dict | None) -> None:
    """Atualiza o cache da sessao com as credenciais da base atual."""
    st.session_state.bb_credenciais_workspace = dict(cfg or _cfg_vazia())


def limpar_cache_token_bb() -> None:
    st.session_state.pop("bb_access_token", None)
    st.session_state.pop("bb_token_expira_em", None)
    st.session_state.pop("bb_scopes_ativos", None)


def bb_credenciais_configuradas() -> bool:
    cfg = _secrets_bb()
    return bool(cfg["client_id"] and cfg["client_secret"] and cfg["app_key"])


def mensagem_credenciais_bb(cnpj: str = "") -> str:
    trecho = f" do CNPJ `{cnpj}`" if cnpj else " deste CNPJ"
    return (
        f"Credenciais da API do BB{trecho} nao configuradas. "
        "Abra a aba **API BB**, selecione o CNPJ e cole Client ID, Client Secret, App Key e ambiente."
    )


def ativar_credenciais_bb(cfg: dict | None) -> None:
    """Define na sessao as credenciais do CNPJ que sera usado na chamada API."""
    sincronizar_credenciais_bb_sessao(cfg)
    limpar_cache_token_bb()


def testar_conexao_bb() -> tuple[bool, str]:
    """Tenta obter token OAuth. Retorna (ok, mensagem)."""
    try:
        limpar_cache_token_bb()
        obter_token(force=True)
        cfg = _secrets_bb()
        escopo = st.session_state.get("bb_scopes_ativos") or "(padrao)"
        return (
            True,
            f"Conexao OK no ambiente **{cfg['ambiente']}** (escopo: `{escopo}`).",
        )
    except BbApiError as exc:
        return False, str(exc)
    except Exception as exc:
        return False, f"Falha na conexao: {exc}"


def _ambiente_urls(ambiente: str) -> dict[str, str]:
    if ambiente not in AMBIENTES:
        raise BbApiError(
            f"Ambiente BB invalido: {ambiente}. Use sandbox, homologacao ou producao."
        )
    return AMBIENTES[ambiente]


def obter_token(force: bool = False) -> str:
    """OAuth2 client_credentials. Cacheia o token na sessão Streamlit."""
    if not force and st.session_state.get("bb_access_token") and st.session_state.get(
        "bb_token_expira_em", 0
    ) > datetime.now().timestamp() + 30:
        return st.session_state.bb_access_token

    cfg = _secrets_bb()
    if not (cfg["client_id"] and cfg["client_secret"] and cfg["app_key"]):
        raise BbApiError(mensagem_credenciais_bb())

    urls = _ambiente_urls(cfg["ambiente"])
    scopes_lista = [cfg["scopes"]] if cfg["scopes"] else list(SCOPES_PREFERIDOS)
    ultimo_erro = ""
    data = None
    with httpx.Client(timeout=30.0) as client:
        for scope in scopes_lista:
            resp = client.post(
                urls["token_url"],
                data={"grant_type": "client_credentials", "scope": scope},
                auth=(cfg["client_id"], cfg["client_secret"]),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if resp.status_code < 400:
                data = resp.json()
                st.session_state.bb_scopes_ativos = scope
                break
            ultimo_erro = f"{resp.status_code}: {resp.text[:300]}"
            # Sem autorizacao para algum escopo — tenta o proximo mais restrito
            if "invalid_scope" not in resp.text.lower():
                raise BbApiError(f"Falha ao obter token OAuth do BB ({ultimo_erro})")

    if not data:
        raise BbApiError(
            f"Falha ao obter token OAuth do BB. Ultimo erro: {ultimo_erro}. "
            "No Portal Developers BB, habilite os escopos "
            "cobrancas.boletos-info e cobrancas.boletos-requisicao."
        )
    token = data.get("access_token")
    if not token:
        raise BbApiError("Resposta OAuth do BB sem access_token.")
    expires_in = int(data.get("expires_in") or 600)
    st.session_state.bb_access_token = token
    st.session_state.bb_token_expira_em = datetime.now().timestamp() + expires_in
    return token


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def montar_numero_titulo_cliente(numero_convenio: str, nosso_numero: str) -> str:
    """
    numeroTituloCliente / path :id do BB — 20 digitos:
    \"000\" + convenio (7) + numero de controle (10).
    Ex. homologacao: 00031285570000030000
    """
    conv = "".join(filter(str.isdigit, str(numero_convenio)))[-7:].zfill(7)
    nn = limpar_nosso_numero(nosso_numero)
    if not nn:
        raise BbApiError("Nosso Numero vazio.")

    # Ja no formato completo de 20 digitos
    if len(nn) >= 20:
        return nn[-20:].zfill(20)
    # Formato antigo 17 digitos (convenio+controle) — prefixa 000
    if len(nn) == 17:
        return ("000" + nn)[-20:]
    # So o controle (ate 10 digitos)
    controle = nn[-10:].zfill(10)
    return f"000{conv}{controle}"


def _montar_id_boleto(numero_convenio: str, nosso_numero: str) -> str:
    return montar_numero_titulo_cliente(numero_convenio, nosso_numero)


def _data_api(data_str: str) -> str:
    """Converte DD/MM/AAAA ou DDMMYYYY para dd.mm.aaaa."""
    texto = (data_str or "").strip().replace("-", "/").replace(".", "/")
    if "/" in texto:
        partes = texto.split("/")
        if len(partes) == 3:
            d, m, a = partes
            return f"{int(d):02d}.{int(m):02d}.{int(a):04d}"
    digitos = "".join(filter(str.isdigit, texto))
    if len(digitos) == 8:
        return f"{digitos[0:2]}.{digitos[2:4]}.{digitos[4:8]}"
    raise BbApiError(f"Data invalida para a API do BB: {data_str}")


def _corpo_alteracao_base(numero_convenio: int) -> dict:
    corpo = {"numeroConvenio": numero_convenio}
    for ind in INDICADORES_ALTERACAO:
        corpo[ind] = "N"
    return corpo


def _codigo_instrucao(lote: dict) -> str:
    return str(lote.get("instrucao", "")).split(" - ")[0].strip()


def _extrair_erro_bb(resp: httpx.Response) -> str:
    try:
        data = resp.json()
    except Exception:
        return resp.text[:400]
    if isinstance(data, dict):
        erros = data.get("erros") or data.get("errors") or data.get("error")
        if isinstance(erros, list) and erros:
            partes = []
            for e in erros:
                if isinstance(e, dict):
                    partes.append(
                        str(e.get("mensagem") or e.get("message") or e.get("codigo") or e)
                    )
                else:
                    partes.append(str(e))
            return " | ".join(partes)[:400]
        if isinstance(erros, str):
            return erros[:400]
        msg = data.get("message") or data.get("mensagem") or data.get("error_description")
        if msg:
            return str(msg)[:400]
    return str(data)[:400]


def _request_bb(
    method: str,
    path: str,
    *,
    json_body: dict | None = None,
) -> httpx.Response:
    cfg = _secrets_bb()
    urls = _ambiente_urls(cfg["ambiente"])
    token = obter_token()
    url = f"{urls['api_url']}{path}"
    params = {"gw-dev-app-key": cfg["app_key"]}

    with httpx.Client(timeout=45.0) as client:
        resp = client.request(
            method,
            url,
            params=params,
            headers=_headers(token),
            json=json_body,
        )
        # Token expirado: tenta uma vez
        if resp.status_code == 401:
            token = obter_token(force=True)
            resp = client.request(
                method,
                url,
                params=params,
                headers=_headers(token),
                json=json_body,
            )
    return resp


def _executar_instrucao_linha(
    cod: str,
    row: dict,
    colunas_map: dict,
    dados_bancarios: dict,
    nova_data: str,
    valores_conhecidos: dict[str, float] | None,
) -> tuple[ResultadoLinhaApi, dict | None, dict | None]:
    """
    Retorna (resultado, titulo_atualizar|None, valor_enviado|None).
    """
    nn = limpar_nosso_numero(row.get(colunas_map["nn"], ""))
    if not nn:
        return (
            ResultadoLinhaApi("", False, "Linha sem Nosso Numero."),
            None,
            None,
        )

    convenio_raw = "".join(filter(str.isdigit, str(dados_bancarios.get("convenio", ""))))
    if not convenio_raw:
        return (
            ResultadoLinhaApi(nn, False, "Convenio bancario sem numero."),
            None,
            None,
        )
    numero_convenio = int(convenio_raw)
    boleto_id = _montar_id_boleto(convenio_raw, nn)
    titulo_atualizar = None
    valor_enviado = None

    try:
        if cod == "02":
            resp = _request_bb(
                "POST",
                f"/boletos/{boleto_id}/baixar",
                json_body={"numeroConvenio": numero_convenio},
            )
        elif cod in INSTRUCOES_API_SUPORTADAS - {"02"}:
            corpo = _corpo_alteracao_base(numero_convenio)
            if cod == "06":
                if not nova_data:
                    return (
                        ResultadoLinhaApi(nn, False, "Informe a nova data de vencimento."),
                        None,
                        None,
                    )
                corpo["indicadorNovaDataVencimento"] = "S"
                corpo["alteracaoData"] = {"novaDataVencimento": _data_api(nova_data)}
            elif cod == "47":
                valor = row.get(colunas_map.get("valor") or colunas_map.get("montante"))
                valor_f = normalizar_valor_monetario(valor)
                if valor_f is None:
                    return (
                        ResultadoLinhaApi(nn, False, "Valor nominal invalido na planilha."),
                        None,
                        None,
                    )
                corpo["indicadorNovoValorNominal"] = "S"
                corpo["alteracaoValor"] = {"novoValorNominal": valor_f}
                titulo_atualizar = {
                    "nosso_numero": nn,
                    "seu_numero": str(row.get(colunas_map.get("doc", ""), "")).replace(
                        ".0", ""
                    ),
                    "valor_nominal": valor_f,
                }
            elif cod == "09":
                # BB: so uma alteracao por chamada
                corpo["indicadorProtestar"] = "S"
                corpo["protesto"] = {"quantidadeDiasProtesto": 3}
            elif cod == "10":
                # Uma alteracao por chamada — cancela instrucao ainda nao processada
                corpo["indicadorCancelarProtesto"] = "S"
            else:
                return (
                    ResultadoLinhaApi(nn, False, f"Instrucao {cod} ainda nao mapeada."),
                    None,
                    None,
                )

            # Correcao automatica de valor de face quando a referencia diverge
            if valores_conhecidos and cod not in {"47", "02"}:
                montante_planilha = normalizar_valor_monetario(
                    row.get(colunas_map.get("montante"))
                )
                registrado = buscar_valor_registrado(valores_conhecidos, nn)
                if (
                    montante_planilha is not None
                    and registrado is not None
                    and valores_monetarios_diferem(montante_planilha, registrado)
                ):
                    corpo["indicadorNovoValorNominal"] = "S"
                    corpo["alteracaoValor"] = {"novoValorNominal": registrado}

            resp = _request_bb("PATCH", f"/boletos/{boleto_id}", json_body=corpo)
        else:
            return (
                ResultadoLinhaApi(
                    nn,
                    False,
                    f"Instrucao {cod} ainda nao suportada pela API neste app.",
                ),
                None,
                None,
            )
    except BbApiError as exc:
        return ResultadoLinhaApi(nn, False, str(exc)), None, None
    except Exception as exc:
        return ResultadoLinhaApi(nn, False, f"Erro de comunicacao: {exc}"), None, None

    if 200 <= resp.status_code < 300:
        valor_enviado = {
            "nosso_numero": nn,
            "seu_numero": str(row.get(colunas_map.get("doc", ""), "")).replace(".0", ""),
            "valor_nominal": normalizar_valor_monetario(
                row.get(colunas_map.get("montante"))
            )
            or 0.0,
            "cod_instrucao": cod,
        }
        return (
            ResultadoLinhaApi(nn, True, "Enviado com sucesso.", resp.status_code),
            titulo_atualizar,
            valor_enviado,
        )

    return (
        ResultadoLinhaApi(
            nn,
            False,
            f"HTTP {resp.status_code}: {_extrair_erro_bb(resp)}",
            resp.status_code,
        ),
        None,
        None,
    )


def enviar_lotes_api(
    lotes: list[dict],
    dados_bancarios: dict,
    valores_conhecidos: dict[str, float] | None = None,
) -> ResultadoEnvioApi:
    """Envia cada boleto dos lotes para a API Cobranças do BB."""
    resultado = ResultadoEnvioApi()
    if not bb_credenciais_configuradas():
        raise BbApiError(mensagem_credenciais_bb())

    cfg = _secrets_bb()
    if cfg["ambiente"] in ("homologacao", "sandbox"):
        resultado.avisos.append(AVISO_PRAZO_30_MIN)
        convenio_cfg = "".join(
            filter(str.isdigit, str(dados_bancarios.get("convenio", "")))
        )
        if convenio_cfg and convenio_cfg.lstrip("0") != HOMOLOG_CONVENIO.lstrip("0"):
            resultado.avisos.append(
                f"Homologacao BB usa convenio {HOMOLOG_CONVENIO} "
                f"(carteira {HOMOLOG_CARTEIRA}/{HOMOLOG_VARIACAO}). "
                f"Convenio selecionado no app: {convenio_cfg}."
            )

    # Valida instrucoes antes de disparar
    for lote in lotes:
        cod = _codigo_instrucao(lote)
        if cod not in INSTRUCOES_API_SUPORTADAS:
            resultado.avisos.append(
                f"Instrucao {lote.get('instrucao')} ainda nao e suportada via API. "
                f"Suportadas agora: {', '.join(sorted(INSTRUCOES_API_SUPORTADAS))}."
            )

    # Garante token no inicio
    obter_token()

    for lote in lotes:
        cod = _codigo_instrucao(lote)
        if cod not in INSTRUCOES_API_SUPORTADAS:
            df = lote["df"]
            colunas_map = mapear_colunas_planilha(
                df.assign(columns={c: str(c).strip().lower() for c in df.columns})
            )
            for _, row in df.iterrows():
                nn = limpar_nosso_numero(row.get(colunas_map.get("nn", ""), ""))
                resultado.total += 1
                resultado.falhas += 1
                resultado.linhas.append(
                    ResultadoLinhaApi(
                        nn or "?",
                        False,
                        f"Instrucao {cod} nao suportada via API. Use o botao CNAB.",
                    )
                )
            continue

        df = lote["df"].copy()
        df.columns = [str(c).strip().lower() for c in df.columns]
        colunas_map = mapear_colunas_planilha(df)
        nova_data = lote.get("nova_data") or ""

        for _, row in df.iterrows():
            resultado.total += 1
            linha, titulo, valor_env = _executar_instrucao_linha(
                cod,
                row.to_dict(),
                colunas_map,
                dados_bancarios,
                nova_data,
                valores_conhecidos,
            )
            resultado.linhas.append(linha)
            if linha.sucesso:
                resultado.sucessos += 1
                if titulo:
                    resultado.titulos_atualizar.append(titulo)
                if valor_env:
                    resultado.valores_enviados.append(valor_env)
            else:
                resultado.falhas += 1

    return resultado
