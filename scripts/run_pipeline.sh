#!/usr/bin/env bash
# Executa o Job principal do Sentinel-AI com um RUN_ID único e log próprio.
# Uso: ./scripts/run_pipeline.sh [RUN_ID] [TRIGGER]
#   RUN_ID   por omissão run-AAAAMMDD-HHMMSS
#   TRIGGER  cli (omissão) | dashboard | schedule
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN_ID="${1:-run-$(date +%Y%m%d-%H%M%S)}"
TRIGGER="${2:-cli}"
LOG="$ROOT/results/logs/$RUN_ID.log"
mkdir -p "$ROOT/results/logs"

echo "Sentinel-AI: execução $RUN_ID (trigger=$TRIGGER) — log em $LOG"
set +e
"$ROOT/scripts/pdi.sh" kitchen "$ROOT/etl/jobs/jb_sentinel_main.kjb" Basic \
  "-param:RUN_ID=$RUN_ID" "-param:TRIGGER=$TRIGGER" > "$LOG" 2>&1
rc=$?
set -e
echo "Kitchen terminou com exit code $rc"
"$ROOT/scripts/sql.sh" -c "select stage, status, rows_processed, to_char(finished_at - started_at, 'MI:SS') duracao, message
                           from etl_run_stage where run_id = '$RUN_ID' order by started_at" || true
exit $rc
