"""Normalização de telefone e variantes do nono dígito (SPEC-015).

O canal entrega identificadores em formatos variados (`<lid>@lid`,
`<msisdn>@s.whatsapp.net`, com `+`/espaços/hífen). O WhatsApp BR também resolve o
celular **sem** o nono dígito (`558193112159`), enquanto o cadastro pode estar **com**
(`5581993112159`). Funções puras e determinísticas — sem I/O.
"""

from __future__ import annotations

import re

_NAO_DIGITO = re.compile(r"\D")


def normalizar_msisdn(raw: str) -> str:
    """Tira sufixos de canal (`@lid`, `@s.whatsapp.net`, …) e símbolos; só dígitos."""
    base = raw.split("@", 1)[0]
    return _NAO_DIGITO.sub("", base)


def variantes_nono_digito(msisdn: str) -> list[str]:
    """Formas com e sem o 9 após o DDD, para um celular BR (`55` + DDD + local).

    - local de 8 dígitos -> adiciona a forma com 9 (`9` + local).
    - local de 9 dígitos começando com 9 -> adiciona a forma sem o 9.
    Não-celular / fora do padrão -> só o próprio número. O original vem sempre primeiro.
    """
    out = [msisdn]
    if not msisdn.startswith("55"):
        return out
    local = msisdn[4:]  # após '55' + DDD(2)
    if len(local) == 8:
        out.append(f"{msisdn[:4]}9{local}")
    elif len(local) == 9 and local[0] == "9":
        out.append(f"{msisdn[:4]}{local[1:]}")
    return out
