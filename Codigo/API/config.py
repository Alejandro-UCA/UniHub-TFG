import os

class Settings:
    # API Configuration
    API_TITLE: str = "API RUCT - Universidades y Titulaciones de España"
    API_VERSION: str = "1.0.0"
    API_DESCRIPTION: str = (
        "API REST oficial para acceder a los datos recolectados sobre universidades públicas y privadas "
        "de España, sus titulaciones oficiales vigentes (Grados y Másteres) y sus planes de estudio extraídos del BOE."
    )
    
    # PostgreSQL Configuration
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "admin")  # Admin password provided by user
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: str = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "ruct_db")
    
    # API Reader Role for Restricted Access
    API_DB_USER: str = os.getenv("API_DB_USER", "ruct_api_user")
    API_DB_PASSWORD: str = os.getenv("API_DB_PASSWORD", "ruct_api_password_sec2026")

    @property
    def DATABASE_URL(self) -> str:
        """Constructs PostgreSQL SQLAlchemy connection string."""
        return f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def API_READONLY_DATABASE_URL(self) -> str:
        """Constructs Read-Only PostgreSQL connection string for API Service Role."""
        return f"postgresql+psycopg2://{self.API_DB_USER}:{self.API_DB_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

settings = Settings()
