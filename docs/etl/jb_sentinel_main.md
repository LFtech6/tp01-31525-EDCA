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
      → Stage: notify (SQL) → Build notification → Attach exports → Send summary e-mail (SMTP) → Stage: notify done
            (falha em qualquer destes três → Stage: notify failed, e a execução continua)
      → Finish run (SQL) → Log summary (Write to log) → Success

qualquer entrada falhada → Mark run failed (SQL) → Build alert → Send alert e-mail (SMTP) → Stage: alert sent → Abort  (exit code ≠ 0)
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
| Build notification / Build alert | Transformation (`tr_build_notification.ktr`) | lê a BD (`etl/sql/notification_message.sql`) e compõe assunto + corpo HTML; *Set variables* → `MAIL_SUBJECT`, `MAIL_BODY` (âmbito do Job) |
| Attach exports | Add filenames to result | limpa a lista de ficheiros do resultado e junta `incidents.csv` e `metrics.csv` |
| Send summary e-mail / Send alert e-mail | Mail | SMTP autenticado (`${SMTP_HOST}:${SMTP_PORT}`, `${SMTP_USER}`/`${SMTP_PASSWORD}`), de `${MAIL_FROM}` para `${MAIL_TO}`, HTML UTF-8; o resumo leva os 2 anexos |

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

## Notificação por e-mail (SMTP)
O enunciado (Fase 3) pede "envio automático de relatórios, resumos ou alertas de erro por e-mail". O Job envia:
- **Resumo** (execução sem falhas): contagens por etapa (eventos, rejeições, casos, suspeitos por regras e por IA, falhas de IA), tabela regras vs IA (TP/FP/TN/FN, precisão, recall, F1), os 15 incidentes prioritários e, em anexo, `incidents.csv` e `metrics.csv`.
- **Alerta de erro** (execução FAILED): a etapa que falhou, a mensagem de erro e o caminho do log do Kitchen.

Decisões:
- A notificação faz-se **depois** da persistência e exportação. Se o envio falhar (por exemplo, SMTP indisponível), a etapa `NOTIFY` fica FAILED com o motivo, mas a execução termina SUCCEEDED: os dados já estão corretos e o e-mail não deve invalidá-los.
- No ramo de erro, o alerta é enviado na medida do possível: o *Abort* acontece sempre e o exit code continua ≠ 0.
- Servidor, credenciais e endereços vêm do `.env` (→ `kettle.properties`). O `.kjb` só contém `${SMTP_PASSWORD}`.
- A configuração segue o exemplo da aula 06 (`EmailPrevisão.kjb`). Uma transformação põe o corpo HTML numa variável (*Set variables*) e a entrada **Mail** usa-a como mensagem (`only_comment`, HTML, UTF-8). O envio é feito por um **servidor SMTP real** com autenticação segura **TLS** na porta 587 (por omissão `smtp.office365.com`, a conta institucional). Diferença em relação ao exemplo: aqui as variáveis têm âmbito `ROOT_JOB` em vez de `JVM`, para não ficarem visíveis a outros Jobs na mesma JVM.
- A conta e os destinatários podem vir de duas origens:
  - do `.env`, por omissão;
  - do **dashboard** (página Controlo → "Notificação por e-mail"). O formulário envia-os para `PUT /ops/mail-settings` (protegido com `X-API-Key`).
- Como a API trata a configuração vinda do dashboard:
  - valida-a, incluindo endereços e destinatários (1 a 10), e recusa quebras de linha e caracteres de comando;
  - guarda-a **só em memória**: perde-se ao reiniciar a API, que volta a usar o `.env`;
  - **nunca devolve a password**: o GET só indica `password_set`.
- Na execução seguinte, a configuração chega ao Kitchen por variáveis de ambiente (`OVERRIDE_*`, aplicadas por `scripts/kettle_env.sh`). Nunca passa pela linha de comandos.
- No Office 365 o remetente tem de ser a própria conta.

Limitação conhecida: se a própria BD estiver indisponível, `Build alert` não consegue compor a mensagem. O alerta é enviado na mesma, mas com o corpo por compor (`${MAIL_BODY}`); a causa fica no log do Kitchen.

### Resultado verificado
2026-10-21, servidor real `smtp.office365.com:587`:
| Caso | Resultado |
|---|---|
| Ligação ao servidor | STARTTLS anunciado; após TLS, o servidor aceita `AUTH LOGIN` |
| Execução com credenciais por preencher (`run-20261021-094000-b001`) | exit 0; execução SUCCEEDED; `NOTIFY` FAILED com `AuthenticationFailedException: 535 5.7.3` (o TLS funcionou e o servidor recusou as credenciais `change_me`) |
| Configuração vinda do dashboard (`run-20261021-122829-6806`, servidor `smtp.gmail.com`, credenciais falsas) | o Pentaho usou os valores do formulário: `535-5.7.8 Username and Password not accepted` (Gmail); a password não aparece no log do Kitchen |
| Execução com a conta real | por executar pelo estudante |

2026-10-20, versão anterior com servidor SMTP local de testes (entretanto removido). Valida a lógica do Job, que é independente do servidor:
| Caso | Resultado |
|---|---|
| Execução normal (`run-20261020-120000-a001`) | exit 0; `NOTIFY` SUCCEEDED; e-mail "Resumo da execução …: 13 incidentes (8 de risco alto/crítico)" recebido com `incidents.csv` (10 363 B) e `metrics.csv` |
| Servidor SMTP parado (`run-20261020-120500-a002`) | exit 0; execução SUCCEEDED; `NOTIFY` FAILED ("servidor SMTP indisponível…"); `MailConnectException: Connection refused` no log |
| Falha forçada na exportação (ficheiros só de leitura, `run-20261020-121000-a003`) | exit 1; execução FAILED; `EXPORT` FAILED; e-mail "ALERTA: a execução … falhou" recebido com a etapa e o log |
| Pelo dashboard (`/ops`, `run-20261020-115947-9ed2`) | 7 etapas SUCCEEDED, incluindo `NOTIFY`; e-mail com 2 anexos |
