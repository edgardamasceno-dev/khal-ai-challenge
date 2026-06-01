"""Value objects compartilhados do dominio.

Imutaveis (frozen), validam invariantes na construcao. Primeira linha de
guardrail: entrada tipada e validada (RNF-05).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from src.domain.shared.errors import InvariantError

_SLA_POR_TIPO = {
    "falta_energia": 48,
    "religacao": 24,
    "segunda_via": 48,
    "titularidade": 72,
    "reclamacao": 72,
}


def _cpf_dv(nums: list[int]) -> int:
    """Digito verificador de CPF (modulo 11)."""
    soma = sum(v * w for v, w in zip(nums, range(len(nums) + 1, 1, -1), strict=True))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def cpf_valido(digitos: str) -> bool:
    if len(digitos) != 11 or not digitos.isdigit() or len(set(digitos)) == 1:
        return False
    n = [int(c) for c in digitos]
    return _cpf_dv(n[:9]) == n[9] and _cpf_dv(n[:10]) == n[10]


@dataclass(frozen=True)
class CPF:
    value: str

    def __post_init__(self) -> None:
        digitos = re.sub(r"\D", "", self.value)
        if not cpf_valido(digitos):
            raise InvariantError(f"CPF invalido: {self.value!r}")
        object.__setattr__(self, "value", digitos)

    def mascarado(self) -> str:
        d = self.value
        return f"{d[:3]}.***.***-{d[9:]}"


@dataclass(frozen=True)
class Telefone:
    """E.164 sem '+', 10 a 15 digitos."""

    value: str

    def __post_init__(self) -> None:
        digitos = re.sub(r"\D", "", self.value)
        if not 10 <= len(digitos) <= 15:
            raise InvariantError(f"Telefone invalido: {self.value!r}")
        object.__setattr__(self, "value", digitos)

    def mascarado(self) -> str:
        d = self.value
        return f"{d[:4]}****{d[-2:]}"


@dataclass(frozen=True)
class Dinheiro:
    """Valor em centavos (BRL), nao-negativo."""

    centavos: int

    def __post_init__(self) -> None:
        if isinstance(self.centavos, bool) or not isinstance(self.centavos, int):
            raise InvariantError("Dinheiro.centavos deve ser int")
        if self.centavos < 0:
            raise InvariantError("Dinheiro nao pode ser negativo")

    @property
    def reais(self) -> float:
        return self.centavos / 100

    def formatado(self) -> str:
        return f"R$ {self.reais:.2f}"


@dataclass(frozen=True)
class MesReferencia:
    """Mes de referencia no formato YYYY-MM."""

    value: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", self.value):
            raise InvariantError(f"MesReferencia invalido (use YYYY-MM): {self.value!r}")


class TipoChamado(StrEnum):
    falta_energia = "falta_energia"
    religacao = "religacao"
    segunda_via = "segunda_via"
    titularidade = "titularidade"
    reclamacao = "reclamacao"

    @property
    def sla_horas(self) -> int:
        return _SLA_POR_TIPO[self.value]


class StatusChamado(StrEnum):
    """Estados do chamado. O operador encerra `aberto` -> `resolvido` (SPEC-020)."""

    aberto = "aberto"
    resolvido = "resolvido"


@dataclass(frozen=True)
class Protocolo:
    """Protocolo de chamado: 'LDV' + AAAAMMDD + sufixo. Max. 16 chars."""

    value: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"LDV\d{8}[A-Z0-9]{1,5}", self.value):
            raise InvariantError(f"Protocolo invalido: {self.value!r}")

    @classmethod
    def gerar(cls, data_aaaammdd: str, sufixo: str) -> Protocolo:
        return cls(f"LDV{data_aaaammdd}{sufixo.upper()[:4]}")
