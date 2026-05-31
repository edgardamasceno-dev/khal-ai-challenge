"""Adapters de persistencia (SQLAlchemy) que implementam os ports.
Mapeiam linhas ORM -> entidades de dominio puras.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import delete as pg_delete
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from src.domain.billing.entities import Contrato, Fatura, Titular, UnidadeConsumidora
from src.domain.conversation.entities import MemoriaConversa
from src.domain.outage.entities import Interrupcao
from src.domain.shared.errors import ConflictError
from src.domain.shared.value_objects import CPF, Dinheiro, Telefone, TipoChamado
from src.domain.ticketing.entities import Chamado, Handoff
from src.infrastructure.orm import (
    ChamadoORM,
    ContratoORM,
    FaturaORM,
    HandoffORM,
    InterrupcaoORM,
    MemoriaORM,
    PagamentoORM,
    TitularORM,
    UnidadeORM,
)

# ---------------------------- mappers ORM -> dominio ----------------------- #


def _to_titular(o: TitularORM) -> Titular:
    return Titular(
        id=o.id, nome=o.nome, cpf=CPF(o.cpf), telefone=Telefone(o.telefone_principal),
        email=o.email, persona_key=o.persona_key,
    )


def _to_unidade(o: UnidadeORM) -> UnidadeConsumidora:
    return UnidadeConsumidora(
        id=o.id, numero_uc=o.numero_uc, titular_id=o.titular_id, logradouro=o.logradouro,
        bairro=o.bairro, cidade=o.cidade, uf=o.uf, classe=o.classe,
        subgrupo=o.subgrupo, status=o.status,
    )


def _to_fatura(o: FaturaORM) -> Fatura:
    return Fatura(
        id=o.id, uc_id=o.uc_id, mes_referencia=o.mes_referencia, consumo_kwh=o.consumo_kwh,
        valor=Dinheiro(o.valor_total_centavos), bandeira=o.bandeira, vencimento=o.vencimento,
        status=o.status, linha_digitavel=o.linha_digitavel, pix_copia_cola=o.pix_copia_cola,
    )


def _to_interrupcao(o: InterrupcaoORM) -> Interrupcao:
    return Interrupcao(
        id=o.id, bairro=o.bairro, cidade=o.cidade, uf=o.uf, tipo=o.tipo, causa=o.causa,
        inicio=o.inicio, previsao_retorno=o.previsao_retorno, status=o.status,
    )


def _to_chamado(o: ChamadoORM) -> Chamado:
    return Chamado(
        id=o.id, protocolo=o.protocolo, titular_id=o.titular_id, uc_id=o.uc_id,
        tipo=TipoChamado(o.tipo), descricao=o.descricao, status=o.status,
        sla_horas=o.sla_horas, canal=o.canal, aberto_em=o.aberto_em, atualizado_em=o.atualizado_em,
    )


def _to_handoff(o: HandoffORM) -> Handoff:
    return Handoff(
        id=o.id, chamado_id=o.chamado_id, motivo=o.motivo, status=o.status,
        operador=o.operador, criado_em=o.criado_em, remetente=o.remetente,
    )


def _to_memoria(o: MemoriaORM) -> MemoriaConversa:
    return MemoriaConversa(
        chat_id=o.chat_id, chave=o.chave, valor=o.valor, atualizado_em=o.atualizado_em
    )


# ------------------------------- repositorios ------------------------------ #


class SqlTitularRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def find_by_phone(self, telefone: str) -> Titular | None:
        o = self._s.execute(
            select(TitularORM).where(TitularORM.telefone_principal == telefone)
        ).scalar_one_or_none()
        return _to_titular(o) if o else None

    def find_by_phone_em(self, telefones: list[str]) -> Titular | None:
        """Primeiro titular cujo telefone esteja em `telefones` (variantes do 9º dígito)."""
        if not telefones:
            return None
        o = self._s.execute(
            select(TitularORM).where(TitularORM.telefone_principal.in_(telefones))
        ).scalars().first()
        return _to_titular(o) if o else None

    def get(self, titular_id: uuid.UUID) -> Titular | None:
        o = self._s.get(TitularORM, titular_id)
        return _to_titular(o) if o else None

    def list_all(self) -> list[Titular]:
        stmt = select(TitularORM).order_by(TitularORM.nome)
        return [_to_titular(o) for o in self._s.execute(stmt).scalars().all()]

    def list_contratos(self, titular_id: uuid.UUID) -> list[Contrato]:
        rows = self._s.execute(
            select(ContratoORM, UnidadeORM)
            .join(UnidadeORM, ContratoORM.uc_id == UnidadeORM.id)
            .where(ContratoORM.titular_id == titular_id)
            .order_by(UnidadeORM.numero_uc)
        ).tuples().all()
        return [
            Contrato(
                id=c.id, modalidade=c.modalidade, data_inicio=c.data_inicio,
                status=c.status, unidade=_to_unidade(u),
            )
            for c, u in rows
        ]


class SqlUnidadeRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def get(self, uc_id: uuid.UUID) -> UnidadeConsumidora | None:
        o = self._s.get(UnidadeORM, uc_id)
        return _to_unidade(o) if o else None


class SqlFaturaRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def list_for_unidade(self, uc_id: uuid.UUID, status: str | None, limit: int) -> list[Fatura]:
        stmt = select(FaturaORM).where(FaturaORM.uc_id == uc_id)
        if status:
            stmt = stmt.where(FaturaORM.status == status)
        stmt = stmt.order_by(FaturaORM.mes_referencia.desc()).limit(limit)
        return [_to_fatura(o) for o in self._s.execute(stmt).scalars().all()]

    def get(self, fatura_id: uuid.UUID) -> Fatura | None:
        o = self._s.get(FaturaORM, fatura_id)
        return _to_fatura(o) if o else None

    def marcar_paga(
        self, fatura_id: uuid.UUID, idempotency_key: str, now: dt.datetime
    ) -> Fatura | None:
        """Da baixa: status -> 'paga' + insere pagamento (idempotente por key)."""
        o = self._s.get(FaturaORM, fatura_id)
        if o is None:
            return None
        if o.status != "paga":
            o.status = "paga"
            stmt = pg_insert(PagamentoORM).values(
                id=uuid.uuid4(), fatura_id=o.id, valor_centavos=o.valor_total_centavos,
                data_pagamento=now, meio="pix", idempotency_key=idempotency_key,
            ).on_conflict_do_nothing(index_elements=["idempotency_key"])
            self._s.execute(stmt)
            self._s.flush()
        return _to_fatura(o)

    def atualizar_status(
        self, fatura_id: uuid.UUID, status: str, now: dt.datetime
    ) -> Fatura | None:
        """Operador ajusta o status (em_aberto/vencida). Reverter de 'paga' apaga os
        pagamentos da fatura (consistência + libera a idempotency_key)."""
        o = self._s.get(FaturaORM, fatura_id)
        if o is None:
            return None
        if o.status == "paga" and status != "paga":
            self._s.execute(pg_delete(PagamentoORM).where(PagamentoORM.fatura_id == o.id))
        o.status = status
        self._s.flush()
        return _to_fatura(o)


class SqlInterrupcaoRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def find_ativa_por_regiao(
        self, bairro: str, cidade: str | None, uf: str | None
    ) -> Interrupcao | None:
        stmt = select(InterrupcaoORM).where(
            InterrupcaoORM.status == "ativa",
            InterrupcaoORM.bairro.ilike(bairro),
        )
        if cidade:
            stmt = stmt.where(InterrupcaoORM.cidade.ilike(cidade))
        if uf:
            stmt = stmt.where(InterrupcaoORM.uf == uf.upper())
        o = self._s.execute(stmt.order_by(InterrupcaoORM.inicio.desc())).scalars().first()
        return _to_interrupcao(o) if o else None

    def _ativa_orm(self, bairro: str, cidade: str | None, uf: str | None) -> InterrupcaoORM | None:
        stmt = select(InterrupcaoORM).where(
            InterrupcaoORM.status == "ativa", InterrupcaoORM.bairro.ilike(bairro)
        )
        if cidade:
            stmt = stmt.where(InterrupcaoORM.cidade.ilike(cidade))
        if uf:
            stmt = stmt.where(InterrupcaoORM.uf == uf.upper())
        return self._s.execute(stmt.order_by(InterrupcaoORM.inicio.desc())).scalars().first()

    def abrir(
        self, bairro: str, cidade: str, uf: str, causa: str | None,
        previsao: dt.datetime | None, now: dt.datetime,
    ) -> Interrupcao:
        """Abre (ativa) uma interrupcao no bairro. Idempotente: se ja ha ativa, devolve-a."""
        existente = self._ativa_orm(bairro, cidade, uf)
        if existente is not None:
            return _to_interrupcao(existente)
        o = InterrupcaoORM(
            bairro=bairro, cidade=cidade, uf=uf.upper(), tipo="nao_programada",
            causa=causa or "Interrupcao registrada pelo operador", inicio=now,
            previsao_retorno=previsao, status="ativa",
        )
        self._s.add(o)
        self._s.flush()
        return _to_interrupcao(o)

    def encerrar(
        self, bairro: str, cidade: str | None, uf: str | None, now: dt.datetime
    ) -> Interrupcao | None:
        """Encerra a interrupcao ativa do bairro -> status 'encerrada' + encerrada_em."""
        o = self._ativa_orm(bairro, cidade, uf)
        if o is None:
            return None
        o.status = "encerrada"
        o.encerrada_em = now
        self._s.flush()
        return _to_interrupcao(o)


class SqlChamadoRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def get_by_protocolo(self, protocolo: str) -> Chamado | None:
        o = self._s.execute(
            select(ChamadoORM).where(ChamadoORM.protocolo == protocolo)
        ).scalar_one_or_none()
        return _to_chamado(o) if o else None

    def get_by_idempotency_key(self, key: str) -> Chamado | None:
        o = self._s.execute(
            select(ChamadoORM).where(ChamadoORM.idempotency_key == key)
        ).scalar_one_or_none()
        return _to_chamado(o) if o else None

    def list_for_titular(self, titular_id: uuid.UUID) -> list[Chamado]:
        rows = self._s.execute(
            select(ChamadoORM)
            .where(ChamadoORM.titular_id == titular_id)
            .order_by(ChamadoORM.aberto_em.desc())
        ).scalars().all()
        return [_to_chamado(o) for o in rows]

    def add(self, chamado: Chamado, idempotency_key: str) -> Chamado:
        o = ChamadoORM(
            id=chamado.id, protocolo=chamado.protocolo, titular_id=chamado.titular_id,
            uc_id=chamado.uc_id, tipo=chamado.tipo.value, descricao=chamado.descricao,
            status=chamado.status, sla_horas=chamado.sla_horas, canal=chamado.canal,
            aberto_em=chamado.aberto_em, atualizado_em=chamado.atualizado_em,
            idempotency_key=idempotency_key,
        )
        self._s.add(o)
        self._s.flush()
        return _to_chamado(o)


class SqlHandoffRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(self, handoff: Handoff) -> Handoff:
        o = HandoffORM(
            id=handoff.id, chamado_id=handoff.chamado_id, motivo=handoff.motivo,
            status=handoff.status, operador=handoff.operador, criado_em=handoff.criado_em,
            remetente=handoff.remetente,
        )
        self._s.add(o)
        self._s.flush()
        return _to_handoff(o)

    def list_pendentes(self) -> list[Handoff]:
        rows = self._s.execute(
            select(HandoffORM)
            .where(HandoffORM.status == "pendente")
            .order_by(HandoffORM.criado_em.desc())
        ).scalars().all()
        return [_to_handoff(o) for o in rows]

    def get(self, handoff_id: uuid.UUID) -> Handoff | None:
        o = self._s.get(HandoffORM, handoff_id)
        return _to_handoff(o) if o else None

    def set_status(
        self, handoff_id: uuid.UUID, status: str, operador: str | None
    ) -> Handoff | None:
        o = self._s.get(HandoffORM, handoff_id)
        if o is None:
            return None
        o.status = status
        o.operador = operador
        self._s.flush()
        return _to_handoff(o)


class SqlMemoriaRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def list_for_chat(self, chat_id: str) -> list[MemoriaConversa]:
        rows = self._s.execute(
            select(MemoriaORM).where(MemoriaORM.chat_id == chat_id).order_by(MemoriaORM.chave)
        ).scalars().all()
        return [_to_memoria(o) for o in rows]

    def upsert(self, chat_id: str, chave: str, valor: object) -> MemoriaConversa:
        agora = dt.datetime.now(dt.UTC)
        stmt = (
            pg_insert(MemoriaORM)
            .values(id=uuid.uuid4(), chat_id=chat_id, chave=chave, valor=valor, atualizado_em=agora)
            .on_conflict_do_update(
                index_elements=[MemoriaORM.chat_id, MemoriaORM.chave],
                set_={"valor": valor, "atualizado_em": agora},
            )
            .returning(MemoriaORM)
        )
        o = self._s.execute(stmt).scalar_one()
        return _to_memoria(o)


class SqlAlchemyUnitOfWork:
    def __init__(self, session: Session) -> None:
        self._s = session

    def commit(self) -> None:
        try:
            self._s.commit()
        except Exception as exc:
            self._s.rollback()
            raise ConflictError(str(exc)) from exc

    def rollback(self) -> None:
        self._s.rollback()
