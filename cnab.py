"""Geração de arquivos CNAB 240 - Banco do Brasil."""

from __future__ import annotations

import io
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from validation import limpar_nosso_numero, mapear_colunas_planilha


def normalizar_valor_monetario(valor) -> float | None:
    if pd.isna(valor) or str(valor).strip().lower() in ["", "nan"]:
        return None
    texto = str(valor).strip().replace("R$", "").replace(" ", "")
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")
    try:
        return round(float(texto), 2)
    except (ValueError, TypeError):
        return None


def chaves_nosso_numero(nn: str) -> list[str]:
    if not nn:
        return []
    chaves = [nn]
    sem_zeros = nn.lstrip("0") or "0"
    if sem_zeros not in chaves:
        chaves.append(sem_zeros)
    padded = nn.zfill(20)
    if padded not in chaves:
        chaves.append(padded)
    return chaves


def buscar_valor_registrado(valores: dict[str, float], nn: str) -> float | None:
    for chave in chaves_nosso_numero(nn):
        if chave in valores:
            return valores[chave]
    return None


def formatar_real(valor: float) -> str:
    texto = f"{valor:,.2f}"
    return "R$ " + texto.replace(",", "X").replace(".", ",").replace("X", ".")


def valores_monetarios_diferem(valor_a, valor_b, tolerancia: float = 0.009) -> bool:
    a = normalizar_valor_monetario(valor_a)
    b = normalizar_valor_monetario(valor_b)
    if a is None or b is None:
        return False
    return abs(a - b) > tolerancia


def coletar_nosso_numeros_lotes(lotes: list[dict]) -> list[str]:
    numeros: list[str] = []
    for lote in lotes:
        df = lote["df"].copy()
        df.columns = [str(c).strip().lower() for c in df.columns]
        colunas_map = mapear_colunas_planilha(df)
        for _, row in df.iterrows():
            nn = limpar_nosso_numero(row.get(colunas_map["nn"], ""))
            if nn:
                numeros.append(nn)
    return list(dict.fromkeys(numeros))


def fmt_num(valor, tamanho):
    if pd.isna(valor):
        valor = 0
    v_str = str(valor).strip()
    if v_str.endswith(".0"):
        v_str = v_str[:-2]
    return "".join(filter(str.isdigit, v_str)).zfill(tamanho)[:tamanho]


def fmt_alfa(valor, tamanho):
    if pd.isna(valor) or str(valor).lower() == "nan":
        valor = ""
    texto = str(valor)
    texto = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    texto = "".join(c for c in texto if c.isalnum() or c.isspace())
    return texto.upper().ljust(tamanho, " ")[:tamanho]


def fmt_date(valor):
    if pd.isna(valor) or str(valor).strip().lower() in ["nan", "nat", ""]:
        return "00000000"
    v_str = str(valor).strip()
    try:
        if v_str.replace(".0", "").isdigit():
            serial = int(float(v_str))
            return (
                pd.to_datetime("1899-12-30") + pd.to_timedelta(serial, unit="D")
            ).strftime("%d%m%Y")
        return pd.to_datetime(v_str).strftime("%d%m%Y")
    except (ValueError, TypeError):
        return "00000000"


def fmt_money(valor, tamanho):
    normalizado = normalizar_valor_monetario(valor)
    if normalizado is None:
        return "0".zfill(tamanho)
    return str(int(round(normalizado * 100))).zfill(tamanho)[:tamanho]


def fmt_conta_bb(dados):
    return (
        fmt_num(dados.get("agencia", ""), 5)
        + fmt_alfa(dados.get("dv_agencia", ""), 1)
        + fmt_num(dados.get("conta", ""), 12)
        + fmt_alfa(dados.get("dv_conta", ""), 1)
        + " "
    )


def fmt_convenio_bb(dados):
    return (
        fmt_num(dados.get("convenio", ""), 9)
        + "0014"
        + fmt_num(dados.get("carteira", ""), 2)
        + fmt_num(dados.get("variacao", ""), 3)
        + "  "
    )


