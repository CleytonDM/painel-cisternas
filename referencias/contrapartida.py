"""Planilha da contrapartida por natureza de despesa (investimento e custeio) de cada parceria.

Os dados abertos do Transferegov não dizem em que natureza entra a contrapartida do parceiro; a área
de negócio preenche a divisão a partir do plano de trabalho, e o painel passa a usá-la no lugar da regra.

    python referencias/contrapartida.py gerar      # cria referencias/contrapartida_natureza.xlsx
    python referencias/contrapartida.py importar   # grava a planilha preenchida em contrapartida_natureza.csv

"gerar" lista as parcerias com contrapartida em que o painel ainda depende da regra (e as já informadas),
com os valores já gravados no CSV. "importar" confere cada linha preenchida com a contrapartida atual
do Transferegov e só grava as que somam certo.
"""
import sys
from datetime import date
from pathlib import Path

import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

RAIZ = Path(__file__).resolve().parent.parent
CSV = RAIZ / "referencias" / "contrapartida_natureza.csv"
XLSX = RAIZ / "referencias" / "contrapartida_natureza.xlsx"
CAMPOS_CSV = ["nr", "investimento", "custeio", "documento", "data_documento", "responsavel", "observacao"]
TOLERANCIA = 1.0  # R$: investimento + custeio tem de bater com a contrapartida do Transferegov

# colunas da aba de preenchimento: (cabeçalho, largura, preenchida pela área de negócio?)
COLUNAS = [
    ("Nº do instrumento", 13, False), ("Parceiro", 42, False), ("UF", 5, False), ("Situação", 26, False),
    ("Contrapartida no Transferegov (R$)", 18, False),
    ("Investimento (R$)", 17, True), ("Custeio, com ISS (R$)", 17, True),
    ("Soma (R$)", 17, False), ("Diferença (R$)", 15, False), ("Conferência", 24, False),
    ("Documento de origem", 38, True), ("Data do documento", 13, True), ("Responsável", 20, True),
    ("Observação", 40, True),
]
LINHA_CAB = 4

FONTE = "Arial"
AZUL = Font(name=FONTE, color="0000FF")
PRETO = Font(name=FONTE)
NEGRITO = Font(name=FONTE, bold=True)
BRANCO = Font(name=FONTE, bold=True, color="FFFFFF")
AMARELO = PatternFill("solid", fgColor="FFF2CC")
CINZA = PatternFill("solid", fgColor="F2F2F2")
CABECALHO = PatternFill("solid", fgColor="1F4E79")
FINA = Side(style="thin", color="BFBFBF")
BORDA = Border(left=FINA, right=FINA, top=FINA, bottom=FINA)
MOEDA = '#,##0.00;-#,##0.00;"-"'


def brl(v):
    """1234567.8 -> '1.234.567,80'"""
    return f"{v:,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")


def numero(v):
    """Valor da célula: número, ou texto no padrão brasileiro ('1.234,56', 'R$ 1.234,56')."""
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).replace("R$", "").replace(" ", "").replace(" ", "")
    return float(t.replace(".", "").replace(",", ".") if "," in t else t)


def ler_csv():
    ref = pd.read_csv(CSV, dtype=str).fillna("")
    for c in CAMPOS_CSV:
        if c not in ref:
            ref[c] = ""
    return ref[CAMPOS_CSV].set_index("nr")


def ler_dados():
    inst = pd.read_csv(RAIZ / "dados" / "instrumentos.csv", dtype={"nr": str})
    nat = pd.read_csv(RAIZ / "dados" / "natureza.csv", dtype={"nr": str})
    regra = nat[nat.linha == "contrapartida"].set_index("nr").regra
    inst["regra"] = inst.nr.map(regra)
    return inst


