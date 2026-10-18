#!/usr/bin/env bash
# Wrapper do Pentaho com o KETTLE_HOME do projeto.
# Uso:
#   ./scripts/pdi.sh spoon
#   ./scripts/pdi.sh pan     etl/transformations/tr_load_reference.ktr [nível_log]
#   ./scripts/pdi.sh kitchen etl/jobs/jb_sentinel_main.kjb            [nível_log]
set -euo pipefail
. "$(dirname "$0")/kettle_env.sh"
PDI_HOME="${PDI_HOME/#\$HOME/$HOME}"

tool="${1:?spoon|pan|kitchen}"; shift || true
case "$tool" in
  spoon)   cd "$PDI_HOME" && exec ./spoon.sh ;;
  pan)     f="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
           exec "$PDI_HOME/pan.sh" -file="$f" -level="${2:-Basic}" ;;
  kitchen) f="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
           exec "$PDI_HOME/kitchen.sh" -file="$f" -level="${2:-Basic}" ;;
  *) echo "Ferramenta desconhecida: $tool" >&2; exit 2 ;;
esac
