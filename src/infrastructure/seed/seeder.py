"""Geração determinística da massa de seed por persona (SPEC-006)."""

from __future__ import annotations

import datetime as dt
import hashlib
import unicodedata
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from src.domain.persona import PerfilPersona, Persona
from src.infrastructure.orm import (
    ChamadoORM,
    ContratoORM,
    FaturaORM,
    InterrupcaoORM,
    LeituraORM,
    PagamentoORM,
    TitularORM,
    UnidadeORM,
)

# Namespace fixo p/ IDs determinísticos (uuid5) -> re-runs estáveis e idempotentes.
_NS = uuid.uuid5(uuid.NAMESPACE_DNS, "luzdovale.seed")
_VERAO = (12, 1, 2, 3)
_ADICIONAL_BANDEIRA = {"verde": 0, "amarela": 2, "vermelha_p1": 4, "vermelha_p2": 7}


@dataclass
class SeedReport:
    titulares: int = 0
    unidades: int = 0
    contratos: int = 0
    leituras: int = 0
    faturas: int = 0
    pagamentos: int = 0
    interrupcoes: int = 0
    chamados: int = 0


# --------------------------------------------------------------------------- #
# Helpers determinísticos
# --------------------------------------------------------------------------- #
def _slug(nome: str) -> str:
    norm = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return ".".join(norm.lower().split())


def _det_uuid(*parts: str) -> uuid.UUID:
    return uuid.uuid5(_NS, ":".join(parts))


def _numero_uc(telefone: str, idx: int) -> str:
    h = int(hashlib.sha256(f"uc:{telefone}:{idx}".encode()).hexdigest(), 16)
    return str(100_000_000 + (h % 900_000_000))  # 9 dígitos estáveis


