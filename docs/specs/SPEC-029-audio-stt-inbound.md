# SPEC-029 - Inbound de áudio do cliente via STT do Omni (transcrever e atender)

- Status: Draft (2026-05-31) — **dependente de capacidade ao vivo** (`POST /api/v2/media/stt` do Omni)
- Versão alvo: 1.8.0 (o turno do agente passa a aceitar **áudio** do WhatsApp, não só texto)
- Item do roadmap: **M-01** (`docs/11-roadmap-melhorias-agente.md §3.2 M-01, §4.2, §6 ondas`).
- ADRs: **ADR-0007** (runtime do agente via Genie/Claude Code — o inbound `omni.message` é
  consumido pelo bridge do Genie, fora do nosso código Python; o handling de áudio vive na
  borda do canal, **não** no MCP), **ADR-0003** (mídia entra/sai por ação de canal, nunca pelo
  texto do reply — a transcrição é texto, mas o **arquivo de áudio** é mídia), **ADR-0006/0010**
  (sandbox + egress allowlist — a chamada de STT do Omni é egress controlado), **ADR-0018**
  (presença/typing — o `composing` cobre a latência somada do STT). Relaciona-se com **SPEC-018**
  (`ChatTranscriptPort.mensagens` já normaliza `hasMedia` → `"📎 (mídia)"`, ponto onde a
  transcrição substitui o placeholder) e com **M-08** (cenário de eval de áudio).
- **Onda C, prioridade P1, esforço M.** **Não toca o contrato MCP.**

## 1. Problema

Cliente real manda **áudio** no WhatsApp (caso comum de CX no 1º contato). Hoje o fluxo é
**texto-only**: o payload inbound do Genie (`OmniMessage = { content, sender, instanceId, chatId,
agent }`, ver `sandbox/RUNBOOK.md`) carrega o texto em `content`; quando a mensagem é um áudio,
`content` vem **vazio** e a mídia chega em `files: ProviderFile[]` (inbound `omni.message.*`,
`docs/09`). Sem handling, um áudio:
- **quebra ou é ignorado** no turno (o agente recebe `content` vazio e responde no escuro);
- na transcrição lida por `get_chat_history` (SPEC-018), vira o placeholder genérico
  `"📎 (mídia)"` (`omni_chats.py:156`) — sem o que foi **dito**.

Isso derruba dois sinais do desafio: **"integração robusta"** (o Omni **já** tem STT embutido,
`POST /api/v2/media/stt`; não usá-lo é desperdício de uma capacidade pronta) e **UX de canal
real**. Diferencia de um bot de texto genérico.

## 2. Objetivo

Quando o inbound traz um **arquivo de áudio** (e `content` vazio/insuficiente), **transcrever via
STT do Omni** e injetar a transcrição como a mensagem do turno, **prefixada** com
`"[áudio transcrito] "` (transparência: o agente e os evals sabem que a origem foi voz, e a regra
de **eco antes de escrever** se aplica). Sem LLM novo no caminho (o STT é do Omni). O contrato MCP
permanece **imutável**.

## 3. Fronteira: onde o handling vive

```
WhatsApp ──áudio──▶ Omni (Baileys) ──omni.message{files:[audio]}──▶ bridge Genie (TS, /srv/genie)
                                                              │
                                       (M-01) detecta áudio ──┤──▶ POST /api/v2/media/stt ──▶ texto
                                                              ▼
                                         turno do agente = "[áudio transcrito] <texto>"
                                                              ▼
                                              Claude Code (spawn) ──▶ tools MCP (inalteradas)
```

- O **ponto de injeção real** é o **bridge do Genie** (TypeScript, em `/srv/genie`, **não** versionado
  neste repo — é `libs/genie`, só-leitura por `docs/07`). Lá a `OmniMessage` é montada antes do spawn.
  **Esta é a parte que só valida ao vivo** (ADR-0007): exige o endpoint STT do Omni e o bridge
  rodando no sandbox.
- O que **fica testável neste repo** (Python) é a **lógica pura de decisão e montagem do turno**,
  modelada como porta + função pura, para (a) ser exercida por unit test com fixtures de payload e
  (b) servir de **contrato de referência** que o bridge implementa (paridade conceitual com o que o
  Python já faz em `ChatTranscriptPort`).

## 4. Design

### 4.1 Porta `SttPort` (Hexagonal/DDD, `src/application/ports.py`)

```python
@runtime_checkable
class SttPort(Protocol):
    """Transcrição de áudio inbound. Best-effort: erro -> None (cai no fluxo de texto)."""
    def transcrever(self, *, audio_url: str, mime: str, idioma: str = "pt-BR") -> str | None: ...
```

