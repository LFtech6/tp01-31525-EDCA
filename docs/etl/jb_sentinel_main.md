# jb_sentinel_main.kjb — Orquestração

## Objetivo
Executar o processo completo de forma reprodutível e observável, com registo de cada etapa (consultado pelo dashboard), logs nativos do Kettle e tratamento de falhas.

## Parâmetros
`RUN_ID` (identificador único; passado a todas as transformações) e `TRIGGER` (`cli`, `dashboard`, `schedule`).

## Fluxo
```
START → Register run (SQL) → Load reference data → Extract events → Stage (SQL) → Correlate and apply rules
      → Stage (SQL) → AI service available? (GET ${API_URL}/ai/health)
            ├── sim → AI analysis → Stage: AI done ──┐
            └── não → Stage: AI skipped ─────────────┴→ Evaluate approaches → Stage → Export incidents
      → Finish run (SQL) → Log summary (Write to log) → Success

qualquer entrada falhada → Mark run failed (SQL) → Abort  (exit code ≠ 0)
```

| Entrada | Tipo | Função |
|---|---|---|
| Register run | SQL | `etl_run` em RUNNING (upsert por `RUN_ID`); início da etapa EXTRACT |
| Load reference data / Extract events / … | Transformation | executa o `.ktr`, passando todos os parâmetros |
| Stage: … | SQL | fecha a etapa anterior (estado, nº de linhas) e abre a seguinte em `etl_run_stage` |
| AI service available? | Check webservice availability | decide entre analisar e marcar a etapa AI como SKIPPED |
| Mark run failed | SQL | etapa ativa e execução ficam FAILED, com mensagem |
| Abort | Abort job | termina com erro (exit code ≠ 0) |
| Log summary | Write to log | mensagem final no log |

## Logs
- `etl_run` / `etl_run_stage`: estado funcional (PENDING/RUNNING/SUCCEEDED/FAILED/SKIPPED, duração, nº de linhas).
- `log_job`: **tabela de log nativa do Kettle** (configurada no Job).
- `results/logs/<RUN_ID>.log`: log completo do Kitchen (`scripts/run_pipeline.sh`).

## Concorrência
No máximo uma execução ativa: índice único parcial em `etl_run (status IN ('PENDING','RUNNING'))`. Uma segunda execução falha logo no registo.

## Execução e resultado verificado (2026-10-19)
```bash
./scripts/run_api.sh &            # gateway REST + IA
./scripts/run_pipeline.sh         # RUN_ID automático
```
| Execução | Resultado |
|---|---|
| `run-test-001` | Falhou na avaliação (erro no Text file output) → EVALUATE = FAILED, execução FAILED, Abort, exit 1 — **caminho de falha validado** |
| `run-20261019-001` | exit 0; 6 etapas SUCCEEDED; ~15 s (IA em cache); exportações geradas; `log_job` preenchido |
