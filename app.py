import streamlit as st
import pandas as pd
from supabase import create_client, Client
import io
import unicodedata
from datetime import datetime

# ==========================================
# CONFIGURAÇÃO DA PÁGINA
# ==========================================
st.set_page_config(page_title="Gerador CNAB 240", layout="wide")

# ==========================================
# CONEXÃO SUPABASE
# ==========================================
@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

try:
    supabase: Client = init_connection()
except Exception as e:
    st.error(f"Erro ao conectar com o banco de dados: {e}")

# ==========================================
# ESTADO DA SESSÃO
# ==========================================
if 'user' not in st.session_state:
    st.session_state.user = None
if 'lotes' not in st.session_state:
    st.session_state.lotes = []
# ==========================================
# FUNÇÕES AUXILIARES DE FORMATAÇÃO
# ==========================================
def fmt_num(valor, tamanho):
    """Formata números com zeros à esquerda"""
    tamanho = int(tamanho) # <--- CORREÇÃO: Força a ser número
    v = str(valor).replace(".0", "").strip()
    if v.lower() == 'nan' or v == 'None': v = ""
    v = ''.join(filter(str.isdigit, v))
    return v.zfill(tamanho)[:tamanho]

def fmt_alfa(valor, tamanho):
    """Formata texto com espaços à direita e remove acentos"""
    tamanho = int(tamanho) # <--- CORREÇÃO: Força a ser número
    v = str(valor).strip()
    if v.lower() == 'nan' or v == 'None': v = ""
    v = ''.join(c for c in unicodedata.normalize('NFD', v) if unicodedata.category(c) != 'Mn')
    return v.upper().ljust(tamanho)[:tamanho]

def fmt_money(valor, tamanho):
    """Formata valor financeiro (remove vírgula e preenche com zeros)"""
    tamanho = int(tamanho) # <--- CORREÇÃO: Força a ser número
    if pd.isna(valor) or str(valor).strip() == "" or str(valor).lower() == 'nan':
        return "0".zfill(tamanho)
    try:
        v = int(round(float(valor) * 100))
        return str(v).zfill(tamanho)[:tamanho]
    except:
        return "0".zfill(tamanho)

def fmt_date(data):
    """Formata data para DDMMAAAA"""
    if pd.isna(data) or str(data).strip() == "" or str(data).lower() == 'nan':
        return "00000000"
    try:
        if isinstance(data, pd.Timestamp) or isinstance(data, datetime):
            return data.strftime('%d%m%Y')
        d = pd.to_datetime(data)
        return d.strftime('%d%m%Y')
    except:
        return "00000000"

def limpar_nosso_numero(nn):
    """Limpa caracteres especiais do Nosso Número"""
    nn_str = str(nn).replace(".0", "").strip()
    if nn_str.lower() == 'nan' or nn_str == 'None': return ""
    return ''.join(filter(str.isalnum, nn_str))

def fmt_convenio_bb(dados):
    """Formata o bloco de convênio específico do Banco do Brasil (20 posições)"""
    conv = fmt_num(dados.get('convenio', ''), 9)
    fixo = "0126"
    brancos = fmt_alfa("", 5)
    teste = fmt_alfa("", 2) # Espaços em branco para produção
    return conv + fixo + brancos + teste

def fmt_conta_bb(dados):
    """Formata o bloco de conta específico do Banco do Brasil (20 posições)"""
    ag = fmt_num(dados.get('agencia', ''), 5)
    dv_ag = fmt_alfa(dados.get('dv_agencia', ''), 1)
    conta = fmt_num(dados.get('conta', ''), 12)
    dv_conta = fmt_alfa(dados.get('dv_conta', ''), 1)
    dv_ag_conta = fmt_alfa("", 1) # Geralmente em branco
    return ag + dv_ag + conta + dv_conta + dv_ag_conta

