"""Value objects de persona (imutaveis)."""

from __future__ import annotations

from dataclasses import dataclass

# Cenarios de fatura possiveis para o mes-ancora de uma persona.
CENARIOS_FATURA = ("em_dia", "uma_aberta", "uma_vencida")


@dataclass(frozen=True)
class Persona:
    """Identidade declarada no ambiente: nome + telefone (E.164 sem '+')."""

    nome: str
    telefone: str


@dataclass(frozen=True)
class PerfilPersona:
    """Perfil determinístico derivado do telefone (+ seed).

    Define os dados que o seeder materializa (titular, UC(s), faturas,
    interrupcao, chamado) e que os evals usam para gerar asserções.
    """

    cpf: str
    bairro: str
    cidade: str
    uf: str
    classe: str  # residencial | comercial | rural
    subgrupo: str  # B1 | B2 | B3
    n_ucs: int  # 1..2
    base_kwh: tuple[int, ...]  # consumo base por UC (len == n_ucs)
    cenario_fatura: str  # CENARIOS_FATURA
    outage_ativa: bool  # interrupcao nao programada ativa no bairro
    corte_religacao: bool  # historico de corte + religacao

    def __post_init__(self) -> None:
        if self.cenario_fatura not in CENARIOS_FATURA:
            raise ValueError(f"cenario_fatura invalido: {self.cenario_fatura!r}")
        if len(self.base_kwh) != self.n_ucs:
            raise ValueError("base_kwh deve ter um valor por UC (len == n_ucs)")
