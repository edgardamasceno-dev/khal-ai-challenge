# Egress-proxy com allowlist (so Anthropic + WhatsApp). Unica rota de saida do
# sandbox para a internet (ADR-0006: egress allowlist).
FROM alpine:3.20
RUN apk add --no-cache tinyproxy
COPY tinyproxy.conf /etc/tinyproxy/tinyproxy.conf
COPY filter /etc/tinyproxy/filter
EXPOSE 8888
CMD ["tinyproxy", "-d", "-c", "/etc/tinyproxy/tinyproxy.conf"]
