# Runbook operacional — khal-ai-challenge

Playbook reutilizavel para **operar** a entrega: subir o stack, ligar a sandbox do agente, rodar
os evals, diagnosticar problemas comuns e mitigar o cold-start. E o roteiro determinístico que um
operador (ou o CI) segue sem precisar do contexto de engenharia.

- Item do roadmap: **R-18** (`docs/11-roadmap-melhorias-agente.md`).
- Complementa: `sandbox/RUNBOOK.md` (passo a passo **interativo** de login/QR/E2E WhatsApp),
  `README.md` (setup rapido), `docs/adrs/ADR-0006` (topologia de execucao/sandbox),
  `docs/adrs/ADR-0016` (cloud provisioning como decisao-de-nao-fazer — secao "Promocao a cloud"
  abaixo).

> Convencao: comandos a partir da raiz do repo (`implementation/`). Onde houver alvo de Makefile,
> ele e a forma canonica; o comando cru aparece so quando esclarece o que o alvo faz.

---

## 0. Pre-requisitos

- Docker + Docker Compose.
- Para os evals ao vivo: **Claude Code autenticado** (ADR-0007, sem API key dedicada) **ou** o
  segredo `ANTHROPIC_API_KEY` (no CI / eval headless).
- Para o E2E WhatsApp real: dois numeros (bot + cliente) — ver `sandbox/RUNBOOK.md`.
- `.env` a partir de `.env.example` (ajuste `SEED_PERSONAS` com os numeros de demo; **nunca**
  commitar numeros reais).

---

## 1. Subir o stack de negocio (determinístico)

```bash
cp .env.example .env     # ajuste SEED_PERSONAS e credenciais locais
make compose-up          # database + seed (one-shot) + backend + frontend + mcp-server + gateway
```

Verifique a convergencia:

```bash
docker compose ps                                  # todos Up; o servico `seed` sai 0 (one-shot)
curl -s -o /dev/null -w "backend %{http_code}\n" http://localhost/api/health
curl -s -o /dev/null -w "mcp %{http_code} (espera 406)\n" http://localhost/mcp
```

Superficies expostas (via gateway):
- Console do operador: `http://localhost/`
- API legada (Swagger): `http://localhost/api/docs`
- MCP server (streamable-HTTP): `http://localhost/mcp`
- Faturas (PDF servidas do MinIO): `http://localhost/files/...`

**Re-seed do zero** (massa determinística, idempotente — `SEED_RANDOM_SEED=42`):

```bash
docker compose down -v && make compose-up
```

**Trocar persona** (1 a ~100; persona unica → perfil rico, SPEC-006):

```bash
# .env: SEED_PERSONAS="Nome:telefone;Outra:telefone"
docker compose down -v && make compose-up
# ou pontual (sem recriar tudo):
docker compose run --rm -e 'SEED_PERSONAS=Edgar Damasceno:5511999998888' seed
```

---

## 2. Subir a sandbox do agente (Omni/Genie) — determinístico

A sandbox e isolada (ADR-0006): so alcanca o negocio via `mcp-server`. Build das imagens (uma vez):

```bash
docker build -f sandbox/Dockerfile -t khal-sandbox:base .
docker build -t khal-egress-proxy sandbox/egress
```

Subir (sandbox + mcp na `mcpnet` + egress):

```bash
docker compose -f docker-compose.yml -f sandbox/compose.sandbox.yml \
  up -d --force-recreate mcp-server egress-proxy sandbox
```

**Checagem de isolamento** (o sandbox so enxerga o MCP — guardrail de rede, ADR-0006/ADR-0017):

```bash
docker exec khal-sandbox sh -c '
  curl -s -o /dev/null -w "mcp-server -> %{http_code} (espera 406)\n" http://mcp-server:8000/mcp
  curl -s -o /dev/null -w "backend    -> %{http_code} (espera 000)\n" --max-time 4 http://backend:8000/health
  curl -s -o /dev/null -w "database   -> %{http_code} (espera 000)\n" --max-time 4 http://database:5432'
```

Login + wiring + daemons + E2E (interno e WhatsApp real) seguem o **passo a passo interativo** de
`sandbox/RUNBOOK.md` (§2–§6). Resumo dos comandos-chave:

