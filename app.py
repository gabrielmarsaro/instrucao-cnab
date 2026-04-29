import streamlit as st
import pandas as pd
from datetime import datetime
import unicodedata
import io
from supabase import create_client, Client

# --- Configurações da Página ---
st.set_page_config(page_title="Gerador CNAB 240 - BB", layout="wide")

# --- Conexão com Supabase ---
@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

try:
    supabase: Client = init_connection()
except Exception as e:
    st.error("Erro ao conectar com o banco de dados. Verifique os Secrets no Streamlit.")
    st.stop()

# --- Variáveis de Sessão ---
if 'user' not in st.session_state:
    st.session_state.user = None
if 'lotes' not in st.session_state:
    st.session_state.lotes = []

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

# --- Funções de Formatação CNAB ---
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
    return fmt_num(dados.get('agencia', ''), 5) + fmt_alfa(dados.get('dv_agencia', ''), 1) + fmt_num(dados.get('conta', ''), 12) + fmt_alfa(dados.get('dv_conta', ''), 1) + " "

def fmt_convenio_bb(dados):
    return fmt_num(dados.get('convenio', ''), 9) + "0014" + fmt_num(dados.get('carteira', ''), 2) + fmt_num(dados.get('variacao', ''), 3) + "  "

def header_arquivo(dados, nsa):
    reg = fmt_num("001", 3) + fmt_num("0000", 4) + fmt_num("0", 1) + fmt_alfa("", 9) + fmt_num("2", 1) + fmt_num(dados['cnpj'], 14) + fmt_convenio_bb(dados) + fmt_conta_bb(dados) + fmt_alfa(dados['razao_social'], 30) + fmt_alfa("BANCO DO BRASIL", 30) + fmt_alfa("", 10) + fmt_num("1", 1) + datetime.now().strftime('%d%m%Y') + datetime.now().strftime('%H%M%S') + fmt_num(nsa, 6) + fmt_num("083", 3) + fmt_alfa("", 5) + fmt_alfa("", 20) + fmt_alfa("", 20) + fmt_alfa("", 29)
    return reg

def header_lote(dados, lote, nsa):
    reg = fmt_num("001", 3) + fmt_num(lote, 4) + fmt_num("1", 1) + fmt_alfa("R", 1) + fmt_num("01", 2) + fmt_alfa("", 2) + fmt_num("045", 3) + fmt_alfa("", 1) + fmt_num("2", 1) + fmt_num(dados['cnpj'], 15) + fmt_convenio_bb(dados) + fmt_conta_bb(dados) + fmt_alfa(dados['razao_social'], 30) + fmt_alfa("", 40) + fmt_alfa("", 40) + fmt_num(nsa, 8) + datetime.now().strftime('%d%m%Y') + fmt_num("0", 8) + fmt_alfa("", 33)
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
    valor_boleto = row.get(colunas_map['valor']) if cod_instrucao == "47" else row.get(colunas_map['montante'])
    reg += vencimento + fmt_money(valor_boleto, 15) + fmt_num("0", 5) + fmt_alfa("", 1) + fmt_num("99", 2) + fmt_alfa("N", 1)
    reg += fmt_date(row.get(colunas_map['venc'])) + fmt_num("3", 1) + fmt_num("0", 8) + fmt_num("0", 15) + fmt_num("0", 1) + fmt_num("0", 8) + fmt_num("0", 15) + fmt_num("0", 15) + fmt_num("0", 15) + fmt_alfa("", 25) + fmt_num("3", 1) + fmt_num("0", 2) + fmt_num("0", 1) + fmt_num("0", 3) + fmt_num("09", 2) + fmt_num("0", 10) + fmt_alfa("", 1)
    return reg

def segmento_q(row, lote, seq, colunas_map, cod_instrucao):
    reg = fmt_num("001", 3) + fmt_num(lote, 4) + fmt_num("3", 1) + fmt_num(seq, 5) + fmt_alfa("Q", 1) + fmt_alfa("", 1) + fmt_num(cod_instrucao, 2)
    cpf_cnpj = str(row.get("cnpj_cpf", "")).strip().replace(".0", "")
    if cpf_cnpj.lower() == 'nan': cpf_cnpj = ""
    tipo_inscricao = "2" if len(cpf_cnpj) > 11 else ("1" if cpf_cnpj else "0")
    reg += fmt_num(tipo_inscricao, 1) + fmt_num(cpf_cnpj, 15)
    nome = str(row.get("nome", ""))
    reg += fmt_alfa("" if nome.lower() == 'nan' else nome, 40)
    end = str(row.get("endereco", ""))
    reg += fmt_alfa("" if end.lower() == 'nan' else end, 40)
    bairro = str(row.get("bairro", ""))
    reg += fmt_alfa("" if bairro.lower() == 'nan' else bairro, 15)
    cep = str(row.get("cep", "")).replace("-", "").replace(".0", "")
    reg += fmt_num(cep if cep.isdigit() else "0", 8)
    cidade = str(row.get("cidade", ""))
    reg += fmt_alfa("" if cidade.lower() == 'nan' else cidade, 15)
    uf = str(row.get("uf", ""))
    reg += fmt_alfa("" if uf.lower() == 'nan' else uf, 2)
    reg += fmt_num("0", 1) + fmt_num("0", 15) + fmt_alfa("", 40) + fmt_num("0", 3) + fmt_alfa("", 20) + fmt_alfa("", 8)
    return reg

