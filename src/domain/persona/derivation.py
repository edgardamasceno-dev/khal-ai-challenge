"""Derivação determinística de `PerfilPersona` a partir do telefone (+ seed).

Função pura: mesma entrada -> mesma saída, reproduzível entre execuções e
plataformas. Usa `hashlib` (estável) para semear um `random.Random` (Mersenne
Twister, determinístico). **Nunca** usa `hash()` (semeado por processo).

Precedência de perfil (do mais forte ao mais fraco):

1. **Canônico por nome** (`persona_key` ∈ `_CANONICOS`): as 3 personas default
   (Ana/Carlos/Joana) recebem o cenário canônico **fixo** que a demo e os evals
   esperam, **independente do telefone**. A fixação é cirúrgica (só esses três
   `persona_key`); qualquer outra persona não é tocada.
2. **Rico** (`rico=True`, persona única): cenário demonstrável (fatura vencida +
   outage no bairro).
3. **Derivado**: tudo sorteado pelo RNG semeado por `(seed, telefone)`.

Em todos os casos o CPF, o consumo e as UCs continuam **derivados do telefone**
(estáveis/idempotentes): o overlay canônico só fixa os campos de *cenário*
(classe, bairro, fatura, outage, corte e — para o comercial — `n_ucs>=2`),
preservando o determinismo por telefone exigido pelas personas dinâmicas.
"""

from __future__ import annotations

import hashlib
import random
import unicodedata
from dataclasses import dataclass

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

# classe -> pesos de n_ucs em (1, 2, 3, 4). Comercial tende a mais unidades
# (SPEC-013); 1 segue sendo o mais comum em residencial/rural.
_UC_WEIGHTS = {
    "residencial": (5, 3, 2, 1),
    "comercial": (1, 3, 3, 3),
    "rural": (6, 2, 1, 1),
}


@dataclass(frozen=True)
class _Canonico:
    """Overlay de cenário fixo de uma persona canônica (por `persona_key`).

    Só descreve os campos de *cenário* que a banca espera ver; os campos
    derivados do telefone (cpf, consumo, nº de UCs no caso geral) são
    preservados. `classe` redireciona o subgrupo/consumo coerentes e, quando
    `n_ucs_min` é definido, força um mínimo de UCs (multi-UC do comercial).
    `local` fixa bairro/cidade/uf quando o cenário exige um bairro específico
    (Ana → "Jardim das Flores", o bairro de outage das journeys); `None` usa o
    bairro coerente com a classe.
    """

    classe: str  # residencial | comercial | rural
    cenario_fatura: str
    outage_ativa: bool
    corte_religacao: bool
    n_ucs_min: int = 1
    local: tuple[str, str, str] | None = None


# Cenários canônicos das 3 personas default (`.env.example`), fixados por NOME
# (persona_key = slug do nome). **Fato**, não mais sorteio: a demo e os evals
# precisam destes cenários exatos (SPEC-006 / ADR-0011). A chave é o slug do nome
# — a mesma normalização do seeder (`_slug`) — para casar independente do telefone.
_CANONICOS: dict[str, _Canonico] = {
    # Ana Souza: residencial, Jardim das Flores, fatura vencida, outage ativa.
    "ana.souza": _Canonico(
        classe="residencial",
        cenario_fatura="uma_vencida",
        outage_ativa=True,
        corte_religacao=False,
        local=_LOCAIS[0],  # "Jardim das Flores" (bairro de outage das journeys)
    ),
    # Carlos Lima: comercial, multi-UC (>=2), em dia.
    "carlos.lima": _Canonico(
        classe="comercial",
        cenario_fatura="em_dia",
        outage_ativa=False,
        corte_religacao=False,
        n_ucs_min=2,
    ),
    # Joana Pereira: rural, com corte + religação no histórico.
    "joana.pereira": _Canonico(
        classe="rural",
        cenario_fatura="uma_vencida",
        outage_ativa=False,
        corte_religacao=True,
    ),
}


def _slug(nome: str) -> str:
    """Normaliza um nome para `persona_key` (mesma normalização do seeder)."""
    norm = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return ".".join(norm.lower().split())


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


