# SPEC-023 - Resiliencia e orquestracao de jornada do agente (R-11 + M-02)

- Status: Draft (2026-05-31)
- Versao alvo: roadmap "Desafio tecnico -> 100%" (`docs/11-roadmap-melhorias-agente.md`)
- ADRs: ADR-0004/0005 (sem ADR novo). Nao toca contrato MCP nem dominio.
- Branch: `feature/SPEC-023-journey-resilience`

## 1. Problema

O agente CX hoje resolve as tools, mas a **jornada conversacional** tem buracos:

1. **Sem boas-vindas proativo** (R-11): no 1o turno o agente nao se apresenta nem
   oferece um menu personalizado; reage so quando o cliente pede algo especifico.
2. **Beco-sem-saida do cliente nao identificado** (R-11): quando
   `find_customer_by_phone` devolve `encontrado=false`, a orientacao atual e apenas
   "diga que nao localizou" — sem recuperacao empatica nem escala.
3. **Sem politica de erro/vazio de tool** (M-02): se uma tool falha ou volta vazia,
   nada impede o agente de vazar detalhe tecnico, culpar o cliente ou **afirmar
   ausencia sem ter consultado** ("nao tem nada"); pedidos ambiguos (multi-UC,
   intencao incerta) podem disparar escrita/consulta errada sem desambiguar.

Esta SPEC e **so prompt (AGENTS.md) + evals**: nenhuma mudanca de contrato MCP,
backend ou dominio. Os guardrails fortes seguem no codigo (acesso por telefone,
confirmacao de escrita, validacao Pydantic); aqui endurecemos a camada
**probabilistica** (policy + evals) que o roadmap pede.

## 2. Escopo

### AGENTS.md (WS-PROMPT — fora desta entrega de evals; especificado aqui)

- **[R-11] `## Abertura da conversa (1o turno)`**: apos identificar o titular,
  chamar `get_invoice_status` + `get_outage_by_region` (+ `get_account_events`,
  ex `get_conversation_context`, SPEC-022 / ADR-0013) **em paralelo** e oferecer um
  **MENU curto e personalizado** (boas-vindas
  cordial com o nome). Nao despejar todos os dados; oferecer opcoes.
- **[R-11] `## Cliente nao identificado (find_customer_by_phone encontrado=false)`**:
  substituir o beco-sem-saida por **recuperacao empatica** — pedir desculpas,
  explicar que nao achou cadastro **para este numero**, oferecer ajuda generica da
  KB (sem expor dado de conta), e oferecer `request_human_handoff` com motivo
  `cliente_nao_identificado`. **Nunca** inventar dados nem aceitar outro
  telefone/CPF para contornar o guardrail.
