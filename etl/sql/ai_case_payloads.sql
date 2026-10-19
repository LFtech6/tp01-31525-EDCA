-- Casos a enviar à IA + payload JSON (usado pelo step "Build case payloads" da tr_ai_analysis).
-- Seleção por FACTOS do caso (nunca pelo veredicto das regras) + amostra de controlo de 5 casos sem sinais.
-- Exclui casos já analisados com sucesso para a mesma composição (events_hash) e versão do prompt.
WITH c AS (
  SELECT sc.*,
         (sc.denied_count + sc.off_hours_count + sc.unauthorized_count + sc.inactive_user_count
          + sc.outside_schedule_count + sc.unknown_user_count) AS signals
  FROM security_case sc
), sel AS (
  SELECT case_id, 'SIGNAL' AS selection_reason FROM c WHERE signals > 0
  UNION ALL
  SELECT case_id, 'CONTROL_SAMPLE' FROM (SELECT case_id FROM c WHERE signals = 0 ORDER BY events_hash LIMIT 5) s
)
SELECT c.case_id, c.events_hash, sel.selection_reason,
  json_build_object(
    'case_id', c.case_id,
    'zone', json_build_object('zone_id', z.zone_id, 'name', z.name, 'security_level', z.security_level,
                              'open_time', to_char(z.open_time, 'HH24:MI'), 'close_time', to_char(z.close_time, 'HH24:MI'),
                              'open_weekends', z.open_weekends),
    'start_ts', c.start_ts,
    'end_ts', c.end_ts,
    'events', (SELECT json_agg(json_build_object(
                   'event_id', e.event_id, 'timestamp', e.event_ts, 'source', e.source,
                   'event_type', e.event_type, 'device_id', e.device_id,
                   'user', CASE WHEN u.user_id IS NULL THEN NULL ELSE json_build_object(
                             'user_id', u.user_id, 'role', u.role,
                             'schedule_start', to_char(u.schedule_start, 'HH24:MI'),
                             'schedule_end', to_char(u.schedule_end, 'HH24:MI'),
                             'active', u.active,
                             'has_permission_for_zone', NOT coalesce(e.is_unauthorized_zone, false)) END,
                   'zone_closed_at_event_time', coalesce(e.is_off_hours, false),
                   'outside_user_schedule', coalesce(e.is_outside_schedule, false))
                 ORDER BY e.event_ts, e.event_id)
               FROM case_event ce JOIN event e USING (event_id) LEFT JOIN app_user u ON u.user_id = e.user_id
               WHERE ce.case_id = c.case_id)
  )::text AS payload
FROM c
JOIN sel USING (case_id)
JOIN zone z ON z.zone_id = c.zone_id
WHERE NOT EXISTS (SELECT 1 FROM ai_analysis a
                  WHERE a.events_hash = c.events_hash AND a.prompt_version = '${PROMPT_VERSION}' AND a.status = 'OK')
ORDER BY c.start_ts
