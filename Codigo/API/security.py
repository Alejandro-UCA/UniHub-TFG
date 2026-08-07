from fastapi import Security, HTTPException, status
from fastapi.security.api_key import APIKeyHeader
from config import settings

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

def verify_api_key(api_key: str = Security(api_key_header)):
    """
    Verifica que la petición incluya el API Key correcto en la cabecera X-API-Key.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Falta la cabecera X-API-Key. Acceso denegado."
        )
        
    if api_key != settings.ADMIN_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API Key inválida. Acceso denegado."
        )
    return api_key
