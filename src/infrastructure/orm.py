"""Modelos ORM (SQLAlchemy 2.0). Mapeiam as tabelas seedadas (SPEC-000).
Mapeamento parcial: apenas as colunas usadas pelos endpoints.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import CHAR, Date, DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TitularORM(Base):
    __tablename__ = "titulares"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    nome: Mapped[str] = mapped_column(Text)
    cpf: Mapped[str] = mapped_column(CHAR(11))
    email: Mapped[str | None] = mapped_column(Text)
    telefone_principal: Mapped[str] = mapped_column(String(15))
    persona_key: Mapped[str | None] = mapped_column(Text)


class UnidadeORM(Base):
    __tablename__ = "unidades_consumidoras"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    numero_uc: Mapped[str] = mapped_column(String(12))
    titular_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("titulares.id"))
    logradouro: Mapped[str | None] = mapped_column(Text)
    bairro: Mapped[str] = mapped_column(Text)
    cidade: Mapped[str] = mapped_column(Text)
    uf: Mapped[str] = mapped_column(CHAR(2))
    classe: Mapped[str] = mapped_column(Text)
    subgrupo: Mapped[str | None] = mapped_column(String(4))
    status: Mapped[str] = mapped_column(Text)


class ContratoORM(Base):
    __tablename__ = "contratos"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    titular_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("titulares.id"))
    uc_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("unidades_consumidoras.id"))
    modalidade: Mapped[str] = mapped_column(Text)
    data_inicio: Mapped[dt.date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text)


class FaturaORM(Base):
    __tablename__ = "faturas"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    uc_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("unidades_consumidoras.id"))
    mes_referencia: Mapped[str] = mapped_column(CHAR(7))
    consumo_kwh: Mapped[int] = mapped_column(Integer)
    valor_total_centavos: Mapped[int] = mapped_column(Integer)
    bandeira: Mapped[str] = mapped_column(Text)
    vencimento: Mapped[dt.date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text)
    linha_digitavel: Mapped[str | None] = mapped_column(String(54))
    pix_copia_cola: Mapped[str | None] = mapped_column(Text)
    emitida_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LeituraORM(Base):
    __tablename__ = "leituras"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    uc_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("unidades_consumidoras.id"))
    mes_referencia: Mapped[str] = mapped_column(CHAR(7))
    consumo_kwh: Mapped[int] = mapped_column(Integer)
    data_leitura: Mapped[dt.date] = mapped_column(Date)


class PagamentoORM(Base):
    __tablename__ = "pagamentos"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    fatura_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("faturas.id"))
    valor_centavos: Mapped[int] = mapped_column(Integer)
    data_pagamento: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    meio: Mapped[str] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(Text)


class InterrupcaoORM(Base):
    __tablename__ = "interrupcoes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    bairro: Mapped[str] = mapped_column(Text)
    cidade: Mapped[str] = mapped_column(Text)
    uf: Mapped[str] = mapped_column(CHAR(2))
    tipo: Mapped[str] = mapped_column(Text)
    causa: Mapped[str | None] = mapped_column(Text)
    inicio: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    previsao_retorno: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text)


class ChamadoORM(Base):
    __tablename__ = "chamados"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    protocolo: Mapped[str] = mapped_column(String(16))
    titular_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("titulares.id"))
    uc_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("unidades_consumidoras.id")
    )
    tipo: Mapped[str] = mapped_column(Text)
    descricao: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    sla_horas: Mapped[int] = mapped_column(Integer)
    canal: Mapped[str] = mapped_column(Text, default="whatsapp")
    aberto_em: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    atualizado_em: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str] = mapped_column(Text)


class HandoffORM(Base):
    __tablename__ = "handoff_queue"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    chamado_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("chamados.id"))
    motivo: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="pendente")
    operador: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))


class MemoriaORM(Base):
    __tablename__ = "conversation_memory"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    chat_id: Mapped[str] = mapped_column(Text)
    titular_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("titulares.id"))
    chave: Mapped[str] = mapped_column(Text)
    valor: Mapped[Any] = mapped_column(JSONB)
    atualizado_em: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