def header_arquivo(dados, nsa):
    return (
        fmt_num("001", 3)
        + fmt_num("0000", 4)
        + fmt_num("0", 1)
        + fmt_alfa("", 9)
        + fmt_num("2", 1)
        + fmt_num(dados["cnpj"], 14)
        + fmt_convenio_bb(dados)
        + fmt_conta_bb(dados)
        + fmt_alfa(dados["razao_social"], 30)
        + fmt_alfa("BANCO DO BRASIL", 30)
        + fmt_alfa("", 10)
        + fmt_num("1", 1)
        + datetime.now().strftime("%d%m%Y")
        + datetime.now().strftime("%H%M%S")
        + fmt_num(nsa, 6)
        + fmt_num("083", 3)
        + fmt_alfa("", 5)
        + fmt_alfa("", 20)
        + fmt_alfa("", 20)
        + fmt_alfa("", 29)
    )


def header_lote(dados, lote, nsa):
    return (
        fmt_num("001", 3)
        + fmt_num(lote, 4)
        + fmt_num("1", 1)
        + fmt_alfa("R", 1)
        + fmt_num("01", 2)
        + fmt_alfa("", 2)
        + fmt_num("045", 3)
        + fmt_alfa("", 1)
        + fmt_num("2", 1)
        + fmt_num(dados["cnpj"], 15)
        + fmt_convenio_bb(dados)
        + fmt_conta_bb(dados)
        + fmt_alfa(dados["razao_social"], 30)
        + fmt_alfa("", 40)
        + fmt_alfa("", 40)
        + fmt_num(nsa, 8)
        + datetime.now().strftime("%d%m%Y")
        + fmt_num("0", 8)
        + fmt_alfa("", 33)
    )


def trailer_lote(lote, qtd_registros):
    return (
        fmt_num("001", 3)
        + fmt_num(lote, 4)
        + fmt_num("5", 1)
        + fmt_alfa("", 9)
        + fmt_num(qtd_registros, 6)
        + fmt_num("0", 6)
        + fmt_alfa("", 205)
    )


def trailer_arquivo(qtd_lotes, qtd_registros):
    return (
        fmt_num("001", 3)
        + fmt_num("9999", 4)
        + fmt_num("9", 1)
        + fmt_alfa("", 9)
        + fmt_num(qtd_lotes, 6)
        + fmt_num(qtd_registros, 6)
        + fmt_num("0", 6)
        + fmt_alfa("", 205)
    )


def segmento_p(row, lote, seq, dados, colunas_map, cod_instrucao, nova_data_venc=""):
    reg = (
        fmt_num("001", 3)
        + fmt_num(lote, 4)
        + fmt_num("3", 1)
        + fmt_num(seq, 5)
        + fmt_alfa("P", 1)
        + fmt_alfa("", 1)
        + fmt_num(cod_instrucao, 2)
        + fmt_conta_bb(dados)
    )
    nn = limpar_nosso_numero(row.get(colunas_map["nn"], ""))
    reg += (
        fmt_alfa(nn, 20)
        + fmt_num(dados.get("carteira", "17"), 1)
        + fmt_num("1", 1)
        + fmt_alfa("2", 1)
        + fmt_num("2", 1)
        + fmt_alfa("2", 1)
    )
    seu_numero = str(row.get(colunas_map["doc"], "")).replace(".0", "")
    if seu_numero.lower() == "nan":
        seu_numero = ""
    reg += fmt_alfa(seu_numero, 15)
    vencimento = (
        nova_data_venc.replace("/", "")
        if cod_instrucao == "06" and nova_data_venc
        else fmt_date(row.get(colunas_map["venc"]))
    )
    valor_boleto = (
        row.get(colunas_map["valor"])
        if cod_instrucao == "47"
        else row.get(colunas_map["montante"])
    )
    reg += (
        vencimento
        + fmt_money(valor_boleto, 15)
        + fmt_num("0", 5)
        + fmt_alfa("", 1)
        + fmt_num("99", 2)
        + fmt_alfa("N", 1)
    )
    reg += (
        fmt_date(row.get(colunas_map["venc"]))
        + fmt_num("3", 1)
        + fmt_num("0", 8)
        + fmt_num("0", 15)
        + fmt_num("0", 1)
        + fmt_num("0", 8)
        + fmt_num("0", 15)
        + fmt_num("0", 15)
        + fmt_num("0", 15)
        + fmt_alfa("", 25)
        + fmt_num("3", 1)
        + fmt_num("0", 2)
        + fmt_num("0", 1)
        + fmt_num("0", 3)
        + fmt_num("09", 2)
        + fmt_num("0", 10)
        + fmt_alfa("", 1)
    )
    return reg


