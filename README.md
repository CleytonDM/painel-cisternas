# Painel Programa Cisternas

Painel por convênio e termo do Programa Cisternas (MDS, ações orçamentárias 8948 e 11V1). Mostra execução física e financeira, saldo em conta e alertas de cada instrumento.

**Painel publicado:** https://cleytondm.github.io/painel-cisternas/

## Como os dados chegam ao painel

Os dados vêm dos dados abertos do Transferegov, módulo Discricionárias. O Transferegov publica uma carga por dia em https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/.

Todo dia às 7h (horário de Brasília), o workflow [`atualizar.yml`](.github/workflows/atualizar.yml):

1. roda `atualizar_dados.py`, que baixa os arquivos `siconv_*.zip` e filtra os instrumentos do programa;
2. grava os CSVs do painel em `dados/` e faz commit deles quando mudam;
3. monta o site com `site/montar_site.py` e publica no GitHub Pages.

Para rodar fora do horário, use **Actions › Atualizar e publicar o painel › Run workflow**.

O Transferegov informa só o saldo do dia. Por isso o `dados/historico_saldo.csv` guarda uma foto do saldo de cada instrumento a cada carga, e o histórico fica no repositório.

## Arquivos

| Caminho | O que é |
| --- | --- |
| `atualizar_dados.py` | Baixa a carga do Transferegov e gera `dados/*.csv` (`--sem-download` reaproveita os zips de `brutos/`) |
| `dados/` | CSVs que o painel lê: instrumentos, pagamentos, repasses, cronograma, metas, tecnologias e o histórico do saldo |
| `painel/index.html` | O painel. É o mesmo arquivo usado na versão do painel no Claude |
| `site/` | Monta o painel como site estático: `dash.js` (runtime mínimo), `tema.css` e `montar_site.py` |

## Rodar localmente

```bash
pip install -r requirements.txt
python atualizar_dados.py
python site/montar_site.py
python -m http.server 8000 --directory _site
```

O CPF de pagamentos a pessoa física aparece mascarado. A marca do Programa Cisternas segue o manual de identidade visual do MDS.
