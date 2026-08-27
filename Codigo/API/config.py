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
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "*")

    @property
    def CORS_ORIGINS_LIST(self) -> list:
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    # Configuración de PostgreSQL
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "" if os.getenv("ENVIRONMENT", os.getenv("ENV", "development")).lower() in ["production", "prod"] else "admin")
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: str = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "unihub_db")
    
    # Rol de Solo Lectura para Acceso Restringido de la API REST
    API_DB_USER: str = os.getenv("API_DB_USER", "unihub_api_user")
    API_DB_PASSWORD: str = os.getenv("API_DB_PASSWORD", "" if os.getenv("ENVIRONMENT", os.getenv("ENV", "development")).lower() in ["production", "prod"] else "unihub_api_password_sec2026")

    # Clave de Administración para Operaciones CRUD y Sincronización ETL
    ADMIN_API_KEY: str = os.getenv("ADMIN_API_KEY", "" if os.getenv("ENVIRONMENT", os.getenv("ENV", "development")).lower() in ["production", "prod"] else "unihub_super_secret_admin_key_2026")

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
            insecure_defaults = [
                (self.POSTGRES_PASSWORD, "admin", "POSTGRES_PASSWORD"),
                (self.API_DB_PASSWORD, "unihub_api_password_sec2026", "API_DB_PASSWORD"),
                (self.ADMIN_API_KEY, "unihub_super_secret_admin_key_2026", "ADMIN_API_KEY")
            ]
            for current_val, default_val, var_name in insecure_defaults:
                if not current_val or current_val == default_val:
                    raise ValueError(f"ERROR CRÍTICO DE SEGURIDAD: La variable {var_name} no puede estar vacía ni usar el valor por defecto en producción. Configure una clave segura.")
            
            if self.CORS_ORIGINS.strip() == "*":
                raise ValueError("ERROR CRÍTICO DE SEGURIDAD: CORS_ORIGINS no puede ser '*' en entorno de producción. Especifique los dominios autorizados.")

settings = Settings()
settings.validate_production_security()
