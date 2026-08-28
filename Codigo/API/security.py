import logging
import ipaddress
import secrets
import threading
import time
from collections import defaultdict, deque
from fastapi import Request, Security, HTTPException, status
from fastapi.security.api_key import APIKeyHeader

try:
    from API.config import settings
except (ImportError, AttributeError):
    from config import settings

logger = logging.getLogger("unihub_security")
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

_RATE_LIMIT_WINDOW_SECONDS = 60
_RATE_LIMIT_MAX_FAILURES = 10
_failed_attempts: dict[str, deque[float]] = defaultdict(deque)
_rate_limit_lock = threading.Lock()


def _client_identifier(request: Request) -> str:
    """Obtiene una IP limitable sin aceptar cabeceras falsificables por defecto."""
    if settings.TRUST_PROXY_HEADERS and _is_trusted_proxy(request):
        proxied_ip = request.headers.get("X-Real-IP", "").strip()
        if proxied_ip:
            return proxied_ip
    return request.client.host if request.client else "unknown"


def _is_trusted_proxy(request: Request) -> bool:
    """Acepta cabeceras de reenvío sólo desde redes de proxy explícitas."""
    if not request.client or not settings.TRUSTED_PROXY_NETWORKS.strip():
        return False
    try:
        client_ip = ipaddress.ip_address(request.client.host)
        networks = [
            ipaddress.ip_network(value.strip(), strict=False)
            for value in settings.TRUSTED_PROXY_NETWORKS.split(",")
            if value.strip()
        ]
        return any(client_ip in network for network in networks)
    except ValueError:
        logger.error("TRUSTED_PROXY_NETWORKS contiene una red inválida; se ignorarán cabeceras reenviadas.")
        return False


def _is_rate_limited(client_id: str, now: float) -> bool:
    with _rate_limit_lock:
        attempts = _failed_attempts[client_id]
        while attempts and now - attempts[0] >= _RATE_LIMIT_WINDOW_SECONDS:
            attempts.popleft()
        return len(attempts) >= _RATE_LIMIT_MAX_FAILURES


def _record_failed_attempt(client_id: str, now: float) -> int:
    with _rate_limit_lock:
        attempts = _failed_attempts[client_id]
        while attempts and now - attempts[0] >= _RATE_LIMIT_WINDOW_SECONDS:
            attempts.popleft()
        attempts.append(now)
        return max(1, int(_RATE_LIMIT_WINDOW_SECONDS - (now - attempts[0])))


def _clear_failed_attempts(client_id: str) -> None:
    with _rate_limit_lock:
        _failed_attempts.pop(client_id, None)


def verify_api_key(request: Request, api_key: str = Security(api_key_header)):
    """
    Verifica que la petición incluya el API Key correcto en la cabecera X-API-Key,
    utilizando comparación segura contra ataques de tiempo con registro de auditoría.
    """
    client_id = _client_identifier(request)
    now = time.monotonic()
    if _is_rate_limited(client_id, now):
        logger.warning("Se ha aplicado rate limiting al cliente %s por exceso de intentos inválidos.", client_id)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados intentos de autenticación. Espere un minuto.",
            headers={"Retry-After": str(_RATE_LIMIT_WINDOW_SECONDS)},
        )

    if not api_key:
        logger.warning("Intento de acceso a endpoint administrativo sin cabecera X-API-Key.")
        retry_after = _record_failed_attempt(client_id, now)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Falta la cabecera X-API-Key. Acceso denegado.",
            headers={"Retry-After": str(retry_after)}
        )

    valid = any(secrets.compare_digest(api_key, candidate) for candidate in settings.ADMIN_API_KEYS)
    if not valid:
        logger.warning("Intento de acceso no autorizado con X-API-Key inválida.")
        retry_after = _record_failed_attempt(client_id, now)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API Key inválida. Acceso denegado.",
            headers={"Retry-After": str(retry_after)}
        )
    _clear_failed_attempts(client_id)
    return api_key
