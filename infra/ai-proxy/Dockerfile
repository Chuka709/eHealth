# Egress for the AI worker (BETA B10, Phase 8.3): a forward proxy that allows HTTPS CONNECT to
# api.anthropic.com only. tinyproxy is GPL-2.0 (not AGPL/SSPL - CLAUDE.md rule 11).
FROM alpine:3.21
RUN apk add --no-cache tinyproxy
COPY tinyproxy.conf filter /etc/tinyproxy/
USER tinyproxy
EXPOSE 8888
CMD ["tinyproxy", "-d", "-c", "/etc/tinyproxy/tinyproxy.conf"]