def gerar():
    inst, ref = ler_dados(), ler_csv()
    # parcerias com contrapartida em que a divisão não sai dos dados (regra) ou já foi informada
    alvo = inst[(inst.vl_contrapartida >= 1) & (inst.regra.isin(["custeio primeiro", "proporcional", "informada"])
                                                | inst.nr.isin(ref.index))].copy()
    alvo["ordem"] = (alvo.situacao != "Em execução").astype(int)
    alvo = alvo.sort_values(["ordem", "vl_contrapartida"], ascending=[True, False])

    wb = Workbook()
    ws = wb.active
    ws.title = "Contrapartida"
    ws["A1"] = "Contrapartida do parceiro por natureza de despesa"
    ws["A1"].font = Font(name=FONTE, bold=True, size=14)
    ws["A2"] = (f"Gerada em {date.today():%d/%m/%Y} a partir da carga do Transferegov de "
                f"{pd.to_datetime(inst.data_carga.iloc[0]):%d/%m/%Y}. Preencha só as células amarelas; "
                "veja a aba Instruções.")
    ws["A2"].font = Font(name=FONTE, italic=True, color="595959")

    for c, (cab, larg, entrada) in enumerate(COLUNAS, 1):
        cel = ws.cell(LINHA_CAB, c, cab)
        cel.font, cel.fill, cel.border = BRANCO, CABECALHO, BORDA
        cel.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        ws.column_dimensions[get_column_letter(c)].width = larg
    ws.row_dimensions[LINHA_CAB].height = 45

    for r, i in enumerate(alvo.itertuples(), LINHA_CAB + 1):
        dado = ref.loc[i.nr] if i.nr in ref.index else None
        num = lambda campo: float(dado[campo]) if dado is not None and dado[campo] != "" else None
        txt = lambda campo: dado[campo] if dado is not None else ""
        valores = [
            i.nr, i.parceiro, i.uf, i.situacao, round(float(i.vl_contrapartida), 2),
            num("investimento"), num("custeio"),
            f'=IF(AND(F{r}="",G{r}=""),"",N(F{r})+N(G{r}))',
            f'=IF(H{r}="","",ROUND(E{r}-H{r},2))',
            f'=IF(H{r}="","A preencher",IF(OR(F{r}="",G{r}=""),"Preencha os dois valores",'
            f'IF(ABS(I{r})<={TOLERANCIA},"OK","Soma difere da contrapartida")))',
            txt("documento"),
            pd.to_datetime(txt("data_documento")).date() if txt("data_documento") else None,
            txt("responsavel"), txt("observacao"),
        ]
        for c, v in enumerate(valores, 1):
            cel = ws.cell(r, c, v)
            cel.border = BORDA
            entrada = COLUNAS[c - 1][2]
            cel.font = AZUL if entrada else PRETO
            if entrada:
                cel.fill = AMARELO
            elif c <= 5:
                cel.fill = CINZA
            if c in (5, 6, 7, 8, 9):
                cel.number_format = MOEDA
            if c == 12:
                cel.number_format = "dd/mm/yyyy"
            if c in (2, 11, 14):
                cel.alignment = Alignment(wrap_text=True, vertical="top")
    ultima = LINHA_CAB + len(alvo)

    faixa = f"J{LINHA_CAB + 1}:J{ultima}"
    ws.conditional_formatting.add(faixa, CellIsRule(operator="equal", formula=['"OK"'],
                                                    fill=PatternFill("solid", fgColor="C6EFCE"), font=Font(name=FONTE, color="006100")))
    ws.conditional_formatting.add(faixa, CellIsRule(operator="equal", formula=['"Soma difere da contrapartida"'],
                                                    fill=PatternFill("solid", fgColor="FFC7CE"), font=Font(name=FONTE, color="9C0006")))
    ws.conditional_formatting.add(faixa, CellIsRule(operator="equal", formula=['"Preencha os dois valores"'],
                                                    fill=PatternFill("solid", fgColor="FFEB9C"), font=Font(name=FONTE, color="9C5700")))
    valor = DataValidation(type="decimal", operator="greaterThanOrEqual", formula1="0", allow_blank=True,
                           error="Informe um valor em reais, maior ou igual a zero.", errorTitle="Valor inválido")
    valor.add(f"F{LINHA_CAB + 1}:G{ultima}")
    data = DataValidation(type="date", operator="greaterThan", formula1="36526", allow_blank=True,
                          error="Informe uma data (dd/mm/aaaa).", errorTitle="Data inválida")
    data.add(f"L{LINHA_CAB + 1}:L{ultima}")
    ws.add_data_validation(valor)
    ws.add_data_validation(data)
    ws.freeze_panes = ws.cell(LINHA_CAB + 1, 3)
    ws.auto_filter.ref = f"A{LINHA_CAB}:{get_column_letter(len(COLUNAS))}{ultima}"

    instrucoes(wb.create_sheet("Instruções"))
    wb.calculation.fullCalcOnLoad = True  # o openpyxl não calcula as fórmulas; o Excel calcula ao abrir
    wb.save(XLSX)
    print(f"{XLSX.relative_to(RAIZ)}: {len(alvo)} parcerias "
          f"({(alvo.situacao == 'Em execução').sum()} em execução; {alvo.nr.isin(ref.index).sum()} já preenchidas)")