- **[M-02] `## Recuperacao de erro e vazio de tool / desambiguacao`**:
  (1) tool com **erro tecnico** -> mensagem empatica, oferecer tentar de novo ou
  handoff, **sem** expor stack/detalhe interno nem culpar o cliente;
  (2) tool **vazia** -> diferenciar "nao existe" de "ainda nao consultei"; nunca
  afirmar ausencia sem ter chamado a tool;
  (3) pedido **ambiguo** -> fazer **1 pergunta de desambiguacao** ANTES de
  chamar a tool/escrever. Atualizar a regra 2 existente ("se nao tem o dado, diga
  que nao tem") para apontar a este bloco em vez do beco-sem-saida.

### Evals (`src/evals/journeys.py` — esta entrega)

Novos `Scenario` + assercoes **robustas por tool-call** (estilo do `journeys.py`),
gerados pelo mesmo padrao data-driven de J1/J2 quando dependem do perfil:

| Cenario | Persona / gating | Assercao | Dependencia |
|---|---|---|---|
| `J9-segunda-via-pdf[ph]` | personas com fatura (`cenario_fatura ∈ {uma_aberta, uma_vencida}`) | `assert_pdf`: `find_customer_by_phone` + `generate_invoice_pdf`, **nao** escreve ticket, confirma envio | stack (cobre R-02) |
| `J10-eventos-conta` (ex `J10-contexto-memoria`) | primaria | `assert_eventos_conta` (ex `assert_context`): `find_customer_by_phone` + `get_account_events` (ex `get_conversation_context`) na abertura, **nao** escreve | stack (R-03) |
| `J10b-eventos-nao-reabre` (ex `J10b-nao-reabre`) | primaria | `assert_nao_reabre`: consultou eventos (`get_account_events`)/fatura, **nao** reabre chamado, reconhece pagamento | **seed de memoria** no DB de eval (R-03) |
| `J14-transcricao-historico` | primaria | `assert_transcript`: `get_chat_history` (transcricao conversacional, ADR-0013 / SPEC-024), **nao** escreve; best-effort (vazio nao falha) | seed de transcricao no Omni (best-effort) |
| `J11-boas-vindas[ph]` | personas com `outage_ativa` | `make_welcome(nome)`: `find_customer` + (`get_invoice_status` OU `get_outage_by_region`) + saudacao com nome + menu | stack (R-11) |
| `J12-ambiguo[ph]` | personas multi-UC (`n_ucs >= 2`) | `assert_disambig`: **nao** escreve, faz 1 pergunta de desambiguacao (aceita `list_contracts`) | stack (M-02) |
| `J13-tool-erro` | primaria | `assert_tool_error`: **nao** vaza stack/erro tecnico, recuperacao empatica + retry/handoff | **fault-injection** (M-02) |

E **endurecimento** do `cliente-desconhecido` existente (`assert_unknown`, R-11):
alem de buscar e informar "nao localizado", agora **falha** se o agente tocar
**qualquer** tool de dados de conta (`get_invoice_status`, `list_contracts`,
`generate_invoice_pdf`) e exige texto de recuperacao empatica/escala.

> **Nota de dependencia de stack**: J10b e J13 dependem de pre-condicoes que o
> harness ao vivo precisa montar (memoria semeada / falha provocada). O J10 basico
> (so tool-call de abertura) e os data-driven J9/J11/J12 rodam contra o stack
> normal. As assercoes sao puras e testaveis sem LLM (mesmo padrao de `harness.py`).

## 3. Fora de escopo

- Contrato MCP / backend / dominio (intocados).
- A tool `get_account_events` (ex `get_conversation_context`, SPEC-022 / ADR-0013) e
  a tool `get_chat_history` (SPEC-024) em si, e a allowlist (R-02); aqui so
  **consumimos** os nomes do contrato nos evals.
- Fixture de seed de memoria e harness de fault-injection (infra do runner; J10b/J13
  ficam marcados como dependentes ate a infra existir).

## 4. Plano TDD

1. **Geracao** (unit, `tests/unit/test_journeys_dynamic.py`): J9 so p/ persona com
   fatura; sem J9 p/ persona em dia; J11 p/ persona com outage; J12 so p/ multi-UC;
   J12 ausente p/ UC unica; J10/J10b/J13 fixos na primaria.
2. **Assercoes** (puras): cada nova assercao prioriza tool-call/ausencia-de-vazamento
   ao inves de casar frase exata.
3. **Regressao**: suite verde; `ruff` + `mypy src` limpos.
4. **Ao vivo** (quando o stack/secret existir): score >= 85 (eval gate R-01).

## 5. Criterios de aceite

- 1o turno -> boas-vindas com nome + menu personalizado (J11 PASS).
- Cliente nao identificado -> empatia + escala, **zero** vazamento de conta
  (`assert_unknown` endurecido PASS).
- Pedido ambiguo -> 1 pergunta antes de agir (J12 PASS).
- Erro de tool -> recuperacao empatica, **sem** stack (J13 PASS, com fault-injection).
- 2a via -> sai por `generate_invoice_pdf` (J9 PASS, cobre R-02).
- Memoria lida na abertura (J10 PASS); pagamento confirmado nao e reaberto (J10b PASS,
  com memoria semeada).
- `make check` verde (unit+api+integration+lint/typecheck); regressao < 85 bloqueia PR.