def _local_da_classe(
    classe: str, rng: random.Random
) -> tuple[str, str, str]:
    """Bairro/cidade/uf coerentes com a classe (rural/comercial fixos)."""
    if classe == "rural":
        return _LOCAL_RURAL
    if classe == "comercial":
        return _LOCAL_COMERCIAL
    return _LOCAIS[rng.randrange(len(_LOCAIS))]


def _ucs_da_classe(
    telefone: str, seed: int, classe: str, base_uc0: int, n_ucs_min: int
) -> tuple[int, tuple[int, ...]]:
    """Deriva (n_ucs, base_kwh) no stream dedicado de UCs, clampado por `n_ucs_min`.

    Stream separado (`{telefone}:ucs`) preserva a sequência principal do RNG —
    cenário/outage/corte das personas derivadas não se deslocam (SPEC-013).
    """
    _, (kwh_lo, kwh_hi) = _CLASSE_PARAMS[classe]
    rng_ucs = _rng(f"{telefone}:ucs", seed)
    n_ucs = rng_ucs.choices((1, 2, 3, 4), weights=_UC_WEIGHTS[classe], k=1)[0]
    n_ucs = max(n_ucs, n_ucs_min)
    base_kwh = (base_uc0, *(rng_ucs.randint(kwh_lo, kwh_hi) for _ in range(n_ucs - 1)))
    return n_ucs, base_kwh


def perfil_de(
    telefone: str,
    seed: int,
    *,
    rico: bool = False,
    persona_key: str | None = None,
    nome: str | None = None,
) -> PerfilPersona:
    """Deriva o perfil determinístico de uma persona.

    Precedência (forte → fraco): **canônico por nome** > `rico` > derivado.

    - `persona_key`/`nome`: se a persona é uma das 3 canônicas (Ana/Carlos/Joana),
      aplica o cenário canônico **fixo** (independente do telefone). Pode-se passar
      o `nome` (slug calculado aqui) ou o `persona_key` (slug pronto).
    - `rico=True` (usado quando há uma única persona): garante um perfil que
      exercita várias tools (fatura vencida + outage ativa no bairro). Só vale
      quando a persona **não** é canônica.
    """
    if persona_key is None and nome is not None:
        persona_key = _slug(nome)

    rng = _rng(telefone, seed)
    cpf = _cpf(rng)

    classe = rng.choices(
        ("residencial", "comercial", "rural"), weights=(6, 3, 1), k=1
    )[0]

    # Ordem dos draws preservada do baseline (SPEC-006/013) para não deslocar o
    # perfil das personas derivadas: bairro (randrange p/ residencial) ANTES do
    # consumo da UC primária. n_ucs e consumos extras vêm de um stream dedicado.
    bairro, cidade, uf = _local_da_classe(classe, rng)
    _, (kwh_lo, kwh_hi) = _CLASSE_PARAMS[classe]
    base_uc0 = rng.randint(kwh_lo, kwh_hi)
    n_ucs, base_kwh = _ucs_da_classe(telefone, seed, classe, base_uc0, n_ucs_min=1)

    cenario_fatura = rng.choices(
        ("em_dia", "uma_aberta", "uma_vencida"), weights=(3, 4, 3), k=1
    )[0]
    outage_ativa = rng.random() < 0.35
    corte_religacao = classe == "rural" and rng.random() < 0.5

    canonico = _CANONICOS.get(persona_key) if persona_key else None
    if canonico is not None:
        # Precedência máxima: cenário canônico fixo por nome. Re-deriva classe,
        # bairro, subgrupo, consumo e UCs coerentes com a classe canônica (tudo
        # ainda função do telefone -> idempotente), e fixa os campos de cenário.
        classe = canonico.classe
        bairro, cidade, uf = canonico.local or _local_da_classe(classe, rng)
        base_uc0 = rng.randint(*_CLASSE_PARAMS[classe][1])
        n_ucs, base_kwh = _ucs_da_classe(
            telefone, seed, classe, base_uc0, n_ucs_min=canonico.n_ucs_min
        )
        cenario_fatura = canonico.cenario_fatura
        outage_ativa = canonico.outage_ativa
        corte_religacao = canonico.corte_religacao
    elif rico:
        # Persona única (não-canônica): garante cenário demonstrável e bairro
        # com outage.
        cenario_fatura = "uma_vencida"
        outage_ativa = True
        bairro, cidade, uf = _LOCAIS[0]

    subgrupo = _CLASSE_PARAMS[classe][0]

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
