# tr_load_reference.ktr — Carregamento dos dados de referência

## Objetivo
Carregar os dados mestre necessários à correlação: edifícios, zonas e horários, dispositivos, utilizadores e permissões. Os dados chegam em formatos heterogéneos (YAML e XML) e com problemas de qualidade.

## Entradas
| Ficheiro | Formato | Registos |
|---|---|---|
| `data/raw/zones.yaml` | YAML multi-documento | 8 zonas (2 edifícios) |
| `data/raw/devices.yaml` | YAML multi-documento | 24 dispositivos |
| `data/raw/users.xml` | XML com lista aninhada `allowed_zones/zone` | 16 utilizadores (1 duplicado), 52 permissões |

## Ramos e operadores

| Ramo | Steps (por ordem) | Operadores ETL demonstrados |
|---|---|---|
| 1. Edifícios | YAML input → Select values → Sort rows → Unique rows → Insert/Update `building` | Extração YAML, mapeamento de schema, ordenação, remoção de duplicados, upsert |
| 2. Zonas | YAML input (cópia) → Select values (meta-data `HH:mm`) → Block until steps finish → Insert/Update `zone` | Conversão de tipos, sincronização de ramos (respeito da FK) |
| 3. Utilizadores | Get data from XML (`/users/user`) → String operations (trim, minúsculas) → Replace in string (**Regex**) → String operations (padding) → Calculator (concatenação) → Value mapper → If field value is null → Sort rows → Unique rows → Select values → Insert/Update `app_user` | XPath, limpeza, Regex, normalização, mapeamento de valores, tratamento de nulos, deduplicação |
| 4. Permissões | Get data from XML (`/users/user/allowed_zones/zone`, `../../@id`) → Replace in string (**Regex**) → String operations (padding) → Calculator → Sort → Unique → Block until steps finish → Insert/Update `user_zone_permission` | Reestruturação de schema (lista aninhada → linhas), normalização de chaves compostas |
| 5. Dispositivos | YAML input → Block until steps finish → Insert/Update `device` | Extração YAML, integridade referencial |

## Regras de transformação

| Problema na fonte | Exemplo | Regra |
|---|---|---|
| ID de utilizador mal formatado | `u-7`, ` U012`, `user15` | Regex `[^0-9]` → `""`; padding à esquerda com `0` até 3 dígitos; prefixo `U` → `U007`, `U012`, `U015` |
| ID de zona mal formatado | `z3` | Regex `[^0-9]` → `""`; padding até 2 dígitos; prefixo `Z` → `Z03` |
| Hora sem zero à esquerda | `8:00` | Regex `^(\d):` → `0$1:` → `08:00` |
| E-mail/username em maiúsculas | `DIOGO.FERNANDES@…` | String operations: minúsculas + trim |
| Booleano heterogéneo | `true`, `yes`, `1`, `false` | Value mapper → `Y`/`N`, convertido para Boolean |
| Campo obrigatório vazio | `<role></role>` | If field value is null → `unassigned` |
| Registo duplicado | `U003` (2×) | Sort rows + Unique rows por `user_id` |
| Horas como texto | `"07:00"` | Select values (meta-data) → Date com máscara `HH:mm` |

## Erros tratados (descobertos em teste)
1. **YAML em lista** — o *YAML Input* do PDI 10.2 devolve cada item de uma lista como texto numa coluna `Value`. Solução: YAML multi-documento (`---` por registo).
2. **Texto em coluna `time`** — PostgreSQL recusa `varchar` em `time`. Solução: opção JDBC `stringtype=unspecified`.
3. **Reexecução falhava** — o Insert/Update compara o valor da BD (`time`) com o do fluxo (`String`) e falha na 2.ª execução. Solução: converter as horas para `Date` (`HH:mm`) no Select values antes do upsert.
4. **Chave estrangeira** — os steps correm em paralelo; zonas, dispositivos e permissões esperam pelos ramos de que dependem (*Block this step until steps finish*).

## Resultado esperado (verificado em 2026-10-19)

| Tabela | Linhas | 1.ª execução | 2.ª execução |
|---|---|---|---|
| `building` | 2 | inseridas | O=0, U=0 |
| `zone` | 8 | inseridas | O=0, U=0 |
| `device` | 24 | O=24 | O=0, U=0 |
| `app_user` | 15 | O=15 | O=0, U=0 |
| `user_zone_permission` | 49 | O=49 | O=0, U=0 |

## Como testar
```bash
./scripts/pdi.sh pan etl/transformations/tr_load_reference.ktr     # exit code 0
./scripts/sql.sh -c "select user_id, schedule_start, role, active from app_user order by 1"
```
