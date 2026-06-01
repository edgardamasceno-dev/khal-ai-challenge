"""Hash de invalidação de sessão do agente (R-05 — cold-start estrutural).

O Genie re-anexa o pane tmux de um chat via ``--resume`` (``findLatestByMetadata``),
o que torna o cold-start um custo pago **uma vez por chat na vida** — desde que o
``GENIE_PGDATA`` sobreviva ao ``--force-recreate`` (agora em volume nomeado, ver
``sandbox/compose.sandbox.yml``). Mas re-anexar tem um risco: reusar uma sessão
cujo **prompt/tool-set mudou** (persona editada, allowlist nova) faz o agente
responder com instruções obsoletas.

A mitigação é um *fingerprint* determinístico do que define o comportamento do
agente — persona (``AGENTS.md``) + frontmatter (tool-scoping) + catálogo de tools
na ordem canônica. Quando o hash muda, a sessão antiga deve ser invalidada
(``clear-session``/``delete from genie_bridge_sessions``) antes de re-anexar, em
vez de retomar um pane com prompt velho. O cálculo é **puro e testável** aqui; o
disparo (comparar com o hash gravado e invalidar) é CONFIG do sandbox e validação
ao vivo.

Funções puras, sem I/O: o chamador lê os arquivos/lista de tools e passa o
conteúdo. Determinístico e estável entre execuções (mesma entrada → mesmo hash),
que é o pré-requisito para usá-lo como chave de invalidação.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

#: Comprimento do hash curto exposto para logs/metadata da sessão. SHA-256 hex
#: tem 64 chars; 16 são suficientes para colisão desprezível neste uso (poucas
#: variações de prompt na vida do sandbox) e cabem em metadata/log.
_SHORT_LEN = 16


def session_fingerprint(
    *,
    agents_md: str,
    frontmatter: str,
    tool_names: Iterable[str],
) -> str:
    """Hash hex curto e determinístico do contrato comportamental do agente.

    Combina, em ordem fixa e com separadores explícitos (evita ambiguidade de
    concatenação), as três fontes que mudam o comportamento do agente entre
    deploys:

    - ``agents_md``: a persona (corpo do ``AGENTS.md`` da entrega);
    - ``frontmatter``: o tool-scoping/permissões (``*.frontmatter.yaml``);
    - ``tool_names``: o catálogo de tools MCP na ORDEM canônica (``allowlist``).

    A ordem das ``tool_names`` é significativa de propósito: reordenar o catálogo
    invalida o cache de prompt (R-07), logo *deve* invalidar a sessão também. Por
    isso NÃO ordenamos a coleção aqui — preservamos a ordem recebida.

    Idempotente: a mesma entrada produz sempre o mesmo hash; entradas diferentes
    em qualquer das três fontes produzem hashes diferentes.
    """
    h = hashlib.sha256()
    # Domínio de separação por campo: o byte 0x1f (unit separator) não aparece em
    # texto markdown/yaml normal, então ("a", "b") nunca colide com ("ab", "").
    h.update(b"agents_md\x1f")
    h.update(agents_md.encode("utf-8"))
    h.update(b"\x1efrontmatter\x1f")
    h.update(frontmatter.encode("utf-8"))
    h.update(b"\x1etools\x1f")
    for name in tool_names:
        h.update(name.encode("utf-8"))
        h.update(b"\x1f")
    return h.hexdigest()[:_SHORT_LEN]


def session_changed(previous: str | None, current: str) -> bool:
    """``True`` se a sessão deve ser invalidada (prompt/tool-set mudou).

    Convenção de borda: ``previous is None`` (nenhum hash gravado ainda, ex.:
    primeiro boot do sandbox) NÃO conta como mudança — não há sessão anterior
    para invalidar, então o caminho normal de spawn segue. Só retorna ``True``
    quando havia um hash anterior e ele diverge do atual.
    """
    if previous is None:
        return False
    return previous != current
