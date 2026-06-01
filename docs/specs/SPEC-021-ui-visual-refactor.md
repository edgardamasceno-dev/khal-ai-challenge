# SPEC-021 - Refatoração visual do console do operador

- Status: Approved (2026-05-31)
- Versao alvo: 1.6.0 (refatoração APENAS VISUAL do console; zero mudança de comportamento)
- ADRs: ADR-0002 (console fino do operador, cliente gerado do OpenAPI). Sem ADR novo.
- Branch: `feature/ui-visual-refactor` -> PR para `develop`.

## 1. Problema

O console (`ui/`) funciona, mas tem baixa percepção de qualidade e nenhum
ponto de vista visual. A paleta é 100% acromática (`oklch(... 0 0)` em todo o
`index.css`); a Geist está carregada mas nunca explorada como sistema (mono vs.
sans aplicado a esmo); o layout é o template shadcn cru (header `text-sm`, cards
genéricos, densidade desigual). As cores semânticas de domínio vivem em literais
`emerald/amber/red/blue/purple` espalhados em `lib/format.tsx` e dentro de
`CustomerWorkspace.tsx`, fora dos tokens. Operacionalmente, os sinais de urgência
de uma distribuidora — **fatura vencida, interrupção ativa, fila de handoff** —
não saltam no nível de leitura imediata; estão enterrados em abas. O alvo do
avaliador é um console **confiável, polido e distinto**, não o template shadcn cru.

## 2. Objetivo

Elevar o acabamento visual a um **"Painel de Despacho / Utility-grade"**
(minimalismo refinado-industrial, leitura em 3 segundos), introduzindo um
`--primary` de marca elétrico, tokens semânticos de status centralizados, sistema
tipográfico Geist Sans/Mono e hierarquia de severidade — **sem alterar nenhuma
funcionalidade**. Props, handlers, `useEffect`/polling, refs/timers, chamadas a
`lib/api.ts`, `value` de Tabs/Select, payloads/idempotência, toasts e a copy de
domínio em pt-BR ficam **congelados**. shadcn/radix-only; build + lint VERDES por
workstream.

## 3. Direção visual e decisões

### 3.1 Conceito
Painel de Despacho / Utility-grade: minimalismo refinado-industrial, ponto de
vista claro, densidade operacional, leitura em 3 segundos. A "boldness" exigida
pela SKILL oficial é canalizada em **um primário de marca** e em **hierarquia de
severidade**, não em ornamento. **Vetado** (incompatível com console operacional):
gradient mesh, noise, grain, custom cursor, layout diagonal/assimétrico, fonte
exótica, dark forçado como default.

### 3.2 Cor (tokens em `index.css`)
- Introduz-se um `--primary` de **marca** (azul-elétrico/teal de utility),
  substituindo o cinza acromático em `:root` e `.dark`. É mudança de CSS variable,
  risco funcional zero. `--primary-foreground` validado em contraste AA nos dois temas.
- Adicionam-se tokens semânticos `--status-ok / --status-warn / --status-danger /
  --status-info` (e respectivos `-foreground`/superfícies) no `@theme inline` /
  `:root` / `.dark`. **`lib/format.tsx` é refatorado para consumi-los**, eliminando
  os literais `emerald/amber/red/blue/purple`. Resultado visual idêntico ou superior;
  fonte única de verdade de cor de status.
- A **neutra base** (backgrounds/borders OKLCH) permanece; resfriamento leve e
  opcional do `--background`, sem quebrar contraste.
- O `--primary` de marca deve ser **visualmente distinto** dos três tons de status.
- **Hierarquia de severidade (regra de domínio, nunca decorativa):** vermelho =
  corte/vencida/outage ativa; âmbar = atenção/pendente; verde = normalizado;
  azul-marca ≠ status.

### 3.3 Tipografia
- **Geist permanece** (Sans + Mono já carregados). O caráter distintivo vem do
  **sistema**, não de uma fonte nova.
- **Geist Mono obrigatório** em todo identificador técnico (UC, protocolo, CPF,
  telefone E.164, linha digitável, kWh, mês de referência) com `tabular-nums`.
- Hierarquia de header reforçada (hoje `text-sm` é fraco): peso de marca "Luz do Vale".

### 3.4 Densidade e shell
- Apertar a escala vertical do `CustomerWorkspace` (hoje `py-8`/`space-y-6` respira
  demais); header mais baixo; sidebar do titular com peso de **dossiê** persistente.
