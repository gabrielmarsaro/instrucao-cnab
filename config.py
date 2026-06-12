"""Constantes e configurações do aplicativo."""

# Rótulos de interface
# Abas (st.tabs): só ASCII — Chrome trunca/corrompe ê, ó etc. nos botões de aba
ABA_CONVENIOS_TAB = "Convenios"
ABA_HISTORICO_TAB = "Historico"
ABA_VALORES_TAB = "Valores Nominais"

# Texto em markdown/mensagens (fora de st.tabs)
ABA_CONVENIOS = "Conv\u00eanios"

# Títulos: entidades numéricas + st.html (Chrome ignora mal &ecirc; em st.markdown)
TITULO_GESTAO_CONVENIOS_HTML = (
    "<h2 style='margin:0;padding:0;'>Gest&#227;o de Conv&#234;nios</h2>"
)
TITULO_GESTAO_CLIENTES_HTML = (
    "<h2 style='margin:0;padding:0;'>Gest&#227;o de Clientes</h2>"
)
TITULO_HISTORICO_HTML = (
    "<h2 style='margin:0;padding:0;'>Hist&#243;rico de Remessas</h2>"
)
TITULO_VALORES_NOMINAIS_HTML = (
    "<h2 style='margin:0;padding:0;'>Valores Nominais Registrados</h2>"
)

# Segoe UI primeiro — Calibri em abas do Chrome no Windows costuma corromper acentos
FONTE_APP = '"Segoe UI", Tahoma, Calibri, "Helvetica Neue", Arial, sans-serif'

# Referência de valores nominais na geração da remessa
REF_VALORES_ATUAL = "Valores atuais registrados (padrao)"
REF_VALORES_ULTIMA = "Ultima remessa deste convenio"
REF_VALORES_ESCOLHER = "Escolher remessa especifica"
MODOS_REFERENCIA_VALORES = [
    REF_VALORES_ATUAL,
    REF_VALORES_ULTIMA,
    REF_VALORES_ESCOLHER,
]

# Status da remessa no histórico
STATUS_REMESSA_GERADA = "gerada"
STATUS_REMESSA_ACEITA = "aceita"
STATUS_REMESSA_REJEITADA = "rejeitada"

STATUS_REMESSA_OPCOES = [
    STATUS_REMESSA_GERADA,
    STATUS_REMESSA_ACEITA,
    STATUS_REMESSA_REJEITADA,
]

STATUS_REMESSA_LABELS = {
    STATUS_REMESSA_GERADA: "Gerada",
    STATUS_REMESSA_ACEITA: "Aceita pelo banco",
    STATUS_REMESSA_REJEITADA: "Rejeitada pelo banco",
}

INSTRUCOES_CNAB = [
    "01 - Entrada de Títulos",
    "02 - Pedido de baixa",
    "03 - Pedido de Protesto Falimentar",
    "04 - Concessão de Abatimento",
    "05 - Cancelamento de Abatimento",
    "06 - Alteração de Vencimento",
    "07 - Concessão de Desconto",
    "08 - Cancelamento de Desconto",
    "09 - Protestar",
    "10 - Cancela/Sustação da Instrução de protesto",
    "11 - Sustar Protesto e Baixar Título",
    "12 - Alterar Juros de Mora",
    "13 - Dispensar Juros de Mora",
    "14 - Cobrar Multa",
    "15 - Dispensar Multa",
    "16 - Ratificar dados da Concessão de Desconto",
    "18 - Sustar Protesto e Manter em Carteira",
    "19 - Altera Prazo Limite de Recebimento",
    "20 - Dispensar Prazo Limite de Recebimento",
    "21 - Altera do Número do Título dado pelo Beneficiário",
    "22 - Alteração do Número de Controle do Participante",
    "23 - Alteração de Nome e Endereço do Pagador",
    "24 - Transferência de carteira/modalidade",
    "25 - Manutenção em Carteira",
    "26 - Não protestar",
    "30 - Recusa da Alegação do Sacado",
    "31 - Alteração de Outros Dados",
    "34 - Altera Data Para Concessão de Desconto",
    "35 - Cobrança Partilhada",
    "36 - Cancelamento de cobrança partilhada",
    "37 - Alteração de valor mínimo",
    "38 - Alteração do valor máximo",
    "39 - Alteração do número de dias para protesto",
    "40 - Alteração de modalidade",
    "41 - Cancelamento de protesto automático",
    "42 - Alteração de espécie de título",
    "43 - Alteração de aceite",
    "44 - Alteração de datas - desconto, multa, juros",
    "45 - Inclusão de Negativação sem protesto",
    "46 - Exclusão de Negativação sem protesto",
    "47 - Alteração do Valor Nominal do Boleto",
]

PREVIEW_LINHAS = 15

COLUNAS_CLIENTES = {
    "codigo": ["codigo", "código", "cod cliente", "codigo cliente", "id cliente", "cliente", "id"],
    "cnpj": ["cnpj", "cpf", "cnpj/cpf", "cnpj_cpf", "cnpj cpf", "documento"],
    "nome": ["nome", "razao social", "razão social", "nome cliente"],
    "endereco": ["endereco", "endereço", "logradouro"],
    "bairro": ["bairro"],
    "cep": ["cep"],
    "cidade": ["cidade", "municipio", "município"],
    "uf": ["uf", "estado"],
}

COLUNAS_OBRIGATORIAS = {
    "nn": ["nosso numero", "nosso_numero", "nosso número"],
    "doc": ["documento", "nº documento", "numero documento"],
    "venc": ["vencimento", "vencimento liquido", "vencimento líquido"],
    "montante": ["montante", "valor", "valor titulo"],
    "cliente": ["cliente", "cod cliente", "código cliente"],
}

MENSAGENS_ERRO = {
    "invalid_credentials": "E-mail ou senha incorretos. Verifique e tente novamente.",
    "email_not_confirmed": "Confirme seu e-mail antes de fazer login.",
    "user_already_registered": "Este e-mail já está cadastrado. Use a aba Login.",
    "weak_password": "A senha deve ter pelo menos 6 caracteres.",
    "network": "Não foi possível conectar ao servidor. Verifique sua internet.",
    "rls": "Permissão negada no banco. Execute as migrations SQL no Supabase.",
    "default": "Ocorreu um erro inesperado. Tente novamente ou contate o suporte.",
}
