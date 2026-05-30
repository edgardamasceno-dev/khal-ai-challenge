"""Entidades do contexto Billing & Account (puras)."""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

from src.domain.shared.value_objects import CPF, Dinheiro, Telefone


@dataclass(frozen=True)
class Titular:
    id: uuid.UUID
    nome: str
    cpf: CPF
    telefone: Telefone
    email: str | None
    persona_key: str | None


@dataclass(frozen=True)
class UnidadeConsumidora:
    id: uuid.UUID
    numero_uc: str
    titular_id: uuid.UUID
    logradouro: str | None
    bairro: str
    cidade: str
    uf: str
    classe: str
    subgrupo: str | None
    status: str


@dataclass(frozen=True)
class Contrato:
    id: uuid.UUID
    modalidade: str
    data_inicio: dt.date
    status: str
    unidade: UnidadeConsumidora


@dataclass(frozen=True)
class Fatura:
    id: uuid.UUID
    uc_id: uuid.UUID
    mes_referencia: str
    consumo_kwh: int
    valor: Dinheiro
    bandeira: str
    vencimento: dt.date
    status: str
    linha_digitavel: str | None
    pix_copia_cola: str | None