```bash
docker exec -it khal-sandbox claude login              # interativo (OAuth)
docker exec khal-sandbox bash /srv/genie-wire.sh       # monta AGENTS.md + registra o MCP
docker exec -d khal-sandbox sh -c 'bash /srv/sandbox-up.sh > /tmp/up.log 2>&1'   # daemons + genie serve
```

> **Atencao a recriacao de containers** (memoria operacional consolidada):
> - Recriar o **mcp-server sem** o override `sandbox/compose.sandbox.yml` o tira da `mcpnet` →
>   o agente perde **todas** as tools e responde "instabilidade tecnica". Sempre recrie com **ambos**
>   os arquivos `-f`.
> - Recriar o **backend** exige reconectar a rede externa `khal-wanet` (e ter as envs `OMNI_*` do
>   `.env`), senao o disparo de WhatsApp falha.
> - Recriar o **sandbox** depois do `claude login` derruba a sessao TUI → refaca `claude login`.

---

## 3. Rodar os evals

### 3.1 Ao vivo (local, contra o `/mcp`)

```bash
make agent-evals      # python -m src.evals.run — requer stack no ar + Claude Code autenticado
```

Usa o **mesmo** system prompt e o **mesmo** tool-scope de producao (paridade M-07; a allowlist
deriva da fonte unica `src/interfaces/mcp/allowlist.py`). O score e
`round(100 * PASS / TOTAL)`; o **gate >= 85** reprova a entrega.

### 3.2 Headless (CI, com segredo)

O job `eval-gate` do CI roda os evals quando `ANTHROPIC_API_KEY` esta presente; sem o segredo
(ex.: PR de fork) o job e **pulado** (skip), nao falha. Limiar por `EVAL_GATE_MIN` (default 85).

```bash
ANTHROPIC_API_KEY=... EVAL_GATE_MIN=85 python -m src.evals.run
```

---

## 4. Testes e qualidade

```bash
make test-unit          # dominio + use cases + API (repositorios fake) — dispensa banco
make test-integration   # repositorios contra Postgres (DATABASE_URL)
make check              # ruff + mypy + suite completa
```

Comandos crus equivalentes (uso direto com `uv`):

```bash
uv run ruff check .
uv run mypy src
uv run pytest tests/unit tests/api -q --ignore=tests/unit/test_invoice_renderer.py
DATABASE_URL="postgresql+psycopg://khal:khal_local_dev@localhost:5432/khal_test" \
  uv run pytest tests/integration -q
```

O teste de **paridade da allowlist** (`tests/unit/test_tool_scope_parity.py`) trava o drift do
tool-scope entre `server.py`, frontmatter e evals — ele falha de proposito se uma tool nova nao
entrar nas 3 fontes.

---

## 5. Lembrete proativo de vencimento (cron determinístico — SPEC-026)

O lembrete D-3/D-0 e **sem LLM** e roda como entrypoint de backend (idempotente por
`(fatura_id, dia)`):

```bash
docker exec khal-backend python -m src.infrastructure.events.reminder
```

Agendar (compose/CI/cron do host) com periodicidade diaria; reexecutar no mesmo dia **nao**
duplica (idempotencia). O cliente recebe o lembrete pelo Omni (best-effort) e ele vira fato de
sistema em `conversation_memory` (lido pelo agente via `get_account_events`).

---

## 6. Troubleshooting

