# SPEC-031 - 2ª via em PDF de QUALQUER fatura (paga/vencida/em aberto), por competência + UC

- Status: Approved (2026-06-01)
- Versao alvo: 1.x (`generate_invoice_pdf` aceita `mes_referencia` + `numero_uc` opcionais)
- ADRs: ADR-0003 (PDF por `send/media`, não pelo reply). Relaciona-se com SPEC-008 (render do PDF,
  que já marca d'água `PAGA`/`VENCIDA`/`EM ABERTO`) e SPEC-017 (envio por id, sem trava de status).
  Sem ADR novo.

## 1. Problema

O cliente pediu: deveria ser possível gerar o PDF de **qualquer** fatura — **paga**, **vencida** ou
**em aberto**. Hoje o tool MCP `generate_invoice_pdf(phone)` resolve **uma** fatura sozinho
(`src/interfaces/mcp/tools.py`): `alvo = max(abertas or faturas, key=mes_referencia)` — prioriza a
**mais recente em aberto** e só cai numa paga se **não houver aberta**. Logo o cliente **não
consegue pedir uma fatura específica** (ex.: a paga de março, ou a de abril de uma UC) quando há
faturas em aberto.

A trava é **só na seleção do tool**: o envio por id (`InvoiceDocumentService.enviar_2a_via`) e o
renderer (WeasyPrint) já tratam qualquer status — não há restrição abaixo.

## 2. Objetivo

Dar ao agente como **mirar a fatura**: `generate_invoice_pdf` ganha `mes_referencia` (competência
`AAAA-MM`) e `numero_uc` (UC humana) **opcionais**. Com eles, gera o PDF da fatura exata, **qualquer
status**. Sem eles, comportamento atual (default = mais recente em aberto, senão a mais recente).

## 3. Escopo

### Tool (`src/interfaces/mcp/tools.py` + `server.py` + `audit.py`)
- `generate_invoice_pdf(phone, presigned=False, mes_referencia=None, numero_uc=None)`.
- Anexa `numero_uc` (da unidade do contrato) a cada fatura coletada.
- Filtra por `mes_referencia` e/ou `numero_uc` quando dados:
  - sem candidata → `{gerado: False, motivo: "Sem fatura de <mês>[ na UC <uc>] nesta conta."}`;
  - candidatas em **mais de uma UC** e **sem** `numero_uc` → `{gerado: False, precisa_unidade: True,
    unidades: [...], motivo: ...}` (desambigua: o agente pergunta a UC) — atende o "preciso";
  - senão → a fatura (determinística), **qualquer status**.
- Sem filtro → seleção default de hoje (intacta).

### Agente (`agent/AGENTS.md`)
- Regra: o agente pode gerar a 2ª via de **qualquer** fatura. Se o cliente pedir uma específica
  (mês/"a paga"/"a de abril"), passa `mes_referencia` (usa `get_invoice_status`/insights p/ os meses);
  em multi-UC, passa `numero_uc` (ou pergunta se ambíguo via `precisa_unidade`).

## 4. Fora de escopo
- Mudar o renderer ou o envio por id (já fazem qualquer status).
- Listar/paginar todas as faturas no tool (continua 1 PDF por chamada).
- Mudar a seleção default (sem filtro = comportamento atual).

## 5. Plano TDD
1. **mes_referencia → paga** (unit): `generate_invoice_pdf(ANA, mes_referencia="2026-04")` →
   `gerado=True`, `status="paga"`, `mes_referencia="2026-04"` (fake `send_invoice` passa a ecoar a
   fatura do id — necessário p/ a asserção; não quebra os testes existentes).
2. **não encontrada**: `mes_referencia` inexistente → `gerado=False` com motivo.
3. **numero_uc**: UC errada → `gerado=False`; UC certa + mês → a fatura.
4. **multi-UC ambíguo** (fake local de 2 UCs, mesmo mês, sem `numero_uc`) → `precisa_unidade=True`.
5. **regressão**: `generate_invoice_pdf(ANA)` sem filtro segue na 2026-05 em aberto; paridade de
   allowlist verde (o **nome** da tool não muda).

## 6. Critérios de aceite
- `generate_invoice_pdf` gera o PDF de uma fatura **paga** quando `mes_referencia` é dado.
- Multi-UC: mira preciso com `numero_uc`; desambigua quando ambíguo.
- Default inalterado; unit + paridade de allowlist + ruff/mypy verdes.
