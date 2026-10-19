# tr_ai_analysis.ktr + serviço /ai/analyze — Análise contextual por IA (abordagem B)

## Papel da IA (e o que ela não faz)
A IA **não integra nem correlaciona dados**: recebe um caso já construído pelo Pentaho e devolve uma **interpretação** (suspeito ou não, risco, tipo, explicação, ação). As relações entre eventos vêm sempre do ETL determinístico.

## Fluxo
```
Table input (SQL: seleção + payload JSON por caso)
  → Calculator (Content-Type)
  → REST Client POST ${API_URL}/ai/analyze ──(erro de ligação)──► API_UNAVAILABLE → ai_analysis
  → JSON Input ($.status, $.risk_level, …)
  → User Defined Java Expression (HTTP ≠ 200 → MODEL_ERROR)
  → Get variables (RUN_ID, PROMPT_VERSION) → Select values → Table output ai_analysis
```

## Seleção dos casos (triagem)
Feita por **factos** do caso e **nunca** pelo veredicto das regras (`etl/sql/ai_case_payloads.sql`):
- `SIGNAL`: o caso tem ≥1 recusa, evento fora de horas, acesso sem permissão, utilizador inativo, fora do turno ou desconhecido.
- `CONTROL_SAMPLE`: 5 casos sem sinais (amostra fixa por `events_hash`), para medir falsos positivos da IA em tráfego comum.
- **Cache**: casos já analisados com sucesso para a mesma composição (`events_hash`) e `PROMPT_VERSION` não são reenviados.

O payload contém factos e contexto: a zona (nível, horário), cada evento (hora, tipo, dispositivo), o utilizador (papel, turno, ativo, se tem permissão para a zona) e as flags. **Não contém**: o veredicto das regras, as regras, o ground truth, o nome do cenário nem o `case_id`.

## Serviço FastAPI `/ai/analyze` (stateless)
| Aspeto | Implementação |
|---|---|
| Modelo | `qwen3:4b-instruct` (Ollama, nativo, Metal), digest `0edcdef34593…` registado por análise |
| Saída estruturada | `format` = JSON schema gerado do modelo Pydantic `ModelOutput` (`extra=forbid`) |
| Evidências | o schema de cada pedido restringe `evidence_event_ids` a um **enum com os IDs do caso**; o serviço volta a validar |
| Coerência | rejeita `is_suspicious=false` com risco MEDIUM/HIGH/CRITICAL e `true` com NONE |
| Determinismo | `temperature=0`, `seed=42`; `num_ctx=4096` (RAM), `num_predict=400` |
| Falhas | resposta sempre HTTP 200 com `status`: `OK`, `TIMEOUT` (150 s), `INVALID_OUTPUT`, `INVALID_INPUT`, `MODEL_ERROR` |
| Prompt | v1, congelado antes de observar resultados (`app/llm.py`). Alterações exigem nova `PROMPT_VERSION` |
| Saúde | `GET /ai/health` → 503 se o modelo não estiver disponível (o Job marca a etapa como SKIPPED) |

Não é atribuída nenhuma "probabilidade" ou "confiança" à classificação: o LLM não produz valores calibrados.

## Testes (pytest, Ollama simulado com `httpx.MockTransport`)
Resposta válida, restrição das evidências no pedido, `case_id` oculto, evidência inventada, classificação incoerente, JSON inválido, campos extra, timeout, Ollama em baixo, input inválido (HTTP 200 + `INVALID_INPUT`), `/ai/health` 503. **17 testes a passar.**

## Testes de falha da transformação (verificados)
| Situação | Resultado |
|---|---|
| Rota inexistente (HTTP 404) | 20 linhas `MODEL_ERROR` (`HTTP 404`), transformação termina (exit 0) |
| API desligada (ligação recusada) | *error hop* → 20 linhas `API_UNAVAILABLE`, transformação termina (exit 0) |

## Execução real (2026-10-19, `run-ai-001`)
- 20 casos (15 `SIGNAL` + 5 `CONTROL_SAMPLE`): **20 OK**, 0 inválidos, 0 timeouts, 0 evidências inventadas.
- Duração total: 10 min 52 s. Latência média: 36,2 s (SIGNAL) e 19,8 s (controlo); máximo: 82,0 s.
- 2.ª execução: 0 pedidos (cache).
