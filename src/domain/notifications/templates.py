"""Templates canônicos das notificações proativas (SPEC-009).

Determinístico: mesma entrada -> mesma mensagem. **Sem LLM** (ADR-0005).
"""

from __future__ import annotations

from src.domain.notifications.entities import EventoCX


def render_notificacao(evento: EventoCX) -> str:
    d = evento.dados
    nome = evento.nome.split()[0] if evento.nome else "cliente"
    if evento.tipo == "pagamento" and evento.subtipo == "confirmado":
        return (
            f"Oi, {nome}! ✅ Confirmamos o pagamento da sua fatura de {d.get('mes', '—')} "
            f"no valor de {d.get('valor', '—')}. Obrigado! 🙌"
        )
    if evento.tipo == "outage" and evento.subtipo == "aberta":
        prev = d.get("previsao")
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
