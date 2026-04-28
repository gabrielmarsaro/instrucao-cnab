import streamlit as st
import pandas as pd
from datetime import datetime
import json
import os
import unicodedata
import io

# --- Configurações da Página ---
st.set_page_config(page_title="Gerador CNAB 240 - BB", layout="wide")

# --- Constantes e Bancos de Dados ---
DB_BENEFICIARIOS = "banco_beneficiarios.json"
DB_PAGADORES = "banco_pagadores.json"
CONFIG_FILE = "config_sistema.json"

INSTRUCOES_CNAB = [
    "02 - Pedido de baixa", "04 - Concessão de Abatimento", "05 - Cancelamento de Abatimento",
    "06 - Alteração de Vencimento", "07 - Concessão de Desconto", "08 - Cancelamento de Desconto",
    "09 - Protestar", "10 - Cancela/Sustação da Instrução de protesto", "12 - Alterar Juros de Mora",
    "13 - Dispensar Juros de Mora", "14 - Cobrar Multa", "15 - Dispensar Multa",
    "16 - Ratificar dados da Concessão de Desconto", "19 - Altera Prazo Limite de Recebimento",
    "20 - Dispensar Prazo Limite de Recebimento", "21 - Altera do Número do Título dado pelo Beneficiário",
    "22 - Alteração do Número de Controle do Participante", "23 - Alteração de Nome e Endereço do Pagador",
    "30 - Recusa da Alegação do Sacado", "31 - Alteração de Outros Dados",
    "34 - Altera Data Para Concessão de Desconto", "40 - Alteração de modalidade",
    "45 - Inclusão de Negativação sem protesto", "46 - Exclusão de Negativação sem protesto",
    "47 - Alteração do Valor Nominal do Boleto"
]

