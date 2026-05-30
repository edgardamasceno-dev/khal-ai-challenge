"""Dominio de personas do seed/evals (SPEC-006).

Personas vem do ambiente (`SEED_PERSONAS`); cada uma ganha um perfil
deterministico (derivado do telefone + seed) que simula um cliente real.
"""

from src.domain.persona.derivation import perfil_de
from src.domain.persona.models import PerfilPersona, Persona

__all__ = ["Persona", "PerfilPersona", "perfil_de"]
