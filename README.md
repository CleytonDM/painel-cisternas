# Painel Programa Cisternas

Painel por convênio e termo do Programa Cisternas (MDS, ações orçamentárias 8948 e 11V1). Mostra execução física e financeira, saldo em conta e alertas de cada instrumento.

**Painel publicado:** https://cleytondm.github.io/painel-cisternas/

## Como os dados chegam ao painel

Os dados vêm dos dados abertos do Transferegov, módulo Discricionárias. O Transferegov publica uma carga por dia em https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/.

A carga sai por volta das 8h15 (horário de Brasília). Quando há carga nova, o workflow [`atualizar.yml`](.github/workflows/atualizar.yml):

1. roda `atualizar_dados.py`, que baixa os arquivos `siconv_*.zip` e filtra os instrumentos do programa;
2. grava os CSVs do painel em `dados/` e faz commit deles quando mudam;
3. monta o site com `site/montar_site.py` e publica no GitHub Pages.

### Quando roda

- **Disparo principal (cron-job.org), às 9h e às 10h de Brasília.** O agendamento do próprio GitHub atrasa horas e às vezes pula horários; já o disparo pela API começa em segundos. O cron-job.org chama a API com a opção `vigiar`: o workflow espera a carga do dia aparecer (consulta a cada 5 minutos, até as 13h) e só então baixa. Às 10h, se a carga já entrou, ele só confere e encerra.
- **Reserva (agendamento do GitHub):** de hora em hora das 3h30 às 8h30, e às 12h37, 16h37 e 20h37. Cada execução só baixa se a carga mudou.

Configuração do cron-job.org (um job com os horários 9h e 10h, fuso America/Sao_Paulo):

| Campo | Valor |
| --- | --- |
| URL | `https://api.github.com/repos/CleytonDM/painel-cisternas/actions/workflows/atualizar.yml/dispatches` |
| Método | `POST` |
| Cabeçalhos | `Accept: application/vnd.github+json`, `Authorization: Bearer <token>`, `X-GitHub-Api-Version: 2022-11-28`, `Content-Type: application/json`, `User-Agent: painel-cisternas-cron` |
| Corpo | `{"ref": "main", "inputs": {"vigiar": "true"}}` |
| Resposta esperada | `204 No Content` |

O token é um *fine-grained personal access token* do GitHub com acesso só a este repositório e só à permissão **Actions: Read and write**. Ele vence: renove antes da data de validade, ou o disparo passa a responder `401`.

Para rodar à mão, use **Actions › Atualizar e publicar o painel › Run workflow** (marque "Esperar a carga nova" para aguardar a publicação do dia).

O Transferegov informa só o saldo do dia. Por isso o `dados/historico_saldo.csv` guarda uma foto do saldo de cada instrumento a cada carga, e o histórico fica no repositório.

## Arquivos

| Caminho | O que é |
| --- | --- |
| `atualizar_dados.py` | Baixa a carga do Transferegov e gera `dados/*.csv` (`--sem-download` reaproveita os zips de `brutos/`) |
| `dados/` | CSVs que o painel lê: instrumentos, pagamentos, repasses, cronograma, metas, tecnologias, execução (parcela × NE × OB), empenhos e o histórico do saldo |
| `referencias/modelos_tecnologia.csv` | Nº e nome resumido dos modelos de tecnologia social (SIG Cisternas), usados na Tabela 2 |
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