def segmento_q(row, lote, seq, colunas_map, cod_instrucao):
    reg = (
        fmt_num("001", 3)
        + fmt_num(lote, 4)
        + fmt_num("3", 1)
        + fmt_num(seq, 5)
        + fmt_alfa("Q", 1)
        + fmt_alfa("", 1)
        + fmt_num(cod_instrucao, 2)
    )
    cpf_cnpj = str(row.get("cnpj_cpf", "")).strip().replace(".0", "")
    if cpf_cnpj.lower() == "nan":
        cpf_cnpj = ""
    tipo_inscricao = "2" if len(cpf_cnpj) > 11 else ("1" if cpf_cnpj else "0")
    reg += fmt_num(tipo_inscricao, 1) + fmt_num(cpf_cnpj, 15)
    nome = str(row.get("nome", ""))
    reg += fmt_alfa("" if nome.lower() == "nan" else nome, 40)
    end = str(row.get("endereco", ""))
    reg += fmt_alfa("" if end.lower() == "nan" else end, 40)
    bairro = str(row.get("bairro", ""))
    reg += fmt_alfa("" if bairro.lower() == "nan" else bairro, 15)
    cep = str(row.get("cep", "")).replace("-", "").replace(".0", "")
    reg += fmt_num(cep if cep.isdigit() else "0", 8)
    cidade = str(row.get("cidade", ""))
    reg += fmt_alfa("" if cidade.lower() == "nan" else cidade, 15)
    uf = str(row.get("uf", ""))
    reg += fmt_alfa("" if uf.lower() == "nan" else uf, 2)
    reg += fmt_num("0", 1) + fmt_num("0", 15) + fmt_alfa("", 40) + fmt_num("0", 3) + fmt_alfa("", 20) + fmt_alfa("", 8)
    return reg


def enriquecer_row_com_cliente(row_dict, colunas_map, df_clientes_banco):
    cod_cliente_boleto = str(row_dict.get(colunas_map["cliente"], "")).replace(".0", "").strip()
    if (
        not df_clientes_banco.empty
        and "id_cliente_planilha" in df_clientes_banco.columns
        and cod_cliente_boleto
    ):
        match = df_clientes_banco[
            df_clientes_banco["id_cliente_planilha"].astype(str) == cod_cliente_boleto
        ]
        if not match.empty:
            dados_cli = match.iloc[0].to_dict()
            row_dict["cnpj_cpf"] = dados_cli.get("cnpj_cpf", "")
            row_dict["nome"] = dados_cli.get("nome", "")
            row_dict["endereco"] = dados_cli.get("endereco", "")
            row_dict["bairro"] = dados_cli.get("bairro", "")
            row_dict["cep"] = dados_cli.get("cep", "")
            row_dict["cidade"] = dados_cli.get("cidade", "")
            row_dict["uf"] = dados_cli.get("uf", "")
    return row_dict


def linhas_para_bytes(linhas: list[str]) -> bytes:
    cnab_bytes = io.BytesIO()
    for linha in linhas:
        linha_limpa = "".join(
            c for c in unicodedata.normalize("NFD", linha) if unicodedata.category(c) != "Mn"
        )
        linha_final = linha_limpa.ljust(240, " ")[:240] + "\r\n"
        bytes_linha = linha_final.encode("ascii", errors="replace").replace(b"?", b" ")
        cnab_bytes.write(bytes_linha)
    return cnab_bytes.getvalue()


@dataclass
class ResultadoGeracao:
    linhas: list[str] = field(default_factory=list)
    erros_linha: list[str] = field(default_factory=list)
    avisos_correcao: list[str] = field(default_factory=list)
    titulos_atualizar: list[dict] = field(default_factory=list)
    valores_enviados: list[dict] = field(default_factory=list)
    total_boletos: int = 0
    total_lotes: int = 0


