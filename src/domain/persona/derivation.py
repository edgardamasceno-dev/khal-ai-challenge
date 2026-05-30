"""Derivação determinística de `PerfilPersona` a partir do telefone (+ seed).

Função pura: mesma entrada -> mesma saída, reproduzível entre execuções e
plataformas. Usa `hashlib` (estável) para semear um `random.Random` (Mersenne
Twister, determinístico). **Nunca** usa `hash()` (semeado por processo).
"""

from __future__ import annotations

import hashlib
import random

from src.domain.persona.models import PerfilPersona
from src.domain.shared.value_objects import _cpf_dv

# Bairros/cidades fictícios. O 1º (Jardim das Flores) é o cenário canônico de
# outage usado nas journeys; mantê-lo no índice 0 preserva compatibilidade.
_LOCAIS = (
    ("Jardim das Flores", "Vale do Sol", "SP"),
    ("Centro", "Vale do Sol", "SP"),
    ("Bela Vista", "Vale do Sol", "SP"),
    ("Vila Nova", "Rio Claro do Vale", "SP"),
    ("Parque das Águas", "Rio Claro do Vale", "SP"),
    ("Alto da Serra", "Monte Verde", "MG"),
)
_LOCAL_RURAL = ("Zona Rural", "Vale do Sol", "SP")
_LOCAL_COMERCIAL = ("Distrito Industrial", "Vale do Sol", "SP")

# classe -> (subgrupo, faixa de consumo base por UC)
_CLASSE_PARAMS = {
    "residencial": ("B1", (120, 320)),
    "comercial": ("B3", (380, 900)),
    "rural": ("B2", (150, 360)),
}


def _rng(telefone: str, seed: int) -> random.Random:
    """RNG determinístico semeado pelo SHA-256 de `seed:telefone`."""
    digest = hashlib.sha256(f"{seed}:{telefone}".encode()).hexdigest()
    return random.Random(int(digest, 16))


def _cpf(rng: random.Random) -> str:
    """CPF fictício de 11 dígitos com DV válido (mod 11), estável pelo RNG."""
    base = [rng.randint(0, 9) for _ in range(9)]
    if len(set(base)) == 1:  # cpf_valido rejeita todos-iguais; força variedade
        base[0] = (base[0] + 1) % 10
    d1 = _cpf_dv(base)
    d2 = _cpf_dv([*base, d1])
    return "".join(str(d) for d in [*base, d1, d2])


def perfil_de(telefone: str, seed: int, *, rico: bool = False) -> PerfilPersona:
    """Deriva o perfil determinístico de uma persona.

    `rico=True` (usado quando há uma única persona) garante um perfil que
    exercita várias tools: fatura vencida + outage ativa no bairro.
    """
    rng = _rng(telefone, seed)
    cpf = _cpf(rng)

    classe = rng.choices(
        ("residencial", "comercial", "rural"), weights=(6, 3, 1), k=1
    )[0]
    subgrupo, (kwh_lo, kwh_hi) = _CLASSE_PARAMS[classe]

    if classe == "rural":
        bairro, cidade, uf = _LOCAL_RURAL
    elif classe == "comercial":
        bairro, cidade, uf = _LOCAL_COMERCIAL
    else:
        bairro, cidade, uf = _LOCAIS[rng.randrange(len(_LOCAIS))]

    n_ucs = 2 if (classe == "comercial" and rng.random() < 0.6) else 1
    base_kwh = tuple(rng.randint(kwh_lo, kwh_hi) for _ in range(n_ucs))

    cenario_fatura = rng.choices(
        ("em_dia", "uma_aberta", "uma_vencida"), weights=(3, 4, 3), k=1
    )[0]
    outage_ativa = rng.random() < 0.35
    corte_religacao = classe == "rural" and rng.random() < 0.5

    if rico:
        # Persona única: garante cenário demonstrável e bairro com outage.
        cenario_fatura = "uma_vencida"
        outage_ativa = True
        bairro, cidade, uf = _LOCAIS[0]

    return PerfilPersona(
        cpf=cpf,
        bairro=bairro,
        cidade=cidade,
        uf=uf,
        classe=classe,
        subgrupo=subgrupo,
        n_ucs=n_ucs,
        base_kwh=base_kwh,
        cenario_fatura=cenario_fatura,
        outage_ativa=outage_ativa,
        corte_religacao=corte_religacao,
    )
