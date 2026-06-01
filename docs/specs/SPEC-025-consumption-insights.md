# SPEC-025 - `get_consumption_insights`: tool MCP read-only de insights de consumo (~24 meses do seed)

- Status: Approved (2026-05-31)
- Versao alvo: 1.6.0 (o agente passa a explicar o consumo do titular: media, tendencia,
  sazonalidade e pico, sobre o historico de ~24 meses ja existente no seed)
- Item do roadmap: **R-17** (`docs/11-roadmap-melhorias-agente.md §3.1`).
- ADRs: **ADR-0012** (auditoria por tool-call — cobre a tool sem mudanca de mecanismo),
  **ADR-0017** (camada legada como ACL via MCP-over-REST — a tool **reusa** o REST existente, sem
  endpoint novo), **ADR-0014** (token-opt — calculo deterministico, sem LLM, mantem a tool fora do
  caminho caro), **ADR-0008** (seed determinístico — a fonte dos ~24 meses).
- Relacao com SPEC-013 (multi-UC): um bloco de insights **por UC**, espelhando `list_contracts`.

## 1. Problema

O seed materializa **~24 meses** de faturas por UC (`consumo_kwh` + `valor` por `mes_referencia`,
`src/domain/billing/entities.py:Fatura`), mas o agente **nao tem como ler tendencia/sazonalidade**:
hoje so consulta a fatura corrente (`get_invoice_status`) e a lista de faturas crua via REST. O
cliente pergunta "por que minha conta subiu?", "esse mes foi mais caro que o ano passado?",
"qual meu pico?" — e o agente nao consegue responder com numero, so com texto generico. Falta uma
tool que **resuma** o historico em insights estaveis e deterministicos.

## 2. Objetivo

Uma **12a tool MCP read-only** `get_consumption_insights(phone)` que resolve o titular pelo
telefone do remetente (guardrail identico as demais) e calcula, **sem LLM**, insights de consumo
sobre o historico de ~24 meses **ja disponivel** via `LegacyApiClient.list_invoices`
(`consumo_kwh` + `valor` por `mes_referencia`). **Nao exige endpoint REST novo nem mudanca no
backend** — preserva o cluster legado disjunto (ADR-0017). Um bloco por UC (multi-UC, espelha
`list_contracts`).

## 3. Contrato da tool

```python
get_consumption_insights(phone: str) -> dict[str, Any]
```

- **Sucesso (titular resolvido, com historico):**
  ```json
  {
    "encontrado": true,
    "titular": "Ana Souza",
    "unidades": [
      {
        "numero_uc": "0012345678",
        "meses_analisados": 24,
        "media_kwh": 318.5,
        "tendencia": "subindo",
        "variacao_pct_ult_vs_media": 12.7,
        "pico": {"mes_referencia": "2026-01", "consumo_kwh": 412},
        "comparativo_sazonal": {"mesmo_mes_ano_anterior_kwh": 305, "variacao_pct_yoy": 8.2},
        "ultimo_mes": {"mes_referencia": "2026-05", "consumo_kwh": 359}
      }
    ],
    "observacao": "Analise sobre 24 meses de historico por unidade consumidora."
  }
  ```
  `tendencia` ∈ `"subindo" | "estavel" | "caindo"`. **Shape estavel** (M-03): mesmo formato em
  todos os casos.
- **Telefone nao resolve titular:** `{"encontrado": false, "motivo": "Telefone nao identificado."}`
  (mesmo formato das demais tools) — e **nenhum** historico e lido.
- **Sem historico / UC vazia:** o bloco da UC vem com `meses_analisados=0` e campos numericos
  neutros (`media_kwh=0.0`, `tendencia="estavel"`, `pico`/`ultimo_mes`/`comparativo_sazonal` com
  `None`), e `observacao` amigavel — **nunca** stacktrace (alinhado com M-03).
- **Backend indisponivel:** retorna o **erro tipado amigavel** definido por M-03
  (`{"erro": "instabilidade", ...}`), **nunca** stacktrace cru.
