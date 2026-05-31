"""Use cases (camada de aplicacao). Orquestram dominio + ports. Cada serviço
mapeia para uma ou mais ferramentas MCP que consomem a API REST.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable
from typing import Any

from src.application.ports import (
    ChamadoRepository,
    EventBus,
    FaturaRepository,
    HandoffRepository,
    InterrupcaoRepository,
    InvoicePdfRenderer,
    MemoriaRepository,
    ObjectStorage,
    OmniSender,
    TitularRepository,
    UnidadeRepository,
    UnitOfWork,
)
from src.domain.billing.documento import DocumentoFatura, FaturaDetalhada
from src.domain.billing.entities import Contrato, Fatura, Titular, UnidadeConsumidora
from src.domain.conversation.entities import MemoriaConversa
from src.domain.notifications.entities import EventoCX
from src.domain.notifications.templates import render_notificacao
from src.domain.outage.entities import Interrupcao
from src.domain.shared.errors import InvariantError, NotFoundError
from src.domain.shared.value_objects import Protocolo, Telefone, TipoChamado
from src.domain.ticketing.entities import Chamado, Handoff

Clock = Callable[[], dt.datetime]


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class BillingService:
    """find_customer_by_phone, list_contracts, get_invoice_status."""

    def __init__(
        self,
        titulares: TitularRepository,
        unidades: UnidadeRepository,
        faturas: FaturaRepository,
    ) -> None:
        self._titulares = titulares
        self._unidades = unidades
        self._faturas = faturas

    def find_customer_by_phone(self, telefone: str) -> Titular:
        normalizado = Telefone(telefone)
        titular = self._titulares.find_by_phone(normalizado.value)
        if titular is None:
            raise NotFoundError(f"Nenhum titular para o telefone {normalizado.mascarado()}")
        return titular

    def get_customer(self, titular_id: uuid.UUID) -> Titular:
        titular = self._titulares.get(titular_id)
        if titular is None:
            raise NotFoundError("Titular nao encontrado")
        return titular

    def list_contracts(self, titular_id: uuid.UUID) -> list[Contrato]:
        self.get_customer(titular_id)
        return self._titulares.list_contratos(titular_id)

    def get_unidade(self, uc_id: uuid.UUID) -> UnidadeConsumidora:
        uc = self._unidades.get(uc_id)
        if uc is None:
            raise NotFoundError("Unidade consumidora nao encontrada")
        return uc

    def list_invoices(self, uc_id: uuid.UUID, status: str | None, limit: int) -> list[Fatura]:
        self.get_unidade(uc_id)
        return self._faturas.list_for_unidade(uc_id, status, limit)

    def get_invoice(self, fatura_id: uuid.UUID) -> Fatura:
        fatura = self._faturas.get(fatura_id)
        if fatura is None:
            raise NotFoundError("Fatura nao encontrada")
        return fatura


class InvoiceDocumentService:
    """generate_invoice_pdf: render realista + persistência (MinIO) idempotente.

    Chave determinística `invoices/{id}.pdf`; **não** re-renderiza se já existe.
    Pré-assinado regenera só o link (TTL); o PDF permanece (ADR-0009).
    """

    def __init__(
        self,
        faturas: FaturaRepository,
        unidades: UnidadeRepository,
        titulares: TitularRepository,
        renderer: InvoicePdfRenderer,
        storage: ObjectStorage,
        clock: Clock | None = None,
    ) -> None:
        self._faturas = faturas
        self._unidades = unidades
        self._titulares = titulares
        self._renderer = renderer
        self._storage = storage
        self._clock: Clock = clock or _utcnow

    def _detalhar(self, fatura_id: uuid.UUID) -> FaturaDetalhada:
        fatura = self._faturas.get(fatura_id)
        if fatura is None:
            raise NotFoundError("Fatura nao encontrada")
        unidade = self._unidades.get(fatura.uc_id)
        if unidade is None:
            raise NotFoundError("Unidade consumidora nao encontrada")
        titular = self._titulares.get(unidade.titular_id)
        if titular is None:
            raise NotFoundError("Titular nao encontrado")
        historico = sorted(
            (f.mes_referencia, f.consumo_kwh)
            for f in self._faturas.list_for_unidade(unidade.id, None, 12)
        )
        return FaturaDetalhada(
            titular=titular, unidade=unidade, fatura=fatura,
            historico=historico, emitida_em=self._clock().date(),
        )

    @staticmethod
    def _key(fatura_id: uuid.UUID) -> str:
        return f"invoices/{fatura_id}.pdf"

    def obter_ou_gerar(
        self, fatura_id: uuid.UUID, presign: bool = False, expires: int = 3600
    ) -> DocumentoFatura:
        key = self._key(fatura_id)
        gerou = False
        if not self._storage.exists(key):
            pdf = self._renderer.render(self._detalhar(fatura_id))  # valida existência
            self._storage.put(key, pdf, "application/pdf")
            gerou = True
        if presign:
            url = self._storage.presigned_url(key, expires)
            expira = self._clock() + dt.timedelta(seconds=expires)
        else:
            url = self._storage.public_url(key)
            expira = None
        return DocumentoFatura(url=url, presigned=presign, expires_at=expira, gerado_agora=gerou)


class OutageService:
    """get_outage_by_region."""

    def __init__(self, interrupcoes: InterrupcaoRepository) -> None:
        self._interrupcoes = interrupcoes

    def find_active_by_region(
        self, bairro: str, cidade: str | None = None, uf: str | None = None
    ) -> Interrupcao | None:
        return self._interrupcoes.find_ativa_por_regiao(bairro.strip(), cidade, uf)


class TicketingService:
    """create_ticket (idempotente), get_ticket_status, request_human_handoff."""

    def __init__(
        self,
        chamados: ChamadoRepository,
        handoffs: HandoffRepository,
        titulares: TitularRepository,
        uow: UnitOfWork,
        clock: Clock | None = None,
    ) -> None:
        self._chamados = chamados
        self._handoffs = handoffs
        self._titulares = titulares
        self._uow = uow
        self._clock: Clock = clock or _utcnow

    def open_ticket(
        self,
        *,
        titular_id: uuid.UUID,
        uc_id: uuid.UUID | None,
        tipo: str,
        descricao: str | None,
        idempotency_key: str,
    ) -> tuple[Chamado, bool]:
        existente = self._chamados.get_by_idempotency_key(idempotency_key)
        if existente is not None:
            return existente, False

        if self._titulares.get(titular_id) is None:
            raise NotFoundError("Titular nao encontrado")

        try:
            tipo_vo = TipoChamado(tipo)
        except ValueError as exc:
            raise InvariantError(f"Tipo de chamado invalido: {tipo!r}") from exc

        agora = self._clock()
        protocolo = Protocolo.gerar(agora.strftime("%Y%m%d"), uuid.uuid4().hex[:4])
        chamado = Chamado(
            id=uuid.uuid4(),
            protocolo=protocolo.value,
            titular_id=titular_id,
            uc_id=uc_id,
            tipo=tipo_vo,
            descricao=descricao,
            status="aberto",
            sla_horas=tipo_vo.sla_horas,
            canal="whatsapp",
            aberto_em=agora,
            atualizado_em=agora,
        )
        try:
            salvo = self._chamados.add(chamado, idempotency_key)
            self._uow.commit()
        except Exception:
            self._uow.rollback()
            raise
        return salvo, True

    def get_ticket_status(self, protocolo: str) -> Chamado:
        chamado = self._chamados.get_by_protocolo(protocolo)
        if chamado is None:
            raise NotFoundError(f"Chamado {protocolo} nao encontrado")
        return chamado

    def list_customer_tickets(self, titular_id: uuid.UUID) -> list[Chamado]:
        return self._chamados.list_for_titular(titular_id)

    def request_handoff(
        self, *, chamado_id: uuid.UUID | None, motivo: str | None
    ) -> Handoff:
        handoff = Handoff(
            id=uuid.uuid4(),
            chamado_id=chamado_id,
            motivo=motivo,
            status="pendente",
            operador=None,
            criado_em=self._clock(),
        )
        try:
            salvo = self._handoffs.add(handoff)
            self._uow.commit()
        except Exception:
            self._uow.rollback()
            raise
        return salvo


class MemoryService:
    """Memoria curta por chatId (RF-11)."""

    def __init__(self, memorias: MemoriaRepository, uow: UnitOfWork) -> None:
        self._memorias = memorias
        self._uow = uow

    def get(self, chat_id: str) -> list[MemoriaConversa]:
        return self._memorias.list_for_chat(chat_id)

    def put(self, chat_id: str, chave: str, valor: object) -> MemoriaConversa:
        try:
            salvo = self._memorias.upsert(chat_id, chave, valor)
            self._uow.commit()
        except Exception:
            self._uow.rollback()
            raise
        return salvo


class ProactiveService:
    """Notificações proativas determinísticas (SPEC-009 / ADR-0005). Sem LLM.

    `disparar` publica o evento em utilitycx.* (consumido pelo worker). `processar`
    (worker) renderiza o template canônico, envia pelo Omni e grava na memória.
    """

    def __init__(
        self,
        bus: EventBus,
        sender: OmniSender,
        memorias: MemoriaRepository,
        titulares: TitularRepository,
        faturas: FaturaRepository,
        interrupcoes: InterrupcaoRepository,
        uow: UnitOfWork,
        clock: Clock | None = None,
    ) -> None:
        self._bus = bus
        self._sender = sender
        self._memorias = memorias
        self._titulares = titulares
        self._faturas = faturas
        self._interrupcoes = interrupcoes
        self._uow = uow
        self._clock: Clock = clock or _utcnow

    @staticmethod
    def _payload(evento: EventoCX) -> dict[str, object]:
        return {
            "tipo": evento.tipo, "subtipo": evento.subtipo, "telefone": evento.telefone,
            "nome": evento.nome, "idempotency_key": evento.idempotency_key, "dados": evento.dados,
        }

    def disparar(self, evento: EventoCX) -> dict[str, object]:
        """Operador dispara o evento: publica no bus + devolve o preview canônico."""
        self._bus.publish(evento.subject, self._payload(evento))
        return {"publicado": True, "subject": evento.subject, "preview": render_notificacao(evento)}

    def disparar_por_telefone(
        self, phone: str, tipo: str, subtipo: str, dados: dict[str, Any]
    ) -> dict[str, object]:
        """Resolve o titular (nome) pelo telefone, monta o evento e dispara."""
        normalizado = Telefone(phone)
        titular = self._titulares.find_by_phone(normalizado.value)
        if titular is None:
            raise NotFoundError("Telefone nao identificado")
        chave_dado = dados.get("fatura_id") or dados.get("mes") or dados.get("bairro") or ""
        evento = EventoCX(
            tipo=tipo, subtipo=subtipo, telefone=normalizado.value, nome=titular.nome,
            idempotency_key=f"{tipo}.{subtipo}.{normalizado.value}.{chave_dado}", dados=dados,
        )
        return self.disparar(evento)

    def processar(self, evento: EventoCX) -> dict[str, object]:
        """Worker: render determinístico -> envia (Omni) -> grava na memória."""
        texto = render_notificacao(evento)
        enviado = self._sender.send_text(evento.chat_id, texto)
        try:
            self._memorias.upsert(
                evento.chat_id, evento.memoria_chave,
                {"texto": texto, "em": self._clock().isoformat(), "dados": evento.dados,
                 "idempotency_key": evento.idempotency_key},
            )
            self._uow.commit()
        except Exception:
            self._uow.rollback()
            raise
        return {"enviado": enviado, "texto": texto, "memoria_chave": evento.memoria_chave}

    def candidatos(self, phone: str) -> dict[str, object]:
        """Eventos elegíveis p/ o cliente: faturas em aberto (pagamento) + interrupção (outage)."""
        normalizado = Telefone(phone)
        titular = self._titulares.find_by_phone(normalizado.value)
        if titular is None:
            return {"encontrado": False, "motivo": "Telefone nao identificado."}
        pagamentos: list[dict[str, object]] = []
        outages: list[dict[str, object]] = []
        bairros_vistos: set[str] = set()
        for c in self._titulares.list_contratos(titular.id):
            uc = c.unidade
            for f in self._faturas.list_for_unidade(uc.id, None, 24):
                if f.status in ("em_aberto", "vencida"):
                    pagamentos.append({
                        "fatura_id": str(f.id), "numero_uc": uc.numero_uc,
                        "mes_referencia": f.mes_referencia, "valor": f.valor.formatado(),
                        "status": f.status,
                    })
            if uc.bairro and uc.bairro not in bairros_vistos:
                bairros_vistos.add(uc.bairro)
                inter = self._interrupcoes.find_ativa_por_regiao(uc.bairro, uc.cidade, uc.uf)
                if inter is not None:
                    prev = inter.previsao_retorno
                    outages.append({
                        "bairro": uc.bairro,
                        "previsao": prev.isoformat() if prev else None,
                        "status": inter.status,
                    })
        return {
            "encontrado": True, "titular": titular.nome, "telefone": normalizado.value,
            "pagamentos": pagamentos, "outages": outages,
        }