def carregar_db(arquivo):
    if os.path.exists(arquivo):
        try:
            with open(arquivo, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return {}
    return {}

def salvar_db(arquivo, dados):
    with open(arquivo, 'w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False, indent=4)

def carregar_nsa():
    config = carregar_db(CONFIG_FILE)
    return config.get("nsa_atual", 1)

def salvar_nsa(novo_nsa):
    config = carregar_db(CONFIG_FILE)
    config["nsa_atual"] = novo_nsa
    salvar_db(CONFIG_FILE, config)

# --- Funções de Formatação (Mantidas do original) ---
def normalizar_id_cliente(valor):
    if pd.isna(valor): return ""
    v = str(valor).replace('.0', '').strip().upper()
    if v.lower() == 'nan' or v == '': return ""
    if v.isdigit(): return str(int(v)) 
    return v

def fmt_num(valor, tamanho):
    if pd.isna(valor): valor = 0
    v_str = str(valor).strip()
    if v_str.endswith('.0'): v_str = v_str[:-2]
    return "".join(filter(str.isdigit, v_str)).zfill(tamanho)[:tamanho]

def fmt_alfa(valor, tamanho):
    if pd.isna(valor) or str(valor).lower() == 'nan': valor = ""
    texto = str(valor)
    texto = ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    texto = "".join(c for c in texto if c.isalnum() or c.isspace())
    return texto.upper().ljust(tamanho, ' ')[:tamanho]

def fmt_date(valor):
    if pd.isna(valor) or str(valor).strip().lower() in ['nan', 'nat', '']: return "00000000"
    v_str = str(valor).strip()
    try:
        if v_str.replace('.0', '').isdigit():
            serial = int(float(v_str))
            return (pd.to_datetime('1899-12-30') + pd.to_timedelta(serial, unit='D')).strftime('%d%m%Y')
        return pd.to_datetime(v_str).strftime('%d%m%Y')
    except: return "00000000"

def fmt_money(valor, tamanho):
    if pd.isna(valor) or str(valor).strip().lower() in ['nan', '']: return "0".zfill(tamanho)
    try: return str(int(round(float(str(valor).replace(',', '.')) * 100))).zfill(tamanho)[:tamanho]
    except: return "0".zfill(tamanho)

def limpar_nosso_numero(valor):
    if pd.isna(valor) or str(valor).lower() == 'nan': return ""
    v_str = str(valor).strip().upper()
    if 'E' in v_str or '+' in v_str:
        try: return str(int(float(v_str)))
        except: pass
    if v_str.endswith('.0'): v_str = v_str[:-2]
    return "".join(filter(str.isdigit, v_str))

def fmt_conta_bb(dados):
    return fmt_num(dados.get('agencia', ''), 5) + fmt_alfa(dados.get('agencia_dv', ''), 1) + fmt_num(dados.get('conta', ''), 12) + fmt_alfa(dados.get('conta_dv', ''), 1) + " "

def fmt_convenio_bb(dados):
    return fmt_num(dados.get('convenio', ''), 9) + "0014" + fmt_num(dados.get('carteira', ''), 2) + fmt_num(dados.get('variacao', ''), 3) + "  "

def header_arquivo(dados, nsa):
    reg = fmt_num("001", 3) + fmt_num("0000", 4) + fmt_num("0", 1) + fmt_alfa("", 9) + fmt_num("2", 1) + fmt_num(dados['cnpj_empresa'], 14) + fmt_convenio_bb(dados) + fmt_conta_bb(dados) + fmt_alfa(dados['nome_empresa'], 30) + fmt_alfa("BANCO DO BRASIL", 30) + fmt_alfa("", 10) + fmt_num("1", 1) + datetime.now().strftime('%d%m%Y') + datetime.now().strftime('%H%M%S') + fmt_num(nsa, 6) + fmt_num("083", 3) + fmt_alfa("", 5) + fmt_alfa("", 20) + fmt_alfa("", 20) + fmt_alfa("", 29)
    return reg

def header_lote(dados, lote, nsa):
    reg = fmt_num("001", 3) + fmt_num(lote, 4) + fmt_num("1", 1) + fmt_alfa("R", 1) + fmt_num("01", 2) + fmt_alfa("", 2) + fmt_num("045", 3) + fmt_alfa("", 1) + fmt_num("2", 1) + fmt_num(dados['cnpj_empresa'], 15) + fmt_convenio_bb(dados) + fmt_conta_bb(dados) + fmt_alfa(dados['nome_empresa'], 30) + fmt_alfa("", 40) + fmt_alfa("", 40) + fmt_num(nsa, 8) + datetime.now().strftime('%d%m%Y') + fmt_num("0", 8) + fmt_alfa("", 33)
    return reg

def trailer_lote(lote, qtd_registros):
    return fmt_num("001", 3) + fmt_num(lote, 4) + fmt_num("5", 1) + fmt_alfa("", 9) + fmt_num(qtd_registros, 6) + fmt_num("0", 6) + fmt_alfa("", 205)

def trailer_arquivo(qtd_lotes, qtd_registros):
    return fmt_num("001", 3) + fmt_num("9999", 4) + fmt_num("9", 1) + fmt_alfa("", 9) + fmt_num(qtd_lotes, 6) + fmt_num(qtd_registros, 6) + fmt_num("0", 6) + fmt_alfa("", 205)

def segmento_p(row, lote, seq, dados, colunas_map, cod_instrucao, nova_data_venc=""):
    reg = fmt_num("001", 3) + fmt_num(lote, 4) + fmt_num("3", 1) + fmt_num(seq, 5) + fmt_alfa("P", 1) + fmt_alfa("", 1) + fmt_num(cod_instrucao, 2) + fmt_conta_bb(dados)
    nn = limpar_nosso_numero(row.get(colunas_map['nn'], ""))
    reg += fmt_alfa(nn, 20) + fmt_num(dados.get('carteira', '17'), 1) + fmt_num("1", 1) + fmt_alfa("2", 1) + fmt_num("2", 1) + fmt_alfa("2", 1)
    seu_numero = str(row.get(colunas_map['doc'], "")).replace(".0", "")
    if seu_numero.lower() == 'nan': seu_numero = ""
    reg += fmt_alfa(seu_numero, 15)
    vencimento = nova_data_venc.replace("/", "") if cod_instrucao == "06" and nova_data_venc else fmt_date(row.get(colunas_map['venc']))

    if cod_instrucao == "47":
        valor_boleto = row.get(colunas_map['valor'])
    else:
        valor_boleto = row.get(colunas_map['montante'])

    reg += vencimento + fmt_money(valor_boleto, 15) + fmt_num("0", 5) + fmt_alfa("", 1) + fmt_num("99", 2) + fmt_alfa("N", 1)
    reg += fmt_date(row.get(colunas_map['venc'])) + fmt_num("3", 1) + fmt_num("0", 8) + fmt_num("0", 15) + fmt_num("0", 1) + fmt_num("0", 8) + fmt_num("0", 15) + fmt_num("0", 15) + fmt_num("0", 15) + fmt_alfa("", 25) + fmt_num("3", 1) + fmt_num("0", 2) + fmt_num("0", 1) + fmt_num("0", 3) + fmt_num("09", 2) + fmt_num("0", 10) + fmt_alfa("", 1)
    return reg

def segmento_q(row, lote, seq, colunas_map, cod_instrucao):
    reg = fmt_num("001", 3) + fmt_num(lote, 4) + fmt_num("3", 1) + fmt_num(seq, 5) + fmt_alfa("Q", 1) + fmt_alfa("", 1) + fmt_num(cod_instrucao, 2)
    cpf_cnpj = str(row.get("CNPJ", "")).strip().replace(".0", "")
    if cpf_cnpj.lower() == 'nan': cpf_cnpj = ""
    tipo_inscricao = "2" if len(cpf_cnpj) > 11 else ("1" if cpf_cnpj else "0")
    reg += fmt_num(tipo_inscricao, 1) + fmt_num(cpf_cnpj, 15)
    nome = str(row.get(colunas_map['nome'], ""))
    reg += fmt_alfa("" if nome.lower() == 'nan' else nome, 40)
    end = str(row.get("Endereco", ""))
    reg += fmt_alfa("" if end.lower() == 'nan' else end, 40)
    bairro = str(row.get("Bairro", ""))
    reg += fmt_alfa("" if bairro.lower() == 'nan' else bairro, 15)
    cep = str(row.get("CEP", "")).replace("-", "").replace(".0", "")
    reg += fmt_num(cep if cep.isdigit() else "0", 8)
    cidade = str(row.get("Cidade", ""))
    reg += fmt_alfa("" if cidade.lower() == 'nan' else cidade, 15)
    uf = str(row.get("UF", ""))
    reg += fmt_alfa("" if uf.lower() == 'nan' else uf, 2)
    reg += fmt_num("0", 1) + fmt_num("0", 15) + fmt_alfa("", 40) + fmt_num("0", 3) + fmt_alfa("", 20) + fmt_alfa("", 8)
    return reg

# --- Interface Streamlit ---
st.title("Gerador de Remessa CNAB 240 - Banco do Brasil")

# Carregar dados
perfis_salvos = carregar_db(DB_BENEFICIARIOS)
db_pagadores = carregar_db(DB_PAGADORES)

# --- 1. Dados da Empresa ---
st.header("1. Dados da Empresa")
nomes_perfis = ["Novo Convênio"] + list(perfis_salvos.keys())
perfil_selecionado = st.selectbox("Selecione um Convênio Salvo:", nomes_perfis)

col1, col2 = st.columns(2)
if perfil_selecionado != "Novo Convênio":
    dados_atuais = perfis_salvos[perfil_selecionado]
    cnpj = col1.text_input("CNPJ", dados_atuais.get("CNPJ", ""))
    razao = col2.text_input("Razão Social", dados_atuais.get("Razão Social", ""))
    agencia = col1.text_input("Agência", dados_atuais.get("Agência", ""))
    dv_agencia = col2.text_input("DV Agência", dados_atuais.get("DV Agência", ""))
    conta = col1.text_input("Conta", dados_atuais.get("Conta", ""))
    dv_conta = col2.text_input("DV Conta", dados_atuais.get("DV Conta", ""))
    convenio = col1.text_input("Convênio", dados_atuais.get("Convênio", ""))
    carteira = col2.text_input("Carteira (Padrão 17)", dados_atuais.get("Carteira (Padrão 17)", "17"))
    variacao = col1.text_input("Variação (Padrão 019)", dados_atuais.get("Variação (Padrão 019)", "019"))

    if st.button("Excluir Convênio"):
        del perfis_salvos[perfil_selecionado]
        salvar_db(DB_BENEFICIARIOS, perfis_salvos)
        st.rerun()
else:
    cnpj = col1.text_input("CNPJ")
    razao = col2.text_input("Razão Social")
    agencia = col1.text_input("Agência")
    dv_agencia = col2.text_input("DV Agência")
    conta = col1.text_input("Conta")
    dv_conta = col2.text_input("DV Conta")
    convenio = col1.text_input("Convênio")
    carteira = col2.text_input("Carteira (Padrão 17)", "17")
    variacao = col1.text_input("Variação (Padrão 019)", "019")

if st.button("Salvar Convênio"):
    if razao and convenio:
        nome_perfil = f"{razao} - Conv: {convenio}"
        perfis_salvos[nome_perfil] = {
            "CNPJ": cnpj, "Razão Social": razao, "Agência": agencia, "DV Agência": dv_agencia,
            "Conta": conta, "DV Conta": dv_conta, "Convênio": convenio, 
            "Carteira (Padrão 17)": carteira, "Variação (Padrão 019)": variacao
        }
        salvar_db(DB_BENEFICIARIOS, perfis_salvos)
        st.success("Convênio salvo com sucesso!")
        st.rerun()
    else:
        st.warning("Preencha Razão Social e Convênio para salvar.")

# --- 2. Bancos de Dados ---
st.header("2. Bancos de Dados")
st.write(f"**Clientes salvos no sistema:** {len(db_pagadores)}")

arquivo_pagadores = st.file_uploader("Importar/Atualizar Planilha de Clientes (Opcional se já salvos)", type=["xlsx", "xls"])
if arquivo_pagadores:
    if st.button("Processar e Salvar Clientes"):
        df_pagadores_raw = pd.read_excel(arquivo_pagadores, dtype=str)
        colunas_pag_lower = [str(c).strip().lower() for c in df_pagadores_raw.columns]
        df_pagadores_raw.columns = colunas_pag_lower
        col_cliente_pag = next((c for c in colunas_pag_lower if 'cliente' in c), None)

        if col_cliente_pag:
            novos = 0
            for _, row in df_pagadores_raw.iterrows():
                cid = normalizar_id_cliente(row.get(col_cliente_pag))
                if cid:
                    db_pagadores[cid] = {
                        "CNPJ": "".join(filter(str.isdigit, str(row.get(next((c for c in colunas_pag_lower if 'cnpj' in c or 'cpf' in c), 'cnpj'), "")))),
                        "Nome": str(row.get(next((c for c in colunas_pag_lower if 'nome' in c or 'raz' in c or 'sacado' in c), 'nome'), "")),
                        "Endereco": str(row.get(next((c for c in colunas_pag_lower if 'endere' in c), 'endereco'), "")),
                        "Bairro": str(row.get(next((c for c in colunas_pag_lower if 'bairro' in c), 'bairro'), "")),
                        "CEP": "".join(filter(str.isdigit, str(row.get(next((c for c in colunas_pag_lower if 'cep' in c), 'cep'), "")))),
                        "Cidade": str(row.get(next((c for c in colunas_pag_lower if 'cidade' in c), 'cidade'), "")),
                        "UF": str(row.get(next((c for c in colunas_pag_lower if 'uf' in c or 'estado' in c), 'uf'), "")).upper()
                    }
                    novos += 1
            salvar_db(DB_PAGADORES, db_pagadores)
            st.success(f"{novos} clientes atualizados/salvos!")
            st.rerun()
        else:
            st.error("Coluna 'cliente' não encontrada.")

arquivo_boletos = st.file_uploader("Selecione a Planilha de Boletos (Obrigatório)", type=["xlsx", "xls"])

# --- 3. Instrução ---
st.header("3. Instrução")
instrucao_selecionada = st.selectbox("Selecione a Instrução:", INSTRUCOES_CNAB, index=24)
nova_data_str = ""
if instrucao_selecionada.startswith("06"):
    nova_data_str = st.text_input("Nova Data Vencimento (DD/MM/AAAA):")

# --- Geração ---
if st.button("GERAR ARQUIVO CNAB", type="primary"):
    if not db_pagadores:
        st.error("Você precisa importar a planilha de clientes pelo menos uma vez.")
    elif not arquivo_boletos:
        st.error("Selecione a planilha de boletos.")
    elif not cnpj or not agencia:
        st.error("Preencha os dados da empresa.")
    elif instrucao_selecionada.startswith("06") and (len(nova_data_str) != 10 or nova_data_str.count('/') != 2):
        st.error("Para alterar o vencimento, digite a data no formato DD/MM/AAAA.")
    else:
        dados_bancarios = {
            "cnpj_empresa": cnpj, "nome_empresa": razao, "agencia": agencia, "agencia_dv": dv_agencia,
            "conta": conta, "conta_dv": dv_conta, "convenio": convenio, "carteira": carteira, "variacao": variacao
        }
        cod_instrucao = instrucao_selecionada.split(" - ")[0].strip()

        try:
            df_boletos = pd.read_excel(arquivo_boletos)
            colunas_bol_lower = [str(c).strip().lower() for c in df_boletos.columns]
            df_boletos.columns = colunas_bol_lower

            colunas_map = {
                'nn': next((c for c in colunas_bol_lower if 'nosso numero' in c or 'nosso_numero' in c), 'nosso numero'),
                'doc': next((c for c in colunas_bol_lower if 'documento' in c), 'nº documento'),
                'venc': next((c for c in colunas_bol_lower if 'vencimento' in c), 'vencimento líquido'),
                'valor': next((c for c in colunas_bol_lower if 'corrigido' in c or 'novo valor' in c), 'total corrigido'),
                'montante': next((c for c in colunas_bol_lower if 'montante' in c), 'montante'),
                'cliente': next((c for c in colunas_bol_lower if 'cliente' in c), 'cliente'),
                'nome': next((c for c in colunas_bol_lower if 'nome' in c), 'nome 1')
            }

            df_boletos = df_boletos.dropna(subset=[colunas_map['nn']])
            df_boletos['Cliente_ID_Join'] = df_boletos[colunas_map['cliente']].apply(normalizar_id_cliente)

            df_pag_df = pd.DataFrame.from_dict(db_pagadores, orient='index')
            df_pag_df.index.name = 'Cliente_ID_Join'

            df_completo = pd.merge(df_boletos, df_pag_df, on='Cliente_ID_Join', how='left')

            nsa = carregar_nsa()

            # Geração em memória
            linhas = []
            linhas.append(header_arquivo(dados_bancarios, nsa))
            numero_lote = 1
            linhas.append(header_lote(dados_bancarios, numero_lote, nsa))

            seq_reg = 1
            for index, row in df_completo.iterrows():
                linhas.append(segmento_p(row, numero_lote, seq_reg, dados_bancarios, colunas_map, cod_instrucao, nova_data_str))
                seq_reg += 1
                linhas.append(segmento_q(row, numero_lote, seq_reg, colunas_map, cod_instrucao))
                seq_reg += 1

            linhas.append(trailer_lote(numero_lote, seq_reg + 1))
            linhas.append(trailer_arquivo(1, seq_reg + 3))

            cnab_bytes = io.BytesIO()
            for linha in linhas:
                linha_limpa = ''.join(c for c in unicodedata.normalize('NFD', linha) if unicodedata.category(c) != 'Mn')
                linha_final = linha_limpa.ljust(240, " ")[:240] + "\r\n"
                bytes_linha = linha_final.encode('ascii', errors='replace').replace(b'?', b' ')
                cnab_bytes.write(bytes_linha)

            salvar_nsa(nsa + 1)

            st.success(f"Arquivo gerado com sucesso! NSA: {nsa}")
            st.download_button(
                label="📥 Baixar Arquivo CNAB",
                data=cnab_bytes.getvalue(),
                file_name=f"remessa_bb_nsa{nsa}.rem",
                mime="text/plain"
            )

        except Exception as e:
            st.error(f"Falha ao processar: {str(e)}")