-- Compõe a notificação por e-mail da execução ${RUN_ID} (usado por tr_build_notification.ktr).
-- Devolve exatamente UMA linha: mail_kind (SUMMARY | ALERT), mail_subject e mail_body (HTML).
--   SUMMARY: execução sem falhas → contagens por etapa, métricas regras vs IA e incidentes prioritários;
--   ALERT:   execução marcada FAILED → etapa que falhou, mensagem de erro e onde está o log.
WITH run AS (
    SELECT r.run_id, r.status, r.trigger_source, r.started_at, r.error_message,
           coalesce(r.log_path, '${SENTINEL_RESULTS}/logs/' || r.run_id || '.log') AS log_path
    FROM etl_run r WHERE r.run_id = '${RUN_ID}'
),
risk(level, rank) AS (VALUES ('CRITICAL', 4), ('HIGH', 3), ('MEDIUM', 2), ('LOW', 1), ('NONE', 0)),
inc AS (   -- mesma definição de incidente que tr_export_incidents
    SELECT c.case_id, z.name AS zone_name, c.start_ts, c.event_count,
           r.is_suspicious AS rules_susp, r.risk_level AS rules_risk, r.matched_rules,
           a.is_suspicious AS ai_susp, a.risk_level AS ai_risk, a.incident_type,
           greatest(rr.rank, coalesce(ra.rank, 0)) AS max_rank
    FROM security_case c
    JOIN zone z USING (zone_id)
    JOIN rule_result r USING (case_id)
    JOIN risk rr ON rr.level = r.risk_level
    LEFT JOIN LATERAL (SELECT * FROM ai_analysis x
                       WHERE x.events_hash = c.events_hash AND x.prompt_version = '${PROMPT_VERSION}' AND x.status = 'OK'
                       ORDER BY x.analyzed_at DESC LIMIT 1) a ON true
    LEFT JOIN risk ra ON ra.level = a.risk_level
    WHERE r.is_suspicious OR coalesce(a.is_suspicious, false)
),
stats AS (
    SELECT (SELECT count(*) FROM event) AS n_events,
           (SELECT count(*) FROM dq_rejection WHERE run_id = '${RUN_ID}') AS n_rejected,
           (SELECT count(*) FROM security_case) AS n_cases,
           (SELECT count(*) FROM rule_result WHERE is_suspicious) AS n_rules,
           (SELECT count(*) FROM inc WHERE coalesce(ai_susp, false)) AS n_ai,
           (SELECT count(*) FROM inc) AS n_inc,
           (SELECT count(*) FROM inc WHERE max_rank >= 3) AS n_high,
           (SELECT count(*) FROM ai_analysis WHERE run_id = '${RUN_ID}') AS n_ai_calls,
           (SELECT count(*) FROM ai_analysis WHERE run_id = '${RUN_ID}' AND status <> 'OK') AS n_ai_fail
),
metrics AS (
    SELECT string_agg(format('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>',
                             m.approach, m.tp, m.fp, m.tn, m.fn,
                             coalesce(to_char(m.precision_val, 'FM0.000'), '—'),
                             coalesce(to_char(m.recall_val, 'FM0.000'), '—'),
                             coalesce(to_char(m.f1_val, 'FM0.000'), '—')), '' ORDER BY m.approach DESC) AS rows
    FROM evaluation_metric m WHERE m.run_id = '${RUN_ID}' AND m.approach IN ('RULES', 'AI')
),
top_inc AS (
    SELECT string_agg(format('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>',
                             case_id, replace(zone_name, '&', '&amp;'), to_char(start_ts, 'DD/MM HH24:MI'),
                             CASE WHEN rules_susp AND coalesce(ai_susp, false) THEN 'Regras + IA'
                                  WHEN rules_susp THEN 'Só regras' ELSE 'Só IA' END,
                             CASE WHEN rules_susp THEN rules_risk || ' (' || coalesce(matched_rules, '') || ')' ELSE '—' END,
                             coalesce(ai_risk, '—'),
                             coalesce(replace(replace(replace(incident_type, '&', '&amp;'), '<', '&lt;'), '>', '&gt;'), '—')),
                      '' ORDER BY max_rank DESC, start_ts) AS rows
    FROM (SELECT * FROM inc ORDER BY max_rank DESC, start_ts LIMIT 15) t
),
failed AS (
    SELECT string_agg(format('<li><b>%s</b>: %s</li>', stage, coalesce(message, 'sem mensagem')), '' ORDER BY started_at) AS items
    FROM etl_run_stage WHERE run_id = '${RUN_ID}' AND status = 'FAILED'
)
SELECT CASE WHEN run.status = 'FAILED' THEN 'ALERT' ELSE 'SUMMARY' END AS mail_kind,
       CASE WHEN run.status = 'FAILED'
            THEN format('[Sentinel-AI] ALERTA: a execução %s falhou', run.run_id)
            ELSE format('[Sentinel-AI] Resumo da execução %s: %s incidentes (%s de risco alto/crítico)',
                        run.run_id, s.n_inc, s.n_high) END AS mail_subject,
       CASE WHEN run.status = 'FAILED' THEN
            '<h2 style="color:#b91c1c">Sentinel-AI: falha na execução do ETL</h2>'
            || format('<p>Execução <b>%s</b> (origem: %s), iniciada em %s.</p>',
                      run.run_id, run.trigger_source, to_char(run.started_at, 'DD/MM/YYYY HH24:MI:SS'))
            || format('<p><b>Erro:</b> %s</p>', coalesce(run.error_message, '—'))
            || '<p>Etapas com falha:</p><ul>' || coalesce(f.items, '<li>—</li>') || '</ul>'
            || format('<p>Log do Kitchen: <code>%s</code></p>', run.log_path)
            || '<p>Os dados da execução anterior mantêm-se; corrija a causa e volte a executar o Job.</p>'
       ELSE
            '<h2>Sentinel-AI: resumo da execução do ETL</h2>'
            || format('<p>Execução <b>%s</b> (origem: %s), iniciada em %s.</p>',
                      run.run_id, run.trigger_source, to_char(run.started_at, 'DD/MM/YYYY HH24:MI:SS'))
            || '<table border="1" cellpadding="4" cellspacing="0">'
            || format('<tr><td>Eventos normalizados (CSV + API REST)</td><td>%s</td></tr>', s.n_events)
            || format('<tr><td>Registos rejeitados (qualidade de dados)</td><td>%s</td></tr>', s.n_rejected)
            || format('<tr><td>Casos correlacionados</td><td>%s</td></tr>', s.n_cases)
            || format('<tr><td>Casos suspeitos segundo as regras</td><td>%s</td></tr>', s.n_rules)
            || format('<tr><td>Casos suspeitos segundo a IA (Qwen3)</td><td>%s</td></tr>', s.n_ai)
            || format('<tr><td>Análises de IA nesta execução (falhadas)</td><td>%s (%s)</td></tr>', s.n_ai_calls, s.n_ai_fail)
            || format('<tr><td><b>Incidentes (regras e/ou IA)</b></td><td><b>%s</b></td></tr>', s.n_inc)
            || '</table>'
            || '<h3>Regras vs IA (face ao ground truth)</h3>'
            || '<table border="1" cellpadding="4" cellspacing="0"><tr><th>Abordagem</th><th>TP</th><th>FP</th><th>TN</th><th>FN</th><th>Precisão</th><th>Recall</th><th>F1</th></tr>'
            || coalesce(mt.rows, '<tr><td colspan="8">sem métricas nesta execução</td></tr>') || '</table>'
            || '<h3>Incidentes prioritários (máx. 15)</h3>'
            || '<table border="1" cellpadding="4" cellspacing="0"><tr><th>Caso</th><th>Zona</th><th>Início</th><th>Detetado por</th><th>Risco (regras)</th><th>Risco (IA)</th><th>Tipo (IA)</th></tr>'
            || coalesce(ti.rows, '<tr><td colspan="7">sem incidentes</td></tr>') || '</table>'
            || '<p>Em anexo: incidents.csv (todos os incidentes, com evidências e explicação) e metrics.csv.</p>'
       END AS mail_body
FROM run CROSS JOIN stats s CROSS JOIN metrics mt CROSS JOIN top_inc ti CROSS JOIN failed f
