# tr_correlate_rules.ktr — Enriquecimento, correlação e motor de regras

## Objetivo
Transformar eventos isolados em **casos de segurança**: grupos de eventos relacionados por zona e proximidade temporal, com contexto (horários, permissões, estado do utilizador). Cada caso é classificado pelo motor de regras determinístico (abordagem A). A rastreabilidade é total: cada caso aponta para os eventos de origem (`case_event`).

## Entradas
`event` (152), `zone`, `app_user`, `user_zone_permission`. Parâmetros: `RUN_ID`, `CORRELATION_GAP_MIN` (5), `CORRELATION_MAX_SPAN_MIN` (20).

## 1. Enriquecimento
Table input (eventos) → **Stream lookup** (horário da zona) → **Stream lookup** (perfil do utilizador) → **Database lookup** (permissão utilizador×zona) → User Defined Java Expression (minutos do dia) → User Defined Java Expression (flags) → Insert/Update `event`

| Flag | Regra |
|---|---|
| `is_off_hours` | hora fora do horário da zona, ou fim de semana numa zona que não abre ao fim de semana |
| `is_outside_schedule` | hora fora do turno do utilizador. Suporta **turnos que atravessam a meia-noite** (ex. 20:00–08:00) |
| `is_unauthorized_zone` | acesso de um utilizador sem permissão para a zona |
| `is_unknown_user` | acesso sem utilizador identificado |
| `is_inactive_user` | utilizador desativado no IAM |

## 2. Correlação (sessionização)
**Sort rows** (zona, hora, ID) → **Modified JavaScript** com estado entre linhas:

```
novo caso  ⇐  zona diferente  OU  intervalo desde o evento anterior > 5 min  OU  duração do caso > 20 min
```

O limite de duração evita **associações em cadeia** (A–B a 4 min, B–C a 4 min, …), que uma janela simples criaria.

**Group by** por caso: início/fim (MIN/MAX), nº de eventos, utilizadores distintos (COUNT_DISTINCT), contagens de recusas/presença/fora de horas/sem permissão (SUM), primeira recusa e última presença (MIN/MAX), lista de IDs (CONCAT_COMMA) → User Defined Java Expression:
- `case_id` determinístico: `CASE-<zona>-<aaaammdd-hhmmss do início>`
- `events_hash` = MD5 da lista ordenada de IDs (chave de cache da IA)

**Rastreabilidade:** Stream lookup (evento → caso) → Block until steps finish (respeita a FK) → Table output `case_event`.

Os casos são reconstruídos em cada execução (`TRUNCATE security_case CASCADE`), numa única transação (*unique connections*). São determinísticos: a mesma entrada dá os mesmos IDs.

## 3. Motor de regras (abordagem A)

| Regra | Condição | Peso |
|---|---|---|
| R1 — Recusa seguida de presença | existe movimento/abertura de porta **depois** de um acesso recusado no mesmo caso | 3 |
| R2 — Acesso fora de horas | ≥1 tentativa de acesso com a zona fechada | 1 |
| R3 — Recusas repetidas | ≥3 acessos recusados no caso | 3 |
| R4 — Atividade sem permissão | ≥1 acesso **concedido** a uma zona sem permissão | 3 |

Pontuação = soma dos pesos. Risco: ≥6 CRITICAL, ≥3 HIGH, 2 MEDIUM, 1 LOW, 0 NONE. Suspeito se pontuação ≥1.

## Resultado verificado (2026-10-19)
- 152 eventos → **82 casos**; 152 ligações em `case_event` (cada evento num só caso).
- Os 15 cenários de teste ficaram cada um num caso próprio, sem mistura com outros eventos.
- 2.ª execução: flags com U=0; os mesmos 82 `case_id`.

**Desempenho das regras face ao ground truth (nível de caso):**

| TP | FP | TN | FN | Precisão | Recall |
|---|---|---|---|---|---|
| 6 | 5 | 70 | 1 | 0,55 | 0,86 |

- **FN:** S04 (movimento noturno sem acesso). Nenhuma regra cobre presença sem acesso.
- **FP:** B01 (cartão mal lido → R1), B02/B03/B04/B05 (fora de horas mas legítimos → R2). As regras não usam o contexto do turno nem o papel do utilizador.

Estes erros não foram afinados de propósito: o objetivo é comparar com a análise contextual da IA (abordagem B) sem enviesar a avaliação.

## Como testar
```bash
./scripts/pdi.sh pan etl/transformations/tr_correlate_rules.ktr
./scripts/sql.sh -c "select case_id, event_count, matched_rules, risk_level from security_case join rule_result using(case_id) where is_suspicious"
```
