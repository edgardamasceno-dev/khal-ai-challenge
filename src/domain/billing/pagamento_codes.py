"""Códigos de pagamento da fatura: PIX (BR Code/EMV) e barras do boleto (SPEC-008).

Puro e determinístico. O PIX é um EMV estático fictício, porém estruturado e com
CRC16-CCITT válido. O boleto deriva os 44 dígitos do código de barras (ITF).
"""

from __future__ import annotations


def _crc16(payload: str) -> str:
    """CRC16-CCITT (poly 0x1021, init 0xFFFF) — padrão do BR Code do PIX."""
    crc = 0xFFFF
    for ch in payload.encode():
        crc ^= ch << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def _tlv(tag: str, value: str) -> str:
    return f"{tag}{len(value):02d}{value}"


def pix_emv(chave: str, nome: str, cidade: str, valor: float, txid: str) -> str:
    """Monta um BR Code (EMV) estático de PIX com CRC16. Fictício mas válido em forma."""
    mai = _tlv("26", _tlv("00", "BR.GOV.BCB.PIX") + _tlv("01", chave))
    payload = (
        _tlv("00", "01") + _tlv("01", "11") + mai + _tlv("52", "0000")
        + _tlv("53", "986") + _tlv("54", f"{valor:.2f}") + _tlv("58", "BR")
        + _tlv("59", nome[:25]) + _tlv("60", cidade[:15])
        + _tlv("62", _tlv("05", txid[:25])) + "6304"
    )
    return payload + _crc16(payload)


def boleto_barcode_digits(linha_digitavel: str | None) -> str:
    """44 dígitos do código de barras (ITF) a partir da linha digitável."""
    digits = "".join(c for c in (linha_digitavel or "") if c.isdigit())
    return digits[:44].ljust(44, "0")