Adapter best-effort em `src/infrastructure/events/omni_stt.py` (`HttpxOmniStt(SttPort)`):
`POST {base}/api/v2/media/stt` com `{ url|mediaKey, instanceId, language }`; `try/except ->
None`, timeout curto (mesmo padrão de `omni_sender`/`omni_chats`). **NUNCA** levanta para o turno —
falha de STT = sem transcrição, não erro de canal.

### 4.2 Detecção e montagem do turno (função pura, `src/domain/conversation/inbound_audio.py`)

Funções **puras, sem I/O, 100% unit-testáveis** com fixtures do payload `omni.message`:

```python
PREFIXO_AUDIO = "[áudio transcrito] "
_MIMES_AUDIO = ("audio/ogg", "audio/mpeg", "audio/mp4", "audio/amr", "audio/wav", "audio/webm")

def primeiro_audio(files: list[dict]) -> dict | None:
    """1º file cujo mime começa com 'audio/' (ou está na allowlist). None se não houver."""

def precisa_transcrever(content: str, files: list[dict]) -> bool:
    """True quando content é vazio/whitespace E há um file de áudio (texto vence áudio)."""

def montar_turno(content: str, transcricao: str | None) -> str:
    """content não-vazio -> content (texto vence). transcrição -> PREFIXO_AUDIO + transcrição.
    Sem nenhum dos dois -> '' (turno vazio; o bridge ignora ou pede repetição)."""
```

Regras determinísticas:
- **Texto vence áudio**: se `content` tem texto, ignora `files` (cliente que digita + anexa).
- **Idempotência**: `montar_turno` é pura; mesma entrada → mesma saída.
- **Prefixo único** `"[áudio transcrito] "`: o agente reconhece a origem e, antes de **qualquer
  ação de escrita** (`create_ticket`), **ecoa a transcrição entendida** (mitiga erro de STT,
  §M-01 riscos). Regra adicionada ao `AGENTS.md` (§4.4).

### 4.3 Substituição do placeholder na transcrição (SPEC-018, opcional/sinérgico)

Em `omni_chats.py:156`, hoje `hasMedia and not texto -> "📎 (mídia)"`. Quando o item de mídia for
**áudio** e o Omni já tiver a transcrição persistida no histórico, preferir a transcrição ao
placeholder (mantendo `"📎 (mídia)"` para mídia não-áudio). **Best-effort, fora do caminho crítico**
do turno — só melhora o recall de `get_chat_history`. Sem mudança de assinatura de
`ChatTranscriptPort`.

### 4.4 Regra no `AGENTS.md` (runtime — coordenar com cluster runtime)

Acréscimo curto na seção de estilo/recuperação: *"Se a mensagem vier prefixada por
`[áudio transcrito]`, a transcrição pode conter erros; antes de **abrir um chamado** ou outra ação
de escrita, **confirme em uma frase** o que você entendeu."* Reforça a regra 3 (confirmação antes de
escrever) já existente.

## 5. O que é testável neste repo vs. validação ao vivo

| Parte | Onde | Tipo | Validação |
| --- | --- | --- | --- |
| `primeiro_audio`/`precisa_transcrever`/`montar_turno` | `src/domain/conversation/inbound_audio.py` | **CÓDIGO+TESTE** (unit, sem mock) | `tests/unit/test_inbound_audio.py` com fixtures de `omni.message` (áudio, texto+áudio, vazio, mime não-áudio) |
| `SttPort` + `HttpxOmniStt` (best-effort) | `src/infrastructure/events/omni_stt.py` | **CÓDIGO+TESTE** (unit, httpx `MockTransport`) | assert URL/payload; erro/timeout → `None` |
| Substituição do placeholder na transcrição | `omni_chats.py` | **CÓDIGO+TESTE** (unit) | item áudio com transcrição → texto; não-áudio → `"📎 (mídia)"` |
| **Detecção de `files` de áudio no inbound real + chamada STT + injeção no turno** | **bridge Genie** (`/srv/genie`, TS) | **NOTA / VALIDAÇÃO AO VIVO** | exige `POST /api/v2/media/stt` do Omni + bridge no sandbox; **não** versionado aqui |
| Cenário de eval de áudio (M-08) | `src/evals/journeys.py` | depende de fixture/stub do turno transcrito | eval injeta turno já prefixado `[áudio transcrito]` (não chama STT real) |

## 6. Escopo

### Entregue nesta SPEC (testável neste repo)
- `src/application/ports.py`: `SttPort` (Protocol `@runtime_checkable`).
- `src/domain/conversation/inbound_audio.py` **(NOVO)**: `primeiro_audio`, `precisa_transcrever`,
  `montar_turno`, constantes `PREFIXO_AUDIO`/`_MIMES_AUDIO` — puro, sem I/O.