# ==========================================
# FUNÇÕES DE FORMATAÇÃO CNAB 240
# ==========================================
def header_arquivo(dados, nsa):
    reg = fmt_num("001", 3) + fmt_num("0000", 4) + fmt_num("0", 1) + fmt_alfa("", 9) + fmt_num("2", 1) + fmt_num(dados['cnpj'], 14) + fmt_convenio_bb(dados) + fmt_conta_bb(dados) + fmt_alfa(dados['razao_social'], 30) + fmt_alfa("BANCO DO BRASIL", 30) + fmt_alfa("", 10) + fmt_num("1", 1) + datetime.now().strftime('%d%m%Y') + datetime.now().strftime('%H%M%S') + fmt_num(nsa, 6) + fmt_num("083", 3) + fmt_alfa("", 5) + fmt_alfa("", 20) + fmt_alfa("", 20) + fmt_alfa("", 29)
    return reg

def header_lote(dados, lote, nsa):
    reg = fmt_num("001", 3) + fmt_num(lote, 4) + fmt_num("1", 1) + fmt_alfa("R", 1) + fmt_num("01", 2) + fmt_alfa("", 2) + fmt_num("045", 3) + fmt_alfa("", 1) + fmt_num("2", 1) + fmt_num(dados['cnpj'], 15) + fmt_convenio_bb(dados) + fmt_conta_bb(dados) + fmt_alfa(dados['razao_social'], 30) + fmt_alfa("", 40) + fmt_alfa("", 40) + fmt_num(nsa, 8) + datetime.now().strftime('%d%m%Y') + fmt_num("0", 8) + fmt_alfa("", 33)
    return reg

def trailer_lote(lote, qtd_registros):
    # Força a conversão para inteiro antes de formatar
    lote_int = int(lote)
    qtd_int = int(qtd_registros)
    return fmt_num("001", 3) + fmt_num(lote_int, 4) + fmt_num("5", 1) + fmt_alfa("", 9) + fmt_num(qtd_int, 6) + fmt_num("0", 6) + fmt_alfa("", 205)

def trailer_arquivo(qtd_lotes, qtd_registros):
    # Força a conversão para inteiro antes de formatar
    lotes_int = int(qtd_lotes)
    qtd_int = int(qtd_registros)
    return fmt_num("001", 3) + fmt_num("9999", 4) + fmt_num("9", 1) + fmt_alfa("", 9) + fmt_num(lotes_int, 6) + fmt_num(qtd_int, 6) + fmt_num("0", 6) + fmt_alfa("", 205)

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

    # CORREÇÃO AQUI: Trocado > por >
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
    
# ==========================================
# TELA DE LOGIN E CADASTRO
# ==========================================
if not st.session_state.user:
    st.title("Bem-vindo ao Gerador CNAB 240")

    col_vazia1, col_login, col_vazia2 = st.columns([1, 2, 1])

    with col_login:
        aba_login, aba_cadastro = st.tabs(["Entrar", "Criar Conta"])

        with aba_login:
            st.subheader("Acesse sua conta")
            email_login = st.text_input("E-mail", key="log_email")
            senha_login = st.text_input("Senha", type="password", key="log_senha")

            if st.button("Entrar", type="primary", use_container_width=True):
                try:
                    # CORREÇÃO: Comando correto do Python (sign_in_with_password)
                    resposta = supabase.auth.sign_in_with_password({"email": email_login, "password": senha_login})
                    st.session_state.user = resposta.user
                    st.rerun()
                except Exception as e:
                    # Agora ele vai mostrar o erro real se você errar a senha
                    st.error(f"Erro ao logar: {e}")

        with aba_cadastro:
            st.subheader("Novo Usuário")
            email_cad = st.text_input("E-mail", key="cad_email")
            senha_cad = st.text_input("Senha", type="password", key="cad_senha")

            if st.button("Cadastrar", type="primary", use_container_width=True):
                try:
                    # CORREÇÃO: Comando correto do Python (sign_up)
                    resposta = supabase.auth.sign_up({"email": email_cad, "password": senha_cad})
                    st.success("Conta criada com sucesso! Volte na aba 'Entrar' para fazer o login.")
                except Exception as e:
                    st.error(f"Erro ao criar conta: {e}")

