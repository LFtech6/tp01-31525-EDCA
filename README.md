# Sentinel-AI — EDCA (ETL Data Correlation Agent)

Sistema de integração, correlação e análise de eventos de segurança física e digital.
Trabalho Prático I — Integração de Sistemas de Informação, LESI, EST-IPCA, 2026/27.

Pentaho Data Integration extrai cinco fontes heterogéneas (CSV, JSON via REST, XML, YAML e syslog) e normaliza-as. Depois correlaciona os eventos por zona e proximidade temporal e persiste tudo em PostgreSQL. Cada caso correlacionado é avaliado por um motor de regras determinístico e, de forma independente, por um modelo de linguagem local (Qwen3 4B via Ollama), exposto por um serviço FastAPI. Os resultados são comparados com um *ground truth* definido à priori.

- Arquitetura e decisões: [`docs/architecture/ARCHITECTURE.md`](docs/architecture/ARCHITECTURE.md)
- Plano e critérios de aceitação: [`docs/PLAN.md`](docs/PLAN.md)

## Requisitos

| Componente | Versão verificada |
|---|---|
| macOS Apple Silicon | 26.2 (M2, 8 GB) |
| Pentaho Data Integration | 10.2.0.0-222 |
| Java | 21 (Oracle) / 17 (Temurin) |
| PostgreSQL | 14.18 (Homebrew) |
| Python | 3.12 (venv via `uv`) |
| Ollama + `qwen3:4b-instruct` | a instalar |

## Arranque rápido

```bash
cp .env.example .env          # ajustar password
./scripts/check_env.sh        # verificação do ambiente (só leitura)
```

As instruções completas de execução são acrescentadas à medida que cada etapa fica validada.

## Estrutura

```text
data/            raw/ (fontes), test_scenarios/ (ground truth), generator/ (gerador sintético)
database/        scripts SQL (bootstrap, schema, seeds)
etl/             transformations/*.ktr, jobs/*.kjb, kettle-home/ (KETTLE_HOME local)
ai-engine/       serviço FastAPI (gateway de sensores + /analyze) e testes
dashboard/       Streamlit
scripts/         utilitários de execução e verificação
docs/            arquitetura, documentação ETL, diagramas, relatório
results/         exportações, avaliação, logs
```
