"""Baixa os dados abertos do Transferegov (módulo Discricionárias) e gera a base
do Painel Cisternas: um arquivo por bloco do painel (inclusive as metas do
cronograma físico, os prazos e alterações, o histórico de situação, os empenhos
e os rendimentos), só com os instrumentos do Programa Cisternas (MDS, ações 8948/11V1).

Uso: python atualizar_dados.py [--sem-download]
Saída: cisternas/dados/*.csv (+ historico_saldo.csv acumulado a cada carga)
"""
import io
import re
import shutil
import sys
import time
import unicodedata
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

BASE_URL = "https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/"
EXECUCAO = int(time.time())
AQUI = Path(__file__).resolve().parent
BRUTOS = AQUI / "brutos"
DADOS = AQUI / "dados"

ORGAO_MDS = "55000"
ACOES_CISTERNAS = r"8948|11V1"

# Detalhe (pagamentos, repasses, cronograma) só para instrumentos ainda em acompanhamento.
SITUACOES_ENCERRADAS = {
    "Prestação de Contas Concluída",
    "Prestação de Contas Aprovada",
    "Prestação de Contas Aprovada com Ressalvas",
    "Prestação de Contas Rejeitada",
    "Convênio Anulado",
    "Cancelado",
}

MODALIDADES = {
    "CONVENIO": "Convênio",
    "TERMO DE COLABORACAO": "Termo de colaboração",
    "TERMO DE FOMENTO": "Termo de fomento",
    "TERMO DE PARCERIA": "Termo de parceria",
    "CONTRATO DE REPASSE": "Contrato de repasse",
}

ARQUIVOS = [
    "data_carga_siconv",
    "siconv_programa",
    "siconv_programa_proposta",
    "siconv_proposta",
    "siconv_convenio",
    "siconv_pagamento",
    "siconv_desembolso",
    "siconv_cronograma_desembolso",
    "siconv_meta_crono_fisico",
    "siconv_etapa_crono_fisico",
    "siconv_termo_aditivo",
    "siconv_prorroga_oficio",
    "siconv_solicitacao_alteracao",
    "siconv_historico_situacao",
    "siconv_empenho",
    "siconv_empenho_desembolso",
    "siconv_solicitacao_rendimento_aplicacao",
]

# Situações do histórico (siconv_historico_situacao) com o nome que o Transferegov mostra
SITUACOES = {
    "PROPOSTA_CADASTRADA": "Proposta cadastrada",
    "PROPOSTA_ENVIADA_ANALISE": "Proposta enviada para análise",
    "PROPOSTA_EM_ANALISE": "Proposta em análise",
    "PROPOSTA_EM_COMPLEMENTACAO": "Proposta em complementação",
    "PROPOSTA_COMPLEMENTADA_ENVIADA_ANALISE": "Proposta complementada enviada para análise",
    "PROPOSTA_COMPLEMENTADA_EM_ANALISE": "Proposta complementada em análise",
    "PROPOSTA_APROVADA_AGUARDANDO_PLANO_TRABALHO": "Proposta aprovada, aguardando plano de trabalho",
    "EM_CHAMAMENTO_PUBLICO_ENVIADA_PARA_ANALISE_PRELIMINAR": "Chamamento público: enviada para análise preliminar",
    "EM_CHAMAMENTO_PUBLICO_CLASSIFICADA_ANALISE_PRELIMINAR": "Chamamento público: classificada na análise preliminar",
    "PLANO_TRABALHO_ENVIADO_ANALISE": "Plano de trabalho enviado para análise",
    "PLANO_TRABALHO_EM_ANALISE": "Plano de trabalho em análise",
    "PLANO_TRABALHO_EM_COMPLEMENTACAO": "Plano de trabalho em complementação",
    "PLANO_TRABALHO_COMPLEMENTADO_ENVIADO_ANALISE": "Plano de trabalho complementado enviado para análise",
    "PLANO_TRABALHO_COMPLEMENTADO_EM_ANALISE": "Plano de trabalho complementado em análise",
    "PLANO_TRABALHO_APROVADO": "Plano de trabalho aprovado",
    "ASSINATURA_PENDENTE_REGISTRO_TV_SIAFI": "Assinatura pendente de registro no SIAFI",
    "ASSINADA": "Assinado",
    "EM_EXECUCAO": "Em execução",
    "INADIMPLENTE": "Inadimplente",
    "AGUARDANDO_PRESTACAO_CONTAS": "Aguardando prestação de contas",
    "PRESTACAO_CONTAS_ENVIADA_ANALISE": "Prestação de contas enviada para análise",
    "PRESTACAO_CONTAS_EM_ANALISE": "Prestação de contas em análise",
    "PRESTACAO_CONTAS_EM_COMPLEMENTACAO": "Prestação de contas em complementação",
    "PRESTACAO_CONTAS_COMPROVADA_EM_ANALISE": "Prestação de contas comprovada em análise",
    "PRESTACAO_CONTAS_REJEITADA": "Prestação de contas rejeitada",
}


