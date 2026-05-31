"""Repositórios fake em memória + UoW fake. Implementam os ports
estruturalmente (Protocol), permitindo testar os use cases sem banco.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import uuid

from src.domain.billing.entities import Contrato, Fatura, Titular, UnidadeConsumidora
from src.domain.conversation.entities import MemoriaConversa
from src.domain.knowledge.entities import ResultadoKB
from src.domain.outage.entities import Interrupcao
from src.domain.ticketing.entities import Chamado, Handoff


class FakeTitularRepository:
    def __init__(
        self,
        titulares: list[Titular] | None = None,
        contratos: dict[uuid.UUID, list[Contrato]] | None = None,
    ) -> None:
        self._by_id = {t.id: t for t in (titulares or [])}
        self._contratos = contratos or {}

    def find_by_phone(self, telefone: str) -> Titular | None:
        return next((t for t in self._by_id.values() if t.telefone.value == telefone), None)

    def get(self, titular_id: uuid.UUID) -> Titular | None:
        return self._by_id.get(titular_id)

    def list_all(self) -> list[Titular]:
        return sorted(self._by_id.values(), key=lambda t: t.nome)

    def list_contratos(self, titular_id: uuid.UUID) -> list[Contrato]:
        return list(self._contratos.get(titular_id, []))


class FakeUnidadeRepository:
    def __init__(self, unidades: list[UnidadeConsumidora] | None = None) -> None:
        self._by_id = {u.id: u for u in (unidades or [])}

    def get(self, uc_id: uuid.UUID) -> UnidadeConsumidora | None:
        return self._by_id.get(uc_id)


class FakeFaturaRepository:
    def __init__(self, faturas: list[Fatura] | None = None) -> None:
        self._items = list(faturas or [])

    def list_for_unidade(self, uc_id: uuid.UUID, status: str | None, limit: int) -> list[Fatura]:
        out = [
            f
            for f in self._items
            if f.uc_id == uc_id and (status is None or f.status == status)
        ]
        return out[:limit]

    def get(self, fatura_id: uuid.UUID) -> Fatura | None:
        return next((f for f in self._items if f.id == fatura_id), None)

    def marcar_paga(
        self, fatura_id: uuid.UUID, idempotency_key: str, now: dt.datetime
    ) -> Fatura | None:
        for idx, f in enumerate(self._items):
            if f.id == fatura_id:
                if f.status != "paga":
                    f = dataclasses.replace(f, status="paga")
                    self._items[idx] = f
                return f
        return None

    def atualizar_status(
        self, fatura_id: uuid.UUID, status: str, now: dt.datetime
    ) -> Fatura | None:
        for idx, f in enumerate(self._items):
            if f.id == fatura_id:
                f = dataclasses.replace(f, status=status)
                self._items[idx] = f
                return f
        return None


class FakeInterrupcaoRepository:
    def __init__(self, interrupcoes: list[Interrupcao] | None = None) -> None:
        self._items = list(interrupcoes or [])

    def find_ativa_por_regiao(
        self, bairro: str, cidade: str | None, uf: str | None
    ) -> Interrupcao | None:
        for i in self._items:
            if i.status == "ativa" and i.bairro.lower() == bairro.lower():
                if cidade and i.cidade.lower() != cidade.lower():
                    continue
                if uf and i.uf.upper() != uf.upper():
                    continue
                return i
        return None

    def abrir(
        self, bairro: str, cidade: str, uf: str, causa: str | None,
        previsao: dt.datetime | None, now: dt.datetime,
    ) -> Interrupcao:
        existente = self.find_ativa_por_regiao(bairro, cidade, uf)
        if existente is not None:
            return existente
        nova = Interrupcao(
            id=uuid.uuid4(), bairro=bairro, cidade=cidade, uf=uf.upper(),
            tipo="nao_programada", causa=causa or "Interrupcao registrada pelo operador",
            inicio=now, previsao_retorno=previsao, status="ativa",
        )
        self._items.append(nova)
        return nova

    def encerrar(
        self, bairro: str, cidade: str | None, uf: str | None, now: dt.datetime
    ) -> Interrupcao | None:
        ativa = self.find_ativa_por_regiao(bairro, cidade, uf)
        if ativa is None:
            return None
        encerrada = dataclasses.replace(ativa, status="encerrada")
        self._items = [encerrada if i.id == ativa.id else i for i in self._items]
        return encerrada


class FakeChamadoRepository:
    def __init__(self, chamados: list[Chamado] | None = None) -> None:
        self._items = list(chamados or [])
        self._by_idem: dict[str, Chamado] = {}

    def get_by_protocolo(self, protocolo: str) -> Chamado | None:
        return next((c for c in self._items if c.protocolo == protocolo), None)

    def get_by_idempotency_key(self, key: str) -> Chamado | None:
        return self._by_idem.get(key)

    def list_for_titular(self, titular_id: uuid.UUID) -> list[Chamado]:
        return [c for c in self._items if c.titular_id == titular_id]

    def add(self, chamado: Chamado, idempotency_key: str) -> Chamado:
        self._items.append(chamado)
        self._by_idem[idempotency_key] = chamado
        return chamado


class FakeHandoffRepository:
    def __init__(self) -> None:
        self.items: list[Handoff] = []

    def add(self, handoff: Handoff) -> Handoff:
        self.items.append(handoff)
        return handoff


class FakeMemoriaRepository:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], MemoriaConversa] = {}

    def list_for_chat(self, chat_id: str) -> list[MemoriaConversa]:
        return [m for (c, _), m in self._store.items() if c == chat_id]

    def upsert(self, chat_id: str, chave: str, valor: object) -> MemoriaConversa:
        import datetime as dt

        m = MemoriaConversa(
            chat_id=chat_id, chave=chave, valor=valor, atualizado_em=dt.datetime.now(dt.UTC)
        )
        self._store[(chat_id, chave)] = m
        return m


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class FakeKnowledgeRetrieval:
    def __init__(self, resultados: list[ResultadoKB]) -> None:
        self._res = resultados

    def search(self, query: str, limit: int) -> list[ResultadoKB]:
        q = query.lower()
        hits = [
            r
            for r in self._res
            if r.slug in q or any(t in q for t in r.titulo.lower().split())
        ]
        return hits[:limit]
