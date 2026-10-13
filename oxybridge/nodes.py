import json
from contextlib import closing
from urllib.parse import urljoin, urlsplit

import certifi
import httpx
import psycopg
import regex

from oxybridge.config import settings
from oxybridge.graph import TRIGGERS, NodeError, condition, lookup, resolve
from oxybridge.json_validation import errors as schema_errors
from oxybridge.security import connection_references, destination


def http_request(config, context, credential=None, connection_type=None, allowed_hosts=None):
    try:
        connection_references(config)
    except ValueError as error:
        raise NodeError(
            "NODE_CONFIG_INVALID",
            "Use an encrypted connection or runtime expression for HTTP authentication.",
        ) from error
    url = resolve(config["url"], context)
    if credential:
        initial = urlsplit(url)
        if initial.hostname not in (allowed_hosts or []):
            raise NodeError(
                "CREDENTIAL_SCOPE_DENIED",
                "This API credential is not approved for the request hostname.",
            )
        if settings().app_env in {"staging", "production"} and initial.scheme != "https":
            raise NodeError(
                "CREDENTIAL_TLS_REQUIRED",
                "Authenticated HTTP requests require HTTPS in production.",
            )
    headers = resolve(config.get("headers", {}), context)
    # Credentials are scoped to the initial host and never forwarded on a cross-host redirect.
    auth_headers = {}
    if credential:
        if connection_type == "bearer":
            auth_headers["Authorization"] = "Bearer " + credential["token"]
        elif connection_type == "api_key":
            auth_headers[credential.get("header", "X-API-Key")] = credential["token"]
        elif connection_type == "basic":
            import base64

            auth_headers["Authorization"] = (
                "Basic "
                + base64.b64encode(
                    f"{credential['username']}:{credential['password']}".encode()
                ).decode()
            )
    headers.update(auth_headers)
    headers["Idempotency-Key"] = context["run"]["id"] + ":" + context["run"]["node_id"]
    headers = {str(k): str(v) for k, v in headers.items()}
    for unsafe in (
        "host",
        "content-length",
        "transfer-encoding",
        "connection",
        "proxy-authorization",
    ):
        if any(k.lower() == unsafe for k in headers):
            raise NodeError(
                "NODE_CONFIG_INVALID", "Transport headers cannot be configured manually."
            )
    method = config.get("method", "GET")
    body = resolve(config.get("body"), context)
    query = resolve(config.get("query", {}), context)
    try:
        with httpx.Client(
            timeout=float(config.get("timeout", 30)), trust_env=False, follow_redirects=False
        ) as client:
            initial = urlsplit(url)
            original_origin = (
                initial.scheme,
                initial.hostname,
                initial.port or (443 if initial.scheme == "https" else 80),
            )
            for redirect in range(6):
                try:
                    host, ip, port = destination(url)
                except ValueError as error:
                    raise NodeError(
                        "SSRF_BLOCKED", "The HTTP destination is blocked or unavailable."
                    ) from error
                parsed = httpx.URL(url)
                pinned = parsed.copy_with(host=ip)
                host_header = host if port in (80, 443) else f"{host}:{port}"
                request_headers = dict(headers)
                if (parsed.scheme, host, port) != original_origin:
                    request_headers = {
                        k: v for k, v in request_headers.items() if k not in auth_headers
                    }
                request_headers["Host"] = host_header
                # Pinned IP URLs must not share a cookie jar across distinct original hosts.
                client.cookies.clear()
                request = client.build_request(
                    method,
                    pinned,
                    headers=request_headers,
                    params=parsed.params.merge(query),
                    json=body if method not in {"GET", "HEAD"} else None,
                )
                request.extensions["sni_hostname"] = host.encode()
                response = client.send(request, stream=True)
                with closing(response):
                    if response.is_redirect and config.get("follow_redirects", False):
                        if redirect == 5 or "location" not in response.headers:
                            raise NodeError(
                                "HTTP_REDIRECT_LIMIT", "The HTTP redirect limit was reached."
                            )
                        url = urljoin(url, response.headers["location"])
                        query = {}
                        if response.status_code == 303 or (
                            response.status_code in {301, 302} and method == "POST"
                        ):
                            method, body = "GET", None
                        continue
                    chunks, size = [], 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > settings().http_node_max_response_bytes:
                            raise NodeError(
                                "HTTP_RESPONSE_TOO_LARGE",
                                "The HTTP response exceeds the configured limit.",
                            )
                        chunks.append(chunk)
                    if response.status_code not in config.get(
                        "expected_status", list(range(200, 300))
                    ):
                        raise NodeError(
                            "HTTP_UNEXPECTED_STATUS",
                            f"HTTP Request returned status {response.status_code}.",
                            response.status_code == 429 or response.status_code >= 500,
                            response.status_code,
                        )
                    raw = b"".join(chunks)
                    try:
                        result = json.loads(raw)
                    except (ValueError, UnicodeDecodeError):
                        result = raw.decode(errors="replace")
                    output = {
                        "status": response.status_code,
                        "body": result,
                        "headers": dict(response.headers),
                    }
                    if config.get("extract"):
                        output = lookup({"vars": output}, "vars." + config["extract"])
                    return output
    except httpx.TimeoutException as error:
        raise NodeError("HTTP_TIMEOUT", "The HTTP request exceeded its timeout.", True) from error
    except httpx.RequestError as error:
        raise NodeError(
            "HTTP_CONNECTION_ERROR", "The HTTP connection could not complete.", True
        ) from error
    except NodeError:
        raise
    except (KeyError, ValueError, TypeError) as error:
        raise NodeError(
            "NODE_CONFIG_INVALID", "The HTTP request configuration is invalid."
        ) from error


