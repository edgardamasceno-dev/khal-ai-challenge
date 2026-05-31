"""Use cases (camada de aplicacao). Orquestram dominio + ports. Cada serviço
mapeia para uma ou mais ferramentas MCP que consomem a API REST.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from src.application.ports import (
    ChamadoRepository,
    ChannelControlPort,
    ChannelHealthPort,
    ChatDirectoryPort,
    ChatTranscriptPort,
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
from src.domain.conversation.entities import MemoriaConversa, MensagemChat
from src.domain.notifications.entities import EventoCX
from src.domain.notifications.templates import render_notificacao
from src.domain.outage.entities import Interrupcao
from src.domain.shared.errors import InvariantError, NotFoundError
from src.domain.shared.phone import normalizar_msisdn, variantes_nono_digito
from src.domain.shared.value_objects import Protocolo, Telefone, TipoChamado
from src.domain.ticketing.entities import Chamado, Handoff

Clock = Callable[[], dt.datetime]


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _parse_dt(valor: object) -> dt.datetime | None:
    """ISO 8601 -> datetime; None se ausente/ inválido (mantém best-effort)."""
    if not isinstance(valor, str) or not valor:
        return None
    try:
        return dt.datetime.fromisoformat(valor)
    except ValueError:
        return None


@dataclass(frozen=True)
class HealthReport:
    status: str  # ok | degraded
    db: str  # ok | down
    components: list[tuple[str, str]]  # (name, status)


class HealthService:
    """Agrega a saúde dos componentes: API (db), WhatsApp e Agente (SPEC-014)."""

    def __init__(self, channel: ChannelHealthPort) -> None:
        self._channel = channel

    def check(self, db_ok: bool) -> HealthReport:
        componentes = [
            ("api", "ok" if db_ok else "down"),
            ("whatsapp", self._channel.whatsapp()),
            ("agente", self._channel.agente()),
        ]
        geral = "ok" if all(status == "ok" for _, status in componentes) else "degraded"
        return HealthReport(
            status=geral, db="ok" if db_ok else "down", components=componentes
        )


class OperatorChatService:
    """Aba Chat do operador (SPEC-018): transcript do Omni + takeover/envio.

    Assumir o controle pausa a IA (agentPaused, SPEC-016); devolver retoma.
    """

    def __init__(
        self,
        transcript: ChatTranscriptPort,
        control: ChannelControlPort,
        sender: OmniSender,
    ) -> None:
        self._transcript = transcript
        self._control = control
        self._sender = sender

    def transcript(
        self, phone: str, limit: int = 10, cursor: str | None = None
    ) -> tuple[list[MensagemChat], str | None, bool]:
        return self._transcript.mensagens(phone, limit, cursor)

    def status(self, phone: str) -> dict[str, object]:
        return {"pausado": self._control.esta_pausado(phone)}

    def takeover(self, phone: str) -> dict[str, object]:
        """Operador assume: pausa a IA."""
        ok = self._control.pausar_agente(phone)
        return {"pausado": True, "ok": ok}

    def release(self, phone: str) -> dict[str, object]:
        """Operador devolve ao agente: retoma a IA."""
        ok = self._control.retomar_agente(phone)
        return {"pausado": False, "ok": ok}

    def send(self, phone: str, texto: str) -> dict[str, object]:
        return {"enviado": self._sender.send_text(phone, texto)}


class BillingService:
    """find_customer_by_phone, list_contracts, get_invoice_status."""

    STATUS_EDITAVEIS = ("em_aberto", "vencida")

    def __init__(
        self,
        titulares: TitularRepository,
        unidades: UnidadeRepository,
        faturas: FaturaRepository,
        uow: UnitOfWork | None = None,
        directory: ChatDirectoryPort | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._titulares = titulares
        self._unidades = unidades
        self._faturas = faturas
        self._uow = uow
        self._directory = directory
        self._clock: Clock = clock or _utcnow

    def find_customer_by_phone(self, identificador: str) -> Titular:
        """Resolve o titular a partir do identificador do remetente (SPEC-015).

        Aceita telefone (com/sem 9º dígito) ou LID do WhatsApp: tenta pelas
        variantes do nono dígito; se não achar, resolve o LID -> telefone canônico
        pelo Omni e tenta de novo. Guardrail intacto (só o titular do remetente).
        """
        raw = normalizar_msisdn(identificador)
        titular = self._titulares.find_by_phone_em(variantes_nono_digito(raw))
        if titular is None and self._directory is not None:
            canonical = self._directory.resolve_canonical(identificador)
            if canonical:
                titular = self._titulares.find_by_phone_em(variantes_nono_digito(canonical))
        if titular is None:
            raise NotFoundError(f"Nenhum titular para o remetente …{raw[-4:]}")
        return titular

    def list_personas(self) -> list[Titular]:
        """Personas cadastradas (atalhos do console). Ordenadas por nome."""
        return self._titulares.list_all()

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

    def get_titular_por_fatura(self, fatura_id: uuid.UUID) -> Titular:
        """Resolve o titular dono da fatura (fatura -> UC -> titular)."""
        fatura = self.get_invoice(fatura_id)
        unidade = self.get_unidade(fatura.uc_id)
        titular = self._titulares.get(unidade.titular_id)
        if titular is None:
            raise NotFoundError("Titular nao encontrado")
        return titular

    def atualizar_status_fatura(self, fatura_id: uuid.UUID, status: str) -> Fatura:
        """Operador ajusta o status da fatura (em_aberto/vencida). Muta + commit.

        Reverter de 'paga' desfaz a baixa (remove o pagamento). 'paga' não é
        aceito aqui — a baixa continua pela aba Proativos (SPEC-010/011).
        """
        if status not in self.STATUS_EDITAVEIS:
            raise InvariantError(
                f"status invalido: {status!r} (use {self.STATUS_EDITAVEIS})"
            )
        fatura = self._faturas.atualizar_status(fatura_id, status, self._clock())
        if fatura is None:
            raise NotFoundError("Fatura nao encontrada")
        if self._uow is not None:
            try:
                self._uow.commit()
            except Exception:
                self._uow.rollback()
                raise
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
        sender: OmniSender | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._faturas = faturas
        self._unidades = unidades
        self._titulares = titulares
        self._renderer = renderer
        self._storage = storage
        self._sender = sender
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

    def enviar_2a_via(self, fatura_id: uuid.UUID, expires: int = 3600) -> dict[str, object]:
        """Envia a 2ª via ao titular: PDF **anexo** no WhatsApp + **link** no texto
        (ADR-0003 / SPEC-017). Destino = telefone cadastrado do dono da fatura."""
        detalhe = self._detalhar(fatura_id)  # resolve titular dono + valida a fatura
        doc = self.obter_ou_gerar(fatura_id, presign=True, expires=expires)
        enviado = False
        if self._sender is not None:
            pdf = self._renderer.render(detalhe)
            mes = detalhe.fatura.mes_referencia
            telefone = detalhe.titular.telefone.value
            caption = f"Luz do Vale — 2ª via da fatura de {mes}."
            enviado = self._sender.send_document(
                telefone, pdf, f"fatura-{mes}.pdf", caption
            )
            if enviado:
                self._sender.send_text(telefone, f"Link da sua 2ª via: {doc.url}")
        return {
            "enviado": enviado,
            "mes_referencia": detalhe.fatura.mes_referencia,
            "status": detalhe.fatura.status,
            "url": doc.url,
            "presigned": doc.presigned,
            "expires_at": doc.expires_at.isoformat() if doc.expires_at else None,
        }


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
        control: ChannelControlPort | None = None,
        directory: ChatDirectoryPort | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._chamados = chamados
        self._handoffs = handoffs
        self._titulares = titulares
        self._uow = uow
        self._control = control
        self._directory = directory
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
        self,
        *,
        chamado_id: uuid.UUID | None,
        motivo: str | None,
        remetente: str | None = None,
    ) -> Handoff:
        """Registra o handoff e **pausa a IA** no canal (SPEC-016), p/ atendimento
        humano. A pausa é best-effort: sem canal/remetente, só registra.

        O remetente é normalizado para o telefone canônico (resolve LID via Omni),
        para que a fila e a aba Chat casem pelo mesmo telefone."""
        try:
            salvo = self._handoffs.add(
                Handoff(
                    id=uuid.uuid4(), chamado_id=chamado_id, motivo=motivo,
                    status="pendente", operador=None, criado_em=self._clock(),
                    remetente=self._normalizar_remetente(remetente),
                )
            )
            self._uow.commit()
        except Exception:
            self._uow.rollback()
            raise
        if remetente and self._control is not None:
            self._control.pausar_agente(remetente)
        return salvo

    def _normalizar_remetente(self, remetente: str | None) -> str | None:
        """LID/telefone -> telefone canônico (para casar com o phone da aba Chat)."""
        if not remetente:
            return None
        if self._directory is not None:
            canonical = self._directory.resolve_canonical(remetente)
            if canonical:
                return canonical
        return normalizar_msisdn(remetente)

    def list_handoffs(self) -> list[Handoff]:
        """Fila de handoffs pendentes (atendimento humano em aberto)."""
        return self._handoffs.list_pendentes()

    def resolver_handoffs_do_remetente(self, phone: str) -> int:
        """Marca como resolvidos os handoffs pendentes do cliente (casa pelo telefone,
        tolerando o 9º dígito). Mantém a fila de Chamados consistente quando o operador
        devolve pela aba Chat (SPEC-018)."""
        variantes = set(variantes_nono_digito(normalizar_msisdn(phone)))
        resolvidos = 0
        for h in self._handoffs.list_pendentes():
            if h.remetente and normalizar_msisdn(h.remetente) in variantes:
                self._handoffs.set_status(h.id, "resolvido", "chat")
                resolvidos += 1
        if resolvidos:
            self._uow.commit()
        return resolvidos

    def resume_handoff(self, handoff_id: uuid.UUID, operador: str | None = None) -> Handoff:
        """Operador devolve à IA: retoma o agente no canal + marca `resolvido`."""
        atual = self._handoffs.get(handoff_id)
        if atual is None:
            raise NotFoundError("Handoff nao encontrado")
        if atual.remetente and self._control is not None:
            self._control.retomar_agente(atual.remetente)
        try:
            resolvido = self._handoffs.set_status(handoff_id, "resolvido", operador)
            self._uow.commit()
        except Exception:
            self._uow.rollback()
            raise
        assert resolvido is not None
        return resolvido


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
        """Resolve o titular, **executa a ação de domínio** (muta o estado) e dispara.

        A mutação (SPEC-010) roda aqui, no caso de uso do backend que tem repos + UoW:
        pagamento dá baixa na fatura; outage abre/encerra a interrupção. Determinístico,
        idempotente. O worker (SPEC-009) segue só notificando.
        """
        normalizado = Telefone(phone)
        titular = self._titulares.find_by_phone(normalizado.value)
        if titular is None:
            raise NotFoundError("Telefone nao identificado")
        self._executar_acao(titular, tipo, subtipo, dados)
        chave_dado = dados.get("fatura_id") or dados.get("mes") or dados.get("bairro") or ""
        evento = EventoCX(
            tipo=tipo, subtipo=subtipo, telefone=normalizado.value, nome=titular.nome,
            idempotency_key=f"{tipo}.{subtipo}.{normalizado.value}.{chave_dado}", dados=dados,
        )
        return self.disparar(evento)

    def _regiao_do_bairro(self, titular: Titular, bairro: str) -> tuple[str, str]:
        """Resolve (cidade, uf) do bairro a partir das UCs do titular; fallback 1ª UC."""
        primeira: UnidadeConsumidora | None = None
        for c in self._titulares.list_contratos(titular.id):
            uc = c.unidade
            primeira = primeira or uc
            if uc.bairro and uc.bairro.casefold() == bairro.casefold():
                return uc.cidade, uc.uf
        return (primeira.cidade, primeira.uf) if primeira else ("", "")

    def _executar_acao(
        self, titular: Titular, tipo: str, subtipo: str, dados: dict[str, Any]
    ) -> None:
        """Muta o estado de domínio conforme o evento e faz commit (idempotente)."""
        now = self._clock()
        if (tipo, subtipo) == ("pagamento", "confirmado"):
            fid = dados.get("fatura_id")
            if fid:
                fatura = self._faturas.marcar_paga(
                    uuid.UUID(str(fid)), f"pagamento.confirmado.{fid}", now
                )
                if fatura is not None:
                    dados.setdefault("mes", fatura.mes_referencia)
                    dados.setdefault("valor", fatura.valor.formatado())
        elif (tipo, subtipo) == ("outage", "aberta"):
            bairro = dados.get("bairro")
            if bairro:
                cidade, uf = self._regiao_do_bairro(titular, bairro)
                self._interrupcoes.abrir(
                    bairro, cidade, uf, dados.get("causa"),
                    _parse_dt(dados.get("previsao")), now,
                )
        elif (tipo, subtipo) == ("outage", "encerrada"):
            bairro = dados.get("bairro")
            if bairro:
                cidade, uf = self._regiao_do_bairro(titular, bairro)
                self._interrupcoes.encerrar(bairro, cidade, uf, now)
        else:
            return
        try:
            self._uow.commit()
        except Exception:
            self._uow.rollback()
            raise

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
                prev = inter.previsao_retorno if inter else None
                # Lista o bairro mesmo sem interrupção (status "normal") p/ dirigir o
                # toggle do console: abrir quando normal, encerrar quando ativa (SPEC-010).
                outages.append({
                    "bairro": uc.bairro,
                    "previsao": prev.isoformat() if prev else None,
                    "status": inter.status if inter else "normal",
                })
        return {
            "encontrado": True, "titular": titular.nome, "telefone": normalizado.value,
            "pagamentos": pagamentos, "outages": outages,
        }