def _add_months(d: dt.date, n: int) -> dt.date:
    total = (d.year * 12 + (d.month - 1)) + n
    return dt.date(total // 12, total % 12 + 1, 1)


def _bandeira(mes_num: int) -> str:
    if mes_num in (8, 9):
        return "vermelha_p2"
    if mes_num in (6, 7, 10, 11):
        return "vermelha_p1"
    if mes_num in (4, 5, 12):
        return "amarela"
    return "verde"


def _consumo(base_kwh: int, mes_num: int) -> int:
    extra = base_kwh * 35 // 100 if mes_num in _VERAO else 0
    return base_kwh + extra + mes_num  # variação leve determinística


def _upsert(
    session: Session, model: Any, values: dict[str, Any], *, index_elements: list[str]
) -> int:
    """Insert idempotente. RETURNING id conta só o que foi de fato inserido
    (ON CONFLICT DO NOTHING não retorna linha em conflito; rowcount é -1/instável)."""
    stmt = (
        pg_insert(model)
        .values(**values)
        .on_conflict_do_nothing(index_elements=index_elements)
        .returning(model.id)
    )
    return len(session.execute(stmt).fetchall())


# --------------------------------------------------------------------------- #
# Seeder
# --------------------------------------------------------------------------- #
def seed_personas(
    session: Session,
    personas_perfis: list[tuple[Persona, PerfilPersona]],
    *,
    anchor: dt.date = dt.date(2026, 5, 1),
    history_months: int = 24,
    now: dt.datetime | None = None,
) -> SeedReport:
    """Materializa a massa de seed (idempotente) para as personas dadas."""
    now = now or dt.datetime.now(dt.UTC)
    rep = SeedReport()

    for persona, perfil in personas_perfis:
        titular_id = _det_uuid("titular", perfil.cpf)
        rep.titulares += _upsert(
            session,
            TitularORM,
            {
                "id": titular_id,
                "nome": persona.nome,
                "cpf": perfil.cpf,
                "email": f"{_slug(persona.nome)}@example.test",
                "telefone_principal": persona.telefone,
                "persona_key": _slug(persona.nome),
            },
            index_elements=["cpf"],
        )

        for idx in range(perfil.n_ucs):
            numero_uc = _numero_uc(persona.telefone, idx)
            uc_id = _det_uuid("uc", numero_uc)
            data_ligacao = dt.date(2019, 3, 10)
            rep.unidades += _upsert(
                session,
                UnidadeORM,
                {
                    "id": uc_id,
                    "numero_uc": numero_uc,
                    "titular_id": titular_id,
                    "logradouro": f"Rua das Acacias, {100 + idx}",
                    "bairro": perfil.bairro,
                    "cidade": perfil.cidade,
                    "uf": perfil.uf,
                    "classe": perfil.classe,
                    "subgrupo": perfil.subgrupo,
                    "status": "ativa",
                },
                index_elements=["numero_uc"],
            )
            rep.contratos += _upsert(
                session,
                ContratoORM,
                {
                    "id": _det_uuid("contrato", str(uc_id)),
                    "titular_id": titular_id,
                    "uc_id": uc_id,
                    "modalidade": "convencional",
                    "data_inicio": data_ligacao,
                    "status": "ativo",
                },
                index_elements=["id"],
            )
            rep.leituras += _seed_faturas_de_uc(
                session, rep, perfil, uc_id, idx, anchor, history_months
            )

        rep.interrupcoes += _seed_interrupcoes(session, perfil, now)
        rep.chamados += _seed_chamados(session, perfil, titular_id, persona, now)

    return rep


def _seed_faturas_de_uc(
    session: Session,
    rep: SeedReport,
    perfil: PerfilPersona,
    uc_id: uuid.UUID,
    idx: int,
    anchor: dt.date,
    history_months: int,
) -> int:
    """Leituras + faturas + pagamentos dos N meses. Retorna nº de leituras novas."""
    base_kwh = perfil.base_kwh[idx]
    anchor_ref = anchor.strftime("%Y-%m")
    prev_ref = _add_months(anchor, -1).strftime("%Y-%m")
    leituras_novas = 0

    for g in range(history_months):
        mes = _add_months(anchor, -g)
        mes_ref = mes.strftime("%Y-%m")
        consumo = _consumo(base_kwh, mes.month)
        leituras_novas += _upsert(
            session,
            LeituraORM,
            {
                "id": _det_uuid("leitura", str(uc_id), mes_ref),
                "uc_id": uc_id,
                "mes_referencia": mes_ref,
                "consumo_kwh": consumo,
                "data_leitura": dt.date(mes.year, mes.month, 5),
            },
            index_elements=["uc_id", "mes_referencia"],
        )

        bandeira = _bandeira(mes.month)
        valor = consumo * 95 + consumo * _ADICIONAL_BANDEIRA[bandeira]
        venc = _add_months(mes, 1) + dt.timedelta(days=9)  # ~dia 10 do mês seguinte
        status = _status_fatura(perfil, idx, mes_ref, anchor_ref, prev_ref)
        chave = mes_ref.replace("-", "")
        rep.faturas += _upsert(
            session,
            FaturaORM,
            {
                "id": _det_uuid("fatura", str(uc_id), mes_ref),
                "uc_id": uc_id,
                "mes_referencia": mes_ref,
                "consumo_kwh": consumo,
                "valor_total_centavos": valor,
                "bandeira": bandeira,
                "vencimento": venc,
                "status": status,
                "linha_digitavel": f"34191.79001 01043.510047 91020.150008 1 {chave}00",
                "pix_copia_cola": f"00020126LUZDOVALEFICTICIO{chave}",
                "emitida_em": dt.datetime(mes.year, mes.month, 2, tzinfo=dt.UTC),
            },
            index_elements=["uc_id", "mes_referencia"],
        )

        if status == "paga":
            rep.pagamentos += _upsert(
                session,
                PagamentoORM,
                {
                    "id": _det_uuid("pagamento", str(uc_id), mes_ref),
                    "fatura_id": _det_uuid("fatura", str(uc_id), mes_ref),
                    "valor_centavos": valor,
                    "data_pagamento": dt.datetime(
                        mes.year, mes.month, 16, tzinfo=dt.UTC
                    ),
                    "meio": "pix",
                    "idempotency_key": f"pay-{uc_id}-{mes_ref}",
                },
                index_elements=["idempotency_key"],
            )
    return leituras_novas


def _status_fatura(
    perfil: PerfilPersona,
    idx: int,
    mes_ref: str,
    anchor_ref: str,
    prev_ref: str,
) -> str:
    """Status conforme o cenário (só a UC primária, idx 0, carrega o cenário)."""
    if idx != 0:
        return "em_aberto" if mes_ref == anchor_ref else "paga"
    if perfil.cenario_fatura == "uma_vencida":
        if mes_ref == anchor_ref:
            return "em_aberto"
        if mes_ref == prev_ref:
            return "vencida"
    elif perfil.cenario_fatura == "uma_aberta":
        if mes_ref == anchor_ref:
            return "em_aberto"
    # em_dia (ou meses antigos): paga
    return "paga"


def _seed_interrupcoes(session: Session, perfil: PerfilPersona, now: dt.datetime) -> int:
    """Interrupção ativa no bairro (se o perfil pedir) + 1 histórica. Idempotente
    por chave natural (bairro+causa) — a tabela não tem unique key."""
    if not perfil.outage_ativa:
        return 0
    session.flush()  # materializa adds pendentes p/ a checagem de existência ver
    candidatos = [
        {
            "tipo": "nao_programada",
            "causa": "Falha em equipamento de rede",
            "inicio": now - dt.timedelta(hours=2),
            "previsao_retorno": now + dt.timedelta(hours=3),
            "status": "ativa",
        },
        {
            "tipo": "programada",
            "causa": "Manutencao preventiva em alimentador",
            "inicio": now - dt.timedelta(days=40),
            "previsao_retorno": now - dt.timedelta(days=40) + dt.timedelta(hours=4),
            "status": "encerrada",
        },
    ]
    novas = 0
    for c in candidatos:
        existe = session.execute(
            select(InterrupcaoORM.id).where(
                InterrupcaoORM.bairro == perfil.bairro,
                InterrupcaoORM.causa == c["causa"],
            )
        ).first()
        if existe:
            continue
        session.add(
            InterrupcaoORM(
                bairro=perfil.bairro,
                cidade=perfil.cidade,
                uf=perfil.uf,
                **c,
            )
        )
        novas += 1
    if novas:
        session.flush()
    return novas


def _seed_chamados(
    session: Session,
    perfil: PerfilPersona,
    titular_id: uuid.UUID,
    persona: Persona,
    now: dt.datetime,
) -> int:
    """Chamado de religação quando o perfil tem histórico de corte."""
    if not perfil.corte_religacao:
        return 0
    suf = perfil.cpf[-4:]
    return _upsert(
        session,
        ChamadoORM,
        {
            "id": _det_uuid("chamado", perfil.cpf, "religacao"),
            "protocolo": f"LDV{suf}RELIG",
            "titular_id": titular_id,
            "uc_id": _det_uuid("uc", _numero_uc(persona.telefone, 0)),
            "tipo": "religacao",
            "descricao": "Religacao apos quitacao de debito que gerou corte",
            "status": "resolvido",
            "sla_horas": 24,
            "canal": "whatsapp",
            "aberto_em": now - dt.timedelta(days=45),
            "atualizado_em": now - dt.timedelta(days=44),
            "idempotency_key": f"tk-{_slug(persona.nome)}-religacao",
        },
        index_elements=["idempotency_key"],
    )