# ==========================================
# ÁREA LOGADA (SISTEMA PRINCIPAL)
# ==========================================
if st.session_state.user:
    # Botão de Logout no topo
    col_vazia, col_logout = st.columns([8, 1])
    with col_logout:
        if st.button("Sair", use_container_width=True):
            supabase.auth.signOut()
            st.session_state.user = None
            st.rerun()

    st.title("Sistema Gerador de CNAB 240")

    aba_gerador, aba_clientes, aba_convenios = st.tabs(["🚀 Gerar Remessa", "👥 Meus Clientes", "🏦 Meus Convênios"])

    # --- ABA: GERAR REMESSA ---
    with aba_gerador:
        st.header("Gerador de Arquivo Remessa")

        resposta_conv = supabase.table("convenios").select("*").eq("user_id", st.session_state.user.id).execute()
        df_convenios = pd.DataFrame(resposta_conv.data)

        if df_convenios.empty:
            st.warning("⚠️ Você precisa cadastrar pelo menos um Convênio na aba 'Meus Convênios' antes de gerar uma remessa.")
        else:
            opcoes_convenios = df_convenios['razao_social'].tolist()
            convenio_selecionado = st.selectbox("Selecione o Convênio:", opcoes_convenios)

            st.write("### Adicionar Lote")
            arquivo_excel = st.file_uploader("Selecione a planilha de boletos (Excel)", type=["xlsx", "xls"])

            col1, col2 = st.columns(2)
            instrucao = col1.selectbox("Código de Instrução:", [                       
                "01 - Entrada de títulos",
                "02 - Pedido de baixa",
                "04 - Concessão de Abatimento",
                "05 - Cancelamento de Abatimento",
                "06 - Alteração de Vencimento",
                "07 - Concessão de Desconto",
                "08 - Cancelamento de Desconto",
                "09 - Protestar",
                "10 - Cancela/Sustação da Instrução de protesto",
                "12 - Alterar Juros de Mora",
                "13 - Dispensar Juros de Mora",
                "14 - Cobrar Multa",
                "15 - Dispensar Multa",
                "16 - Ratificar dados da Concessão de Desconto",
                "19 - Altera Prazo Limite de Recebimento",
                "20 - Dispensar Prazo Limite de Recebimento",
                "21 - Altera do Número do Título dado pelo Beneficiário",
                "22 - Alteração do Número de Controle do Participante",
                "23 - Alteração de Nome e Endereço do Pagador",
                "30 - Recusa da Alegação do Sacado",
                "31 - Alteração de Outros Dados",
                "34 - Altera Data Para Concessão de Desconto",
                "40 - Alteração de modalidade",
                "45 - Inclusão de Negativação sem protesto (campo “Seu número” diferencia a negativação para o mesmo pagador)",
                "46 - Exclusão de Negativação sem protesto",
                "47 - Alteração do Valor Nominal do Boleto"
            ])

            nova_data = None
            if instrucao == "06 - Alteração de Vencimento":
                nova_data = col2.date_input("Nova Data de Vencimento", format="DD/MM/YYYY")

            if st.button("➕ Adicionar ao Lote"):
                if arquivo_excel is not None:
                    try:
                        df = pd.read_excel(arquivo_excel)
                        st.session_state.lotes.append({
                            'df': df,
                            'instrucao': instrucao,
                            'nova_data': nova_data,
                            'nome_arquivo': arquivo_excel.name
                        })
                        st.success(f"Lote adicionado! Total de lotes: {len(st.session_state.lotes)}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao ler arquivo: {e}")
                else:
                    st.warning("Por favor, selecione um arquivo Excel.")

            st.divider()

            if st.session_state.lotes:
                st.write("### Carrinho de Lotes")
                for i, lote in enumerate(st.session_state.lotes):
                    st.write(f"**Lote {i+1}:** {lote['instrucao']} - Arquivo: {lote['nome_arquivo']} ({len(lote['df'])} boletos)")
            else:
                st.info("Nenhum lote adicionado ainda. Você pode adicionar lotes acima ou gerar a remessa vazia (apenas header/trailer).")

            if st.button("🚀 GERAR ARQUIVO REMESSA FINAL", type="primary"):
                try:
                    # 1. Define quais lotes processar (Carrinho ou Geração Imediata)
                    lotes_para_processar = list(st.session_state.lotes)

                    if not lotes_para_processar:
                        if arquivo_excel is not None:
                            # Geração imediata: pega o arquivo que está na tela
                            df_imediato = pd.read_excel(arquivo_excel)
                            lotes_para_processar.append({
                                'df': df_imediato,
                                'instrucao': instrucao,
                                'nova_data': nova_data,
                                'nome_arquivo': arquivo_excel.name
                            })
                        else:
                            st.warning("⚠️ Adicione um lote ao carrinho ou selecione uma planilha para gerar a remessa.")
                            st.stop() # Para a execução aqui se não tiver nada

                    # 2. Inicia a geração do arquivo
                    dados_bancarios = df_convenios[df_convenios['razao_social'] == convenio_selecionado].iloc[0].to_dict()
                    nsa = 1 

                    resposta_cli = supabase.table("clientes").select("*").eq("user_id", st.session_state.user.id).execute()
                    df_clientes_bd = pd.DataFrame(resposta_cli.data)

                    linhas = []
                    linhas.append(header_arquivo(dados_bancarios, nsa))

                    total_registros_arquivo = 0

                    # 3. Processa os lotes
                    for i, lote in enumerate(lotes_para_processar):
                        numero_lote = i + 1
                        linhas.append(header_lote(dados_bancarios, numero_lote, nsa))

                        df_boletos = lote['df']
                        cod_instrucao = lote['instrucao'].split(" - ")[0].strip()

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
                            nome_coluna_codigo = colunas_map.get('cliente')

                            if not df_clientes_bd.empty and nome_coluna_codigo in dados_linha:
                                cod_boleto = str(dados_linha[nome_coluna_codigo]).strip().replace(".0", "")
                                cli_match = df_clientes_bd[df_clientes_bd['id_cliente_planilha'] == cod_boleto]

                                if not cli_match.empty:
                                    cli_dados = cli_match.iloc[0]
                                    dados_linha['cnpj_cpf'] = cli_dados.get('cnpj_cpf', '')
                                    dados_linha['nome'] = cli_dados.get('nome', '')
                                    dados_linha['endereco'] = cli_dados.get('endereco', '')
                                    dados_linha['bairro'] = cli_dados.get('bairro', '')
                                    dados_linha['cep'] = cli_dados.get('cep', '')
                                    dados_linha['cidade'] = cli_dados.get('cidade', '')
                                    dados_linha['uf'] = cli_dados.get('uf', '')
                                else:
                                    st.warning(f"⚠️ Cliente com código '{cod_boleto}' não encontrado no banco.")

                            linhas.append(segmento_p(dados_linha, numero_lote, seq_reg, dados_bancarios, colunas_map, cod_instrucao, lote['nova_data']))
                            seq_reg += 1
                            linhas.append(segmento_q(dados_linha, numero_lote, seq_reg, colunas_map, cod_instrucao))
                            seq_reg += 1

                        linhas.append(trailer_lote(numero_lote, seq_reg + 1))
                        total_registros_arquivo += (seq_reg + 1)

                    linhas.append(trailer_arquivo(len(lotes_para_processar), total_registros_arquivo + 2))

                    # 4. Finaliza e limpa o texto
                    cnab_bytes = io.BytesIO()
                    for linha in linhas:
                        linha_limpa = ''.join(c for c in unicodedata.normalize('NFD', linha) if unicodedata.category(c) != 'Mn')
                        linha_final = linha_limpa.ljust(240, " ")[:240] + "\r\n"
                        bytes_linha = linha_final.encode('ascii', errors='replace').replace(b'?', b' ')
                        cnab_bytes.write(bytes_linha)

                    st.success(f"✅ Arquivo gerado com sucesso! ({len(linhas)} linhas)")
                    st.download_button(
                        label="📥 Baixar Arquivo CNAB",
                        data=cnab_bytes.getvalue(),
                        file_name=f"remessa_bb.rem",
                        mime="text/plain"
                    )

                    # Limpa o carrinho após gerar com sucesso
                    st.session_state.lotes = []

                except Exception as e:
                    st.error(f"Erro ao gerar arquivo: {e}")    # --- ABA: MEUS CLIENTES ---
    with aba_clientes:
        st.header("Gestão de Clientes")

        col_manual, col_planilha = st.columns(2)

        with col_manual:
            with st.expander("➕ Cadastrar Manualmente"):
                with st.form("form_novo_cliente"):
                    cli_cod = st.text_input("Código do Cliente (Planilha)")
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
                            "id_cliente_planilha": cli_cod,
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
                st.write("A planilha deve conter as colunas: **cliente, cnpj, nome, endereco, bairro, cep, cidade, uf**")
                arquivo_importacao = st.file_uploader("Selecione a planilha de clientes", type=["xlsx", "xls"])

                if arquivo_importacao and st.button("Processar Importação"):
                    try:
                        df_import = pd.read_excel(arquivo_importacao)
                        df_import.columns = [str(c).strip().lower() for c in df_import.columns]

                        clientes_para_inserir = []
                        for index, row in df_import.iterrows():
                            cod_planilha = str(row.get("cliente", "")).strip().replace(".0", "")
                            clientes_para_inserir.append({
                                "user_id": st.session_state.user.id,
                                "id_cliente_planilha": cod_planilha,
                                "cnpj_cpf": str(row.get("cnpj", "")).replace(".0", ""),
                                "nome": str(row.get("nome", "")),
                                "endereco": str(row.get("endereco", "")),
                                "bairro": str(row.get("bairro", "")),
                                "cep": str(row.get("cep", "")).replace(".0", ""),
                                "cidade": str(row.get("cidade", "")),
                                "uf": str(row.get("uf", ""))
                            })

                        if clientes_para_inserir:
                            supabase.table("clientes").insert(clientes_para_inserir).execute()
                            st.success(f"{len(clientes_para_inserir)} clientes importados com sucesso!")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Erro na importação: {e}")

        st.divider()
        st.write("### Clientes Cadastrados")

        resposta_cli = supabase.table("clientes").select("*").eq("user_id", st.session_state.user.id).execute()
        df_clientes = pd.DataFrame(resposta_cli.data)

        if not df_clientes.empty:
            st.dataframe(df_clientes.drop(columns=['id', 'user_id', 'created_at']), use_container_width=True)

            mapa_clientes = {}
            for index, row in df_clientes.iterrows():
                texto_exibicao = f"{row['nome']} (Cód: {row['id_cliente_planilha']})"
                mapa_clientes[texto_exibicao] = row['id']

            opcoes_clientes = list(mapa_clientes.keys())

            aba_editar, aba_excluir_lote = st.tabs(["✏️ Editar Cliente", "🗑️ Exclusão em Lote"])

            with aba_editar:
                cliente_selecionado = st.selectbox("Selecione o cliente que deseja alterar:", [""] + opcoes_clientes)
                if cliente_selecionado:
                    id_real = mapa_clientes[cliente_selecionado]
                    dados_cli = df_clientes[df_clientes['id'] == id_real].iloc[0]

                    with st.form("form_editar_cliente"):
                        col1, col2 = st.columns(2)
                        edit_cod = col1.text_input("Código (Cliente)", value=str(dados_cli.get('id_cliente_planilha', '')))
                        edit_cnpj = col2.text_input("CNPJ/CPF", value=str(dados_cli.get('cnpj_cpf', '')))
                        edit_nome = st.text_input("Nome / Razão Social", value=str(dados_cli.get('nome', '')))
                        edit_end = st.text_input("Endereço", value=str(dados_cli.get('endereco', '')))

                        col3, col4, col5, col6 = st.columns(4)
                        edit_bairro = col3.text_input("Bairro", value=str(dados_cli.get('bairro', '')))
                        edit_cep = col4.text_input("CEP", value=str(dados_cli.get('cep', '')))
                        edit_cidade = col5.text_input("Cidade", value=str(dados_cli.get('cidade', '')))
                        edit_uf = col6.text_input("UF", value=str(dados_cli.get('uf', '')))

                        col_salvar, col_excluir = st.columns(2)
                        with col_salvar:
                            btn_salvar = st.form_submit_button("💾 Salvar Alterações", type="primary")
                        with col_excluir:
                            btn_excluir = st.form_submit_button("🗑️ Excluir Este Cliente")

                        if btn_salvar:
                            supabase.table("clientes").update({
                                "id_cliente_planilha": edit_cod, "cnpj_cpf": edit_cnpj, "nome": edit_nome,
                                "endereco": edit_end, "bairro": edit_bairro, "cep": edit_cep,
                                "cidade": edit_cidade, "uf": edit_uf
                            }).eq("id", id_real).execute()
                            st.success("Atualizado!")
                            st.rerun()
                        if btn_excluir:
                            supabase.table("clientes").delete().eq("id", id_real).execute()
                            st.success("Excluído!")
                            st.rerun()

            with aba_excluir_lote:
                st.write("Selecione os clientes que deseja apagar marcando as caixas abaixo.")

                if "marcar_todos" not in st.session_state:
                    st.session_state.marcar_todos = False

                def toggle_todos():
                    st.session_state.marcar_todos = not st.session_state.marcar_todos
                    for cliente in opcoes_clientes:
                        st.session_state[f"chk_{cliente}"] = st.session_state.marcar_todos

                st.checkbox("☑️ Selecionar TODOS os clientes", value=st.session_state.marcar_todos, on_change=toggle_todos)

                container_lista = st.container(height=400)
                clientes_para_excluir = []

                with container_lista:
                    for cliente_texto in opcoes_clientes:
                        if f"chk_{cliente_texto}" not in st.session_state:
                            st.session_state[f"chk_{cliente_texto}"] = st.session_state.marcar_todos

                        if st.checkbox(cliente_texto, key=f"chk_{cliente_texto}"):
                            clientes_para_excluir.append(cliente_texto)

                if clientes_para_excluir:
                    st.warning(f"⚠️ Excluir **{len(clientes_para_excluir)}** cliente(s)?")
                    if st.button("🚨 Confirmar Exclusão em Lote", type="primary"):
                        ids_excluir = [mapa_clientes[c] for c in clientes_para_excluir]
                        for id_interno in ids_excluir:
                            supabase.table("clientes").delete().eq("id", id_interno).execute()
                        st.success("Excluídos com sucesso!")
                        st.rerun()
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
                        "cnpj": conv_cnpj, "razao_social": conv_razao, "agencia": conv_ag,
                        "dv_agencia": conv_ag_dv, "conta": conv_conta, "dv_conta": conv_conta_dv,
                        "convenio": conv_num, "carteira": conv_cart, "variacao": conv_var
                    }
                    supabase.table("convenios").insert(novo_convenio).execute()
                    st.success("Convênio cadastrado!")
                    st.rerun()

        st.write("### Convênios Cadastrados")
        resposta_conv = supabase.table("convenios").select("*").eq("user_id", st.session_state.user.id).execute()
        df_convenios = pd.DataFrame(resposta_conv.data)

        if not df_convenios.empty:
            st.dataframe(df_convenios.drop(columns=['id', 'user_id', 'created_at']), use_container_width=True)
        else:
            st.info("Nenhum convênio cadastrado ainda.")