# --- Funções de Autenticação ---
# --- Funções de Autenticação ---
def login(email, password):
    try:
        res = supabase.auth.sign_in_with_password({"email": email, "password": password})
        st.session_state.user = res.user
        st.success("Login realizado com sucesso!")
        st.rerun()
    except Exception as e:
        st.error("Erro no login. Verifique suas credenciais.")

def signup(email, password):
    try:
        res = supabase.auth.sign_up({"email": email, "password": password})
        st.success("Conta criada! Você já pode fazer login.")
    except Exception as e:
        st.error(f"Erro ao criar conta: {e}")

def logout():
    supabase.auth.sign_out()
    st.session_state.user = None
    st.session_state.lotes = []
    st.rerun()

# --- Tela de Login ---
if not st.session_state.user:
    st.title("🔐 Acesso ao Sistema CNAB")
    tab_login, tab_cadastro = st.tabs(["Login", "Criar Conta"])

    with tab_login:
        email_login = st.text_input("E-mail", key="log_email")
        senha_login = st.text_input("Senha", type="password", key="log_senha")
        if st.button("Entrar"):
            login(email_login, senha_login)

    with tab_cadastro:
        email_cad = st.text_input("E-mail", key="cad_email")
        senha_cad = st.text_input("Senha (mín. 6 caracteres)", type="password", key="cad_senha")
        if st.button("Cadastrar"):
            signup(email_cad, senha_cad)
    st.stop()
# --- Sistema Principal (Logado) ---
st.sidebar.write(f"👤 Logado como: {st.session_state.user.email}")
if st.sidebar.button("Sair"):
    logout()

st.title("🏦 Gerador de Remessa CNAB 240")

aba_gerador, aba_clientes, aba_convenios = st.tabs(["Gerar Remessa", "Meus Clientes", "Meus Convênios"])

# --- ABA: MEUS CLIENTES ---
# --- ABA: MEUS CLIENTES ---
with aba_clientes:
    st.header("Gestão de Clientes")

    col_manual, col_planilha = st.columns(2)

    with col_manual:
        with st.expander("➕ Cadastrar Manualmente"):
            with st.form("form_novo_cliente"):
                cli_cnpj_cpf = st.text_input("CNPJ/CPF (Apenas números)")
                cli_nome = st.text_input("Nome / Razão Social")
                cli_end = st.text_input("Endereço")
                cli_bairro = st.text_input("Bairro")
                cli_cep = st.text_input("CEP (Apenas números)")
                cli_cidade = st.text_input("Cidade")
                cli_uf = st.text_input("UF")

                if st.form_submit_button("Salvar Cliente"):
                    novo_cliente = {
                        "user_id": st.session_state.user.id,
                        "cnpj_cpf": cli_cnpj_cpf,
                        "nome": cli_nome,
                        "endereco": cli_end,
                        "bairro": cli_bairro,
                        "cep": cli_cep,
                        "cidade": cli_cidade,
                        "uf": cli_uf
                    }
                    try:
                        supabase.table("clientes").insert(novo_cliente).execute()
                        st.success("Cliente cadastrado com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar: {e}")

    with col_planilha:
        with st.expander("📂 Importar via Planilha (Excel)"):
            st.write("A planilha deve conter as colunas: **cnpj_cpf, nome, endereco, bairro, cep, cidade, uf**")
            arquivo_importacao = st.file_uploader("Selecione a planilha de clientes", type=["xlsx", "xls"])

            if arquivo_importacao and st.button("Processar Importação"):
                try:
                    df_import = pd.read_excel(arquivo_importacao)

                    # Padroniza o nome das colunas para minúsculo para evitar erros de digitação
                    df_import.columns = [str(c).strip().lower() for c in df_import.columns]

                    clientes_para_inserir = []
                    for index, row in df_import.iterrows():
                        clientes_para_inserir.append({
                            "user_id": st.session_state.user.id,
                            "cnpj_cpf": str(row.get("cnpj_cpf", "")).replace(".0", ""),
                            "nome": str(row.get("nome", "")),
                            "endereco": str(row.get("endereco", "")),
                            "bairro": str(row.get("bairro", "")),
                            "cep": str(row.get("cep", "")).replace(".0", ""),
                            "cidade": str(row.get("cidade", "")),
                            "uf": str(row.get("uf", ""))
                        })

                    if clientes_para_inserir:
                        # O Supabase permite inserir uma lista inteira de uma vez
                        supabase.table("clientes").insert(clientes_para_inserir).execute()
                        st.success(f"{len(clientes_para_inserir)} clientes importados com sucesso!")
                        st.rerun()
                except Exception as e:
                    st.error(f"Erro na importação. Verifique os nomes das colunas. Detalhe: {e}")

    st.divider()
    st.write("### Clientes Cadastrados")
    resposta_cli = supabase.table("clientes").select("*").eq("user_id", st.session_state.user.id).execute()
    df_clientes = pd.DataFrame(resposta_cli.data)
    if not df_clientes.empty:
        st.dataframe(df_clientes.drop(columns=['id', 'user_id', 'created_at', 'id_cliente_planilha']), use_container_width=True)
    else:
        st.info("Nenhum cliente cadastrado ainda.")
        
