"""Registry de personas (SPEC-006): fonte única lida do ambiente.

Parseia `SEED_PERSONAS` ("Nome:telefone;...") e deriva o perfil de cada uma.
Consumido tanto pelo seeder quanto pelo harness de evals (DRY).
"""

from __future__ import annotations

from src.domain.persona import PerfilPersona, Persona, perfil_de
from src.domain.shared.errors import InvariantError
from src.domain.shared.value_objects import Telefone


def parse_personas(raw: str) -> list[Persona]:
    """Parseia `SEED_PERSONAS`. Falha cedo em entrada inválida/duplicada."""
    personas: list[Persona] = []
    vistos: set[str] = set()
    for bruto in (raw or "").split(";"):
        entrada = bruto.strip()
        if not entrada:
            continue
        if ":" not in entrada:
            raise ValueError(
                f"entrada de persona invalida (use 'Nome:telefone'): {entrada!r}"
            )
        nome_raw, _, tel_raw = entrada.rpartition(":")
        nome = nome_raw.strip()
        if not nome:
            raise ValueError(f"persona sem nome: {entrada!r}")
        try:
            telefone = Telefone(tel_raw.strip()).value
        except InvariantError as exc:
            raise ValueError(f"telefone invalido em {entrada!r}: {exc}") from exc
        if telefone in vistos:
            raise ValueError(f"telefone duplicado em SEED_PERSONAS: {telefone}")
        vistos.add(telefone)
        personas.append(Persona(nome=nome, telefone=telefone))
    if not personas:
        raise ValueError("SEED_PERSONAS vazio: defina ao menos 1 'Nome:telefone'")
    return personas


def carregar_personas(
    raw: str, seed: int
) -> list[tuple[Persona, PerfilPersona]]:
    """Personas + perfis derivados. Persona única -> perfil rico (demo)."""
    personas = parse_personas(raw)
    rico = len(personas) == 1
    return [(p, perfil_de(p.telefone, seed, rico=rico)) for p in personas]