UFS = {
    "ACRE": "AC", "ALAGOAS": "AL", "AMAPA": "AP", "AMAZONAS": "AM", "BAHIA": "BA", "CEARA": "CE",
    "DISTRITO FEDERAL": "DF", "ESPIRITO SANTO": "ES", "GOIAS": "GO", "MARANHAO": "MA",
    "MATO GROSSO DO SUL": "MS", "MATO GROSSO": "MT", "MINAS GERAIS": "MG", "PARAIBA": "PB",
    "PARANA": "PR", "PERNAMBUCO": "PE", "PIAUI": "PI", "RIO DE JANEIRO": "RJ",
    "RIO GRANDE DO NORTE": "RN", "RIO GRANDE DO SUL": "RS", "RONDONIA": "RO", "RORAIMA": "RR",
    "SANTA CATARINA": "SC", "SAO PAULO": "SP", "SERGIPE": "SE", "TOCANTINS": "TO",
}

# Tecnologia de cada etapa, pelo texto (sem acento, maiúsculo). A primeira regra que casa vale.
TECNOLOGIAS = [
    (r"CAPACITA|OFIC|PEDREIRO|DIDATICO|MOBILIZA|COMUNICA", None),
    (r"BOMBA MANUAL", None),  # bomba da cisterna de 16 mil, não é a bomba d'água popular
    (r"REUSO|REUTILIZ", "Sistema de tratamento e reuso"),
    (r"PEQUENAS? BARRAGE", "Pequena barragem"),
    (r"BARRAGE(M|NS)", "Barragem subterrânea"),
    (r"ENXURRAD", "Cisterna de enxurrada"),
    (r"CALCAD", "Cisterna calçadão"),
    (r"TELHADAO", "Cisterna telhadão"),
    (r"ESCOLA", "Cisterna escolar"),
    (r"BARREIRO|TRINCHEIRA", "Barreiro trincheira"),
    (r"TANQUES? DE PEDRA", "Tanque de pedra"),
    (r"BOMBA", "Bomba d'água popular"),
    (r"PLUVIAL MULTIUSO", "Sistema pluvial multiuso"),
    (r"CISTERNAS? COMUNITARIA", "Cisterna comunitária"),
    (r"CISTERNAS? DE PRODUCAO", "Cisterna de produção"),
    (r"CISTERNA.*52(\.000| ?MIL)", "Cisterna de 52 mil litros"),
    (r"CISTERNA.*(16|PLACA|CONSUMO)|(16|PLACA).*CISTERNA", "Cisterna de 16 mil litros"),
]

# Meta que não é de implementação de tecnologia, mesmo citando cisternas nas etapas
META_NAO_TEC = r"CAPACITA|OFICINA|SELECAO|CADASTRA|ASSISTENCIA TECNICA|MOBILIZA|COMUNICA|MONITORA|GESTAO|AVALIA|ENCONTRO|INTERCAMBIO"
# Partes de um mesmo lote registradas em etapas separadas: cada uma repete a quantidade do lote
PARTES = [("custeio", r"CUSTEIO"), ("investimento", r"INVESTIMENTO"), ("material", r"\bMATS?\b|MATERIA"),
          ("servico", r"SERV\.?\s*PREST|\bPJ\b")]
# Acessório de uma tecnologia já contada (complemento de valor, ISS, caráter produtivo, sobras...)
ACESSORIO = r"COMPLEMENT|CARATER PRODUTIVO|ABRIGO|AJUDA DE CUSTO|(^|[-–]\s*)ISS(QN)?\b|SOBRA|\bKIT\b"


def sem_acento(s):
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().upper()


