# Plano de implementação — Sentinel-AI

Modo de trabalho: o estudante executa e constrói (≥70%); o Claude guia passo a passo, escreve documentação/relatório e código de suporte.
Uma etapa só está concluída quando o critério de aceitação foi **executado e observado**.

## MVP obrigatório

| # | Etapa | Data alvo | Critério objetivo de conclusão | Estado |
|---|---|---|---|---|
| 0 | Ambiente + estrutura | 14/10 | `check_env.sh` sem falhas; Spoon abre um `.ktr` das aulas legível | Spoon por confirmar |
| 1 | Base de dados | 14/10 | schema corre 2× sem erro; 15 tabelas; `sentinel_ro` lê mas não escreve | ✅ verificado |
| 1b | Ollama + modelo | 16/10 | `ollama list` mostra `0edcdef34593`; inferência estruturada responde | modelo ✅ / teste por fazer |
| 2 | Dados de referência + 1.ª transformação | 16/10 | `tr_load_reference` corre no Spoon e no Pan; contagens conferidas por SQL; 2.ª execução não duplica | |
| 3 | Gerador de cenários + datasets de eventos | 17/10 | ficheiros determinísticos; `ground_truth.csv` por evento | |
| 4 | Extração CSV / syslog / REST | 17–18/10 | eventos em `event`, rejeições em `dq_rejection` com motivo | |
| 5 | Enriquecimento + correlação + regras | 18/10 | casos com eventos de origem; regras por caso | |
| 6 | FastAPI `/gateway` + `/ai` + transformação IA | 18–19/10 | pytest passa (incl. timeout/JSON inválido); `ai_analysis` preenchida | |
| 7 | Job principal | 19/10 | `kitchen.sh` exit 0; reexecução sem duplicados; com Ollama parado termina e regista falha | |
| 8 | Avaliação + exportações | 19–20/10 | P/R/F1 por abordagem; JSON/CSV em `results/exports` | |

## Extensão visual (após MVP)

| # | Etapa | Data alvo | Critério |
|---|---|---|---|
| 9 | API `/ops` | 20/10 | lançar Job, 409 em execução simultânea, 401 sem token, log consultável |
| 10 | Node-RED + FlowFuse Dashboard | 20–21/10 | botão executa ETL; estado/etapas; eventos; incidentes + explicação IA; logs; estatísticas |
| 11 | Simulação de evento | 21/10 (se houver tempo) | evento do formulário aparece em `event` após a execução seguinte |
| 11b | Notificação por e-mail (SMTP) | 20/10 | resumo com anexos em sucesso; alerta em falha; SMTP em baixo não falha a execução |

## Fecho

| # | Etapa | Data | Critério |
|---|---|---|---|
| 12 | Relatório, diagramas, vídeo | 21/10 | 8 secções do enunciado; QR para o vídeo |
| 13 | Entrega | 22/10 | README com execução do zero; repositório limpo |

Regra de corte: se o prazo apertar, prevalece motor completo + painel Node-RED simples.
