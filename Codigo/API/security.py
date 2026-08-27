import logging
import secrets
from fastapi import Security, HTTPException, status
from fastapi.security.api_key import APIKeyHeader

try:
    from API.config import settings
except (ImportError, AttributeError):
    from config import settings

logger = logging.getLogger("unihub_security")
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

def verify_api_key(api_key: str = Security(api_key_header)):
    """
    Verifica que la petición incluya el API Key correcto en la cabecera X-API-Key,
    utilizando comparación segura contra ataques de tiempo con registro de auditoría.
    """
    if not api_key:
        logger.warning("Intento de acceso a endpoint administrativo sin cabecera X-API-Key.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Falta la cabecera X-API-Key. Acceso denegado."
        )
        
    if not secrets.compare_digest(api_key, settings.ADMIN_API_KEY):
        logger.warning("Intento de acceso no autorizado con X-API-Key inválida.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API Key inválida. Acceso denegado."
        )
    return api_key