- `src/infrastructure/events/omni_stt.py` **(NOVO)**: `HttpxOmniStt(SttPort)` best-effort.
- `src/infrastructure/events/omni_chats.py`: preferir transcrição ao placeholder para item áudio
  (best-effort, sem mudar assinatura).
- `agent/AGENTS.md`: regra de **eco antes de escrever** para turno prefixado `[áudio transcrito]`.
- `tests/unit/test_inbound_audio.py` **(NOVO)** + caso de STT mockado.
- `src/evals/journeys.py`: cenário de áudio (turno pré-transcrito) — M-08.

### Validação ao vivo (NOTA — não entregue como código testável)
- Detecção de `files` de áudio e chamada de `POST /api/v2/media/stt` **no bridge do Genie**
  (TypeScript, `/srv/genie`). Documentar no `sandbox/RUNBOOK.md` como passo manual de demo.
- Egress da rota STT do Omni na allowlist do sandbox (ADR-0010), se o STT for serviço externo.

## 7. Fora de escopo

- **Voz/áudio bidirecional (TTS de resposta)**: explicitamente backlog (`docs/11 §6`, "voz
  bidirecional"). Esta SPEC é **só inbound** (áudio→texto).
- **STT próprio** (Whisper local, credencial paga): rejeitado — o Omni já tem STT; adicionar um
  provedor pago no caminho crítico contraria o threat model e o ADR-0004.
- **Mudar o contrato MCP**: proibido — nenhuma tool nova, nenhuma assinatura alterada. O áudio é
  resolvido **antes** do spawn, na borda do canal.
- **Reescrever o bridge do Genie**: `libs/genie` é só-leitura (`docs/07`); o handling ao vivo é
  config/wiring no sandbox, não código deste repo.

## 8. Plano TDD (da parte testável)

1. **`montar_turno` (unit, sem mock):** texto não-vazio → texto; transcrição → `PREFIXO_AUDIO +
   transcrição`; ambos vazios → `""`. Determinístico/idempotente.
2. **`precisa_transcrever` (unit):** `content` vazio + file de áudio → `True`; `content` com texto
   → `False` (texto vence); file não-áudio → `False`.
3. **`primeiro_audio` (unit):** seleciona o 1º mime `audio/*`; ignora `image/*`/`application/pdf`;
   lista vazia → `None`.
4. **`HttpxOmniStt` (unit, httpx `MockTransport`):** assert URL `/api/v2/media/stt` + payload;
   resposta 200 → texto; 5xx/timeout/exceção → `None` (best-effort, não levanta).
5. **Transcrição no histórico (unit):** item áudio com transcrição persistida → texto na
   `MensagemChat`; item mídia não-áudio → `"📎 (mídia)"` (regressão do placeholder).
6. **Eval (M-08):** cenário com turno pré-transcrito `[áudio transcrito] minha luz caiu` exercita o
   fluxo de outage **sem** chamar STT real (o STT ao vivo é validação manual).

## 9. Critérios de aceite

- Funções de detecção/montagem são **puras e idempotentes**, cobertas por unit test com fixtures de
  payload `omni.message` (áudio, texto+áudio, vazio, mime não-áudio).
- `HttpxOmniStt` é **best-effort**: qualquer falha do STT → `None`, **nunca** propaga erro ao turno.
- A transcrição entra no turno **prefixada** por `[áudio transcrito] ` e o `AGENTS.md` instrui o
  **eco antes de escrita**.
- O contrato MCP fica **imutável** (nenhuma tool/assinatura alterada); o teste de contrato das tools
  passa **sem edição**.
- A integração ao vivo (bridge + STT do Omni) está documentada como passo de demo no RUNBOOK e
  marcada como **validação ao vivo** — não como código deste repo.
- unit + lint/typecheck (ruff + mypy strict) verdes.

## 10. Notas

- **Dependência de capacidade ao vivo (motivo do Status: Draft):** a SPEC entrega a lógica pura e o
  adapter best-effort, mas o **fechamento de M-01** (áudio real virando turno) depende de o
  `POST /api/v2/media/stt` do Omni existir e do bridge do Genie chamá-lo. Por isso o grosso de M-01
  é **SPEC + handling testável onde possível**, e o disparo ponta-a-ponta é **NOTA**.
- **Sinergia com ADR-0018 (R-04):** STT soma latência ao turno; o `composing`/typing cobre a espera
  percebida — os dois itens da Onda C se reforçam na UX de canal real.
- **Eco antes de escrever** mitiga o risco de transcrição errada disparar ação indevida
  (`create_ticket`) — alinhado ao guardrail determinístico de confirmação (regra 3 do `AGENTS.md`).
