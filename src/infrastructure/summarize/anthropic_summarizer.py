"""Adapter de resumo de thread via Anthropic Claude Haiku (R-15 / SPEC-028).

Implementa `SummarizerPort`. É **OPT-IN**: o default do `ThreadSummaryService` é o
fallback extrativo determinístico (`resumo_extrativo`), que não toca a rede. Este
adapter só entra quando explicitamente injetado (e a dep `anthropic` instalada +
`ANTHROPIC_API_KEY`/auth do Claude Code disponível no ambiente).

Haiku porque o resumo é uma tarefa curta e barata; o prompt é fixo (prefixo
estável cacheável, ADR-0014). Contrato da porta: devolve resumo não-vazio OU
levanta `SummarizerError` — QUALQUER exceção/empty da API vira `SummarizerError`,
para o serviço cair no fallback. NUNCA bloqueia o fechamento de ticket/handoff.
"""

from __future__ import annotations

from src.application.ports import SummarizerError
from src.domain.conversation.entities import MensagemChat

# Default conservador: família Haiku (barata/rápida). Sobrescrevível por arg.
_DEFAULT_MODEL = "claude-3-5-haiku-latest"
_SYSTEM_PROMPT = (
    "Você resume conversas de atendimento ao cliente de uma distribuidora de "
    "energia (Luz do Vale) em português do Brasil. Produza um resumo objetivo em "
    "1 a 3 frases: motivo do contato, o que foi resolvido e qualquer pendência. "
    "Não invente fatos; use apenas o que está na conversa. Não inclua saudações."
)


class AnthropicHaikuSummarizer:
    """Adapter LLM (Claude Haiku) para resumo de thread. Opt-in, best-effort."""

    def __init__(
        self,
        api_key: str = "",
        model: str = _DEFAULT_MODEL,
        timeout: float = 8.0,
        max_tokens: int = 256,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._max_tokens = max_tokens

    @staticmethod
    def _transcricao(mensagens: list[MensagemChat]) -> str:
        """Serializa a thread em `[autor] texto` por linha (ordem cronológica)."""
        linhas: list[str] = []
        for m in mensagens:
            texto = " ".join(m.texto.split())
            if not texto:
                continue
            autor = "Cliente" if m.do_cliente else "Atendente"
            linhas.append(f"{autor}: {texto}")
        return "\n".join(linhas)

    def summarize(self, mensagens: list[MensagemChat], *, max_chars: int = 600) -> str:
        transcricao = self._transcricao(mensagens)
        if not transcricao:
            raise SummarizerError("transcrição vazia")
        try:
            import anthropic

            client = anthropic.Anthropic(
                api_key=self._api_key or None, timeout=self._timeout
            )
            resp = client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=[
                    {
                        "type": "text",
                        "text": _SYSTEM_PROMPT,
                        # Prefixo estável cacheável (ADR-0014 / R-07).
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[
                    {
                        "role": "user",
                        "content": f"Resuma a conversa abaixo:\n\n{transcricao}",
                    }
                ],
            )
        except SummarizerError:
            raise
        except Exception as exc:  # noqa: BLE001 - qualquer falha -> fallback
            raise SummarizerError(f"falha no adapter Anthropic: {exc}") from exc

        texto = self._extrair_texto(resp)
        if not texto:
            raise SummarizerError("resposta vazia do modelo")
        if len(texto) > max_chars:
            texto = texto[: max_chars - 1].rstrip() + "…"
        return texto

    @staticmethod
    def _extrair_texto(resp: object) -> str:
        """Concatena os blocos de texto da resposta da Messages API (defensivo)."""
        blocos = getattr(resp, "content", None) or []
        partes: list[str] = []
        for bloco in blocos:
            texto = getattr(bloco, "text", None)
            if isinstance(texto, str) and texto.strip():
                partes.append(texto.strip())
        return " ".join(partes).strip()
