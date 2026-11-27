# The one way from the backend network to OpenBao (docs/SERVER_INSTALL_PLAN.md §3, production
# overlay): a plain TCP relay to OPENBAO_UPSTREAM (ip:port). TLS stays end to end - the app
# reaches it under OpenBao's own hostname (a network alias), so the certificate still matches -
# and the workers that read untrusted files keep no other route out. socat is GPL-2.0 (not
# AGPL/SSPL - CLAUDE.md rule 11).
FROM alpine:3.21
RUN apk add --no-cache socat
USER nobody
EXPOSE 8200
CMD ["sh", "-c", "exec socat TCP-LISTEN:8200,fork,reuseaddr,max-children=64 TCP:${OPENBAO_UPSTREAM:?},connect-timeout=5"]
