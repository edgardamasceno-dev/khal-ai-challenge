"""Templates canônicos das notificações proativas (SPEC-009).

Determinístico: mesma entrada -> mesma mensagem. **Sem LLM** (ADR-0005).
"""

from __future__ import annotations

import datetime as dt

from src.domain.notifications.entities import EventoCX

_BRT = dt.timezone(dt.timedelta(hours=-3))  # horário de Brasília (sem DST desde 2019)


def _previsao_amigavel(valor: str | None) -> str | None:
    """ISO -> 'hoje às 22h57' / 'amanhã às 09h00' / '31/05 às 22h57' (BRT).

    Se não for um datetime ISO (ex.: 'hoje as 21h'), devolve o texto como veio.
    """
    if not valor:
        return None
    try:
        quando = dt.datetime.fromisoformat(valor).astimezone(_BRT)
    except (ValueError, TypeError):
        return valor
    agora = dt.datetime.now(_BRT)
    hora = quando.strftime("%Hh%M")
    delta_dias = (quando.date() - agora.date()).days
    if delta_dias == 0:
        return f"hoje às {hora}"
    if delta_dias == 1:
        return f"amanhã às {hora}"
    return f"{quando.strftime('%d/%m')} às {hora}"


def render_notificacao(evento: EventoCX) -> str:
    d = evento.dados
    nome = evento.nome.split()[0] if evento.nome else "cliente"
    if evento.tipo == "pagamento" and evento.subtipo == "confirmado":
        return (
            f"Oi, {nome}! ✅ Confirmamos o pagamento da sua fatura de {d.get('mes', '—')} "
            f"no valor de {d.get('valor', '—')}. Obrigado! 🙌"
        )
    if evento.tipo == "pagamento" and evento.subtipo == "lembrete":
        # R-16 / SPEC-026: lembrete proativo de vencimento. D-0 (vence hoje) tem um tom
        # mais urgente que D-3 (faltam 3 dias). Determinístico, sem LLM.
        dias = d.get("dias_para_vencer")
        if dias == 0:
            prazo = "*vence hoje*"
        else:
            prazo = f"vence em {dias} dias" if isinstance(dias, int) else "está perto de vencer"
        return (
            f"Oi, {nome}! 💡 Passando para lembrar: sua fatura de {d.get('mes', '—')} "
            f"no valor de {d.get('valor', '—')} {prazo} (vencimento em "
            f"{d.get('vencimento', '—')}). Pague pelo PIX ou boleto para evitar juros. "
            "Precisa da 2ª via? É só pedir por aqui. 🙂"
        )
    if evento.tipo == "pagamento" and evento.subtipo == "vencida":
        return (
            f"Oi, {nome}! ⚠️ Sua fatura de {d.get('mes', '—')} no valor de "
            f"{d.get('valor', '—')} está *vencida*. Para evitar juros e multa por atraso "
            "(e risco de suspensão do fornecimento), pague pelo PIX ou boleto o quanto "
            "antes. Precisa da 2ª via? É só pedir por aqui. 🙂"
        )
    if evento.tipo == "outage" and evento.subtipo == "aberta":
        prev = _previsao_amigavel(d.get("previsao"))
        prazo = f" Previsão de retorno: {prev}." if prev else ""
        return (
            f"{nome}, identificamos uma interrupção de energia no seu bairro "
            f"({d.get('bairro', '—')}). Nossa equipe já foi acionada.{prazo} "
            "Pode acompanhar por aqui."
        )
    if evento.tipo == "outage" and evento.subtipo == "encerrada":
        return (
            f"{nome}, boa notícia: o fornecimento no seu bairro ({d.get('bairro', '—')}) "
            "foi normalizado. ⚡ Se ainda estiver sem energia, é só me avisar."
        )
    raise ValueError(f"sem template para {evento.tipo}.{evento.subtipo}")  # pragma: no cover
