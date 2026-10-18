# tr_extract_events.ktr — Extração e normalização de eventos

## Objetivo
Integrar os eventos de duas fontes heterogéneas num modelo único (`event`), garantindo limpeza, validação e rastreabilidade. Os registos inválidos não se perdem: ficam em `dq_rejection` com o motivo da rejeição.

## Entradas
| Fonte | Formato / protocolo | Registos |
|---|---|---|
| Controlo de acessos | CSV (`data/raw/access_logs.csv`) | 99 linhas (6 duplicadas, 5 inválidas) |
| Gateway de sensores | **API REST** `GET ${API_URL}/gateway/sensors/events` → JSON | 79 documentos (4 duplicados, 9 sem deteção, 2 inválidos) |
| Referência | PostgreSQL (`device`, `app_user`) | lookups |

Parâmetro: `RUN_ID` (por omissão `manual`), passado pelo Job.

## Fluxo

**Acessos:** CSV file input → String operations (trim, maiúsculas) → Unique rows (HashSet) → Replace in string (**Regex**: dígitos do utilizador; `dd/MM/yyyy` → `yyyy-MM-dd`) → Replace in string (**Regex**: separador ISO `T`) → Value mapper (estado → tipo de evento) → Database lookup (porta → zona) → User Defined Java Expression (validação) → Filter rows → String operations (padding) → Calculator (`U` + dígitos) → Select values (texto → Date, **com tratamento de erros**) → Database lookup (utilizador existe?) → Get variables (`RUN_ID`) → Select values (schema final) → Insert/Update `event`

**Sensores:** Generate rows → Calculator (cabeçalho) → **REST Client (GET)** → JSON input (JSONPath `$[*].campo`) → String operations → Unique rows (HashSet) → Replace in string (**Regex** ISO 8601 com/sem fuso) → Value mapper (`true`/`1`/`on` → deteção) → Filter rows (só deteções) → Database lookup (sensor → zona) → User Defined Java Expression (validação) → Filter rows → Calculator → Select values (Date, com tratamento de erros) → Get variables → Select values → Insert/Update `event`

**Rejeições:** 4 entradas (2 filtros de validação + 2 *error hops* de conversão de data) → User Defined Java Expression (registo original + motivo) → Select values (schema comum) → Get variables → Table output `dq_rejection`. Um step *Execute SQL* limpa as rejeições anteriores do mesmo `RUN_ID`, para a reexecução não duplicar.

## Regras de transformação

| Problema | Exemplo | Regra |
|---|---|---|
| ID de evento em minúsculas | `acc0066` | String operations: maiúsculas → `ACC0066` |
| Utilizador mal formatado | `u-41`, ` U012 `, `user15` | Regex `[^0-9]` → padding 3 → `U041`, `U012`, `U015` (o valor original fica em `raw_user_ref`) |
| Datas em 3 formatos | `14/10/2026 02:13:00`, `2026-10-14T02:13:00`, `2026-10-14 02:13:00` | Regex `^(\d{2})/(\d{2})/(\d{4})` → `$3-$2-$1`; `T` → espaço; conversão `yyyy-MM-dd HH:mm:ss` |
| Timestamp com fuso | `2026-10-14T02:14:00+01:00` | Regex `^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2}).*$` → `$1 $2` (hora local) |
| Estado heterogéneo | `denied`, `Denied`, `DENIED` | maiúsculas + Value mapper → `ACCESS_DENIED` |
| Valor booleano heterogéneo | `true`, `"true"`, `1`, `"on"`, `false`, `0` | Value mapper; leituras sem deteção descartadas |
| Zona em falta ou mal escrita | ``, `z3` | Zona obtida por lookup do dispositivo (fonte autoritativa) |
| Duplicados | reenvio do controlador | Unique rows (HashSet) por `event_id` |

## Motivos de rejeição (`dq_rejection.reason_code`)
`MISSING_TIMESTAMP`, `MISSING_USER`, `UNKNOWN_DEVICE`, `INVALID_STATUS`, `INVALID_EVENT_TYPE`, `INVALID_TIMESTAMP` (data impossível, ex. `2026-13-45`, apanhada pelo *error hop*).

## Resultado verificado (2026-10-19)
| | Acessos | Sensores |
|---|---|---|
| Lidos | 99 | 79 |
| Duplicados removidos | 6 | 4 |
| Sem deteção (descartados) | — | 9 |
| Rejeitados | 5 | 2 |
| Gravados em `event` | **88** | **64** |

- Os 152 eventos coincidem com `ground_truth.csv`. Uma verificação independente em Python, evento a evento (data, zona, utilizador, tipo), deu 0 diferenças.
- 2.ª execução: Insert/Update com O=0 e U=0, e rejeições substituídas (7, não 14).

## Como testar
```bash
./scripts/run_api.sh &                                   # gateway REST
./scripts/pdi.sh pan etl/transformations/tr_extract_events.ktr
./scripts/sql.sh -c "select source, count(*) from event group by 1"
./scripts/sql.sh -c "select source, source_record_id, reason_code from dq_rejection"
```
