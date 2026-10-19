# Avaliação: motor de regras (A) vs IA contextual (B)

## Metodologia
- **Ground truth** definido por cenário, **antes** das regras, ao nível do evento (`data/test_scenarios/ground_truth.csv`, catálogo em `scenarios.md`). Um caso é "suspeito esperado" se contiver algum evento de um cenário suspeito.
- **Unidade de avaliação**: o caso correlacionado (82 casos).
- **Abordagem A**: regras R1–R4 (`tr_correlate_rules`) sobre todos os casos.
- **Abordagem B (híbrida)**: triagem por factos + Qwen3. Casos não enviados à IA contam como negativos. As falhas da IA são contadas à parte (`n_failed`) e não como negativos.
- O mesmo cálculo é feito também só sobre o **subconjunto enviado à IA** (20 casos), para comparação direta.
- Cálculo em Pentaho (`tr_evaluate`): Merge Join ground truth × resultados → Group by → precisão, recall, F1 → `evaluation_metric` + `results/evaluation/metrics.csv`.

## Resultados (run-20261019-001, prompt v1, `qwen3:4b-instruct` 0edcdef34593)

| Abordagem | Casos | TP | FP | TN | FN | Falhas | Precisão | Recall | F1 | Latência média |
|---|---|---|---|---|---|---|---|---|---|---|
| A — Regras | 82 | 6 | 5 | 70 | 1 | 0 | 0,545 | 0,857 | 0,667 | ~0 (no ETL) |
| B — IA (híbrida) | 82 | 5 | 2 | 73 | 2 | 0 | 0,714 | 0,714 | 0,714 | 32,1 s/caso |
| A — subconjunto IA | 20 | 6 | 5 | 8 | 1 | — | 0,545 | 0,857 | 0,667 | — |
| B — subconjunto IA | 20 | 5 | 2 | 11 | 2 | 0 | 0,714 | 0,714 | 0,714 | 32,1 s |

Tempo de ETL (todas as transformações, sem IA): ~15 s. Inferência: 10 min 52 s para 20 casos (1.ª execução); 0 s nas seguintes (cache).

## Análise por cenário

| Cenário | Esperado | Regras | IA | Comentário |
|---|---|---|---|---|
| S01 Intrusão noturna | suspeito | ✅ | ✅ | ambos |
| S02 Recusas repetidas | suspeito | ✅ | ✅ | ambos |
| S03 Acesso sem permissão | suspeito | ✅ | ✅ | ambos |
| S04 Movimento sem acesso | suspeito | ❌ | ✅ | nenhuma regra cobre presença sem acesso; a IA identificou-a |
| S05 Ex-colaborador | suspeito | ✅ | ❌ | a IA ignorou `active=false` |
| S06 Tailgating | suspeito | ✅ | ❌ | a IA não relacionou a recusa com a entrada seguinte |
| S07 Fora do turno | suspeito | ✅ | ✅ | ambos |
| B01 Cartão mal lido | benigno | ❌ FP | ✅ | a IA usou a sequência recusa→concessão do mesmo utilizador |
| B02 Investigadora no turno | benigno | ❌ FP | ✅ | a IA usou o turno do utilizador |
| B03 Operador noturno | benigno | ❌ FP | ✅ | a IA reconheceu o turno que atravessa a meia-noite |
| B04 Ronda de segurança | benigno | ❌ FP | ❌ FP | a IA classificou como MEDIUM apesar do papel `security` |
| B05 Limpeza | benigno | ❌ FP | ✅ | a IA usou o turno do utilizador |
| B06 Deteção isolada | benigno | ✅ | ❌ FP | a IA classificou uma deteção isolada como HIGH |
| B07 Admin no NOC | benigno | ✅ | ✅ | ambos |
| B08 Porta errada | benigno | ✅ | ✅ | ambos |
| 5 casos de controlo | benigno | ✅ | ✅ | nenhum falso positivo da IA em tráfego normal |

## Conclusões (honestas)
1. **Nenhuma abordagem domina a outra.** A IA tem maior precisão (menos falsos alarmes: 2 vs 5) e as regras têm maior recall (falham menos suspeitos: 1 vs 2). O F1 é ligeiramente superior na IA (0,71 vs 0,67).
2. **As abordagens são complementares.** A IA acerta onde as regras não têm contexto (turnos, sequência recusa→concessão, presença sem acesso). As regras acertam padrões explícitos que o modelo de 4B ignorou (conta inativa, tailgating).
3. Uma combinação simples (alerta se ambas concordam; revisão humana se discordam) é um trabalho futuro natural.
4. **Custo**: as regras são instantâneas; a IA custa ~32 s por caso num M2 com 8 GB. A triagem por factos e a cache tornam esse custo viável.

## Limitações
- Amostra pequena (15 cenários + 5 controlos): as métricas são indicativas e não têm significância estatística.
- Sem conjunto de teste separado: o prompt v1 foi escrito antes de ver resultados e não foi afinado sobre eles (qualquer afinação exigiria nova `PROMPT_VERSION` e novos cenários).
- Dados sintéticos, gerados pelo autor do sistema.
- Explicações da IA em português com traços do Brasil ("usuário", "detecção").
- Temperatura 0 e semente fixa reduzem, mas não garantem, o determinismo do LLM.
