#!/usr/bin/env bash
# Runner do seed: repassa os telefones de demo do ambiente para o psql.
# Telefone vazio/ausente vira placeholder E.164 nao-demonstravel (seed-design.md).
set -euo pipefail

PHONE_PRIMARY="${DEMO_PHONE_PRIMARY:-555199990001}"
PHONE_EVAL1="${DEMO_PHONE_EVAL_1:-555199990002}"
PHONE_EVAL2="${DEMO_PHONE_EVAL_2:-555199990003}"

psql -v ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v phone_primary="$PHONE_PRIMARY" \
  -v phone_eval1="$PHONE_EVAL1" \
  -v phone_eval2="$PHONE_EVAL2" \
  -f /db/seed.sql
