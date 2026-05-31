# SPEC-014 - Menu de status na navbar (API / WhatsApp / Agente)

- Status: Approved (2026-05-30)
- Versao alvo: 1.3.0 (health agrega componentes; navbar vira popover de status)
- ADRs: ADR-0002 (console fino do operador). Sem ADR novo.

## 1. Problema

A navbar tem um `HealthBadge` que só mostra "API online/offline" (checa o DB). Não
há visibilidade do **WhatsApp** (instância Omni) nem do **Agente** (Genie). O operador
quer um status consolidado e um ponto de entrada para configurações.

## 2. Objetivo

A badge vira um **popover** (shadcn) com label "Status" e um indicador que **pulsa**
(verde quando tudo ok, vermelho quando algo caiu). Ao abrir, lista **API, WhatsApp,
Agente** (status real de cada), um separador e **Configurações**, que abre um modal em
branco (placeholder).

## 3. Escopo

### Back
- `/health` passa a agregar componentes: `{status, components: [{name, status}]}` com
  `api` (db), `whatsapp` (Omni `GET /instances/{id}/status` -> `isConnected`) e `agente`
  (Omni `GET /agents` -> agente da instância `isActive`). Status por componente:
  `ok` | `down` | `unknown` (Omni inacessível/best-effort, timeout curto).
- Porta `ChannelHealthPort` + adapter `HttpxOmniHealth` (hexagonal). `status` geral =
  `ok` se todos ok; `degraded` se algum down/unknown.
- **Wiring**: o backend precisa alcançar o Omni do sandbox (rede `khal-wanet` + `OMNI_URL`/
  `OMNI_API_KEY`/`OMNI_INSTANCE_ID`), como o worker. Sem wiring, whatsapp/agente = `unknown`.

### Front (console)
- `popover` (shadcn, via MCP) já adicionado. `HealthBadge` -> `StatusMenu`:
  - Trigger: chip "Status" + indicador com **brilho animado** (halo `animate-ping` +
    dot sólido), cor pelo status geral (verde/vermelho/âmbar enquanto verifica).
  - Conteúdo: linhas API / WhatsApp / Agente (cada uma com dot colorido + estado),
    `Separator`, botão **Configurações** -> abre `Dialog` em branco.
- Poll a cada 15s (mantém o comportamento atual).

## 4. Fora de escopo

- Conteúdo real da tela de Configurações (fica em branco por enquanto).
- Health do processo Genie por dentro do sandbox (usamos o que o Omni expõe do agente).

## 5. Plano TDD

1. **Adapter/Service** (unit, fakes): agrega api+whatsapp+agente; mapeia
   `isConnected`/`isActive` -> ok/down; Omni inacessível -> unknown; status geral.
2. **REST** (api): `/health` devolve `components` com os 3 nomes.
3. **Front**: popover abre, lista os 3 + Configurações (modal); build do console.
4. **Regressão**: suite verde; lint/typecheck.

## 6. Critérios de aceite

- `/health` devolve os 3 componentes com status real (ou `unknown` sem wiring).
- Navbar mostra popover "Status" com indicador pulsante e as 3 linhas + Configurações.
- unit+api+lint/typecheck verdes; console builda.