def instrucoes(ws):
    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 100
    linhas = [
        ("Para que serve", "Os dados abertos do Transferegov informam só o total da contrapartida do parceiro, sem dizer quanto "
         "vai para investimento e quanto para custeio. Sem essa divisão, o painel estima por regra quanto o MDS ainda tem a "
         "empenhar em cada natureza (Tabelas 4 e 5). Com a divisão preenchida aqui, o painel passa a usar o valor informado."),
        ("O que preencher", "Só as células amarelas (texto azul) da aba Contrapartida: Investimento, Custeio, Documento de "
         "origem, Data do documento, Responsável e Observação. As colunas cinza vêm do Transferegov e as demais são calculadas."),
        ("Investimento", "Parte da contrapartida na natureza 449039 (GND 4)."),
        ("Custeio", "Parte da contrapartida nas naturezas 339039 e 339047 (GND 3), com o ISS incluído."),
        ("Conferência", "Investimento + Custeio tem de ser igual à contrapartida no Transferegov (tolerância de R$ 1,00). "
         "Se a contrapartida mudou por termo aditivo, use a divisão do plano de trabalho vigente. Linhas com soma "
         "diferente não são importadas."),
        ("Onde achar a divisão", "No plano de trabalho vigente (relatório do Transferegov): (1) no item \"Cronograma de "
         "desembolso\" do convenente, veja a que metas vai cada parcela de contrapartida; (2) no \"Plano de trabalho\" "
         "(etapas) ou no \"Plano de aplicação detalhado\", veja quanto de cada meta é custeio, ISS e investimento. Itens "
         "do plano de aplicação marcados como contrapartida dão a divisão exata. Quando a meta mistura recursos do MDS e "
         "do parceiro, divida a contrapartida na proporção das naturezas da própria meta e registre isso em Observação. "
         "Notas técnicas de análise do plano também podem trazer a divisão."),
        ("Documento de origem", "Nº SEI e nome do documento usado (ex.: SEI 19405383 – Plano de Trabalho)."),
        ("Linha de exemplo", "O convênio 956085 (Ceará) já está preenchido com a divisão extraída do plano de trabalho "
         "SEI 19405383: serve de modelo de formato."),
        ("Depois de preencher", "Devolva a planilha; ela é importada para referencias/contrapartida_natureza.csv e o painel "
         "usa os valores na próxima atualização. Deixar uma linha em branco mantém a regra do painel para aquela parceria."),
    ]
    ws["A1"] = "Instruções de preenchimento"
    ws["A1"].font = Font(name=FONTE, bold=True, size=14)
    for r, (titulo, texto) in enumerate(linhas, 3):
        ws.cell(r, 1, titulo).font = NEGRITO
        ws.cell(r, 2, texto).font = PRETO
        for c in (1, 2):
            ws.cell(r, c).alignment = Alignment(wrap_text=True, vertical="top")


def importar(caminho=XLSX):
    inst = ler_dados().set_index("nr")
    ws = load_workbook(caminho)["Contrapartida"]  # valores digitados; as fórmulas não são usadas
    cab = {ws.cell(LINHA_CAB, c).value: c for c in range(1, ws.max_column + 1)}
    pega = lambda r, nome: ws.cell(r, cab[nome]).value
    ref = ler_csv()
    gravadas, removidas, recusadas = [], [], []
    for r in range(LINHA_CAB + 1, ws.max_row + 1):
        nr = pega(r, "Nº do instrumento")
        if nr is None:
            continue
        nr = str(nr).strip().split(".")[0]
        inv, cus = pega(r, "Investimento (R$)"), pega(r, "Custeio, com ISS (R$)")
        if inv in (None, "") and cus in (None, ""):
            if nr in ref.index:
                ref = ref.drop(nr)
                removidas.append(nr)
            continue
        try:
            inv, cus = round(numero(inv), 2), round(numero(cus), 2)
        except (TypeError, ValueError):
            recusadas.append(f"{nr}: valor não numérico")
            continue
        if nr not in inst.index:
            recusadas.append(f"{nr}: instrumento fora do painel")
            continue
        cp = round(float(inst.loc[nr, "vl_contrapartida"]), 2)
        if abs(inv + cus - cp) > TOLERANCIA:
            recusadas.append(f"{nr}: investimento + custeio = R$ {brl(inv + cus)}, contrapartida atual = R$ {brl(cp)}")
            continue
        data = pega(r, "Data do documento")
        data = data.strftime("%Y-%m-%d") if hasattr(data, "strftime") else (str(data).strip() if data else "")
        texto = lambda nome: str(pega(r, nome) or "").strip()
        ref.loc[nr] = [f"{inv:.2f}", f"{cus:.2f}", texto("Documento de origem"), data,
                       texto("Responsável"), texto("Observação")]
        gravadas.append(nr)
    ref.sort_index().reset_index().to_csv(CSV, index=False, lineterminator="\n")
    print(f"Gravadas {len(gravadas)}: {', '.join(gravadas) or '-'}")
    print(f"Removidas (linha em branco) {len(removidas)}: {', '.join(removidas) or '-'}")
    for m in recusadas:
        print("Recusada:", m)
    return not recusadas


if __name__ == "__main__":
    acao = sys.argv[1] if len(sys.argv) > 1 else ""
    if acao == "gerar":
        gerar()
    elif acao == "importar":
        sys.exit(0 if importar(Path(sys.argv[2]) if len(sys.argv) > 2 else XLSX) else 1)
    else:
        sys.exit(__doc__)