def postgres_query(config, context, credential, allow_writes=False):
    try:
        host = credential["host"]
        _, pinned, _ = destination(f"http://{host}:{int(credential.get('port', 5432))}")
        write = config.get("mode", "read") == "write"
        if write and not allow_writes:
            raise NodeError("FORBIDDEN", "This connection does not allow writes.")
        parameters = resolve(config.get("parameters", {}), context)
        sslmode = credential.get("sslmode", "verify-full")
        with psycopg.connect(
            host=host,
            hostaddr=pinned,
            port=int(credential.get("port", 5432)),
            dbname=credential["database"],
            user=credential["username"],
            password=credential["password"],
            connect_timeout=5,
            sslmode=sslmode,
            **({"sslrootcert": certifi.where()} if sslmode in {"verify-full", "verify-ca"} else {}),
        ) as connection:
            from psycopg.types.json import JsonbDumper

            connection.adapters.register_dumper(dict, JsonbDumper)
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL statement_timeout = '30000ms'")
                    if not write:
                        cursor.execute("SET TRANSACTION READ ONLY")
                    cursor.execute(config["query"], parameters)
                    if cursor.description:
                        columns = [col.name for col in cursor.description]
                        rows = cursor.fetchmany(1001)
                        if len(rows) > 1000:
                            raise NodeError(
                                "DATABASE_RESULT_TOO_LARGE",
                                "The query returned more than 1000 rows. Add a LIMIT.",
                            )
                        return {
                            "rows": json.loads(
                                json.dumps([dict(zip(columns, row)) for row in rows], default=str)
                            ),
                            "row_count": len(rows),
                        }
                    return {"row_count": cursor.rowcount}
    except psycopg.errors.QueryCanceled as error:
        raise NodeError(
            "DATABASE_TIMEOUT", "The database query exceeded its timeout.", True
        ) from error
    except psycopg.Error as error:
        raise NodeError(
            "DATABASE_QUERY_FAILED",
            "The parameterized database query failed. Check the connection and query.",
            isinstance(error, psycopg.OperationalError),
        ) from error
    except (KeyError, ValueError, TypeError) as error:
        raise NodeError(
            "NODE_CONFIG_INVALID",
            "The database connection is invalid or its destination is blocked.",
        ) from error


def execute_node(node, context, credential=None, connection=None):
    kind, config = node["type"], node.get("config", {})
    if kind in TRIGGERS:
        return context["trigger"]["body"], "success"
    if kind in {"transform", "set"}:
        return resolve(config["mapping"], context), "success"
    if kind == "condition":
        result = condition(config, context)
        return {"result": result}, "true" if result else "false"
    if kind == "validate":
        value = resolve(config.get("input", "{{ trigger.body }}"), context)
        try:
            errors = schema_errors(config["schema"], value)
        except (TimeoutError, RecursionError, regex.error) as error:
            raise NodeError(
                "VALIDATION_LIMIT", "JSON Schema validation exceeded its complexity limit."
            ) from error
        except ValueError as error:
            raise NodeError(
                "NODE_CONFIG_INVALID", "JSON Schema configuration is unsupported or invalid."
            ) from error
        messages = [
            f"{'.'.join(map(str, e.path)) or 'body'}: {e.validator} validation failed"
            for e in errors[:20]
        ]
        return {
            "valid": not errors,
            "data": value,
            "errors": messages,
        }, "invalid" if errors else "valid"
    if kind in {"http", "callback"}:
        if kind == "callback":
            config = {"method": "POST", **config}
        return http_request(
            config,
            context,
            credential,
            connection.type if connection else None,
            connection.config.get("allowed_hosts", []) if connection else None,
        ), "success"
    if kind == "postgres":
        return postgres_query(
            config, context, credential, connection.allow_writes if connection else False
        ), "success"
    if kind == "delay":
        return {"delayed_seconds": config["seconds"]}, "success"
    raise NodeError("NODE_CONFIG_INVALID", "This node type is unsupported.")