- **Read-only:** nao escreve, nao muta estado.

## 4. Calculo deterministico (sem LLM)

Por UC, sobre a lista de `(mes_referencia, consumo_kwh)` ordenada por `mes_referencia`:

1. **`media_kwh`** = media aritmetica dos `consumo_kwh` (arredondada a 1 casa).
2. **`tendencia`** = comparacao **janela recente x media** (media dos 3 ultimos meses vs. media
   geral) com **thresholds fixos**: `> +5%` → `"subindo"`; `< -5%` → `"caindo"`; senao
   `"estavel"`. (Implementacao pode usar slope de regressao simples como equivalente; o contrato
   fixa **so o rotulo e os thresholds**, nao a aritmetica interna.)
3. **`variacao_pct_ult_vs_media`** = `(ultimo_mes - media) / media * 100` (1 casa; `0.0` se media=0).
4. **`pico`** = `max(consumo_kwh)` com seu `mes_referencia`.
5. **`comparativo_sazonal`** = casa o **mes** do ultimo registro (`YYYY-MM` → `MM`) com o **mesmo
   mes do ano anterior** (`YYYY-1`); devolve `mesmo_mes_ano_anterior_kwh` e `variacao_pct_yoy`.
   Sem par do ano anterior → ambos `None`.
6. **`ultimo_mes`** = `mes_referencia` mais recente + seu `consumo_kwh`.

Determinístico e idempotente: mesmas faturas → mesmos numeros. **Sem** chamada de LLM, sem rede
alem do REST que ja existe.

## 5. Guardrail (deterministico, no codigo — nao no prompt)

1. Resolve o titular **sempre** pelo `phone` do remetente (`find_customer`), **nunca** por
   `id`/`numero_uc` citado pelo cliente (nao contornavel por injection). `find_customer` → `None`
   ⇒ `{"encontrado": false}` e **nada** e lido.
2. Le **apenas** as UCs/faturas do proprio titular resolvido (mesmo caminho de `list_contracts` →
   `list_invoices`), nunca de UC citada pelo cliente.
3. **Degradacao graciosa (M-03):** backend caido → erro tipado amigavel, sem stacktrace; historico
   vazio → `meses_analisados=0`, sem afirmar consumo inexistente.
4. Auditada por `AuditedCxTools` (ADR-0012): log estruturado + sink best-effort, PII mascarada
   (`phone` → sufixo de 4 digitos), `trace_id` propagado (R-10).

## 6. Escopo

### MCP (entregue nesta SPEC)
- `tools.py`: `CxTools.get_consumption_insights(phone)` — resolve o titular por `find_customer`,
  itera as UCs (como `list_contracts`), le as faturas de cada UC via `list_invoices` e calcula os
  insights (secao 4). Reusa o caminho de erro tipado de M-03.
- `audit.py`: `AuditedCxTools.get_consumption_insights` (espelha a superficie, instrumentada —
  igual as outras 11 tools).
- `server.py`: **12a** `@mcp.tool() get_consumption_insights`, registrada **por ultimo** (ordem
  estavel/cache R-07; entra apos `get_chat_history`).
- Allowlist (fonte unica `src/interfaces/mcp/allowlist.py`, R-02): a tool entra como **12o** nome
  (`get_consumption_insights`), habilitada em **producao** (frontmatter) e nos **evals**
  (`run.py`), com **teste de paridade** que impede drift (passa de 11 → 12).
- `AGENTS.md` (cluster prompt, R-13): na secao de tools, `get_consumption_insights` =
  "explicar o consumo do cliente (media/tendencia/sazonalidade/pico)"; usar quando o cliente
  pergunta "por que subiu?", "qual meu pico?", "comparado ao ano passado?".

### REST (reuso puro, ADR-0017 — sem endpoint novo)
- **Sem endpoint REST novo.** A tool consome o `list_invoices` que o `LegacyApiClient` ja expoe
  (`GET .../invoices` por UC). Todo o calculo de insight vive no **lado MCP** (cluster mcp);
  o backend/legado **nao muda** (mantem o cluster disjunto).