- Responsivo `lg:grid-cols-[320px_1fr]` **mantido**.
- `Pulse` (`animate-ping`) do `StatusMenu` preservado como assinatura.

### 3.5 Promoção de urgência (visual, SEM novos dados nem novas chamadas)
- **Badges de alerta nas abas** ("Interrupções", "Unidade & Faturas") derivados de
  dados **já carregados** nas props (`contracts`, `tickets`, `selected.bairro`) —
  zero chamada nova, zero novo estado de servidor. A aba "Chamados" já tem badge;
  estende-se o padrão. Estrutura `<Tabs>`/`value` **intocada**.
- **Card do titular vira "dossiê"** com o componente `item` do registry para
  padronizar as linhas (CPF, telefone, e-mail, contadores de UC já existentes).
- **Realce de outage** fica **dentro do `OutageSection`** (intensificar o `Alert
  destructive` já existente, severidade visual máxima, sem novo fetch). A promoção
  a banner global do workspace fica **fora desta SPEC** (exigiria novo fetch/estado
  = mudança funcional; vira backlog).
- **Tabela de faturas:** reorganização visual de colunas (isolar a coluna de ação,
  contraste temporal de vencimento/SLA em vermelho via token). O `Select`, seus
  `value`, estados `disabled`/`busy` e handlers ficam idênticos.

### 3.6 Estados (empty/loading)
- `EmptyState` (App), "Nenhum chamado", "Sem mensagens", "Sem interrupções",
  "Sem candidatos" migram para o componente `empty` do registry; skeletons
  faltantes (`OutageSection`, `ProactiveSection`) padronizados com `Skeleton`.
- **Condição-guarda e copy pt-BR exata preservadas string a string**; só muda o
  invólucro visual.

## 4. Contrato funcional preservado (Definição de Pronto)

Nenhuma alteração em:
- Assinatura de função, props, dependências de hook, condições de render, `value`
  de Tabs (`faturas/interrupcoes/chamados/chat/proativos`) e de Select.
- `lib/api.ts`: querystrings, métodos, `idempotency_key`, payloads — idênticos.
- `App.tsx`: `search(value)` com `trim`/branch 404 vs `ApiError`, `refreshTickets`,
  `listPersonas`, `onKeyDown=Enter`, props passadas ao `CustomerWorkspace`.
- `CustomerWorkspace`: `selectedUcId` + `useEffect([contracts])`, `selected` derivado,
  props derivadas aos filhos (`defaultBairro`, `ucId`, `phone`).
- `InvoicesTable`: flag `active` anti-race, `changeStatus` com guarda
  `status===inv.status`, toasts vencida/em_aberto, `Select` item `paga` disabled.
- `OutageSection`: `useEffect([defaultBairro])`, guarda vazio, os dois ramos de `Alert`.
- `TicketsSection`: `CreateTicketDialog` (default `falta_energia`, copy "idempotente"),
  `HandoffDialog`, `HandoffQueue` com `setInterval(load, 15000)` + `resumeHandoff`,
  `onChanged`.
- `ChatSection` (o mais frágil — **1:1**): `scrollRef`, `useLayoutEffect`
  stick-to-bottom/`prependBefore`, `seen` Set, `merge`/reconciliação `tmp-`,
  `POLL_MS=5000`, `lastToggle` cooldown 1200ms, envio otimista com rollback.
  **Proibido** trocar o `<div ref={scrollRef}>` por `scroll-area` do registry.
- `ProactiveSection`: `load()` com guarda `!phone`, `emit()` recarregando candidatos
  (muta banco), subtipos `pagamento.confirmado`/`outage.aberta|encerrada`, `dados`.
- `StatusMenu`: `health` polling 15s, `overall` derivado, `Pulse` `animate-ping`,
  dialog Configurações.
- Timers de polling: chat 5s, health 15s, fila de handoff 15s — intocados.
- Copy de domínio pt-BR (status, bandeiras, tipos de chamado, toasts "idempotente"/
  "aviso disparado ao cliente"/"IA ativa", termos canônicos: Unidade Consumidora,
  Bandeira, Protocolo, Handoff, Religação, Previsão de retorno) — string a string.
- CPF/telefone **mascarados e em mono**.

## 5. Plano shadcn (componentes a adotar)

