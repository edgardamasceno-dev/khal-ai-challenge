"""Mensagens deterministicas do ciclo de vida do chamado (SPEC-020).

Funcoes puras: dado titular + chamado, devolvem o texto, sem LLM e sem efeito
colateral. Travamos protocolo, primeiro nome, rotulo do tipo e SLA.
"""

from __future__ import annotations

import datetime as dt
import uuid

from src.domain.shared.value_objects import StatusChamado, TipoChamado
from src.domain.ticketing.entities import Chamado
from src.domain.ticketing.mensagens import (
    mensagem_chamado_aberto,
    mensagem_chamado_resolvido,
)

ANA_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


def _chamado(
    protocolo: str = "LDV20260531AB12",
    tipo: TipoChamado = TipoChamado.falta_energia,
    status: str = StatusChamado.aberto.value,
) -> Chamado:
    agora = dt.datetime(2026, 5, 31, 12, tzinfo=dt.UTC)
    return Chamado(
        id=uuid.uuid4(), protocolo=protocolo, titular_id=ANA_ID, uc_id=None,
        tipo=tipo, descricao=None, status=status, sla_horas=tipo.sla_horas,
        canal="whatsapp", aberto_em=agora, atualizado_em=agora,
    )


class TestMensagemChamadoAberto:
    def test_contem_protocolo_primeiro_nome_tipo_e_sla(self) -> None:
        chamado = _chamado(tipo=TipoChamado.religacao)  # SLA 24h, rotulo "religacao"
        texto = mensagem_chamado_aberto("Joana Pereira", chamado)
        assert chamado.protocolo in texto
        assert "Joana" in texto and "Pereira" not in texto  # so o primeiro nome
        assert "religação" in texto  # rotulo amigavel do tipo
        assert "24h" in texto  # SLA em horas (religacao)

    def test_reduz_nome_composto_ao_primeiro_nome(self) -> None:
        texto = mensagem_chamado_aberto("Maria das Dores Albuquerque", _chamado())
        assert "Maria" in texto
        assert "Dores" not in texto and "Albuquerque" not in texto

    def test_eh_deterministica(self) -> None:
        chamado = _chamado()
        assert mensagem_chamado_aberto("Ana Souza", chamado) == mensagem_chamado_aberto(
            "Ana Souza", chamado
        )

    def test_sla_e_tipo_variam_com_o_chamado(self) -> None:
        # titularidade tem SLA 72h e rotulo proprio: prova que nao e hardcoded.
        texto = mensagem_chamado_aberto("Carlos Lima", _chamado(tipo=TipoChamado.titularidade))
        assert "72h" in texto and "titularidade" in texto


class TestMensagemChamadoResolvido:
    def test_contem_protocolo_e_primeiro_nome(self) -> None:
        chamado = _chamado(status=StatusChamado.resolvido.value)
        texto = mensagem_chamado_resolvido("Joana Pereira", chamado)
        assert chamado.protocolo in texto
        assert "Joana" in texto and "Pereira" not in texto

    def test_indica_resolvido(self) -> None:
        texto = mensagem_chamado_resolvido("Ana Souza", _chamado())
        assert "resolvido" in texto.lower()

    def test_eh_deterministica(self) -> None:
        chamado = _chamado()
        assert mensagem_chamado_resolvido("Ana", chamado) == mensagem_chamado_resolvido(
            "Ana", chamado
        )
