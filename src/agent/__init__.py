"""Runtime do agente CX `luz-do-vale`: montagem do system prompt (R-07/R-08) e
roteamento de modelo determinístico (R-09).

Lógica **pura** (sem I/O) compartilhada entre o runner de evals (`src/evals/run.py`)
e o wiring do sandbox (`sandbox/genie-wire.sh`), para garantir paridade
eval↔produção do prompt (M-07) — pré-requisito do prompt caching (R-07).
"""

from __future__ import annotations
