"""Monta o site estático do Painel Cisternas em _site/ (publicado no GitHub Pages).

O painel é o mesmo painel/index.html usado no Claude. Aqui ele ganha um documento HTML
completo, os tokens de tema (tema.css), o d3 e uma versão mínima do runtime de painéis
(dash.js), que lê os CSVs de dados/.

Uso: python site/montar_site.py
"""
import csv
import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
SAIDA = RAIZ / "_site"

GOTA = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E"
        "%3Cpath d='M32 4C40 20 54 32 54 44A22 22 0 0 1 10 44C10 32 24 20 32 4Z' fill='%231B6086'/%3E%3C/svg%3E")


def main():
    painel = (RAIZ / "painel" / "index.html").read_text(encoding="utf-8")
    painel = painel.replace('<meta name="dash-one-writer">\n', "")
    # No Claude cada <script> do painel roda no seu próprio escopo; aqui um bloco faz o mesmo
    painel = re.sub(r"<script>(.*?)</script>", r"<script>{\1}</script>", painel, flags=re.S)
    versao = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    # data de referência da carga do Transferegov em uso; o site é remontado a cada carga nova
    with open(RAIZ / "dados" / "instrumentos.csv", encoding="utf-8") as f:
        carga = datetime.strptime(next(csv.DictReader(f))["data_carga"][:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    # hora da última consulta ao Transferegov, gravada em UTC pelo workflow; Brasília é UTC-3 o ano todo
    verificacao = ""
    arq = RAIZ / "dados" / "verificacao.csv"
    if arq.exists():
        with open(arq, encoding="utf-8") as f:
            quando = datetime.strptime(next(csv.DictReader(f))["verificado_em"], "%Y-%m-%dT%H:%M:%SZ") - timedelta(hours=3)
        verificacao = f" Última verificação: {quando:%d/%m/%Y}, às {quando:%H:%M} (horário de Brasília)."

    html = f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Painel Programa Cisternas</title>
<meta name="description" content="Execução física e financeira, saldo em conta e alertas dos convênios e termos do Programa Cisternas (MDS), com dados abertos do Transferegov atualizados todo dia.">
<link rel="icon" href="{GOTA}">
<link rel="stylesheet" href="tema.css?v={versao}">
<script src="https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js"></script>
<script>window.CIS_VERSAO = '{versao}';</script>
<script src="dash.js?v={versao}"></script>
</head>
<body>
<div id="dash-root">
{painel}
<footer class="site-rodape">
  Dados abertos do Transferegov (módulo Discricionárias), disponíveis até {carga}.{verificacao}<br>
  O painel consulta o Transferegov todo dia, a partir das 9h, e se atualiza assim que uma carga nova é publicada.
  A publicação dos dados abertos pelo Transferegov pode atrasar um ou mais dias; enquanto isso, o painel mostra a carga mais recente disponível.
</footer>
</div>
<script>dash.iniciar();</script>
</body>
</html>
"""
    if SAIDA.exists():
        shutil.rmtree(SAIDA)
    (SAIDA / "dados").mkdir(parents=True)
    (SAIDA / "index.html").write_text(html, encoding="utf-8")
    for nome in ("dash.js", "tema.css"):
        shutil.copy(AQUI / nome, SAIDA / nome)
    for arq in sorted((RAIZ / "dados").glob("*.csv")):
        shutil.copy(arq, SAIDA / "dados" / arq.name)
    (SAIDA / ".nojekyll").touch()
    print(f"site em {SAIDA} ({len(html) / 1e3:.0f} KB de página, versão {versao})")


if __name__ == "__main__":
    main()
