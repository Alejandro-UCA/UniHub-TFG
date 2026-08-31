import os
from urllib.parse import quote_plus

class Settings:
    # Environment
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", os.getenv("ENV", "development")).lower()

    # API Configuration
    API_TITLE: str = "API RUCT - Universidades y Titulaciones de España"
    API_VERSION: str = "1.0.0"
    API_DESCRIPTION: str = (
        "API REST oficial para acceder a los datos recolectados sobre universidades públicas y privadas "
        "de España, sus titulaciones oficiales vigentes (Grados y Másteres) y sus planes de estudio extraídos del BOE."
    )
    
    # CORS Configuration
    # En producción debe declararse explícitamente. No usar '*' por defecto.
    CORS_ORIGINS: str = os.getenv(
        "CORS_ORIGINS",
        "" if os.getenv("ENVIRONMENT", os.getenv("ENV", "development")).lower() in ["production", "prod"]
        else "http://localhost:5173,http://localhost:3000"
    )

    @property
    def CORS_ORIGINS_LIST(self) -> list:
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    # Configuración de PostgreSQL
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "")
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: str = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "unihub_db")
    
    # Rol de Solo Lectura para Acceso Restringido de la API REST
    API_DB_USER: str = os.getenv("API_DB_USER", "unihub_api_user")
    API_DB_PASSWORD: str = os.getenv("API_DB_PASSWORD", "")

    # Clave de Administración para Operaciones CRUD y Sincronización ETL
    ADMIN_API_KEY: str = os.getenv(
        "ADMIN_API_KEY",
        "unihub_admin_secret_2026" if os.getenv("ENVIRONMENT", os.getenv("ENV", "development")).lower() not in ["production", "prod"] else ""
    )

    # El contenedor API no se publica directamente en producción: Nginx es el
    # único proxy de entrada y añade X-Real-IP. Mantenerlo desactivado por
    # defecto evita confiar en cabeceras que un cliente directo pueda falsificar.
    TRUST_PROXY_HEADERS: bool = os.getenv("TRUST_PROXY_HEADERS", "false").lower() in {"1", "true", "yes"}
    TRUSTED_PROXY_NETWORKS: str = os.getenv("TRUSTED_PROXY_NETWORKS", "")

    @property
    def ADMIN_API_KEYS(self) -> tuple[str, ...]:
        """Claves válidas durante una rotación controlada de credenciales."""
        configured = os.getenv("ADMIN_API_KEYS", "")
        values = [value.strip() for value in configured.split(",") if value.strip()]
        if self.ADMIN_API_KEY.strip() and self.ADMIN_API_KEY.strip() not in values:
            values.insert(0, self.ADMIN_API_KEY.strip())
        return tuple(values)

    # Parámetros del Pool de Conexiones SQLAlchemy
    DB_READONLY_POOL_SIZE: int = int(os.getenv("DB_READONLY_POOL_SIZE", "15"))
    DB_READONLY_MAX_OVERFLOW: int = int(os.getenv("DB_READONLY_MAX_OVERFLOW", "25"))
    DB_ADMIN_POOL_SIZE: int = int(os.getenv("DB_ADMIN_POOL_SIZE", "5"))
    DB_ADMIN_MAX_OVERFLOW: int = int(os.getenv("DB_ADMIN_MAX_OVERFLOW", "10"))
    DB_POOL_RECYCLE: int = int(os.getenv("DB_POOL_RECYCLE", "1800"))

    # Rutas de datos canónicas
    @property
    def CRAWLER_DATA_DIR(self) -> str:
        docker_path = "/app/Datos"
        if os.path.exists(docker_path):
            return docker_path
        # Fallback local relativo
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_dir, "Crawler", "Datos")

    @property
    def CHECKPOINT_PATH(self) -> str:
        return os.path.join(self.CRAWLER_DATA_DIR, "checkpoint.json")

    @property
    def DATABASE_URL(self) -> str:
        """Constructs PostgreSQL SQLAlchemy connection string.
        Credentials are URL-encoded to handle special characters (@, /, %, etc.).
        """
        user = quote_plus(self.POSTGRES_USER)
        password = quote_plus(self.POSTGRES_PASSWORD)
        return f"postgresql+psycopg2://{user}:{password}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}?client_encoding=utf8"

    @property
    def API_READONLY_DATABASE_URL(self) -> str:
        """Constructs Read-Only PostgreSQL connection string for API Service Role.
        Credentials are URL-encoded to handle special characters (@, /, %, etc.).
        """
        user = quote_plus(self.API_DB_USER)
        password = quote_plus(self.API_DB_PASSWORD)
        return f"postgresql+psycopg2://{user}:{password}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}?client_encoding=utf8"

    def validate_production_security(self):
        """Valida que no se utilicen credenciales ni configuraciones inseguras en entornos de producción."""
        if self.ENVIRONMENT in ["production", "prod"]:
            required_secrets = [
                (self.POSTGRES_PASSWORD, "POSTGRES_PASSWORD"),
                (self.API_DB_PASSWORD, "API_DB_PASSWORD"),
                (self.ADMIN_API_KEYS, "ADMIN_API_KEY o ADMIN_API_KEYS"),
            ]
            for current_val, var_name in required_secrets:
                if not current_val or (isinstance(current_val, str) and not current_val.strip()):
                    raise ValueError(f"ERROR CRÍTICO DE SEGURIDAD: La variable {var_name} es obligatoria en producción.")
            
            if not self.CORS_ORIGINS.strip() or self.CORS_ORIGINS.strip() == "*":
                raise ValueError("ERROR CRÍTICO DE SEGURIDAD: CORS_ORIGINS debe declarar dominios autorizados en producción.")

settings = Settings()
settings.validate_production_security()
