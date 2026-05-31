"""DTOs (contratos da API) em Pydantic v2, desacoplados das entidades de
dominio. Cada DTO sabe se construir a partir de uma entidade (`from_entity`).
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, Field

from src.domain.billing.entities import Contrato, Fatura, Titular, UnidadeConsumidora
from src.domain.conversation.entities import MemoriaConversa
from src.domain.knowledge.entities import ResultadoKB
from src.domain.outage.entities import Interrupcao
from src.domain.shared.value_objects import TipoChamado
from src.domain.ticketing.entities import Chamado, Handoff


class CustomerDTO(BaseModel):
    id: uuid.UUID
    nome: str
    cpf_mascarado: str
    telefone_mascarado: str
    email: str | None
    persona_key: str | None

    @classmethod
    def from_entity(cls, t: Titular) -> CustomerDTO:
        return cls(
            id=t.id, nome=t.nome, cpf_mascarado=t.cpf.mascarado(),
            telefone_mascarado=t.telefone.mascarado(), email=t.email, persona_key=t.persona_key,
        )


class PersonaHintDTO(BaseModel):
    """Atalho da primeira tela: telefone em claro (console interno do operador)."""

    nome: str
    telefone: str
    persona_key: str | None

    @classmethod
    def from_entity(cls, t: Titular) -> PersonaHintDTO:
        return cls(nome=t.nome, telefone=t.telefone.value, persona_key=t.persona_key)


class UnitDTO(BaseModel):
    id: uuid.UUID
    numero_uc: str
    logradouro: str | None
    bairro: str
    cidade: str
    uf: str
    classe: str
    subgrupo: str | None
    status: str

    @classmethod
    def from_entity(cls, u: UnidadeConsumidora) -> UnitDTO:
        return cls(
            id=u.id, numero_uc=u.numero_uc, logradouro=u.logradouro, bairro=u.bairro,
            cidade=u.cidade, uf=u.uf, classe=u.classe, subgrupo=u.subgrupo, status=u.status,
        )


class ContractDTO(BaseModel):
    id: uuid.UUID
    modalidade: str
    data_inicio: dt.date
    status: str
    unidade: UnitDTO

    @classmethod
    def from_entity(cls, c: Contrato) -> ContractDTO:
        return cls(
            id=c.id, modalidade=c.modalidade, data_inicio=c.data_inicio,
            status=c.status, unidade=UnitDTO.from_entity(c.unidade),
        )


class InvoiceDTO(BaseModel):
    id: uuid.UUID
    uc_id: uuid.UUID
    mes_referencia: str
    consumo_kwh: int
    valor_centavos: int
    valor_formatado: str
    bandeira: str
    vencimento: dt.date
    status: str
    linha_digitavel: str | None
    pix_copia_cola: str | None

    @classmethod
    def from_entity(cls, f: Fatura) -> InvoiceDTO:
        return cls(
            id=f.id, uc_id=f.uc_id, mes_referencia=f.mes_referencia, consumo_kwh=f.consumo_kwh,
            valor_centavos=f.valor.centavos, valor_formatado=f.valor.formatado(),
            bandeira=f.bandeira, vencimento=f.vencimento, status=f.status,
            linha_digitavel=f.linha_digitavel, pix_copia_cola=f.pix_copia_cola,
        )


class InvoicePdfDTO(BaseModel):
    url: str
    presigned: bool
    expires_at: dt.datetime | None = None
    generated: bool = Field(description="True se renderizou agora; False se veio do storage")


class OutageDTO(BaseModel):
    id: uuid.UUID
    bairro: str
    cidade: str
    uf: str
    tipo: str
    causa: str | None
    inicio: dt.datetime
    previsao_retorno: dt.datetime | None
    status: str

    @classmethod
    def from_entity(cls, o: Interrupcao) -> OutageDTO:
        return cls(
            id=o.id, bairro=o.bairro, cidade=o.cidade, uf=o.uf, tipo=o.tipo, causa=o.causa,
            inicio=o.inicio, previsao_retorno=o.previsao_retorno, status=o.status,
        )


class OutageQueryResultDTO(BaseModel):
    encontrada: bool
    interrupcao: OutageDTO | None = None


class TicketDTO(BaseModel):
    id: uuid.UUID
    protocolo: str
    titular_id: uuid.UUID
    uc_id: uuid.UUID | None
    tipo: str
    descricao: str | None
    status: str
    sla_horas: int
    canal: str
    aberto_em: dt.datetime
    atualizado_em: dt.datetime

    @classmethod
    def from_entity(cls, c: Chamado) -> TicketDTO:
        return cls(
            id=c.id, protocolo=c.protocolo, titular_id=c.titular_id, uc_id=c.uc_id,
            tipo=c.tipo.value, descricao=c.descricao, status=c.status, sla_horas=c.sla_horas,
            canal=c.canal, aberto_em=c.aberto_em, atualizado_em=c.atualizado_em,
        )


class CreateTicketRequest(BaseModel):
    titular_id: uuid.UUID
    uc_id: uuid.UUID | None = None
    tipo: TipoChamado
    descricao: str | None = None
    idempotency_key: str = Field(min_length=4, max_length=128)


class CreateTicketResponse(BaseModel):
    criado_agora: bool
    ticket: TicketDTO


class HandoffRequest(BaseModel):
    chamado_id: uuid.UUID | None = None
    motivo: str | None = None
    remetente: str | None = None  # id do chat (LID/telefone) p/ pausar a IA (SPEC-016)


class ResumeHandoffRequest(BaseModel):
    operador: str | None = None


class HandoffDTO(BaseModel):
    id: uuid.UUID
    chamado_id: uuid.UUID | None
    remetente: str | None
    motivo: str | None
    status: str
    operador: str | None
    criado_em: dt.datetime

    @classmethod
    def from_entity(cls, h: Handoff) -> HandoffDTO:
        return cls(
            id=h.id, chamado_id=h.chamado_id, remetente=h.remetente, motivo=h.motivo,
            status=h.status, operador=h.operador, criado_em=h.criado_em,
        )


class MemoryItemDTO(BaseModel):
    chave: str
    valor: Any
    atualizado_em: dt.datetime

    @classmethod
    def from_entity(cls, m: MemoriaConversa) -> MemoryItemDTO:
        return cls(chave=m.chave, valor=m.valor, atualizado_em=m.atualizado_em)


class MemoryPutRequest(BaseModel):
    chave: str = Field(min_length=1, max_length=64)
    valor: Any


class ComponentHealthDTO(BaseModel):
    name: str  # api | whatsapp | agente
    status: str  # ok | down | unknown


class HealthDTO(BaseModel):
    status: str  # ok | degraded
    db: str
    components: list[ComponentHealthDTO] = []


class KbResultDTO(BaseModel):
    slug: str
    titulo: str
    trecho: str
    score: int

    @classmethod
    def from_entity(cls, r: ResultadoKB) -> KbResultDTO:
        return cls(slug=r.slug, titulo=r.titulo, trecho=r.trecho, score=r.score)
