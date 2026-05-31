"""Eventos de domínio do CX (SPEC-009 / ADR-0005). Determinísticos, sem LLM."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.domain.shared.errors import InvariantError

# (tipo, subtipo) suportados.
EVENTOS_VALIDOS: set[tuple[str, str]] = {
    ("pagamento", "confirmado"),
    ("pagamento", "vencida"),
    ("outage", "aberta"),
    ("outage", "encerrada"),
}


@dataclass(frozen=True)
class EventoCX:
    """Evento canônico disparado pelo operador (baixa de pagamento, interrupção)."""

    tipo: str  # "pagamento" | "outage"
    subtipo: str  # "confirmado" | "aberta" | "encerrada"
    telefone: str  # E.164 sem '+'
    nome: str
    idempotency_key: str
    dados: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if (self.tipo, self.subtipo) not in EVENTOS_VALIDOS:
            raise InvariantError(f"evento invalido: {self.tipo}.{self.subtipo}")

    @property
    def chat_id(self) -> str:
        return self.telefone

    @property
    def subject(self) -> str:
        """Subject NATS: utilitycx.<tipo>.<subtipo>."""
        return f"utilitycx.{self.tipo}.{self.subtipo}"

    @property
    def memoria_chave(self) -> str:
        return f"proativo.{self.tipo}.{self.subtipo}"
