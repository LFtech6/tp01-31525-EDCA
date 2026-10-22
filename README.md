# Sentinel-AI — EDCA (ETL Data Correlation Agent)

Trabalho Prático I de **Integração de Sistemas de Informação**: Licenciatura em Engenharia de Sistemas Informáticos, EST-IPCA, 2026/27.

| | |
|---|---|
| **Autor** | Rodrigo Lopes Ferreira, n.º **31525** (trabalho individual) |
| **Docentes** | Luís Ferreira, Óscar Ribeiro |
| **Vídeo com a demonstração** | [Pasta OneDrive com o vídeo](https://alunosipca-my.sharepoint.com/:f:/g/personal/a31525_alunos_ipca_pt/IgDRnBKMuRQfSK5Lao6vEFNJASP6Lu-HhiXyhru9kGlxkms?e=yAm83U) |
| **Repositório Git** | https://github.com/LFtech6/tp01-31525-EDCA (histórico também em `src/31525.bundle`) |
| **Relatório** | `doc/31525_doc.pdf` (na entrega) / `docs/report/31525_doc.pdf` (no repositório) |

## O que é

O processo ETL integra eventos de segurança física de duas fontes heterogéneas:

- **controlo de acessos:** CSV;
- **sensores:** JSON obtido por uma API REST.

Esses eventos são cruzados com os dados de referência (zonas e horários em **YAML**; utilizadores e permissões em **XML**) e agrupados em **casos de segurança** por zona e proximidade temporal. Cada caso é classificado de duas formas independentes:

- **A, regras:** um motor determinístico implementado no Pentaho;
- **B, IA:** o modelo local `qwen3:4b-instruct`, via Ollama, chamado pelo Pentaho através de um serviço FastAPI.

As duas abordagens são comparadas com um *ground truth* definido a priori (precisão, recall, F1). O processo exporta os incidentes (JSON e CSV) e envia um resumo, ou um alerta de erro, por e-mail. Um dashboard Node-RED + FlowFuse Dashboard 2.0 permite executar o ETL e acompanhar etapas, eventos, incidentes, estatísticas e erros.

**O Pentaho Data Integration é o motor ETL central.** A API Python serve três propósitos e mais nenhum:

- fonte REST dos sensores;
- inferência do modelo;
- lançamento controlado do Job.

O Node-RED nunca transforma dados.

## Ficheiros entregues

Organização do ZIP `31525.zip`, segundo as instruções de entrega:

| Pasta / ficheiro | Conteúdo |
|---|---|
| `README.md` | Este ficheiro |
| `doc/31525_doc.pdf` | Relatório final (8 secções do enunciado) |
| `dataintegration/transformations/*.ktr` | As 7 transformações Pentaho |
| `dataintegration/jobs/jb_sentinel_main.kjb` | O Job de orquestração |
| `dataintegration/sql/*.sql` | SQL usado pelos steps *Table input* (payload da IA, mensagem de e-mail) |
| `data/input/` | Dados de entrada: `access_logs.csv`, `sensor_events.json`, `users.xml`, `zones.yaml`, `devices.yaml`, e `test_scenarios/` (`ground_truth.csv` + catálogo `scenarios.md`) |
| `data/output/exports/` | `incidents.json`, `incidents.csv` (incidentes com explicação da IA e evidências) |
| `data/output/evaluation/` | `metrics.csv` (TP/FP/TN/FN, precisão, recall, F1), `case_comparison.csv` (regras vs IA por caso) |
| `data/output/database/sentinel_dump.sql` | Exportação da base de dados PostgreSQL (estrutura + dados) após a última execução |
| `src/` | **Projeto completo e executável** (é daqui que se executa; ver abaixo) |

As pastas `dataintegration/` e `data/` são **cópias para consulta**. Os caminhos usados na execução são os de `src/`, que é igual ao repositório Git. O histórico de commits vem em `src/31525.bundle` (`git clone 31525.bundle sentinel` recupera o repositório completo).

Estrutura de `src/` (= repositório):

```text
etl/transformations/   transformações (.ktr)            etl/jobs/   Job (.kjb)        etl/sql/   SQL dos Table input
data/raw/              fontes (CSV, JSON, XML, YAML)    data/test_scenarios/  ground truth + catálogo de cenários
data/generator/        gerador determinístico dos dados de teste (Python)
database/              00_bootstrap.sql (roles + BD), 01_schema.sql (16 tabelas, idempotente)
ai-engine/             serviço FastAPI: /gateway (fonte REST), /ai (Qwen3), /ops (orquestração) + testes pytest
node-red/              fluxos (flows.json), settings.js, package.json (Node-RED + FlowFuse Dashboard 2.0)
scripts/               arranque, verificação do ambiente e execução (ver tabela abaixo)
docs/                  arquitetura, documentação de cada transformação, avaliação, diagramas, relatório
results/               exportações, avaliação e logs do Kitchen
```

## Ferramentas (versões verificadas)

| Ferramenta | Versão | Papel |
|---|---|---|
| Pentaho Data Integration | 10.2.0.0-222 (Java 21) + driver JDBC `postgresql-42.5.6.jar` em `lib/` | ETL (Spoon / Pan / Kitchen) |
| PostgreSQL | 14.18 (Homebrew) | Base de dados |
| Python + uv | 3.12 / uv 0.12 | Serviço FastAPI |
| Ollama + modelo | 0.40.4, `qwen3:4b-instruct` (digest `0edcdef34593`) | IA local |
| Node.js + npm | 22 / 10 | Node-RED 5.0.8, `@flowfuse/node-red-dashboard` 1.33.0, `node-red-contrib-postgresql` 0.16.2 |
| Conta de e-mail SMTP | ex.: `smtp.office365.com:587` (TLS) | Notificação |

Testado em macOS (Apple M2, 8 GB). Todos os serviços correm localmente, sem Docker, e escutam apenas em `127.0.0.1`.

## Como executar (do zero)

Todos os comandos são executados na raiz do projeto (`src/` na entrega, ou o clone do repositório).

```bash
# 1. Configuração: cria o .env com segredos aleatórios (o .env não vai para o Git)
./scripts/init_env.sh
#    editar o .env: PDI_HOME e, para o e-mail, SMTP_USER / SMTP_PASSWORD / MAIL_FROM / MAIL_TO
#    (os dados do e-mail também podem ser introduzidos depois no dashboard)
./scripts/check_env.sh                       # verificação do ambiente (só leitura)

# 2. Base de dados (PostgreSQL a correr): cria roles, a base 'sentinel' e as 16 tabelas
./scripts/db_bootstrap.sh

# 3. IA local
brew install ollama && brew services start ollama
ollama pull qwen3:4b-instruct

# 4. Serviço FastAPI (terminal 1): gateway REST de sensores + /ai + /ops
(cd ai-engine && uv venv --python 3.12 && uv pip install -r requirements.txt)
./scripts/run_api.sh                         # http://127.0.0.1:8000/docs

# 5a. Executar o ETL pela linha de comandos (terminal 2): Job completo com RUN_ID e log próprios
./scripts/run_pipeline.sh                    # mostra as etapas no fim; log em results/logs/<RUN_ID>.log

# 5b. ...ou pelo dashboard (terminal 2)
./scripts/run_nodered.sh                     # instala as dependências na 1.ª vez (npm)
#    dashboard: http://127.0.0.1:1880/dashboard   editor de fluxos: http://127.0.0.1:1880
#    Controlo → "Executar ETL"; o formulário "Notificação por e-mail" define a conta e os destinatários

# Abrir as transformações e o Job no Spoon (com as variáveis do projeto)
./scripts/pdi.sh spoon
```

A 1.ª execução analisa 20 casos com a IA (cerca de 11 minutos num M2 com 8 GB). As seguintes usam a cache e demoram cerca de 15 s. Se o Ollama não estiver disponível, a etapa de IA fica `SKIPPED` e o resto do processo corre normalmente. Testes do serviço: `cd ai-engine && .venv/bin/python -m pytest -q` (34 testes).

### Scripts

| Script | Função |
|---|---|
| `init_env.sh` / `check_env.sh` | criar o `.env` / verificar o ambiente |
| `db_bootstrap.sh` / `sql.sh` | criar a BD e o schema / abrir o `psql` com as credenciais do `.env` |
| `kettle_env.sh` / `pdi.sh` | gerar o `KETTLE_HOME` local (`kettle.properties` a partir do `.env`) / executar Spoon, Pan ou Kitchen |
| `run_pipeline.sh` | executar o Job `jb_sentinel_main` |
| `run_api.sh` / `run_nodered.sh` | arrancar a API FastAPI / o Node-RED |

## Resultados (última execução)

| Abordagem | TP | FP | TN | FN | Precisão | Recall | F1 |
|---|---|---|---|---|---|---|---|
| A — Regras | 6 | 5 | 70 | 1 | 0,5455 | 0,8571 | 0,6667 |
| B — IA (triagem + Qwen3) | 5 | 2 | 73 | 2 | 0,7143 | 0,7143 | 0,7143 |

152 eventos (88 de acessos + 64 de sensores), 7 rejeições de qualidade e 82 casos correlacionados, dos quais 13 são incidentes. Análise detalhada: `docs/evaluation.md` e secção 7 do relatório.

## Segurança

- **Credenciais:** apenas no `.env` (ignorado pelo Git). O Pentaho recebe-as por `kettle.properties` gerado num `KETTLE_HOME` local, e os `.ktr`/`.kjb` só contêm variáveis (`${PG_PASSWORD}`, `${SMTP_PASSWORD}`).
- **API `/ops`:** exige o cabeçalho `X-API-Key`, lança apenas Jobs de uma lista branca, sem *shell*, e permite uma só execução ativa (HTTP 409).
- **Dashboard:** lê a BD com o utilizador só de leitura `sentinel_ro`.
- **Password do e-mail introduzida no dashboard:** fica só em memória e nunca é devolvida.

## Documentação

- `docs/architecture/ARCHITECTURE.md`: arquitetura e decisões.
- `docs/etl/*.md`: cada transformação e o Job.
- `docs/evaluation.md`: metodologia e resultados regras vs IA.
- `docs/diagrams/`: diagramas (gerados a partir dos `.ktr`/`.kjb` com `render_etl_diagrams.py`).
