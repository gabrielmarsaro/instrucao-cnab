"""Validação de planilhas de boletos."""

from __future__ import annotations

import re

import pandas as pd

from dataclasses import dataclass, field

from config import COLUNAS_CLIENTES, COLUNAS_OBRIGATORIAS


def limpar_nosso_numero(valor):
    if pd.isna(valor) or str(valor).lower() == "nan":
        return ""
    v_str = str(valor).strip().upper()
    if "E" in v_str or "+" in v_str:
        try:
            return str(int(float(v_str)))
        except (ValueError, TypeError):
            pass
    if v_str.endswith(".0"):
        v_str = v_str[:-2]
    return "".join(filter(str.isdigit, v_str))


def mapear_colunas_planilha(df: pd.DataFrame) -> dict[str, str]:
    colunas_lower = [str(c).strip().lower() for c in df.columns]
    df.columns = colunas_lower

    def encontrar(sinonimos, fallback):
        for col in colunas_lower:
            for termo in sinonimos:
                if termo in col:
                    return col
        return fallback

    def encontrar_montante() -> str:
        for col in colunas_lower:
            if "montante" in col:
                return col
        for col in colunas_lower:
            if (
                "valor" in col
                and "corrigido" not in col
                and "novo" not in col
                and "mín" not in col
                and "min" not in col
                and "máx" not in col
                and "max" not in col
            ):
                return col
        return encontrar(COLUNAS_OBRIGATORIAS["montante"], "montante")

    return {
        "nn": encontrar(COLUNAS_OBRIGATORIAS["nn"], "nosso numero"),
        "doc": encontrar(COLUNAS_OBRIGATORIAS["doc"], "nº documento"),
        "venc": encontrar(COLUNAS_OBRIGATORIAS["venc"], "vencimento líquido"),
        "valor": next(
            (c for c in colunas_lower if "corrigido" in c or "novo valor" in c),
            "total corrigido",
        ),
        "montante": encontrar_montante(),
        "cliente": encontrar(COLUNAS_OBRIGATORIAS["cliente"], "cliente"),
    }


def _coluna_existe(df: pd.DataFrame, coluna: str) -> bool:
    return coluna in df.columns


def validar_data_ddmmyyyy(data_str: str) -> bool:
    if not data_str:
        return False
    limpa = data_str.replace("/", "").strip()
    if len(limpa) != 8 or not limpa.isdigit():
        return False
    try:
        pd.to_datetime(limpa, format="%d%m%Y")
        return True
    except (ValueError, TypeError):
        return False


def validar_planilha(
    df: pd.DataFrame,
    instrucao: str,
    nova_data: str = "",
    df_clientes: pd.DataFrame | None = None,
) -> tuple[bool, list[str], list[str]]:
    """
    Retorna (valido, erros, avisos).
    Erros bloqueiam a geração; avisos são informativos.
    """
    erros: list[str] = []
    avisos: list[str] = []

    if df.empty:
        erros.append("A planilha está vazia. Inclua ao menos um boleto.")
        return False, erros, avisos

    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    colunas_map = mapear_colunas_planilha(df)
    cod_instrucao = instrucao.split(" - ")[0].strip()

    obrigatorias = ["nn", "doc", "venc", "montante", "cliente"]
    nomes_amigaveis = {
        "nn": "Nosso Número",
        "doc": "Nº Documento",
        "venc": "Vencimento",
        "montante": "Montante/Valor",
        "cliente": "Cliente",
    }
    for chave in obrigatorias:
        col = colunas_map[chave]
        if not _coluna_existe(df, col):
            erros.append(
                f"Coluna obrigatória não encontrada: {nomes_amigaveis[chave]}. "
                f"Verifique os cabeçalhos da planilha."
            )

    if erros:
        return False, erros, avisos

    for idx, row in df.iterrows():
        linha = idx + 2
        nn = limpar_nosso_numero(row.get(colunas_map["nn"], ""))
        if not nn:
            erros.append(f"Linha {linha}: Nosso Número está vazio.")

        montante = row.get(colunas_map["montante"], "")
        if pd.isna(montante) or str(montante).strip().lower() in ["", "nan"]:
            erros.append(f"Linha {linha}: Montante/Valor está vazio.")

    if cod_instrucao == "06":
        if not nova_data:
            erros.append("Instrução 06 exige informar a Nova Data de Vencimento (DD/MM/AAAA).")
        elif not validar_data_ddmmyyyy(nova_data):
            erros.append(
                "Nova Data de Vencimento inválida. Use o formato DD/MM/AAAA (ex: 15/07/2026)."
            )

    if cod_instrucao == "47":
        col_valor = colunas_map["valor"]
        if not _coluna_existe(df, col_valor):
            erros.append(
                "Instrução 47 exige coluna de novo valor (ex: 'Total Corrigido' ou 'Novo Valor')."
            )
        else:
            vazios = df[col_valor].isna() | (df[col_valor].astype(str).str.strip() == "")
            if vazios.any():
                linhas = [str(i + 2) for i in df.index[vazios]]
                erros.append(
                    f"Instrução 47: valor nominal vazio nas linhas {', '.join(linhas[:5])}"
                    + ("..." if len(linhas) > 5 else "")
                )

    if df_clientes is not None and not df_clientes.empty and "id_cliente_planilha" in df_clientes.columns:
        codigos_cadastrados = set(df_clientes["id_cliente_planilha"].astype(str))
        for idx, row in df.iterrows():
            cod = str(row.get(colunas_map["cliente"], "")).replace(".0", "").strip()
            if cod and cod not in codigos_cadastrados:
                avisos.append(
                    f"Linha {idx + 2}: cliente '{cod}' não cadastrado — segmento Q pode ficar incompleto."
                )

    return len(erros) == 0, erros, avisos


