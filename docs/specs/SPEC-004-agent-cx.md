# SPEC-004 - Agente CX (AGENTS.md + harness de avaliacao)

- Status: Draft
- Versao alvo: 0.5.0 (a "cabeca" do agente)
- ADRs: ADR-0001 (Python), ADR-0006 (compose/sandbox), ADR-0007 (runtime Claude Code, sem key)
- Validado antes em POC (`poc/agent`, 8/8 jornadas via `claude -p` headless).

## 1. Problema

Temos as ferramentas (MCP, SPEC-003), mas nenhum agente decidindo quando usa-las. Falta
a identidade + politica + guardrails que orquestram as tools, e uma forma de **avaliar** o
comportamento (uso correto de tool, confirmacao antes de escrever, recusa de injection).

## 2. Objetivo

Entregar a definicao do agente (`agent/AGENTS.md` + `agent/mcp.config.json` apontando para
o `/mcp`) e um **harness de avaliacao** que dirige o **Claude Code headless** (`claude -p`,
sem key - ADR-0007) nas jornadas, com a logica deterministica (parser + assercoes) coberta
por **TDD**. O `agent/` e o payload que o container `sandbox` (increment 5) montara depois.

## 3. Escopo

- `agent/AGENTS.md`: papel, persona, politica, catalogo das 7 tools, guardrails no prompt
  (so afirmar o que veio de tool; confirmar antes de escrever; recusar acesso a outro
  cliente/injection; escalar fora de escopo).
- `agent/mcp.config.json`: wiring do MCP (`type: http`, `url: http://localhost/mcp`).
- `src/evals/`: **harness** - parser do stream-json (`parse_run`), modelo `AgentRun`,
  assercoes por jornada (puro, testavel) + runner CLI (`run.py`) que invoca `claude -p`.
- Jornadas cobertas: J1 (segunda via), J2 (outage), J3 (chamado com confirmacao - nao
  escreve / escreve), J6 (injection + acesso cruzado), J7 (handoff), cliente desconhecido.

## 4. Fora de escopo

- **J4** (memoria/follow-up): exige sessao multi-turno (Genie) - fora do harness single-turn.
- **J5** (notificacao proativa): deterministica, sem LLM (ADR-0005) - nao e comportamento do agente.
- Wiring Omni/Genie no `sandbox` (increment 5) e KB/`search_knowledge_base` (ADR-0004).

## 5. Criterios de aceite

- Harness (logica) verde por TDD: `parse_run` extrai tool calls + resposta; assercoes
  classificam corretamente cada jornada.
- Run ao vivo (sem TDD) contra o `/mcp`: agente usa a tool certa, **confirma antes de
  escrever**, **recusa injection e acesso a outro cliente**, e informa cliente desconhecido.
- ruff e mypy estrito limpos; suite anterior verde.

## 6. Plano de testes

- **TDD (unit, sem LLM/custo)**: `parse_run` sobre fixture de stream-json; cada assercao
  sobre `AgentRun` sintetico - tool presente/ausente, `create_ticket(confirmar=true)`
  presente/ausente, telefone de outro cliente nos args, palavras de recusa.
- **Eval ao vivo (sem TDD)**: `python -m src.evals.run` dirige `claude -p` por jornada
  contra o stack no ar; relatorio por cenario.

## 7. Riscos

- Variabilidade do LLM nas assercoes por texto: mitigada priorizando assercoes sobre
  **tool calls** (robustas) e usando palavras-chave lenientes no texto.
- Custo/quota do `claude -p`: o run ao vivo e comando separado, nao entra na suite unit.

## 8. PR relacionado

- Branch: `feature/SPEC-004-agent`. PR a preencher ao abrir.