# --- ABA: MEUS CONVÊNIOS ---
with aba_convenios:
    st.header("Gestão de Convênios")

    with st.expander("➕ Cadastrar Novo Convênio"):
        with st.form("form_novo_convenio"):
            col1, col2 = st.columns(2)
            conv_cnpj = col1.text_input("CNPJ da Empresa (Apenas números)")
            conv_razao = col2.text_input("Razão Social da Empresa")

            col3, col4, col5, col6 = st.columns(4)
            conv_ag = col3.text_input("Agência (Sem DV)")
            conv_ag_dv = col4.text_input("DV Agência")
            conv_conta = col5.text_input("Conta (Sem DV)")
            conv_conta_dv = col6.text_input("DV Conta")

            col7, col8, col9 = st.columns(3)
            conv_num = col7.text_input("Número do Convênio (7 dígitos)")
            conv_cart = col8.text_input("Carteira (Ex: 17)")
            conv_var = col9.text_input("Variação (Ex: 019)")

            if st.form_submit_button("Salvar Convênio"):
                novo_convenio = {
                    "user_id": st.session_state.user.id,
                    "cnpj": conv_cnpj,
                    "razao_social": conv_razao,
                    "agencia": conv_ag,
                    "dv_agencia": conv_ag_dv,
                    "conta": conv_conta,
                    "dv_conta": conv_conta_dv,
                    "convenio": conv_num,
                    "carteira": conv_cart,
                    "variacao": conv_var
                }
                try:
                    supabase.table("convenios").insert(novo_convenio).execute()
                    st.success("Convênio cadastrado com sucesso!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao salvar: {e}")

    st.write("### Convênios Cadastrados")
    resposta_conv = supabase.table("convenios").select("*").eq("user_id", st.session_state.user.id).execute()
    df_convenios = pd.DataFrame(resposta_conv.data)
    if not df_convenios.empty:
        st.dataframe(df_convenios.drop(columns=['id', 'user_id', 'created_at']), use_container_width=True)
    else:
        st.info("Nenhum convênio cadastrado ainda.")