def uf_no_texto(t):
    # Pará fica de fora do nome por extenso: "PARA" é preposição nas descrições.
    for nome, sigla in UFS.items():
        if re.search(rf"\b{nome}\b", t):
            return sigla
    # sigla no fim ("... - PE") ou no começo, depois da numeração ("1.1. AC. Sistema ...")
    m = re.search(r"[-–]\s*([A-Z]{2})\s*$", t) or re.match(r"^\s*\d+(?:\.\d+)*[A-Z]?\.?\s+([A-Z]{2})\.\s", t)
    return m.group(1) if m and m.group(1) in UFS.values() else None


def tecnologia(t):
    return next((nome for padrao, nome in TECNOLOGIAS if re.search(padrao, t)), None)


def parte(t):
    if re.search(ACESSORIO, t):
        return "acessorio"
    return next((nome for nome, p in PARTES if re.search(p, t)), "principal")


def lote(g):
    """Unidades de uma tecnologia numa UF dentro da meta, sem contar duas vezes as partes do lote:
    vale a maior soma entre as partes (custeio x investimento, material x serviço); acessório só
    conta quando não há outra etapa da mesma tecnologia."""
    soma = g.groupby("parte").quantidade.sum()
    base = soma.drop("acessorio", errors="ignore")
    return base.max() if len(base) else soma.max()


def baixar(nome):
    destino = BRUTOS / f"{nome}.zip"
    # Os arquivos passam pelo cache da Cloudflare, que pode entregar a carga do dia anterior
    # horas depois da publicação; um parâmetro novo a cada execução busca o arquivo na origem.
    url = BASE_URL + f"{nome}.zip?v={EXECUCAO}"
    with urllib.request.urlopen(url, timeout=600) as r, open(destino, "wb") as f:
        shutil.copyfileobj(r, f, 1 << 20)
    print(f"baixado {nome} ({destino.stat().st_size / 1e6:.1f} MB)")


def ler(nome, usecols=None, filtro=None):
    """Lê o CSV de dentro do zip, em blocos, aplicando `filtro(df) -> df` em cada um."""
    with zipfile.ZipFile(BRUTOS / f"{nome}.zip") as z:
        with z.open(z.namelist()[0]) as f:
            texto = io.TextIOWrapper(f, encoding="utf-8-sig", errors="replace")
            blocos = pd.read_csv(texto, sep=";", dtype=str, usecols=usecols,
                                 chunksize=500_000, on_bad_lines="skip")
            return pd.concat([filtro(b) if filtro else b for b in blocos], ignore_index=True)


