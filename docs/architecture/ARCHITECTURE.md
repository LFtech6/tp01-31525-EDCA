# Sentinel-AI (EDCA — ETL Data Correlation Agent) — Arquitetura e decisões técnicas

Versão 0.2 — 2026-10-16. Documento vivo: cada alteração de arquitetura é registada na secção 10.

## 1. Conformidade com o enunciado (TP1 ISI 2026/27)

### 1.1 Obrigatório (três fases ETL + entregáveis)

| Requisito | Como o Sentinel-AI o cumpre | Onde |
|---|---|---|
| Fase E: ≥2–3 formatos | CSV (acessos), JSON (sensores), XML (utilizadores), YAML (zonas/dispositivos), texto syslog (autenticação) | `data/raw`, `tr_extract_*` |
| Fase E: fontes de natureza variada | Ficheiros locais, API REST (gateway de sensores em FastAPI), BD relacional | `tr_extract_sensors_api`, `tr_load_reference` |
| Fase T: limpeza e validação | Nulos (Filter Rows → `dq_rejection`), duplicados (Unique Rows), Regex | `tr_extract_*` |
| Fase T: conversão de formatos | XML/YAML → relacional; relacional → JSON/CSV; casos → JSON para a API | vários |
| Fase T: joins, lookups, merge | Stream Lookup (dispositivo→zona), Database Lookup (permissões), Merge Join (ground truth) | `tr_enrich_events`, `tr_evaluate` |
| Fase T: agregações, cálculos, ordenação, filtragem | Sort + Analytic Query (LAG) + Group By (soma cumulativa) — sessionização temporal | `tr_correlate_cases` |
| Fase T: mapeamento de schemas | XML aninhado → linhas (loop XPath), Select Values | `tr_load_reference` |
| Fase L: persistência em BD | PostgreSQL, Insert/Update idempotente | todas |
| Fase L: ficheiros de exportação | JSON e CSV de incidentes | `tr_export_incidents` |
| Relatório (8 secções), vídeo (QR), Git, defesa individual | Documentação acompanha cada etapa | `docs/` |

### 1.2 Critérios de valorização incluídos (os que trazem valor com baixo custo)

| Critério | Implementação |
|---|---|
| Regex | Normalização de IDs (`u-41`, ` U041`, `user41` → `U041`), parsing de syslog com grupos de captura |
| YAML | Fonte de zonas e dispositivos via *YAML Input* |
| Jobs / orquestração | Job principal + subjobs com ramos de erro e verificação de serviços |
| API remota | REST Client (GET sensores, POST análise IA) |
| Logs | Tabelas de log nativas do Kettle + `etl_run`/`etl_run_stage` |
| Operações em BD | DDL, upserts, SQL de correlação/agregação |
| Dashboard | Node-RED + FlowFuse Dashboard 2.0 |

### 1.3 Valorização opcional — fora do MVP

E-mail, FTP/SFTP, anonimização nas exportações, MQTT, Isolation Forest. Só entram se as etapas obrigatórias estiverem concluídas.

Notas:
- O enunciado lista "anonimização" entre exemplos de limpeza; não é exigida individualmente. Fica como extensão barata (máscara de nomes/IPs na exportação) se houver tempo.
- A folha de temas (`.xlsx`) ainda não foi disponibilizada; a originalidade baseia-se apenas nos temas já identificados (Sistema de Deteção de Acessos; anonimização de logs DLP).

## 2. Restrições do ambiente

Verificado em 2026-10-14/16:

| Componente | Estado | Decisão |
|---|---|---|
| MacBook Air M2, **8 GB RAM** | Restrição mais forte | Nada em Docker; `num_ctx=4096`; IA corre via Kitchen sem Spoon aberto |
| PDI 10.2.0.0-222 (`~/pentaho/data-integration`) | Pan headless OK (Java 21) | GUI por confirmar visualmente |
| PostgreSQL 14.18 Homebrew :5432 | Base `sentinel`, roles `sentinel` (escrita) e `sentinel_ro` (leitura) | Schema idempotente aplicado |
| Ollama 0.40.4 (brew services) | `qwen3:4b-instruct`, ID `0edcdef34593`, Q4_K_M, 4.02B, 2.5 GB, Apache 2.0 | Nativo (Metal) |
| Node.js 22 (nvm) | Disponível | Node-RED instalado localmente no projeto (sem `-g`) |
| Python 3.12 via uv | Disponível | venv em `ai-engine/.venv` |

## 3. Separação de responsabilidades

| Componente | É responsável por | NÃO faz |
|---|---|---|
| **Pentaho (Kettle)** | Toda a extração, transformação, correlação, regras, chamada à IA, carregamento, exportação; Jobs de orquestração ETL | Interface com o utilizador |
| **FastAPI `/gateway`** | Simula o gateway IoT dos sensores (fonte REST); recebe eventos simulados pelo dashboard | Transformar dados |
| **FastAPI `/ai`** | Inferência: valida input, chama o Ollama, valida output, devolve JSON | Escrever na BD (é *stateless*) |
| **FastAPI `/ops`** | Lançar Jobs Pentaho de uma lista branca, controlar concorrência, expor estado e logs | Executar comandos arbitrários; transformar dados |
| **Ollama / Qwen3** | Classificação contextual e explicação de um caso já correlacionado | Correlacionar, inventar relações |
| **PostgreSQL** | Persistência de dados, resultados, estado de execuções e logs | — |
| **Node-RED + FlowFuse Dashboard** | Interação com o utilizador, visualização do estado, fluxos low-code de controlo (chamar `/ops`, ler a BD) | Qualquer transformação ETL |