Via MCP shadcn, registry `@shadcn` (confirmados `registry:ui`, 1 arquivo cada):

```
npx shadcn@latest add @shadcn/empty @shadcn/tooltip @shadcn/item
```

- `empty` — empty states unificados (App, Chamados, Chat, Interrupções, Proativos).
- `tooltip` — UC/persona/e-mail truncado, ações de ícone.
- `item` — linhas do dossiê do titular e listas de fila de handoff/proativos.

Regra de WS: `components/ui/*` é compartilhado — em **WS1 só ADICIONAR** os
arquivos novos (`empty`/`tooltip`/`item`); nunca editar os existentes em WS2/WS3.
Componentes pontuais sem registry: nenhum necessário (`field`/`button-group` ficam
como opcionais, só se couberem sem editar `components/ui/*`). **Proibido** outras
libs de UI (MUI/Chakra/antd) e gráficos (recharts).

## 6. Fora de escopo

- Banner global de outage persistente no topo do workspace (exige novo fetch/estado
  → backlog).
- Troca do mecanismo de scroll do `ChatSection` por `scroll-area`.
- Reorganização da navegação de abas; novo render condicional; command palette.
- Troca de fonte (Geist permanece); dark forçado como default.
- Qualquer mudança em `lib/api.ts` ou no backend.

## 7. Plano de micro-iterações (workstreams disjuntos, ordem fixa)

**WS1 — Sistema visual + shell** (P0, fundação; habilita os demais)
Arquivos: `src/index.css`, `src/lib/format.tsx`, `src/App.tsx`, `src/sections/StatusMenu.tsx`.
1. Adicionar `empty`/`tooltip`/`item` via MCP (build/lint verde).
2. `index.css`: `--primary` de marca + tokens `--status-*` (`:root`, `.dark`, `@theme inline`); AA.
3. `format.tsx`: refatorar os mapas de tom para consumir os tokens de status.
4. `App.tsx`: header com peso de marca; `EmptyState` via `empty`; personas com `tooltip`; mono nos telefones.
5. `StatusMenu.tsx`: hierarquia/refino preservando `Pulse`.
6. Build + lint verdes.

**WS2 — Superfícies de cliente/cobrança** (P1)
Arquivos: `src/sections/CustomerWorkspace.tsx`, `src/sections/InvoicesTable.tsx`,
`src/sections/OutageSection.tsx`, `src/sections/ProactiveSection.tsx`.
1. `CustomerWorkspace`: densidade + dossiê via `item`; badges de alerta nas abas (derivados de props).
2. `InvoicesTable`: coluna de ação isolada; contraste temporal de vencimento via token; `tabular-nums`/mono.
3. `OutageSection`: `Alert destructive` intensificado + skeleton + `empty`.
4. `ProactiveSection`: listas via `item` + skeleton + `empty`.
5. Build + lint verdes.

**WS3 — Superfícies de operação** (P2)
Arquivos: `src/sections/TicketsSection.tsx`, `src/sections/ChatSection.tsx`.
1. `TicketsSection`: `HandoffQueue` e listas padronizadas com `item`/`empty`; mono em Protocolo.
2. `ChatSection`: restyling de bolhas/scrollbar/markup, distinção IA-no-controle vs humano-no-controle, micro-feedback CSS (sem novo timer); `empty` para "Sem mensagens".
3. Build + lint verdes.

Após **cada** WS: `cd ui && npm run build && npm run lint` VERDES + smoke manual
(buscar persona → cada aba → criar chamado → assumir/enviar no chat → disparar
proativo, confirmando rede e toasts idênticos).

## 8. Critérios de aceite

- `npm run build` (tsc -b && vite build) e `npm run lint` VERDES no HEAD do PR.
- Diff sem alteração em assinatura de função, props, dependências de hook,
  condições de render, `value` de Tabs/Select, strings de domínio ou `lib/api.ts`.
- `--primary` de marca e tokens `--status-*` aplicados; `format.tsx` consome os
  tokens; contraste AA nos temas claro e escuro.
- Geist Mono em todo identificador técnico com `tabular-nums`; CPF/telefone
  mascarados e em mono.
- Badges de alerta nas abas derivados de props já carregadas (zero chamada nova).
- `empty`/`tooltip`/`item` adotados; `Pulse` preservado.
- Smoke manual confirma rede e toasts idênticos aos do baseline.
</content>
</invoke>