def normalizar_documento(valor) -> str:
    if pd.isna(valor) or str(valor).strip().lower() in ["", "nan"]:
        return ""
    texto = str(valor).strip().replace(".0", "")
    return re.sub(r"\D", "", texto)


def validar_cnpj_cpf(valor: str) -> bool:
    digits = normalizar_documento(valor)
    return len(digits) in (11, 14)


def _encontrar_coluna(colunas_lower: list[str], sinonimos: list[str], fallback: str) -> str:
    for col in colunas_lower:
        for termo in sinonimos:
            if termo in col:
                return col
    return fallback


def mapear_colunas_clientes(df: pd.DataFrame) -> dict[str, str]:
    colunas_lower = [str(c).strip().lower() for c in df.columns]
    return {
        chave: _encontrar_coluna(colunas_lower, termos, chave)
        for chave, termos in COLUNAS_CLIENTES.items()
    }


def _valor_celula(row, coluna: str) -> str:
    if coluna not in row.index:
        return ""
    valor = row.get(coluna, "")
    if pd.isna(valor) or str(valor).strip().lower() == "nan":
        return ""
    texto = str(valor).strip()
    if texto.endswith(".0") and texto.replace(".0", "").isdigit():
        texto = texto[:-2]
    return texto


@dataclass
class ResultadoImportacaoClientes:
    registros: list[dict] = field(default_factory=list)
    ignorados_cnpj: list[str] = field(default_factory=list)
    ignorados_planilha: list[str] = field(default_factory=list)
    erros: list[str] = field(default_factory=list)


def preparar_importacao_clientes(
    df: pd.DataFrame,
    df_existentes: pd.DataFrame | None = None,
) -> ResultadoImportacaoClientes:
    resultado = ResultadoImportacaoClientes()

    if df.empty:
        resultado.erros.append("A planilha está vazia.")
        return resultado

    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    colunas = mapear_colunas_clientes(df)

    col_codigo = colunas["codigo"]
    col_nome = colunas["nome"]
    if col_codigo not in df.columns and col_nome not in df.columns:
        resultado.erros.append(
            "Não encontrei colunas de Código/Cliente ou Nome. "
            "Verifique os cabeçalhos da planilha."
        )
        return resultado

    cnpjs_existentes: set[str] = set()
    if df_existentes is not None and not df_existentes.empty and "cnpj_cpf" in df_existentes.columns:
        for valor in df_existentes["cnpj_cpf"]:
            doc = normalizar_documento(valor)
            if doc:
                cnpjs_existentes.add(doc)

    cnpjs_na_importacao: set[str] = set()

    for idx, row in df.iterrows():
        linha = idx + 2
        codigo = _valor_celula(row, col_codigo) if col_codigo in df.columns else ""
        nome = _valor_celula(row, col_nome) if col_nome in df.columns else ""
        cnpj_raw = _valor_celula(row, colunas["cnpj"]) if colunas["cnpj"] in df.columns else ""
        cnpj_norm = normalizar_documento(cnpj_raw)

        if not codigo and not nome:
            continue

        if not codigo:
            resultado.erros.append(f"Linha {linha}: Código do cliente vazio.")
            continue
        if not nome:
            resultado.erros.append(f"Linha {linha}: Nome vazio.")
            continue

        if cnpj_norm and not validar_cnpj_cpf(cnpj_norm):
            resultado.erros.append(f"Linha {linha}: CNPJ/CPF inválido ({cnpj_raw}).")
            continue

        if cnpj_norm:
            if cnpj_norm in cnpjs_existentes:
                resultado.ignorados_cnpj.append(
                    f"Linha {linha}: CNPJ {cnpj_raw} já cadastrado — ignorado."
                )
                continue
            if cnpj_norm in cnpjs_na_importacao:
                resultado.ignorados_planilha.append(
                    f"Linha {linha}: CNPJ {cnpj_raw} repetido na planilha — ignorado."
                )
                continue
            cnpjs_na_importacao.add(cnpj_norm)

        uf = _valor_celula(row, colunas["uf"]).upper()[:2]
        resultado.registros.append(
            {
                "id_cliente_planilha": codigo,
                "cnpj_cpf": cnpj_raw,
                "nome": nome,
                "endereco": _valor_celula(row, colunas["endereco"]),
                "bairro": _valor_celula(row, colunas["bairro"]),
                "cep": _valor_celula(row, colunas["cep"]),
                "cidade": _valor_celula(row, colunas["cidade"]),
                "uf": uf,
            }
        )

    if not resultado.registros and not resultado.erros and not resultado.ignorados_cnpj:
        resultado.erros.append("Nenhum cliente válido encontrado na planilha.")

    return resultado
