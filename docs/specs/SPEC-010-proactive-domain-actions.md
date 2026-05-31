# SPEC-010 - Proativos como ações de domínio (estado + notificação)

- Status: Approved (2026-05-30)
- Versao alvo: 1.1.0 (proativos mutam o banco, nao so notificam)
- ADRs: ADR-0005 (eventos determinIsticos -> memoria). Sem ADR novo.

## 1. Problema

Os proativos (SPEC-009) **só notificam** + gravam memoria. Mas a acao do operador e
**real**: confirmar pagamento deve **dar baixa na fatura**; abrir/encerrar interrupcao deve
**persistir o status** da interrupcao. Hoje o status nao muda no banco — o agente, num proximo
turno, ainda ve a fatura "em aberto" e a outage "ativa".

## 2. Objetivo

Cada evento proativo executa a **acao de dominio** (muta o estado, deterministico) **e** dispara
a notificacao (SPEC-009). O estado fica consistente: a fatura paga some dos pendentes; o status
da interrupcao reflete o ultimo toggle.

### Decisoes de arquitetura
- A **mutacao** roda no caso de uso do backend (`disparar_por_telefone`), que tem repos + UoW;
  o **worker** (SPEC-009) segue so notificando (render + Omni + memoria).
- Idempotente: pagamento ja pago / outage ja no status alvo -> no-op (sem erro, re-notifica).
- **Toggle** de interrupcao no console: abre (ativa) ou encerra a interrupcao do bairro.

## 3. Escopo

### Acoes
- **pagamento.confirmado** (`fatura_id`): `faturas.status='paga'` + insere `pagamentos`
  (idempotency_key estavel). Enriquece os dados (mes/valor) para a notificacao.
- **outage.aberta** (`bairro`[, `causa`, `previsao`]): se nao ha interrupcao **ativa** no bairro,
  cria (status `ativa`, inicio=now). Se ja ha, no-op.
- **outage.encerrada** (`bairro`): a interrupcao **ativa** do bairro -> `encerrada` + `encerrada_em`.

### Back
- Repos de **escrita**: `FaturaRepository.marcar_paga(...)`, `InterrupcaoRepository.abrir/encerrar(...)`.
- `ProactiveService.disparar_por_telefone`: executa a acao (commit) -> publica o evento -> preview.
- `candidatos` continua listando faturas em aberto + interrupcao ativa (dirige o toggle).

### Front (console)
- Aba **Proativos**: o card de interrupcao vira **toggle** (mostra "Avisar interrupcao" quando
  nao ha ativa; "Avisar normalizacao" quando ha) e **recarrega** os candidatos apos a acao
  (fatura paga some; status da outage atualiza).

## 4. Fora de escopo

- Reverter pagamento (estorno) / historico de toggles de outage (so o status corrente).
- LLM em qualquer ponto (ADR-0005: deterministico).

## 5. Plano TDD

1. **Repos de escrita** (integration): `marcar_paga` (status + pagamento, idempotente),
   `abrir`/`encerrar` interrupcao (status persiste, idempotente).
2. **ProactiveService**: `disparar` muta o estado conforme tipo/subtipo + publica (unit, fakes).
3. **REST**: `POST /events` reflete a mutacao (api).
4. **Front**: toggle + reload (build do console).
5. **Regressao**: suite verde; evals nao afetados.

## 6. Criterios de aceite

- Confirmar pagamento pelo console -> fatura **paga** no banco (some dos pendentes) + notifica.
- Toggle de interrupcao -> status **persiste** (`ativa`/`encerrada`) + notifica.
- Idempotente; unit+integration+api+lint/typecheck verdes; console builda.