def valor_br(s):
    """'1.234,56' -> 1234.56. O SICONV mistura formatos: só troca vírgula quando existe."""
    s = s.fillna("").astype(str).str.strip()
    com_virgula = s.str.contains(",", regex=False)
    s = s.where(~com_virgula, s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
    return pd.to_numeric(s, errors="coerce")


def data_br(s):
    return pd.to_datetime(s.str.slice(0, 10), format="%d/%m/%Y", errors="coerce").dt.strftime("%Y-%m-%d")


def mascarar_cpf(doc):
    d = re.sub(r"\D", "", str(doc or ""))
    return f"***.{d[3:6]}.{d[6:9]}-**" if len(d) == 11 else d


def main():
    BRUTOS.mkdir(exist_ok=True)
    DADOS.mkdir(exist_ok=True)
    if "--sem-download" not in sys.argv:
        for nome in ARQUIVOS:
            baixar(nome)

    carga = ler("data_carga_siconv").iloc[0, 0]
    data_carga = pd.to_datetime(carga, dayfirst=True).strftime("%Y-%m-%d")

    prog = ler("siconv_programa", ["COD_ORGAO_SUP_PROGRAMA", "ID_PROGRAMA", "ACAO_ORCAMENTARIA"])
    prog = prog[(prog.COD_ORGAO_SUP_PROGRAMA == ORGAO_MDS)
                & prog.ACAO_ORCAMENTARIA.str.contains(ACOES_CISTERNAS, na=False)]
    ids_prog = set(prog.ID_PROGRAMA)
    pp = ler("siconv_programa_proposta", filtro=lambda b: b[b.ID_PROGRAMA.isin(ids_prog)])
    ids_prop = set(pp.ID_PROPOSTA)

    conv = ler("siconv_convenio", filtro=lambda b: b[b.ID_PROPOSTA.isin(ids_prop)])
    prop = ler("siconv_proposta", ["ID_PROPOSTA", "MODALIDADE", "NM_PROPONENTE", "IDENTIF_PROPONENTE",
                                   "UF_PROPONENTE", "MUNIC_PROPONENTE", "NATUREZA_JURIDICA",
                                   "OBJETO_PROPOSTA", "NM_BANCO", "CD_AGENCIA", "CD_CONTA"],
               filtro=lambda b: b[b.ID_PROPOSTA.isin(ids_prop)])
    nrs = set(conv.NR_CONVENIO)

    pag = ler("siconv_pagamento", filtro=lambda b: b[b.NR_CONVENIO.isin(nrs)])
    pag["valor"] = valor_br(pag.VL_PAGO)
    pag["data"] = data_br(pag.DATA_PAG)
    des = ler("siconv_desembolso", filtro=lambda b: b[b.NR_CONVENIO.isin(nrs)])
    des["valor"] = valor_br(des.VL_DESEMBOLSADO)
    des["data"] = data_br(des.DATA_DESEMBOLSO)
    cro = ler("siconv_cronograma_desembolso", filtro=lambda b: b[b.NR_CONVENIO.isin(nrs)])

    # --- instrumentos: ficha + resumo financeiro + datas para os alertas
    i = conv.merge(prop, on="ID_PROPOSTA", how="left")
    tot_pag = pag.groupby("NR_CONVENIO").agg(vl_pago=("valor", "sum"), ult_pagamento=("data", "max"),
                                             qtd_pagamentos=("valor", "size"))
    ult_des = des.groupby("NR_CONVENIO").data.max().rename("ult_repasse")
    i = i.join(tot_pag, on="NR_CONVENIO").join(ult_des, on="NR_CONVENIO")
    inst = pd.DataFrame({
        "nr": i.NR_CONVENIO,
        "id_proposta": i.ID_PROPOSTA,
        "modalidade": i.MODALIDADE.map(MODALIDADES).fillna(i.MODALIDADE),
        "parceiro": i.NM_PROPONENTE,
        "cnpj": i.IDENTIF_PROPONENTE,
        "uf": i.UF_PROPONENTE,
        "municipio": i.MUNIC_PROPONENTE,
        "natureza": i.NATUREZA_JURIDICA,
        "objeto": i.OBJETO_PROPOSTA,
        "situacao": i.SIT_CONVENIO.fillna("Sem situação"),
        "processo": i.NR_PROCESSO,
        "assinatura": data_br(i.DIA_ASSIN_CONV.fillna("")),
        "inicio_vigencia": data_br(i.DIA_INIC_VIGENC_CONV.fillna("")),
        "fim_vigencia": data_br(i.DIA_FIM_VIGENC_CONV.fillna("")),
        "fim_vigencia_original": data_br(i.DIA_FIM_VIGENC_ORIGINAL_CONV.fillna("")),
        "limite_prestacao_contas": data_br(i.DIA_LIMITE_PREST_CONTAS.fillna("")),
        "banco": i.NM_BANCO,
        "agencia": i.CD_AGENCIA,
        "conta": i.CD_CONTA,
        "qtd_aditivos": pd.to_numeric(i.QTD_TA, errors="coerce"),
        "qtd_prorrogacoes": pd.to_numeric(i.QTD_PRORROGA, errors="coerce"),
        "vl_global": valor_br(i.VL_GLOBAL_CONV),
        "vl_global_original": valor_br(i.VALOR_GLOBAL_ORIGINAL_CONV),
        "vl_repasse": valor_br(i.VL_REPASSE_CONV),
        "vl_contrapartida": valor_br(i.VL_CONTRAPARTIDA_CONV),
        "vl_empenhado": valor_br(i.VL_EMPENHADO_CONV),
        "vl_repassado": valor_br(i.VL_DESEMBOLSADO_CONV),
        "vl_contrapartida_depositada": valor_br(i.VL_INGRESSO_CONTRAPARTIDA),
        "vl_rendimentos": valor_br(i.VL_RENDIMENTO_APLICACAO),
        "vl_pago": i.vl_pago.fillna(0).round(2),
        "qtd_pagamentos": i.qtd_pagamentos.fillna(0).astype(int),
        "vl_saldo_conta": valor_br(i.VL_SALDO_CONTA),
        "ult_pagamento": i.ult_pagamento,
        "ult_repasse": i.ult_repasse,
        "data_carga": data_carga,
    })
    inst["acompanhamento"] = ~inst.situacao.isin(SITUACOES_ENCERRADAS)
    inst = inst.sort_values(["acompanhamento", "fim_vigencia", "nr"], ascending=[False, False, True])
    inst["vl_empenhado_registrado"] = inst.vl_empenhado

    acomp = set(inst.loc[inst.acompanhamento, "nr"])

    # --- pagamentos feitos pelo parceiro (CPF de pessoa física mascarado)
    p = pag[pag.NR_CONVENIO.isin(acomp)]
    pd.DataFrame({
        "id": p.NR_MOV_FIN,
        "nr": p.NR_CONVENIO,
        "data": p.data,
        "favorecido": p.NOME_FORNECEDOR,
        "documento_favorecido": p.IDENTIF_FORNECEDOR.map(mascarar_cpf),
        "comprovante": p.DESC_DL,
        "nr_comprovante": p.NR_DL,
        "forma": p.TP_MOV_FINANCEIRA.str.replace("PAGAMENTO A FAVORECIDO", "Pagamento", regex=False).str.replace("COM OBTV", "com OBTV", regex=False),
        "valor": p.valor.round(2),
    }).sort_values(["nr", "data", "id"], ascending=[True, False, True]).to_csv(DADOS / "pagamentos.csv", index=False)

    # --- repasses do MDS (ordens bancárias)
    d = des[des.NR_CONVENIO.isin(acomp)]
    pd.DataFrame({
        "id": d.ID_DESEMBOLSO, "nr": d.NR_CONVENIO, "data": d.data,
        "ordem_bancaria": d.NR_SIAFI, "valor": d.valor.round(2),
    }).sort_values(["nr", "data", "id"]).to_csv(DADOS / "repasses.csv", index=False)

    # --- cronograma de desembolso (parcelas previstas)
    c = cro[cro.NR_CONVENIO.isin(acomp)]
    mes = pd.to_numeric(c.MES_CRONO_DESEMBOLSO, errors="coerce").fillna(1).astype(int)
    pd.DataFrame({
        "nr": c.NR_CONVENIO,
        "parcela": pd.to_numeric(c.NR_PARCELA_CRONO_DESEMBOLSO, errors="coerce"),
        "mes": c.ANO_CRONO_DESEMBOLSO + "-" + mes.map("{:02d}".format),
        "responsavel": c.TIPO_RESP_CRONO_DESEMBOLSO,
        "valor": valor_br(c.VALOR_PARCELA_CRONO_DESEMBOLSO),
    }).sort_values(["nr", "mes", "parcela", "responsavel", "valor"]).to_csv(DADOS / "cronograma.csv", index=False)

    # --- cronograma físico (metas). As metas nascem na proposta, antes de existir o número do instrumento.
    nr_por_proposta = inst.loc[inst.acompanhamento].set_index("id_proposta").nr
    m = ler("siconv_meta_crono_fisico",
            ["ID_META", "ID_PROPOSTA", "NR_META", "TIPO_META", "DESC_META", "DATA_INICIO_META",
             "DATA_FIM_META", "QTD_META", "UND_FORNECIMENTO_META", "VL_META"],
            filtro=lambda b: b[b.ID_PROPOSTA.isin(nr_por_proposta.index)])
    metas = pd.DataFrame({
        "id": m.ID_META,
        "nr": m.ID_PROPOSTA.map(nr_por_proposta),
        "meta": pd.to_numeric(m.NR_META, errors="coerce"),
        "tipo": m.TIPO_META.map({"NORMAL": "Normal", "APLICACAO": "Rendimentos"}).fillna(m.TIPO_META),
        # "1. SERVIÇO ..." -> "SERVIÇO ...": o número já está na coluna da meta
        "especificacao": m.DESC_META.str.replace(r"^\s*\d+\s*[.\-)]\s*", "", regex=True).str.strip(),
        "inicio": data_br(m.DATA_INICIO_META.fillna("")),
        "fim": data_br(m.DATA_FIM_META.fillna("")),
        "quantidade": valor_br(m.QTD_META),
        "unidade": m.UND_FORNECIMENTO_META,
        "valor": valor_br(m.VL_META).round(2),
    }).sort_values(["nr", "meta", "id"])
    metas.to_csv(DADOS / "metas.csv", index=False)

    # --- tecnologias por UF, das etapas de cada meta. UF e tecnologia só existem no texto da etapa.
    et = ler("siconv_etapa_crono_fisico", ["ID_META", "ID_ETAPA", "DESC_ETAPA", "QTD_ETAPA", "VL_ETAPA"],
             filtro=lambda b: b[b.ID_META.isin(set(metas.id))])
    et = et.merge(metas[["id", "nr", "meta", "quantidade", "especificacao"]].rename(columns={"quantidade": "qtd_meta"}),
                  left_on="ID_META", right_on="id")
    et = et.merge(inst[["nr", "uf"]].rename(columns={"uf": "uf_parceiro"}), on="nr")
    texto = et.DESC_ETAPA.map(sem_acento)
    et["tecnologia"] = texto.map(tecnologia)
    et["uf"] = texto.map(uf_no_texto)
    # UF do texto só vale em instrumento com mais de um estado; senão é a do parceiro
    # (evita tomar município homônimo, como São Paulo do Potengi, por estado).
    multi_uf = et.groupby("nr").uf.transform("nunique") > 1
    et["uf"] = et.uf.where(multi_uf).fillna(et.uf_parceiro)
    et["valor"] = valor_br(et.VL_ETAPA)
    et["qtd"] = valor_br(et.QTD_ETAPA).fillna(0)
    # Etapa zerada (valor de centavos) ou lançamento que "não integra" a meta não conta unidade
    et["conta"] = (et.valor >= 1) & ~texto.str.contains("NAO INTEGRA", regex=False)
    et["quantidade"] = et.qtd.where(et.conta, 0)
    et["parte"] = texto.map(parte)
    et = et[et.tecnologia.notna() & ~et.especificacao.map(sem_acento).str.contains(META_NAO_TEC)]
    # Uma linha por meta, UF e tecnologia; toda meta de tecnologia entra no quadro
    tec = (et.groupby(["nr", "meta", "id", "qtd_meta", "uf", "tecnologia"])
           .apply(lambda g: pd.Series({"quantidade": lote(g), "valor": g.valor.sum(), "etapas": len(g)}),
                  include_groups=False)
           .reset_index().rename(columns={"id": "id_meta"}))
    tec["soma_etapas"] = tec.groupby("id_meta").quantidade.transform("sum")
    grupos = tec.groupby("id_meta").quantidade.transform("size")
    difere = (tec.soma_etapas - tec.qtd_meta).abs() >= 0.5
    # Quando as etapas não fecham com a meta: meta registrada como 1 unidade vale a soma das
    # etapas ("global"); meta de uma só UF e tecnologia vale a quantidade da meta ("meta");
    # nos demais casos ficam as etapas e o painel mostra a diferença ("diferenca").
    tec["ajuste"] = ""
    tec.loc[difere & (tec.qtd_meta <= 1), "ajuste"] = "global"
    tec.loc[difere & (tec.qtd_meta > 1) & (grupos == 1), "ajuste"] = "meta"
    tec.loc[difere & (tec.qtd_meta > 1) & (grupos > 1), "ajuste"] = "diferenca"
    tec.loc[tec.ajuste == "meta", "quantidade"] = tec.qtd_meta
    tec["id"] = tec.id_meta + "-" + tec.uf + "-" + tec.tecnologia
    tec[["id", "nr", "meta", "uf", "tecnologia", "quantidade", "valor", "etapas", "qtd_meta", "soma_etapas", "ajuste"]] \
        .sort_values(["nr", "meta", "uf", "id"]).to_csv(DADOS / "tecnologias.csv", index=False)

    # --- prazos e alterações: termos aditivos, prorrogações de ofício e solicitações de alteração
    sol = ler("siconv_solicitacao_alteracao", filtro=lambda b: b[b.NR_CONVENIO.isin(acomp)])
    ta = ler("siconv_termo_aditivo", filtro=lambda b: b[b.NR_CONVENIO.isin(acomp)])
    po = ler("siconv_prorroga_oficio", filtro=lambda b: b[b.NR_CONVENIO.isin(acomp)])
    nr_sol = sol.drop_duplicates("ID_SOLICITACAO").set_index("ID_SOLICITACAO").NR_SOLICITACAO
    dias_po = pd.to_numeric(po.DIAS_PRORROGA, errors="coerce")
    prazos = pd.concat([
        pd.DataFrame({
            "id": "ta-" + ta.NUMERO_TA, "nr": ta.NR_CONVENIO, "tipo": "Termo aditivo", "numero": ta.NUMERO_TA,
            "data": data_br(ta.DT_ASSINATURA_TA.fillna("")), "descricao": ta.TIPO_TA, "situacao": "",
            "fim": data_br(ta.DT_FIM_TA.fillna("")), "dias": None, "valor": valor_br(ta.VL_GLOBAL_TA),
            "solicitacao": ta.ID_SOLICITACAO.map(nr_sol), "detalhe": ta.JUSTIFICATIVA_TA.str.slice(0, 600),
        }),
        pd.DataFrame({
            "id": "po-" + po.NR_PRORROGA, "nr": po.NR_CONVENIO, "tipo": "Prorrogação de ofício",
            "numero": po.NR_PRORROGA.str.lstrip("0"), "data": data_br(po.DT_ASSINATURA_PRORROGA.fillna("")),
            "descricao": "Prorrogação de " + dias_po.map("{:.0f}".format) + " dias",
            "situacao": po.SIT_PRORROGA.str.capitalize(), "fim": data_br(po.DT_FIM_PRORROGA.fillna("")),
            "dias": dias_po, "valor": None, "solicitacao": None, "detalhe": None,
        }),
        pd.DataFrame({
            "id": "sa-" + sol.ID_SOLICITACAO, "nr": sol.NR_CONVENIO, "tipo": "Solicitação de alteração",
            "numero": sol.NR_SOLICITACAO, "data": sol.DATA_SOLICITACAO.str.slice(0, 10),
            "descricao": "Solicitação de alteração", "situacao": sol.SITUACAO_SOLICITACAO, "fim": None,
            "dias": None, "valor": None, "solicitacao": None, "detalhe": sol.OBJETO_SOLICITACAO.str.slice(0, 600),
        }),
    ])
    # O número do aditivo ou da prorrogação pode se repetir no mesmo instrumento; a data desempata
    prazos["id"] = prazos.id + "-" + prazos.data.fillna("")
    prazos.sort_values(["nr", "data", "id"], ascending=[True, False, True]).to_csv(DADOS / "prazos.csv", index=False)

    # --- histórico de situação: o Transferegov registra a situação a cada evento; aqui fica um
    # trecho por mudança, com o dia em que o instrumento entrou e saiu de cada situação
    hs = ler("siconv_historico_situacao", ["NR_CONVENIO", "DIA_HISTORICO_SIT", "HISTORICO_SIT"],
             filtro=lambda b: b[b.NR_CONVENIO.isin(acomp)])
    hs["quando"] = pd.to_datetime(hs.DIA_HISTORICO_SIT, format="%d/%m/%Y %H:%M:%S", errors="coerce")
    hs = hs.dropna(subset=["quando"]).sort_values(["NR_CONVENIO", "quando", "HISTORICO_SIT"])
    muda = (hs.HISTORICO_SIT != hs.groupby("NR_CONVENIO").HISTORICO_SIT.shift())
    tr = hs[muda].copy()
    tr["ate"] = tr.groupby("NR_CONVENIO").quando.shift(-1)
    fim_trecho = tr.ate.fillna(pd.Timestamp(data_carga))
    pd.DataFrame({
        "nr": tr.NR_CONVENIO,
        "inicio": tr.quando.dt.strftime("%Y-%m-%d"),
        "fim": tr.ate.dt.strftime("%Y-%m-%d"),
        "situacao": tr.HISTORICO_SIT.map(SITUACOES).fillna(tr.HISTORICO_SIT.str.replace("_", " ").str.capitalize()),
        "codigo": tr.HISTORICO_SIT,
        "dias": (fim_trecho.dt.normalize() - tr.quando.dt.normalize()).dt.days,
        "atual": tr.ate.isna(),
    }).to_csv(DADOS / "situacoes.csv", index=False)

    # --- notas de empenho do MDS, com o que já foi repassado por cada uma
    emp = ler("siconv_empenho", filtro=lambda b: b[b.NR_CONVENIO.isin(acomp)])
    emp["chave"] = emp.ID_EMPENHO + "-" + emp.CD_ORIGEM_EMPENHO
    ed = ler("siconv_empenho_desembolso", filtro=lambda b: b[(b.ID_EMPENHO + "-" + b.CD_ORIGEM_EMPENHO).isin(set(emp.chave))])
    rep_emp = ed.assign(valor=valor_br(ed.VALOR_GRUPO)).groupby(ed.ID_EMPENHO + "-" + ed.CD_ORIGEM_EMPENHO).valor.sum()
    nat = emp.NATUREZA_DESPESA.fillna("")
    notas = pd.DataFrame({
        "id": emp.chave, "nr": emp.NR_CONVENIO, "empenho": emp.NR_EMPENHO, "data": data_br(emp.DATA_EMISSAO.fillna("")),
        "tipo": emp.DESC_TIPO_NOTA, "situacao": emp.DESC_SITUACAO_EMPENHO,
        # 335041 -> 3.3.50.41; as notas antigas trazem o subelemento (44404109 -> 4.4.40.41.09)
        "natureza": nat.str.replace(r"^(\d)(\d)(\d\d)(\d\d)((?:\d\d)?)$", r"\1.\2.\3.\4.\5", regex=True).str.rstrip("."),
        "grupo": nat.str[0].map({"3": "Custeio", "4": "Investimento"}),
        "valor": valor_br(emp.VALOR_EMPENHO).round(2), "repassado": emp.chave.map(rep_emp).fillna(0).round(2),
        "observacao": emp.OBSERVACAO_EMPENHO.str.slice(0, 400),
    })
    # As notas do formato atual (origem NE, desde 2019) vêm só com o valor da emissão: os reforços e
    # anulações feitos depois no SIAFI não entram nos dados abertos, e muitas vêm zeradas. Nelas, o
    # empenhado é ao menos o que já foi repassado com a nota. As notas legadas trazem reforços e
    # anulações em linhas próprias e ficam como estão.
    notas["empenhado"] = notas.valor.where(emp.CD_ORIGEM_EMPENHO != "2", notas[["valor", "repassado"]].max(axis=1))
    notas.sort_values(["nr", "data", "empenho", "id"], ascending=[True, False, True, True]).to_csv(DADOS / "empenhos.csv", index=False)
    # Ordens bancárias sem nota ligada também saíram de algum empenho: o empenhado é ao menos o repassado
    ajuste = (notas.empenhado - notas.valor).groupby(notas.nr).sum()
    com_notas = inst.nr.isin(set(notas.nr))
    inst["vl_empenhado"] = (inst.vl_empenhado + inst.nr.map(ajuste).fillna(0)).round(2)
    inst.loc[com_notas, "vl_empenhado"] = inst.loc[com_notas, ["vl_empenhado", "vl_repassado"]].max(axis=1)
    inst.to_csv(DADOS / "instrumentos.csv", index=False)

    # --- pedidos para usar os rendimentos da aplicação financeira
    ra = ler("siconv_solicitacao_rendimento_aplicacao", filtro=lambda b: b[b.NR_CONVENIO.isin(acomp)])
    pd.DataFrame({
        "id": ra.ID_SOLICITACAO_REND_APLICACAO, "nr": ra.NR_CONVENIO,
        "numero": pd.to_numeric(ra.NR_SOLICITACAO_REND_APLICACAO, errors="coerce"),
        "data": ra.DATA_SOLICITACAO_REND_APLICACAO.str.slice(0, 10), "situacao": ra.STATUS_SOLICITACAO_REND_APLICACAO,
        "valor_solicitado": valor_br(ra.VALOR_SOLICITACAO_REND_APLICACAO).round(2),
        "valor_aprovado": valor_br(ra.VALOR_APROVADO_SOLICITACAO_REND_APLICACAO).round(2),
    }).sort_values(["nr", "numero", "id"]).to_csv(DADOS / "rendimentos.csv", index=False)

    # --- histórico do saldo: o Transferegov só dá o saldo do dia, então guardamos uma foto por carga
    hist_path = DADOS / "historico_saldo.csv"
    foto = inst.loc[inst.acompanhamento, ["nr", "data_carga", "vl_saldo_conta", "vl_repassado", "vl_pago"]]
    if hist_path.exists():
        hist = pd.read_csv(hist_path, dtype={"nr": str})
        hist = pd.concat([hist[hist.data_carga != data_carga], foto])
    else:
        hist = foto
    hist.sort_values(["data_carga", "nr"]).to_csv(hist_path, index=False)

    print(f"carga {data_carga}: {len(inst)} instrumentos, {len(acomp)} em acompanhamento, "
          f"{len(p)} pagamentos, {len(d)} repasses, {len(c)} parcelas, {len(m)} metas")
    for f in sorted(DADOS.glob("*.csv")):
        print(f"  {f.name}: {f.stat().st_size / 1e3:.0f} KB")


if __name__ == "__main__":
    main()
