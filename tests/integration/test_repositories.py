from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy.orm import Session

from src.domain.ticketing.entities import Chamado, Handoff
from src.domain.shared.value_objects import TipoChamado
from src.infrastructure.orm import (
    ContratoORM,
    FaturaORM,
    InterrupcaoORM,
    TitularORM,
    UnidadeORM,
)
from src.infrastructure.repositories import (
    SqlChamadoRepository,
    SqlFaturaRepository,
    SqlHandoffRepository,
    SqlInterrupcaoRepository,
    SqlMemoriaRepository,
    SqlTitularRepository,
    SqlUnidadeRepository,
)

ANA = uuid.UUID("11111111-1111-1111-1111-111111111111")
UC = uuid.UUID("aaaa0001-0000-0000-0000-000000000001")
FAT = uuid.UUID("ffff0001-0000-0000-0000-000000000001")


def _seed(session: Session) -> None:
    session.add(
        TitularORM(
            id=ANA, nome="Ana Souza", cpf="52998224725",
            email=None, telefone_principal="555199990001", persona_key="ana.souza",
        )
    )
    session.add(
        UnidadeORM(
            id=UC, numero_uc="100000001", titular_id=ANA, logradouro="Rua X",
            bairro="Jardim das Flores", cidade="Vale do Sol", uf="SP",
            classe="residencial", subgrupo="B1", status="ativa",
        )
    )
    session.add(
        ContratoORM(
            id=uuid.uuid4(), titular_id=ANA, uc_id=UC, modalidade="convencional",
            data_inicio=dt.date(2019, 3, 10), status="ativo",
        )
    )
    session.add(
        FaturaORM(
            id=FAT, uc_id=UC, mes_referencia="2026-05", consumo_kwh=200,
            valor_total_centavos=19000, bandeira="amarela",
            vencimento=dt.date(2026, 6, 10), status="em_aberto",
            linha_digitavel=None, pix_copia_cola=None,
        )
    )
    session.add(
        InterrupcaoORM(
            id=uuid.uuid4(), bairro="Jardim das Flores", cidade="Vale do Sol", uf="SP",
            tipo="nao_programada", causa="Falha de rede",
            inicio=dt.datetime.now(dt.UTC), previsao_retorno=None, status="ativa",
        )
    )
    session.flush()


class TestBillingRepos:
    def test_find_by_phone_e_get(self, session: Session) -> None:
        _seed(session)
        repo = SqlTitularRepository(session)
        ana = repo.find_by_phone("555199990001")
        assert ana is not None and ana.persona_key == "ana.souza"
        assert ana.cpf.value == "52998224725"
        assert repo.get(ANA) is not None
        assert repo.find_by_phone("550000000000") is None

    def test_list_contratos_com_unidade(self, session: Session) -> None:
        _seed(session)
        contratos = SqlTitularRepository(session).list_contratos(ANA)
        assert len(contratos) == 1
        assert contratos[0].unidade.bairro == "Jardim das Flores"

    def test_unidade_e_faturas(self, session: Session) -> None:
        _seed(session)
        assert SqlUnidadeRepository(session).get(UC) is not None
        faturas = SqlFaturaRepository(session).list_for_unidade(UC, "em_aberto", 12)
        assert len(faturas) == 1 and faturas[0].valor.centavos == 19000
        assert SqlFaturaRepository(session).get(FAT).status == "em_aberto"


class TestOutageRepo:
    def test_find_ativa_por_regiao(self, session: Session) -> None:
        _seed(session)
        repo = SqlInterrupcaoRepository(session)
        assert repo.find_ativa_por_regiao("Jardim das Flores", "Vale do Sol", "SP") is not None
        assert repo.find_ativa_por_regiao("Centro", None, None) is None


class TestTicketingRepos:
    def _chamado(self, protocolo: str) -> Chamado:
        agora = dt.datetime.now(dt.UTC)
        return Chamado(
            id=uuid.uuid4(), protocolo=protocolo, titular_id=ANA, uc_id=UC,
            tipo=TipoChamado.falta_energia, descricao="x", status="aberto",
            sla_horas=48, canal="whatsapp", aberto_em=agora, atualizado_em=agora,
        )

    def test_add_e_consultas(self, session: Session) -> None:
        _seed(session)
        repo = SqlChamadoRepository(session)
        repo.add(self._chamado("LDV20260530AAAA"), "idem-1")
        assert repo.get_by_protocolo("LDV20260530AAAA") is not None
        assert repo.get_by_idempotency_key("idem-1") is not None
        assert len(repo.list_for_titular(ANA)) == 1

    def test_handoff_add(self, session: Session) -> None:
        _seed(session)
        agora = dt.datetime.now(dt.UTC)
        ho = SqlHandoffRepository(session).add(
            Handoff(id=uuid.uuid4(), chamado_id=None, motivo="m",
                    status="pendente", operador=None, criado_em=agora)
        )
        assert ho.status == "pendente"


class TestMemoriaRepo:
    def test_upsert_nao_duplica(self, session: Session) -> None:
        repo = SqlMemoriaRepository(session)
        repo.upsert("chat-1", "ultimo_protocolo", {"v": 1})
        repo.upsert("chat-1", "ultimo_protocolo", {"v": 2})
        itens = repo.list_for_chat("chat-1")
        assert len(itens) == 1 and itens[0].valor == {"v": 2}