| Sintoma | Causa provavel | Acao |
|---|---|---|
| Agente responde "instabilidade tecnica" / sem tools | `mcp-server` fora da `mcpnet` (recriado sem o override) | recrie com `-f docker-compose.yml -f sandbox/compose.sandbox.yml`; valide `curl http://mcp-server:8000/mcp` → 406 dentro do sandbox |
| `mcp %{http_code}` != 406 no host | gateway/mcp nao subiu | `docker compose ps`; `docker logs khal-mcp` |
| Tool nova nao aparece pro agente | drift de allowlist | rode `tests/unit/test_tool_scope_parity.py`; garanta a tool nas 3 fontes (server, frontmatter, run.py) derivadas de `allowlist.py` |
| 1o turno do chat "morto" / resposta duplicada | corrida do spawn a frio (cold-start) | ver §7; reenvie a 1a mensagem; dedup no bridge (M-06) |
| WhatsApp nao egressa a resposta | instancia nao pareada **ou** `backend` sem `khal-wanet`/`OMNI_*` apos recriacao | parear (sandbox/RUNBOOK §6); reconectar `khal-wanet` + envs `OMNI_*` |
| 2a via so vem por link, sem PDF anexo | midia em modo isolado (default) | `bash sandbox/enable-media.sh` (opt-in, ADR-0010); `disable-media.sh` restaura |
| `get_account_events` vazio para titular conhecido | memoria fragmentada por `chat_id` | backfill de `titular_id` (SPEC-027) idempotente; rode no boot/CI |
| Tool retorna stacktrace cru | backend caiu sem degradacao | M-03: a tool deve devolver erro tipado amigavel `{"erro": ...}`; verifique o backend |
| eval-gate "skipped" no CI | sem `ANTHROPIC_API_KEY` (ex.: fork) | esperado; o job `quality` ainda roda; rode os evals localmente |
| `claude` pede OAuth no spawn TUI | sandbox recriado apos `claude login` | `docker exec -it khal-sandbox claude login` |

Coleta rapida de evidencia:

```bash
docker logs khal-mcp | grep -c CallToolRequest                # tool-calls chegando no MCP
docker exec khal-sandbox sh -c 'tail -n 40 /tmp/up.log'        # bridge/genie
docker exec khal-sandbox sh -c 'tmux -L genie ls'             # sessoes do agente
```

---

## 7. Cold-start (mitigacao operacional)

O 1o turno de um chat **cria** a sessao tmux do agente e pode nao entrar na TUI a tempo (a entrega
corre com o bootstrap do Claude Code) — o painel fica vazio; o cliente reenvia e pode disparar dois
fluxos. Mitigacoes (em ordem de custo):

1. **Reenviar a 1a mensagem** (ou um `oi` de aquecimento antes da real) — a 2a entra via `deliver()`.
2. **Dedup no bridge** por `(chatId, messageId/timestamp)` na janela de cold-start (M-06) —
   descarta o 2o disparo se ha turno em voo para o mesmo chat (anti-resposta-duplicada).
3. **Warm-pool determinístico** (R-05): apos `genie serve start`, publicar 1 `omni.message`
   sintetica por persona-ancora (Ana/Carlos/Joana) para deixar o pane quente.
4. **Persistencia do `GENIE_PGDATA`** em volume nomeado (R-05): o `--resume` do Genie so vale 1x na
   vida do chat se o pgdata sobreviver ao `--force-recreate`.

Higiene de sessao (se janelas tmux foram mortas no diagnostico):

```bash
# DB genie (:19642): remova residuos de sessao do chat
delete from genie_bridge_sessions where chat_id ilike '%<lid-ou-telefone>%';
```

---

## 8. Promocao a cloud (decisao-de-nao-fazer — ADR-0016)

A entrega **nao** provisiona nuvem real nem traz IaC (Terraform/`systemd`) — decisao registrada em
**ADR-0016**. O alvo oficial e o **Docker Compose** (ADR-0006) + **CI/CD publico** (GitHub Actions,
R-01). O caminho de evolucao para producao real, se houvesse alvo de deploy, seria:

1. **Registry** de imagens (build → push versionado por tag/commit).
2. **Secrets manager** para `OMNI_*`, credenciais de DB e `ANTHROPIC_API_KEY` (fora do `.env`).
3. **Alvo gerenciado de containers** (o mesmo Compose traduzido para o orquestrador escolhido),
   mantendo o **isolamento de rede so-MCP** da sandbox.
4. **Observabilidade exportada** (o `tool_call_audit` + `trace_id` de R-10/ADR-0012 alimentando um
   backend de tracing/metricas — exportador OTel e o stretch documentado).
5. **Backup/retencao** do Postgres e do object storage (MinIO → bucket gerenciado).

Isso fica como **roteiro**, nao como codigo morto — coerente com "escolher nao-fazer e justificar"
(ADR-0016, `docs/11 §6.2`).