Princípio: **escritas só pelo Pentaho** (dados) e pela API `/ops` (estado das execuções). O Node-RED lê a BD com o utilizador `sentinel_ro` e só atua através da API `/ops`.

## 4. Arquitetura

```text
                         ┌────────────────────── NODE-RED + FLOWFUSE DASHBOARD 2.0 (pós-MVP) ───────────────────┐
                         │  [Executar ETL] [Simular evento]   Estado/etapas   Eventos   Incidentes   IA   Logs   │
                         └──────┬───────────────────┬───────────────────────────────▲────────────────────────────┘
                     POST /ops/runs        POST /gateway/events            SELECT (sentinel_ro)
                     GET  /ops/runs/{id}          │                                │
                                ▼                 ▼                                │
 ┌──────────────── FASTAPI (127.0.0.1) ────────────────┐                           │
 │ /ops  (X-API-Key)  lista branca de Jobs → kitchen.sh │                           │
 │ /gateway           fonte REST de sensores            │                           │
 │ /ai/analyze        inferência (stateless) ──► Ollama │ qwen3:4b-instruct         │
 └───────┬───────────────▲──────────────▲───────────────┘                           │
         │ subprocess    │ GET          │ POST /ai/analyze                          │
         │ (sem shell)   │              │                                           │
         ▼               │              │                                           │
 ┌──────────────────── PENTAHO DATA INTEGRATION (Kitchen/Pan) ─────────────────┐    │
 │ access_logs.csv ─ CSV Input ┐                                               │    │
 │ users.xml ─────── Get XML ──┤ E: extração + validação + rejeições           │    │
 │ zones.yaml ────── YAML Input┤ T: Regex, datas, nulos, duplicados, lookups    │    │
 │ auth.log ──────── Regex ────┤ T: correlação (Sort → Analytic Query → GroupBy)│    │
 │ REST Client (sensores) ─────┘ T: motor de regras                             │    │
 │                               T: IA (Table Input json_agg → REST Client POST)│    │
 │                               L: Insert/Update, exportações JSON/CSV         │    │
 └──────────────────────────────────────┬──────────────────────────────────────┘    │
                                        ▼                                           │
                        ┌──────────── POSTGRESQL (sentinel) ─────────────┐──────────┘
                        │ referência · event · dq_rejection · security_case │
                        │ case_event · rule_result · ai_analysis           │
                        │ ground_truth · evaluation_metric                 │
                        │ etl_run · etl_run_stage · logs Kettle            │
                        └──────────────────────────────────────────────────┘
```

### 4.1 Comunicação entre tecnologias

| De → Para | Protocolo | Detalhe |
|---|---|---|
| Pentaho → ficheiros | FS | caminhos via variável `${SENTINEL_DATA}` |
| Pentaho → `/gateway/sensors/events` | HTTP GET, JSON | REST Client + JSON Input |
| Pentaho → `/ai/analyze` | HTTP POST, JSON | REST Client, 1 cópia do step, read timeout > `OLLAMA_TIMEOUT_S` |
| FastAPI → Ollama | HTTP `/api/chat` | `format`=JSON schema por pedido, `temperature=0`, `num_ctx=4096`, `keep_alive` |
| Pentaho → PostgreSQL | JDBC | ligação parametrizada `${PG_HOST}`… |
| `/ops` → Pentaho | `subprocess` com lista de argumentos (sem shell) | `kitchen.sh -file=<job da lista branca> -param:RUN_ID=<uuid>` |
| Node-RED → `/ops` | HTTP + `X-API-Key` | token do `.env` |
| Node-RED → PostgreSQL | `node-red-contrib-postgresql` | utilizador `sentinel_ro` (só SELECT) |

### 4.2 API de orquestração `/ops` — regras de segurança

- Escuta apenas em `127.0.0.1`; todos os endpoints `/ops` exigem o cabeçalho `X-API-Key`.
- O pedido indica um **nome lógico** de Job (`main`), mapeado no servidor para um `.kjb`; nunca um caminho nem um comando.
- Concorrência: máximo uma execução ativa — garantido por índice único parcial em `etl_run` (`status IN ('PENDING','RUNNING')`) → HTTP 409 em caso de conflito.
- Cada execução tem `run_id` (UUID) passado ao Kitchen como parâmetro; o Job regista as etapas em `etl_run_stage`.
- Logs do Kitchen gravados em `results/logs/<run_id>.log`; `/ops/runs/{id}/log` devolve as últimas N linhas.
- Distinção de falhas: ETL (exit code do Kitchen + `etl_run_stage`), API (`ai_analysis.status = API_UNAVAILABLE`), modelo (`TIMEOUT`, `INVALID_OUTPUT`, `MODEL_ERROR`).

