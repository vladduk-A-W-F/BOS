"""Caddy configuration for one BoS installation; no subprocess or writes."""
import json
from pathlib import Path
from urllib.parse import urlsplit


def _quoted(value):
    value = str(value)
    if any(ord(c) < 32 for c in value) or '\x7f' in value:
        raise ValueError('Некоректний параметр проксі BoS.')
    return json.dumps(value, ensure_ascii=False)


def render(*, origin, http_port, upstream_port, certificate, private_key, static_root):
    from boss_project.server_config import _origin_and_hosts, _absolute
    parsed = urlsplit(origin)
    _origin_and_hosts(origin, [parsed.hostname])
    https_port = parsed.port or 443
    ports = (http_port, upstream_port, https_port)
    if any(type(p) is not int or not 1 <= p <= 65535 for p in ports) or len(set(ports)) != 3:
        raise ValueError('Порти HTTPS, HTTP і застосунку мають бути різними.')
    cert = _absolute(str(certificate), 'TLS certificate')
    key = _absolute(str(private_key), 'TLS private key')
    static = _absolute(str(static_root), 'STATIC_ROOT')
    if not cert.is_file() or not key.is_file() or not static.is_dir():
        raise ValueError('Потрібні наявні TLS-файли та зібрана статика.')
    # This Caddy filter removes nested request fields, but cannot remove its
    # fundamental msg/level/logger fields. lifecycle_server MUST normalize both
    # process streams through proxy_logging before any log reaches disk.
    filtered = '''format filter {
            wrap json
            fields {
                request delete
                resp_headers delete
                msg delete
                error delete
                err_trace delete
                stacktrace delete
            }
        }'''
    return f'''{{
    admin off
    auto_https off
    skip_install_trust
    persist_config off
    log default {{
        output stderr
        {filtered}
    }}
}}
http://:{http_port} {{
    bind 127.0.0.1
    @known host {parsed.hostname}
    redir @known {_quoted(origin + '{uri}')} 308
    respond 421
    log bos_http {{
        output stderr
        {filtered}
    }}
}}
https://:{https_port} {{
    bind 127.0.0.1
    tls {_quoted(cert)} {_quoted(key)}
    @wrong not host {parsed.hostname}
    @private path /media /media/*
    route {{
        respond @wrong 421
        respond @private 404
        request_body {{
            max_size 12MiB
        }}
        handle_path /static/* {{
            root * {_quoted(static)}
            file_server
        }}
        handle {{
            reverse_proxy 127.0.0.1:{upstream_port} {{
                header_up -Forwarded
                header_up -X-Forwarded-Host
                header_up -X-Forwarded-Port
                header_up -X-Forwarded-By
                header_up X-Forwarded-For {{remote_host}}
                header_up X-Forwarded-Proto {{scheme}}
                transport http {{
                    dial_timeout 5s
                    response_header_timeout 60s
                }}
            }}
        }}
    }}
    log bos_https {{
        output stderr
        {filtered}
    }}
}}
'''