# --- ABA: GERADOR ---
with aba_gerador:
    col1, col2 = st.columns(2)

    # Selecionar Convênio
    opcoes_convenios = df_convenios['razao_social'].tolist() if not df_convenios.empty else ["Nenhum convênio cadastrado"]
    convenio_selecionado = col1.selectbox("Selecione o Convênio", opcoes_convenios)

    # Upload de Boletos
    arquivo_boletos = col2.file_uploader("Planilha de Boletos", type=["xlsx", "xls"])

    st.divider()

    # Montar Lotes
    st.subheader("📦 Montar Lotes de Instrução")
    instrucao = st.selectbox("Instrução para este lote:", INSTRUCOES_CNAB)
    nova_data_str = ""
    if instrucao.startswith("06"):
        nova_data_str = st.text_input("Nova Data Vencimento (DD/MM/AAAA):")

    if st.button("➕ Adicionar ao Lote"):
        if arquivo_boletos and not df_convenios.empty:
            df_lote = pd.read_excel(arquivo_boletos)
            st.session_state.lotes.append({
                "instrucao": instrucao,
                "nova_data": nova_data_str,
                "df": df_lote,
                "nome_arquivo": arquivo_boletos.name
            })
            st.success(f"Lote adicionado! ({len(df_lote)} boletos)")
        else:
            st.warning("Anexe a planilha e certifique-se de ter um convênio cadastrado.")

    # Mostrar Lotes e Gerar
    if st.session_state.lotes:
        st.write("### Carrinho de Lotes")
        for i, lote in enumerate(st.session_state.lotes):
            st.write(f"**Lote {i+1}:** {lote['instrucao']} - Arquivo: {lote['nome_arquivo']} ({len(lote['df'])} boletos)")

                if st.button("🚀 GERAR ARQUIVO REMESSA FINAL", type="primary"):
            try:
                # Pega os dados do convênio selecionado
                dados_bancarios = df_convenios[df_convenios['razao_social'] == convenio_selecionado].iloc[0].to_dict()
                nsa = 1 # Em um sistema real, buscaríamos o último NSA do banco

                # 1. BUSCAR CLIENTES DO BANCO DE DADOS
                resposta_cli = supabase.table("clientes").select("*").eq("user_id", st.session_state.user.id).execute()
                df_clientes_bd = pd.DataFrame(resposta_cli.data)

                linhas = []
                linhas.append(header_arquivo(dados_bancarios, nsa))

                total_registros_arquivo = 0

                # Processa cada lote do carrinho
                for i, lote in enumerate(st.session_state.lotes):
                    numero_lote = i + 1
                    linhas.append(header_lote(dados_bancarios, numero_lote, nsa))

                    df_boletos = lote['df']
                    cod_instrucao = lote['instrucao'].split(" - ")[0].strip()

                    # Mapeamento de colunas
                    colunas_bol_lower = [str(c).strip().lower() for c in df_boletos.columns]
                    df_boletos.columns = colunas_bol_lower
                    colunas_map = {
                        'nn': next((c for c in colunas_bol_lower if 'nosso numero' in c or 'nosso_numero' in c), 'nosso numero'),
                        'doc': next((c for c in colunas_bol_lower if 'documento' in c), 'nº documento'),
                        'venc': next((c for c in colunas_bol_lower if 'vencimento' in c), 'vencimento líquido'),
                        'valor': next((c for c in colunas_bol_lower if 'corrigido' in c or 'novo valor' in c), 'total corrigido'),
                        'montante': next((c for c in colunas_bol_lower if 'montante' in c), 'montante'),
                        'cliente': next((c for c in colunas_bol_lower if 'cliente' in c or 'nome' in c), 'cliente')
                    }

                    seq_reg = 1
                    for index, row in df_boletos.iterrows():
                        dados_linha = row.to_dict()

                        # 2. CRUZAR DADOS DA PLANILHA COM O BANCO DE DADOS
                        if not df_clientes_bd.empty and colunas_map['cliente'] in dados_linha:
                            nome_planilha = str(dados_linha[colunas_map['cliente']]).strip().upper()

                            # Procura o cliente no banco pelo nome (ignorando maiúsculas/minúsculas)
                            cli_match = df_clientes_bd[df_clientes_bd['nome'].str.upper() == nome_planilha]

                            if not cli_match.empty:
                                cli_dados = cli_match.iloc[0]
                                # Preenche os dados faltantes com o que está no banco
                                dados_linha['cnpj_cpf'] = cli_dados.get('cnpj_cpf', '')
                                dados_linha['nome'] = cli_dados.get('nome', '')
                                dados_linha['endereco'] = cli_dados.get('endereco', '')
                                dados_linha['bairro'] = cli_dados.get('bairro', '')
                                dados_linha['cep'] = cli_dados.get('cep', '')
                                dados_linha['cidade'] = cli_dados.get('cidade', '')
                                dados_linha['uf'] = cli_dados.get('uf', '')

                        # Gera as linhas do CNAB com os dados completos
                        linhas.append(segmento_p(dados_linha, numero_lote, seq_reg, dados_bancarios, colunas_map, cod_instrucao, lote['nova_data']))
                        seq_reg += 1
                        linhas.append(segmento_q(dados_linha, numero_lote, seq_reg, colunas_map, cod_instrucao))
                        seq_reg += 1

                    linhas.append(trailer_lote(numero_lote, seq_reg + 1))
                    total_registros_arquivo += (seq_reg + 1)

                linhas.append(trailer_arquivo(len(st.session_state.lotes), total_registros_arquivo + 2))

                # Gerar arquivo para download
                cnab_bytes = io.BytesIO()
                for linha in linhas:
                    linha_limpa = ''.join(c for c in unicodedata.normalize('NFD', linha) if unicodedata.category(c) != 'Mn')
                    linha_final = linha_limpa.ljust(240, " ")[:240] + "\r\n"
                    bytes_linha = linha_final.encode('ascii', errors='replace').replace(b'?', b' ')
                    cnab_bytes.write(bytes_linha)

                st.success("Arquivo gerado com sucesso!")
                st.download_button(
                    label="📥 Baixar Arquivo CNAB",
                    data=cnab_bytes.getvalue(),
                    file_name=f"remessa_bb_multiplos_lotes.rem",
                    mime="text/plain"
                )

                # Limpa o carrinho após gerar
                st.session_state.lotes = []

            except Exception as e:
                st.error(f"Erro ao gerar arquivo: {e}")