### 4.3 Simulação de eventos

O dashboard envia um evento (formulário) para `POST /gateway/events`, que o valida e o guarda na fila do gateway. **Não é processado de imediato**: é consumido pelo Pentaho na execução seguinte, juntamente com os restantes eventos de sensores. Isto demonstra o caminho real dos dados sem contornar o ETL.

## 5. Decisões de desenho

1. **Pentaho é dono da persistência de dados**; FastAPI `/ai` é *stateless*.
2. **Independência da avaliação**: a IA não recebe o veredicto das regras nem nada que revele a etiqueta.
3. **Etiquetas** definidas no catálogo de cenários antes de escrever as regras (`ground_truth.csv`, por evento).
4. **Correlação**: sessionização por zona com *gap* máximo de 5 min e duração máxima de 20 min (configuráveis) — evita cadeias falsas.
5. **Arrays JSON**: payload construído em SQL (`json_agg`); resposta guardada como `jsonb`.
6. **Modelo**: regista-se o digest, não só a tag.
7. **Reexecução**: chaves naturais + Insert/Update; casos com ID determinístico; cache da IA por `events_hash + prompt_version + model_digest`.
8. **Fonte digital** (syslog) para correlação físico + digital.
9. **Isolation Forest**: fora do MVP (dados insuficientes para conclusões honestas).

## 6. Fontes de dados

| Fonte | Formato | Origem | Problemas de qualidade injetados |
|---|---|---|---|
| Zonas e dispositivos | YAML | ficheiro | — (referência) |
| Utilizadores e permissões | XML | ficheiro | IDs inconsistentes, horários `8:00` vs `08:00`, duplicado, campo vazio |
| Controlo de acessos | CSV | ficheiro | IDs mal formatados, datas em 3 formatos, duplicados, campos vazios |
| Sensores | JSON | API REST | `value` bool/string, timestamps com/sem fuso, sensor desconhecido |
| Autenticação | syslog | ficheiro | linhas irrelevantes, formatos variáveis |

## 7. Modelo de dados

Implementado em `database/01_schema.sql` (15 tabelas): `etl_run`, `etl_run_stage`, `building`, `zone`, `device`, `app_user`, `user_zone_permission`, `dq_rejection`, `event`, `security_case`, `case_event`, `rule_result`, `ai_analysis`, `ground_truth`, `evaluation_metric`.

## 8. Transformações e Jobs

| Ficheiro | Objetivo |
|---|---|
| `tr_load_reference.ktr` | YAML + XML → edifícios, zonas, dispositivos, utilizadores, permissões |
| `tr_extract_access_csv.ktr` | CSV → limpeza, Regex, datas, duplicados → `event` |
| `tr_extract_sensors_api.ktr` | REST → JSON → normalização → `event` |
| `tr_extract_auth_logs.ktr` | syslog → Regex Evaluation → `event` |
| `tr_enrich_events.ktr` | flags fora de horário / zona não autorizada / utilizador desconhecido |
| `tr_correlate_cases.ktr` | sessionização → `security_case`, `case_event` |
| `tr_rules_engine.ktr` | regras → `rule_result` |
| `tr_ai_analysis.ktr` | casos → POST `/ai/analyze` → `ai_analysis` |
| `tr_evaluate.ktr` | regras vs IA vs ground truth → `evaluation_metric` |
| `tr_export_incidents.ktr` | JSON/CSV de incidentes |
| `jb_sentinel_main.kjb` | orquestração completa com registo de etapas |

## 9. Fora do MVP

E-mail/FTP, anonimização, MQTT, Isolation Forest, Node-RED avançado (só depois do painel básico).

## 10. Registo de decisões

| Data | Decisão | Motivo |
|---|---|---|
| 2026-10-14 | PostgreSQL nativo | 8 GB RAM; instância já ativa |
| 2026-10-14 | Ollama nativo | Metal indisponível em Docker no macOS |
| 2026-10-14 | FastAPI `/ai` sem acesso à BD | Pentaho centraliza persistência |
| 2026-10-14 | `KETTLE_HOME` local ao projeto | Reprodutibilidade; não tocar em `~/.kettle` |
| 2026-10-16 | Node-RED + FlowFuse Dashboard 2.0 substitui Streamlit | Camada low-code de controlo + visualização; pedido do estudante |
| 2026-10-16 | API `/ops` separada de `/ai` (mesma app, routers distintos) | Separação controlo vs inferência; sem shell; autenticação por token |
| 2026-10-16 | `num_ctx` 8192 → 4096 | ~1.7 GB RAM livre medida; KV cache de 8K ≈ 1.2 GB |
| 2026-10-16 | E-mail/FTP/anonimização passam a opcionais | Não obrigatórios; foco nas 3 fases + YAML |
| 2026-10-18 | YAML em formato multi-documento (`---` por registo) | Testado: o *YAML Input* do PDI 10.2 devolve uma lista de mapas como uma única coluna `Value`; com multi-documento separa os campos |