## 7. Fora de escopo

- **Endpoint REST de insights** no backend: nao; o calculo e do lado MCP sobre o `list_invoices`
  existente.
- **Previsao/forecast** de consumo futuro (regressao preditiva, ML): nao — so descritivo sobre o
  historico.
- **Valor em R$** como insight primario: o foco e `consumo_kwh`; valor pode entrar como campo
  secundario em iteracao futura, fora desta SPEC.
- **Grafico/render**: a tool devolve numeros estaveis; visualizacao e do console/cliente, nao da
  tool.
- Escrita/mutacao pela tool (read-only).

## 8. Plano TDD

1. **Calculo (unit, sem rede):** dada uma serie sintetica de 24 meses, assertar `media_kwh`,
   `tendencia` (cada um dos 3 rotulos via series subindo/estavel/caindo), `pico`,
   `comparativo_sazonal` (com e sem par do ano anterior), `ultimo_mes` e
   `variacao_pct_ult_vs_media`.
2. **Tool (unit, fakes):**
   - resolve o titular e devolve um bloco por UC (multi-UC, espelha `list_contracts`);
   - telefone desconhecido → `encontrado=false` e **nao** le faturas;
   - **nao vaza** consumo de outro titular (le so as UCs do titular resolvido);
   - historico vazio → `meses_analisados=0` + `observacao` amigavel, sem quebrar;
   - backend indisponivel → erro tipado amigavel (M-03), sem stacktrace.
3. **Paridade (R-02)** `tests/unit/test_tool_scope_parity.py`: `get_consumption_insights` presente
   nas 3 fontes (server, eval-scope, frontmatter) na posicao 12; server == allowlist em conjunto e
   ordem (**12** tools); `test_pdf_and_memory_tools_present` ganha a nova tool.
4. **Contagem:** `server.py` registra **12** `@mcp.tool()` (11a = `get_chat_history`,
   12a = `get_consumption_insights`).
5. **Eval (cluster evals, M-08)** `J15-insights-consumo`: persona com historico, msg "por que
   minha conta esta mais cara esse mes?" — assercao por tool-call:
   `run.called('get_consumption_insights') and not run.wrote_ticket()`.
6. **Regressao:** suite verde; o contrato das outras 11 tools roda **inalterado** (o teste de
   paridade sobe 11→12 mas as demais tools nao mudam).

## 9. Criterios de aceite

- O agente explica media/tendencia/sazonalidade/pico do titular via `get_consumption_insights`,
  com um bloco por UC, sobre os ~24 meses do seed.
- Guardrail: telefone sem titular → `encontrado=false`, **sem** leitura de faturas; a tool jamais
  devolve consumo de UC que nao seja do titular resolvido.
- Calculo **deterministico**: mesmas faturas → mesmos numeros (idempotente, sem LLM).
- Robustez: historico vazio → `meses_analisados=0` + observacao amigavel; backend caido → erro
  tipado amigavel (M-03), **nunca** stacktrace.
- A tool aparece em **producao** (frontmatter) **e** nos **evals** como `get_consumption_insights`
  (12o nome da allowlist), e o teste de paridade bloqueia drift.
- unit + api + integration + lint/typecheck verdes.

## 10. Notas

- **Sem endpoint REST novo / cluster legado disjunto (ADR-0017):** a tool reusa `list_invoices`; o
  trabalho e so no lado MCP (tool + audit + server + allowlist + frontmatter + evals + AGENTS.md).
- **Ordem de registro** em `server.py` = ordem em `allowlist.TOOL_NAMES` = ordem em `run.py`:
  pre-requisito de prompt caching (R-07, ADR-0014) e contrato do teste de paridade.
- **Coordenacao no cluster MCP:** M-03 define o **erro tipado** primeiro; esta tool **reusa** esse
  caminho de degradacao (nao duplica) — historico vazio e backend-caido sao casos distintos
  (`meses_analisados=0` vs. `{"erro": ...}`).
