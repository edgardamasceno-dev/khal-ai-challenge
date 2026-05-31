# SPEC-011 - Status de fatura editável no console (+ aviso de vencida)

- Status: Approved (2026-05-30)
- Versao alvo: 1.2.0 (operador ajusta o status da fatura; vencida notifica)
- ADRs: ADR-0005 (eventos determinísticos -> memória). Sem ADR novo.

## 1. Problema

A tabela **Unidade & Faturas** (`InvoicesTable`) é read-only. Depois da baixa (SPEC-010)
a fatura vira `paga` e não há como **reverter** para `em_aberto`/`vencida` — nem para
re-testar o fluxo de pagamento, nem para preparar cenários de demo/eval. O operador
precisa **ajustar o status** direto na lista de contas.

## 2. Objetivo

Tornar o status da fatura **editável** pelo operador na tabela: `em_aberto` ou `vencida`.
Reverter de `paga` **desfaz a baixa** (remove o pagamento, libera a `idempotency_key`).
Marcar **vencida** dispara o aviso proativo de fatura vencida; **em aberto** é silencioso.

### Decisões
- A baixa para `paga` continua só pela aba Proativos (SPEC-010). Este controle cobre
  apenas `em_aberto`/`vencida` (validado no domínio).
- Reverter de `paga` **apaga o(s) pagamento(s)** da fatura (consistência; re-pagar volta a
  funcionar). Idempotente.
- A mutação roda no backend; a notificação de `vencida` reusa o pipeline proativo
  (`pagamento.vencida`, novo evento determinístico — ADR-0005).

## 3. Escopo

### Domínio
- `EVENTOS_VALIDOS` += `("pagamento","vencida")`; template `render_notificacao` para o
  aviso de vencimento (nome, mês, valor, alerta de juros/multa + instrução PIX/boleto).

### Back
- `FaturaRepository.atualizar_status(fatura_id, status, now)`: seta o status; se a fatura
  saía de `paga`, **remove** os `pagamentos` dela. Devolve a `Fatura` (ou `None`).
- `BillingService`: ganha `UnitOfWork`; `atualizar_status_fatura(fatura_id, status)` (valida
  status ∈ {em_aberto, vencida}, muta + commit) e `get_titular_por_fatura(fatura_id)`.
- REST: `PATCH /invoices/{fatura_id}/status {status}` -> muta; se `vencida`, resolve o
  titular e dispara `pagamento.vencida` (best-effort). Devolve `InvoiceDTO`.

### Front (console)
- `InvoicesTable` ganha um seletor de status por linha (`em_aberto`/`vencida`; `paga` aparece
  como atual, não selecionável). Ao alterar: `PATCH` -> recarrega a lista; toast com o efeito.

## 4. Fora de escopo

- Marcar `paga` pela tabela (continua na aba Proativos).
- Histórico de transições de status (só o estado corrente).
- LLM em qualquer ponto (ADR-0005).

## 5. Plano TDD

1. **Domínio** (unit): evento `pagamento.vencida` válido + template renderiza mês/valor/alerta.
2. **Repo** (integration): `atualizar_status` persiste; reverter de `paga` remove pagamento.
3. **Service** (unit, fakes): `atualizar_status_fatura` valida e muta; `get_titular_por_fatura`.
4. **REST** (api): `PATCH` muta; `vencida` publica o evento; `em_aberto` não publica.
5. **Front**: seletor + reload (build do console).
6. **Regressão**: suite verde; evals não afetados.

## 6. Critérios de aceite

- Operador muda o status pela tabela -> persiste no banco; reverter de `paga` apaga o pagamento.
- `vencida` dispara o aviso proativo; `em aberto` é silencioso.
- Idempotente; unit+integration+api+lint/typecheck verdes; console builda.