def gerar_remessa(
    lotes: list[dict],
    dados_bancarios: dict,
    df_clientes_banco: pd.DataFrame,
    nsa: int = 1,
    valores_conhecidos: dict[str, float] | None = None,
) -> ResultadoGeracao:
    resultado = ResultadoGeracao(total_lotes=len(lotes))
    valores_registro: dict[str, float] = dict(valores_conhecidos or {})
    linhas = [header_arquivo(dados_bancarios, nsa)]
    total_registros_arquivo = 0

    for i, lote in enumerate(lotes):
        numero_lote = i + 1
        linhas.append(header_lote(dados_bancarios, numero_lote, nsa))

        df_boletos = lote["df"].copy()
        cod_instrucao = lote["instrucao"].split(" - ")[0].strip()
        colunas_map = mapear_colunas_planilha(df_boletos)

        colunas_bol_lower = [str(c).strip().lower() for c in df_boletos.columns]
        df_boletos.columns = colunas_bol_lower

        seq_reg = 1
        nome_planilha = lote.get("nome_arquivo", "")
        for index, row in df_boletos.iterrows():
            try:
                row_dict = enriquecer_row_com_cliente(row.to_dict(), colunas_map, df_clientes_banco)
                nn = limpar_nosso_numero(row_dict.get(colunas_map["nn"], ""))
                linha_planilha = index + 2

                if cod_instrucao == "47" and nn:
                    novo_valor = normalizar_valor_monetario(
                        row_dict.get(colunas_map["valor"])
                    )
                    if novo_valor is not None:
                        seu_numero = str(row_dict.get(colunas_map["doc"], "")).replace(".0", "")
                        if seu_numero.lower() == "nan":
                            seu_numero = ""
                        resultado.titulos_atualizar.append(
                            {
                                "nosso_numero": nn,
                                "seu_numero": seu_numero,
                                "valor_nominal": novo_valor,
                            }
                        )
                        for chave in chaves_nosso_numero(nn):
                            valores_registro[chave] = novo_valor
                elif valores_registro and nn:
                    valor_registrado = buscar_valor_registrado(valores_registro, nn)
                    if valor_registrado is not None:
                        col_montante = colunas_map["montante"]
                        montante_planilha = row_dict.get(col_montante)
                        if valores_monetarios_diferem(montante_planilha, valor_registrado):
                            planilha_fmt = formatar_real(
                                normalizar_valor_monetario(montante_planilha) or 0
                            )
                            registrado_fmt = formatar_real(valor_registrado)
                            resultado.avisos_correcao.append(
                                f"Nosso Nº {nn} — linha {linha_planilha} ({nome_planilha}): "
                                f"valor de face ajustado de {planilha_fmt} para {registrado_fmt}."
                            )
                            row_dict[col_montante] = valor_registrado

                if nn:
                    if cod_instrucao == "47":
                        valor_enviado = normalizar_valor_monetario(
                            row_dict.get(colunas_map["valor"])
                        )
                    else:
                        valor_enviado = normalizar_valor_monetario(
                            row_dict.get(colunas_map["montante"])
                        )
                    if valor_enviado is not None:
                        seu_numero_snap = str(row_dict.get(colunas_map["doc"], "")).replace(
                            ".0", ""
                        )
                        if seu_numero_snap.lower() == "nan":
                            seu_numero_snap = ""
                        resultado.valores_enviados.append(
                            {
                                "nosso_numero": nn,
                                "seu_numero": seu_numero_snap,
                                "valor_nominal": valor_enviado,
                                "cod_instrucao": cod_instrucao,
                            }
                        )

                linhas.append(
                    segmento_p(
                        row_dict,
                        numero_lote,
                        seq_reg,
                        dados_bancarios,
                        colunas_map,
                        cod_instrucao,
                        lote.get("nova_data", ""),
                    )
                )
                seq_reg += 1
                linhas.append(
                    segmento_q(row_dict, numero_lote, seq_reg, colunas_map, cod_instrucao)
                )
                seq_reg += 1
                resultado.total_boletos += 1
            except Exception as exc:
                resultado.erros_linha.append(
                    f"Linha {index + 2} da planilha '{lote.get('nome_arquivo', '')}': {exc}"
                )

        linhas.append(trailer_lote(numero_lote, seq_reg + 1))
        total_registros_arquivo += seq_reg + 1

    linhas.append(trailer_arquivo(len(lotes), total_registros_arquivo + 2))
    resultado.linhas = linhas
    return resultado
