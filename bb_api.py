"""Cliente da API Cobranças v2 do Banco do Brasil (sem gerar CNAB)."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx
import pandas as pd
import streamlit as st

from cnab import normalizar_valor_monetario
from config import (
    AMBIENTES_BB_CLIENTES,
    AMBIENTES_BB_TODOS,
    DEV_EMAILS_PADRAO,
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

# Domínios codigoEstadoTituloCobranca (consulta individual / lista)
ESTADOS_TITULO_COBRANCA = {
    1: "NORMAL",
    2: "MOVIMENTO CARTORIO",
    3: "EM CARTORIO",
    4: "TITULO COM OCORRENCIA DE CARTORIO",
    5: "PROTESTADO ELETRONICO",
    6: "LIQUIDADO",
    7: "BAIXADO",
    8: "TITULO COM PENDENCIA DE CARTORIO",
    9: "TITULO PROTESTADO MANUAL",
    10: "TITULO BAIXADO/PAGO EM CARTORIO",
    11: "TITULO LIQUIDADO/PROTESTADO",
    12: "TITULO LIQUID/PGCRTO",
    13: "TITULO PROTESTADO AGUARDANDO BAIXA",
    14: "TITULO EM LIQUIDACAO",
    15: "TITULO AGENDADO BB",
    16: "TITULO CREDITADO",
    17: "PAGO EM CHEQUE - AGUARD.LIQUIDACAO",
    18: "PAGO PARCIALMENTE",
    19: "PAGO PARCIALMENTE CREDITADO",
    21: "TITULO AGENDADO OUTROS BANCOS",
}


@dataclass
class ResultadoLinhaApi:
    nosso_numero: str
    sucesso: bool
    mensagem: str
    status_http: int | None = None
    boleto_id: str = ""
    instrucao: str = ""
    codigo_bb: str = ""
    providencia: str = ""

    def para_linha_tabela(self) -> dict:
        return {
            "Nosso Número": self.nosso_numero or "",
            "ID API": self.boleto_id or "",
            "Instrução": self.instrucao or "",
            "Status": "OK" if self.sucesso else "Erro",
            "HTTP": self.status_http if self.status_http is not None else "",
            "Código BB": self.codigo_bb or "",
            "Mensagem": self.mensagem or "",
            "Providência": self.providencia or "",
        }


@dataclass
class ResultadoEnvioApi:
    total: int = 0
    sucessos: int = 0
    falhas: int = 0
    linhas: list[ResultadoLinhaApi] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    titulos_atualizar: list[dict] = field(default_factory=list)
    valores_enviados: list[dict] = field(default_factory=list)

    def dataframe_resultado(self) -> pd.DataFrame:
        if not self.linhas:
            return pd.DataFrame()
        return pd.DataFrame([linha.para_linha_tabela() for linha in self.linhas])


@dataclass
class ResultadoConsultaBoleto:
    nosso_numero: str
    boleto_id: str
    sucesso: bool
    mensagem: str = ""
    status_http: int | None = None
    erro_instrucao: str = ""
    codigo_bb_instrucao: str = ""
    providencia_instrucao: str = ""
    status_http_instrucao: int | None = None
    dados: dict = field(default_factory=dict)

    def _rotulo_estado(self) -> str:
        estado = (self.dados or {}).get("codigoEstadoTituloCobranca")
        if estado in (None, ""):
            return ""
        try:
            codigo = int(estado)
        except (TypeError, ValueError):
            return str(estado)
        nome = ESTADOS_TITULO_COBRANCA.get(codigo)
        return f"{codigo} - {nome}" if nome else str(codigo)

    def _texto_erro(self) -> str:
        if self.erro_instrucao:
            return self.erro_instrucao
        if not self.sucesso and self.mensagem:
            return self.mensagem
        return ""

    def _proximo_passo(self) -> str:
        if self.providencia_instrucao:
            return self.providencia_instrucao

        codigo = (self.codigo_bb_instrucao or "").strip()
        erro = (self.erro_instrucao or self.mensagem or "").lower()
        http_inst = self.status_http_instrucao

        if (
            codigo.startswith("4125718")
            or (http_inst is not None and http_inst >= 500)
            or "problema tecnico" in erro
            or "problema técnico" in erro
        ):
            return (
                "Tente novamente em alguns minutos. "
                "Se persistir, registre ocorrencia no Portal Developers (Suporte)."
            )

        if not self.sucesso:
            return (
                "Confirme convenio/nosso numero e consulte de novo. "
                "Se o boleto nao existir, use o CNAB ou registre antes de alterar."
            )

        estado_raw = (self.dados or {}).get("codigoEstadoTituloCobranca")
        try:
            estado = int(estado_raw)
        except (TypeError, ValueError):
            estado = None

        if estado in {6, 7, 10, 11, 12, 16}:
            return (
                "Titulo liquidado/baixado/creditado — "
                "nao e possivel alterar; confira se a instrucao ainda se aplica."
            )
        if estado in {2, 3, 4, 5, 8, 9, 13}:
            return (
                "Titulo em cartorio/protesto — "
                "revise a situacao antes de reenviar alteracao ou baixa."
            )
        if "30 minut" in erro:
            return "Aguarde 30 minutos apos a geracao do boleto (homologacao) e reenvie."

        return (
            "Compare valor/vencimento da planilha com o estado atual e reenvie a instrucao."
        )

    def _primeiro_valor(self, *chaves: str) -> Any:
        """Primeiro valor nao vazio entre chaves (GET BB usa nomes longos)."""
        d = self.dados or {}
        for chave in chaves:
            if chave not in d:
                continue
            valor = d.get(chave)
            if valor in (None, ""):
                continue
            return valor
        # Formato aninhado (alguns endpoints)
        pagador = d.get("pagador") if isinstance(d.get("pagador"), dict) else {}
        for chave in chaves:
            if chave in ("nome", "nomeSacadoCobranca") and pagador.get("nome"):
                return pagador.get("nome")
            if chave in ("numeroInscricao", "numeroInscricaoSacadoCobranca") and pagador.get(
                "numeroInscricao"
            ):
                return pagador.get("numeroInscricao")
            if chave in ("dataVencimento", "dataVencimentoTituloCobranca") and d.get(
                "dataVencimento"
            ):
                return d.get("dataVencimento")
        return ""

    def para_resumo(self) -> dict:
        if not self.sucesso:
            return {
                "Nosso Número": self.nosso_numero or "",
                "Situação": "—",
                "Vencimento": "",
                "Valor original": "",
                "Valor atual": "",
                "Valor pago": "",
                "Recebimento": "",
                "Crédito": "",
                "Pagador": "",
                "CPF": "",
                "Erro": self._texto_erro(),
                "Próximo passo": self._proximo_passo(),
            }

        valor_orig = self._primeiro_valor("valorOriginalTituloCobranca", "valorOriginal")
        valor_atual = self._primeiro_valor("valorAtualTituloCobranca", "valorAtual")
        valor_pago = self._primeiro_valor("valorPagoSacado", "valorPago")
        return {
            "Nosso Número": self.nosso_numero or "",
            "Situação": self._rotulo_estado(),
            "Vencimento": self._primeiro_valor(
                "dataVencimentoTituloCobranca", "dataVencimento"
            ),
            "Valor original": valor_orig if valor_orig != "" else "",
            "Valor atual": valor_atual if valor_atual != "" else "",
            "Valor pago": valor_pago if valor_pago != "" else "",
            "Recebimento": self._primeiro_valor(
                "dataRecebimentoTitulo", "dataRecebimento"
            ),
            "Crédito": self._primeiro_valor(
                "dataCreditoLiquidacao", "dataCredito"
            ),
            "Pagador": self._primeiro_valor("nomeSacadoCobranca", "nome"),
            "CPF": self._primeiro_valor(
                "numeroInscricaoSacadoCobranca", "numeroInscricao"
            ),
            "Erro": self._texto_erro(),
            "Próximo passo": self._proximo_passo(),
        }

    def campos_achatados(self) -> dict[str, Any]:
        base = {
            "nosso_numero": self.nosso_numero,
            "boleto_id": self.boleto_id,
            "consulta_ok": self.sucesso,
            "erro_instrucao": self.erro_instrucao,
            "codigo_bb_instrucao": self.codigo_bb_instrucao,
            "providencia_instrucao": self.providencia_instrucao,
            "proximo_passo": self._proximo_passo(),
        }
        if not self.sucesso:
            base["erro_consulta"] = self.mensagem
            base["http_consulta"] = self.status_http
            return base
        base.update(achatar_dict(self.dados or {}))
        return base


class BbApiError(Exception):
    """Erro de configuração ou autenticação com a API do BB."""


def _emails_dev() -> set[str]:
    emails = {e.strip().lower() for e in DEV_EMAILS_PADRAO if e}
    try:
        extra = st.secrets.get("DEV_EMAILS", None)
        if extra is None:
            extra = st.secrets.get("bb", {}).get("dev_emails")
        if isinstance(extra, str):
            emails.update(p.strip().lower() for p in extra.split(",") if p.strip())
        elif isinstance(extra, (list, tuple)):
            emails.update(str(p).strip().lower() for p in extra if str(p).strip())
    except Exception:
        pass
    return emails


def usuario_pode_homologar(email: str | None) -> bool:
    """Sandbox/homologacao so para e-mails de desenvolvimento."""
    return (email or "").strip().lower() in _emails_dev()


def ambientes_bb_para_usuario(email: str | None) -> list[str]:
    if usuario_pode_homologar(email):
        return list(AMBIENTES_BB_TODOS)
    return list(AMBIENTES_BB_CLIENTES)


def _cfg_vazia() -> dict:
    return {
        "client_id": "",
        "client_secret": "",
        "app_key": "",
        "ambiente": "producao",
        "scopes": "",
    }


def _secrets_bb() -> dict:
    """Credenciais por base/cliente (aba API BB no Supabase). Sem chave global compartilhada."""
    salvas = st.session_state.get("bb_credenciais_workspace") or {}
    return {
        "client_id": str(salvas.get("client_id") or "").strip(),
        "client_secret": str(salvas.get("client_secret") or "").strip(),
        "app_key": str(salvas.get("app_key") or "").strip(),
        "ambiente": str(salvas.get("ambiente") or "producao").strip().lower(),
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


def codigo_instrucao_lote(lote: dict) -> str:
    """Codigo numerico da instrucao do lote (ex.: '47')."""
    return _codigo_instrucao(lote)


def _parse_item_erro_bb(item: dict) -> tuple[str, str, str]:
    """Retorna (codigo, mensagem, providencia)."""
    codigo = str(
        item.get("codigo")
        or item.get("codigoMensagem")
        or item.get("code")
        or item.get("codigoErro")
        or ""
    ).strip()
    versao = item.get("versao") or item.get("versaoMensagem")
    if codigo and versao not in (None, ""):
        codigo = f"{codigo}.{versao}"
    mensagem = str(
        item.get("mensagem")
        or item.get("textoMensagem")
        or item.get("message")
        or item.get("mensagemErro")
        or ""
    ).strip()
    providencia = str(
        item.get("providencia")
        or item.get("acao")
        or item.get("action")
        or item.get("ocorrencia")
        or ""
    ).strip()
    return codigo, mensagem, providencia


def _formatar_item_erro_bb(item: dict) -> str:
    codigo, mensagem, providencia = _parse_item_erro_bb(item)
    partes = []
    if codigo:
        partes.append(f"[{codigo}]")
    if mensagem:
        partes.append(mensagem)
    if providencia:
        partes.append(f"Providencia: {providencia}")
    return " ".join(partes) if partes else str(item)


def _extrair_erro_bb_detalhado(resp: httpx.Response) -> tuple[str, str, str]:
    """Retorna (codigo_bb, mensagem, providencia) do primeiro erro util."""
    try:
        data = resp.json()
    except Exception:
        return "", (resp.text[:500] or f"HTTP {resp.status_code}"), ""
    if not isinstance(data, dict):
        return "", str(data)[:500], ""

    erros = data.get("erros") or data.get("errors")
    if isinstance(erros, list) and erros:
        for e in erros:
            if isinstance(e, dict):
                return _parse_item_erro_bb(e)
            return "", str(e)[:500], ""
    if isinstance(erros, str):
        return "", erros[:500], ""
    if any(k in data for k in ("codigo", "codigoMensagem", "code", "mensagem", "textoMensagem")):
        return _parse_item_erro_bb(data)
    msg = data.get("message") or data.get("mensagem") or data.get("error_description")
    if msg:
        return str(data.get("error") or data.get("statusCode") or ""), str(msg)[:500], ""
    return "", str(data)[:500], ""


def _extrair_erro_bb(resp: httpx.Response) -> str:
    codigo, mensagem, providencia = _extrair_erro_bb_detalhado(resp)
    partes = []
    if codigo:
        partes.append(f"[{codigo}]")
    if mensagem:
        partes.append(mensagem)
    if providencia:
        partes.append(f"Providencia: {providencia}")
    return (" ".join(partes) if partes else f"HTTP {resp.status_code}")[:800]


def _resultado_erro(
    nn: str,
    mensagem: str,
    *,
    boleto_id: str = "",
    instrucao: str = "",
    status_http: int | None = None,
    codigo_bb: str = "",
    providencia: str = "",
) -> ResultadoLinhaApi:
    return ResultadoLinhaApi(
        nosso_numero=nn,
        sucesso=False,
        mensagem=mensagem,
        status_http=status_http,
        boleto_id=boleto_id,
        instrucao=instrucao,
        codigo_bb=codigo_bb,
        providencia=providencia,
    )


def achatar_dict(dados: Any, prefixo: str = "") -> dict[str, Any]:
    """Achata dicts aninhados para exibicao tabular / CSV."""
    saida: dict[str, Any] = {}
    if not isinstance(dados, dict):
        chave = prefixo or "valor"
        if isinstance(dados, list):
            saida[chave] = json.dumps(dados, ensure_ascii=False)
        else:
            saida[chave] = dados
        return saida
    for chave, valor in dados.items():
        caminho = f"{prefixo}.{chave}" if prefixo else str(chave)
        if isinstance(valor, dict):
            saida.update(achatar_dict(valor, caminho))
        elif isinstance(valor, list):
            saida[caminho] = json.dumps(valor, ensure_ascii=False)
        else:
            saida[caminho] = valor
    return saida


def _deve_retentar_bb(resp: httpx.Response) -> bool:
    if resp.status_code >= 500:
        return True
    try:
        codigo, _, _ = _extrair_erro_bb_detalhado(resp)
    except Exception:
        return False
    return bool(codigo and str(codigo).startswith("4125718"))


def _request_bb(
    method: str,
    path: str,
    *,
    json_body: dict | None = None,
    params_extra: dict | None = None,
    client: httpx.Client | None = None,
    max_retries: int = 2,
) -> httpx.Response:
    cfg = _secrets_bb()
    urls = _ambiente_urls(cfg["ambiente"])
    token = obter_token()
    url = f"{urls['api_url']}{path}"
    params = {"gw-dev-app-key": cfg["app_key"]}
    if params_extra:
        params.update(params_extra)

    own_client = client is None
    if own_client:
        client = httpx.Client(timeout=45.0)

    try:
        resp: httpx.Response | None = None
        for attempt in range(max_retries + 1):
            resp = client.request(
                method,
                url,
                params=params,
                headers=_headers(token),
                json=json_body,
            )
            if resp.status_code == 401:
                token = obter_token(force=True)
                resp = client.request(
                    method,
                    url,
                    params=params,
                    headers=_headers(token),
                    json=json_body,
                )
            if attempt < max_retries and _deve_retentar_bb(resp):
                time.sleep(1.5 * (attempt + 1))
                continue
            return resp
        assert resp is not None
        return resp
    finally:
        if own_client:
            client.close()


def consultar_boleto(
    boleto_id: str,
    numero_convenio: str | int,
    *,
    nosso_numero: str = "",
    erro_instrucao: str = "",
    codigo_bb_instrucao: str = "",
    providencia_instrucao: str = "",
    status_http_instrucao: int | None = None,
    client: httpx.Client | None = None,
) -> ResultadoConsultaBoleto:
    """GET /boletos/{id}?numeroConvenio=... — retorna todos os campos da API."""
    if not bb_credenciais_configuradas():
        raise BbApiError(mensagem_credenciais_bb())

    convenio_raw = "".join(filter(str.isdigit, str(numero_convenio)))
    if not convenio_raw:
        raise BbApiError("Convenio bancario sem numero para consulta.")

    boleto_id = "".join(filter(str.isdigit, str(boleto_id or "")))
    if not boleto_id:
        raise BbApiError("ID do boleto vazio para consulta.")

    nn = nosso_numero or boleto_id
    meta = {
        "erro_instrucao": erro_instrucao,
        "codigo_bb_instrucao": codigo_bb_instrucao,
        "providencia_instrucao": providencia_instrucao,
        "status_http_instrucao": status_http_instrucao,
    }
    try:
        resp = _request_bb(
            "GET",
            f"/boletos/{boleto_id}",
            params_extra={"numeroConvenio": int(convenio_raw)},
            client=client,
        )
    except BbApiError:
        raise
    except Exception as exc:
        return ResultadoConsultaBoleto(
            nosso_numero=nn,
            boleto_id=boleto_id,
            sucesso=False,
            mensagem=f"Erro de comunicacao: {exc}",
            **meta,
        )

    if 200 <= resp.status_code < 300:
        try:
            dados = resp.json()
        except Exception:
            dados = {"raw": resp.text[:2000]}
        if not isinstance(dados, dict):
            dados = {"raw": dados}
        return ResultadoConsultaBoleto(
            nosso_numero=nn,
            boleto_id=boleto_id,
            sucesso=True,
            status_http=resp.status_code,
            dados=dados,
            **meta,
        )

    codigo_bb, mensagem_bb, providencia = _extrair_erro_bb_detalhado(resp)
    partes = [p for p in (mensagem_bb, f"Providencia: {providencia}" if providencia else "") if p]
    mensagem = " ".join(partes) or f"HTTP {resp.status_code}"
    if codigo_bb:
        mensagem = f"[{codigo_bb}] {mensagem}"
    return ResultadoConsultaBoleto(
        nosso_numero=nn,
        boleto_id=boleto_id,
        sucesso=False,
        mensagem=mensagem,
        status_http=resp.status_code,
        **meta,
    )


def consultar_boletos_com_erro(
    erros: list[dict | ResultadoLinhaApi],
    numero_convenio: str | int,
    *,
    on_progress=None,
) -> list[ResultadoConsultaBoleto]:
    """Consulta no BB cada boleto que falhou no envio da instrucao."""
    if not bb_credenciais_configuradas():
        raise BbApiError(mensagem_credenciais_bb())

    convenio_raw = "".join(filter(str.isdigit, str(numero_convenio)))
    if not convenio_raw:
        raise BbApiError("Convenio bancario sem numero para consulta.")

    obter_token()
    resultados: list[ResultadoConsultaBoleto] = []
    total = len(erros)
    with httpx.Client(timeout=45.0) as client:
        for idx, item in enumerate(erros, start=1):
            if isinstance(item, ResultadoLinhaApi):
                nn = item.nosso_numero
                boleto_id = item.boleto_id
                erro_instrucao = item.mensagem
                codigo_bb = item.codigo_bb
                providencia = item.providencia
                http_inst = item.status_http
            else:
                nn = str(item.get("nosso_numero") or "")
                boleto_id = str(item.get("boleto_id") or "")
                erro_instrucao = str(item.get("mensagem") or "")
                codigo_bb = str(item.get("codigo_bb") or "")
                providencia = str(item.get("providencia") or "")
                http_raw = item.get("status_http")
                try:
                    http_inst = int(http_raw) if http_raw not in (None, "") else None
                except (TypeError, ValueError):
                    http_inst = None

            meta = {
                "erro_instrucao": erro_instrucao,
                "codigo_bb_instrucao": codigo_bb,
                "providencia_instrucao": providencia,
                "status_http_instrucao": http_inst,
            }

            if not boleto_id and nn:
                try:
                    boleto_id = _montar_id_boleto(convenio_raw, nn)
                except BbApiError as exc:
                    resultados.append(
                        ResultadoConsultaBoleto(
                            nosso_numero=nn or "?",
                            boleto_id="",
                            sucesso=False,
                            mensagem=str(exc),
                            **meta,
                        )
                    )
                    if on_progress:
                        on_progress(idx, total, nn or "")
                    continue

            if not boleto_id:
                resultados.append(
                    ResultadoConsultaBoleto(
                        nosso_numero=nn or "?",
                        boleto_id="",
                        sucesso=False,
                        mensagem="Sem ID API para consultar.",
                        **meta,
                    )
                )
                if on_progress:
                    on_progress(idx, total, nn or "")
                continue

            resultados.append(
                consultar_boleto(
                    boleto_id,
                    convenio_raw,
                    nosso_numero=nn,
                    client=client,
                    **meta,
                )
            )
            if on_progress:
                on_progress(idx, total, nn or "")
    return resultados


def dataframe_resumo_consultas(consultas: list[ResultadoConsultaBoleto]) -> pd.DataFrame:
    if not consultas:
        return pd.DataFrame()
    return pd.DataFrame([c.para_resumo() for c in consultas])


def dataframe_campos_completos_consultas(
    consultas: list[ResultadoConsultaBoleto],
) -> pd.DataFrame:
    """Uma linha por boleto com todos os campos achatados da resposta BB."""
    if not consultas:
        return pd.DataFrame()
    return pd.DataFrame([c.campos_achatados() for c in consultas])


def _executar_instrucao_linha(
    cod: str,
    row: dict,
    colunas_map: dict,
    dados_bancarios: dict,
    nova_data: str,
    valores_conhecidos: dict[str, float] | None,
    *,
    client: httpx.Client | None = None,
    dias_protesto: int = 3,
) -> tuple[ResultadoLinhaApi, dict | None, dict | None]:
    """
    Retorna (resultado, titulo_atualizar|None, valor_enviado|None).
    """
    nn = limpar_nosso_numero(row.get(colunas_map["nn"], ""))
    if not nn:
        return (
            _resultado_erro("", "Linha sem Nosso Numero.", instrucao=cod),
            None,
            None,
        )

    convenio_raw = "".join(filter(str.isdigit, str(dados_bancarios.get("convenio", ""))))
    if not convenio_raw:
        return (
            _resultado_erro(nn, "Convenio bancario sem numero.", instrucao=cod),
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
                client=client,
            )
        elif cod in INSTRUCOES_API_SUPORTADAS - {"02"}:
            corpo = _corpo_alteracao_base(numero_convenio)
            if cod == "06":
                if not nova_data:
                    return (
                        _resultado_erro(
                            nn,
                            "Informe a nova data de vencimento.",
                            boleto_id=boleto_id,
                            instrucao=cod,
                        ),
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
                        _resultado_erro(
                            nn,
                            "Valor nominal invalido na planilha.",
                            boleto_id=boleto_id,
                            instrucao=cod,
                        ),
                        None,
                        None,
                    )
                # BB: apenas UMA alteracao por chamada
                corpo["indicadorNovoValorNominal"] = "S"
                corpo["alteracaoValor"] = {"novoValorNominal": float(valor_f)}
                titulo_atualizar = {
                    "nosso_numero": nn,
                    "seu_numero": str(row.get(colunas_map.get("doc", ""), "")).replace(
                        ".0", ""
                    ),
                    "valor_nominal": valor_f,
                }
            elif cod == "09":
                corpo["indicadorProtestar"] = "S"
                corpo["protesto"] = {
                    "quantidadeDiasProtesto": max(1, int(dias_protesto or 3))
                }
            elif cod == "10":
                corpo["indicadorCancelarProtesto"] = "S"
            else:
                return (
                    _resultado_erro(
                        nn,
                        f"Instrucao {cod} ainda nao mapeada.",
                        boleto_id=boleto_id,
                        instrucao=cod,
                    ),
                    None,
                    None,
                )

            # BB: uma alteracao por PATCH. Se montante diverge em 06/09/10,
            # nao corrige aqui — sinaliza no resultado via aviso embutido na mensagem se falhar.
            resp = _request_bb(
                "PATCH", f"/boletos/{boleto_id}", json_body=corpo, client=client
            )
        else:
            return (
                _resultado_erro(
                    nn,
                    f"Instrucao {cod} ainda nao suportada pela API neste app.",
                    boleto_id=boleto_id,
                    instrucao=cod,
                ),
                None,
                None,
            )
    except BbApiError as exc:
        return (
            _resultado_erro(nn, str(exc), boleto_id=boleto_id, instrucao=cod),
            None,
            None,
        )
    except Exception as exc:
        return (
            _resultado_erro(
                nn,
                f"Erro de comunicacao: {exc}",
                boleto_id=boleto_id,
                instrucao=cod,
            ),
            None,
            None,
        )

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
            ResultadoLinhaApi(
                nosso_numero=nn,
                sucesso=True,
                mensagem="Enviado com sucesso.",
                status_http=resp.status_code,
                boleto_id=boleto_id,
                instrucao=cod,
            ),
            titulo_atualizar,
            valor_enviado,
        )

    codigo_bb, mensagem_bb, providencia = _extrair_erro_bb_detalhado(resp)
    # 503/4125718 costuma ser falha tecnica do BB, nao validacao de negocio
    if resp.status_code >= 500 or codigo_bb.startswith("4125718"):
        if providencia:
            mensagem_final = mensagem_bb
        else:
            mensagem_final = (
                f"{mensagem_bb} (erro tecnico do BB — geralmente nao detalha "
                "campo invalido; tente novamente em alguns minutos)"
            )
    else:
        mensagem_final = mensagem_bb or _extrair_erro_bb(resp)

    return (
        _resultado_erro(
            nn,
            mensagem_final,
            boleto_id=boleto_id,
            instrucao=cod,
            status_http=resp.status_code,
            codigo_bb=codigo_bb,
            providencia=providencia,
        ),
        None,
        None,
    )


def enviar_lotes_api(
    lotes: list[dict],
    dados_bancarios: dict,
    valores_conhecidos: dict[str, float] | None = None,
    *,
    on_progress=None,
    pular_nosso_numeros: set[str] | None = None,
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

    for lote in lotes:
        cod = _codigo_instrucao(lote)
        if cod not in INSTRUCOES_API_SUPORTADAS:
            resultado.avisos.append(
                f"Instrucao {lote.get('instrucao')} ainda nao e suportada via API. "
                f"Suportadas agora: {', '.join(sorted(INSTRUCOES_API_SUPORTADAS))}."
            )

    obter_token()
    pular = {limpar_nosso_numero(n) for n in (pular_nosso_numeros or set()) if n}

    # Conta total para progresso
    total_previsto = 0
    for lote in lotes:
        total_previsto += len(lote.get("df") or [])
    feitos = 0

    with httpx.Client(timeout=45.0) as client:
        for lote in lotes:
            cod = _codigo_instrucao(lote)
            dias_protesto = int(lote.get("dias_protesto") or 3)
            if cod not in INSTRUCOES_API_SUPORTADAS:
                df = lote["df"]
                colunas_map = mapear_colunas_planilha(
                    df.assign(columns={c: str(c).strip().lower() for c in df.columns})
                )
                for _, row in df.iterrows():
                    nn = limpar_nosso_numero(row.get(colunas_map.get("nn", ""), ""))
                    resultado.total += 1
                    resultado.falhas += 1
                    feitos += 1
                    resultado.linhas.append(
                        _resultado_erro(
                            nn or "?",
                            f"Instrucao {cod} nao suportada via API. Use o botao CNAB.",
                            instrucao=cod,
                        )
                    )
                    if on_progress:
                        on_progress(feitos, total_previsto, nn or "")
                continue

            df = lote["df"].copy()
            df.columns = [str(c).strip().lower() for c in df.columns]
            colunas_map = mapear_colunas_planilha(df)
            nova_data = lote.get("nova_data") or ""

            for _, row in df.iterrows():
                resultado.total += 1
                nn = limpar_nosso_numero(row.get(colunas_map.get("nn", ""), ""))
                if nn and nn in pular:
                    feitos += 1
                    resultado.sucessos += 1
                    resultado.linhas.append(
                        ResultadoLinhaApi(
                            nosso_numero=nn,
                            sucesso=True,
                            mensagem="Ignorado: ja enviado com sucesso nesta sessao.",
                            instrucao=cod,
                        )
                    )
                    if on_progress:
                        on_progress(feitos, total_previsto, nn)
                    continue

                linha, titulo, valor_env = _executar_instrucao_linha(
                    cod,
                    row.to_dict(),
                    colunas_map,
                    dados_bancarios,
                    nova_data,
                    valores_conhecidos,
                    client=client,
                    dias_protesto=dias_protesto,
                )
                resultado.linhas.append(linha)
                feitos += 1
                if on_progress:
                    on_progress(feitos, total_previsto, linha.nosso_numero)
                if linha.sucesso:
                    resultado.sucessos += 1
                    if titulo:
                        resultado.titulos_atualizar.append(titulo)
                    if valor_env:
                        resultado.valores_enviados.append(valor_env)
                else:
                    resultado.falhas += 1

    return resultado
