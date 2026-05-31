# SPEC-015 - Resolução de identidade do remetente (LID + nono dígito)

- Status: Approved (2026-05-30)
- Versao alvo: 1.3.1 (find_customer resolve LID e tolera o nono dígito)
- ADRs: ADR-0004 (guardrail determinístico no código). Sem ADR novo.

## 1. Problema

O agente recebe do canal o **LID do WhatsApp** (ex.: `87866608713902@lid`), não o
telefone. As tools MCP começam com `find_customer_by_phone(phone)` passando esse LID;
o backend faz `GET /customers?phone=87866608713902` -> **404**. Resultado: 2ª via,
abrir chamado e handoff **todos falham** com "telefone não identificado".

Há **dois** problemas encadeados:
1. **LID ≠ telefone.** O Omni mapeia em `GET /api/v2/chats` (`externalId` `…@lid`
   ↔ `canonicalId` `…@s.whatsapp.net`).
2. **Nono dígito.** O canonical vem **sem** o 9 (`558193112159`), mas o cadastro é
   **com** 9 (`5581993112159`). Mesmo resolvendo o LID, a busca exata falha.

## 2. Objetivo

`find_customer_by_phone` passa a aceitar **LID ou telefone (com/sem 9)** e resolver o
titular de forma determinística. Conserta 2ª via, abrir chamado e a identificação que
precede o handoff (SPEC-016) — todas as tools chamam `find_customer` primeiro.

## 3. Escopo

### Domínio
- `src/domain/shared/phone.py`: `normalizar_msisdn(raw)` (tira `@lid`/`@s.whatsapp.net`/
  `+`/espaços, valida dígitos) e `variantes_nono_digito(msisdn)` (gera as formas com e
  sem o 9 após o DDD — BR).

### Back
- `TitularRepository.find_by_phone_em(telefones)` — busca por `telefone_principal IN (...)`.
- `ChatDirectoryPort` + adapter `HttpxOmniChats`: `resolve_canonical(external_id)` consulta
  o Omni `/api/v2/chats`, casa o `externalId`, devolve o `canonicalId` normalizado.
- `BillingService.find_customer_by_phone(identificador)`:
  1. normaliza; busca o titular pelas **variantes de nono dígito** (direto).
  2. se não achou, resolve o LID via Omni (`canonicalId`) e busca pelas variantes dele.
  3. senão, `NotFoundError`. (Guardrail intacto: só o titular resolvido pelo remetente.)
- Wiring: o backend já alcança o Omni (SPEC-014); `HttpxOmniChats` usa as mesmas settings.

## 4. Fora de escopo

- Pausar a IA / handoff humano (SPEC-016).
- Persistir o mapeamento LID↔telefone localmente (consulta o Omni on-demand; cache fica p/ depois).

## 5. Plano TDD

1. **Domínio** (unit): `normalizar_msisdn` (tira sufixos); `variantes_nono_digito`
   (`558193112159` ↔ `5581993112159`, idempotente, ignora não-celular).
2. **Repo** (integration): `find_by_phone_em` acha por qualquer variante.
3. **Adapter** (unit, MockTransport): `resolve_canonical` casa o `externalId` -> canonical.
4. **Service** (unit, fakes): acha direto pela variante; acha via LID->Omni; 404 quando nada.
5. **Regressão**: telefone exato (sem LID) continua funcionando; suite verde.

## 6. Critérios de aceite

- `find_customer_by_phone` resolve LID e telefone com/sem 9 para o titular correto.
- 2ª via e abrir chamado voltam a funcionar pelo agente (mesma resolução).
- unit+integration+lint/typecheck verdes.
