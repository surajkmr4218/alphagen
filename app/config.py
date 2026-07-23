from __future__ import annotations

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Push .env into os.environ so libs that read the environment DIRECTLY (langsmith/langchain
# tracing via LANGCHAIN_*) see the vars. pydantic Settings below only populates the Settings
# object, NOT os.environ — two separate mechanisms. Runs on first import of app.config.
load_dotenv()


def guardrail_cfg() -> dict:
    """Deterministic safety thresholds. Injected into validate() — never read globally."""
    return {
        "max_notional": 5.0,       
        "max_exposure": 50.0,      
        "min_conf": 0.60,        
        "allowlist": [            
            "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "PG", "SPY", 
        ],
        "max_per_day": 10,         
        "max_daily_loss": 5.0,     
    }

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # DB — psycopg driver string
    database_url: str = "postgresql+psycopg://app:app@localhost:5432/alphagen"

    # External services  
    gemini_api_key: str = ""
    fmp_api_key: str = ""

    # SEC REQUIRES a descriptive User-Agent with contact info or it 403s you.
    sec_user_agent: str = "AlphaGen your-name your@email.com"

    # Ttoken encryption and clerk auth — defaults keep boot working.
    fernet_key: str = ""
    clerk_jwks_url: str = ""

    # Robinhood Agentic account (agentic_allowed=true) orders place against.
    robinhood_account_number: str = ""

    # Non-owner (public) users read this tenant's rows on the dashboard endpoints.
    demo_user_id: str = "demo"

    # Comma-separated browser origins allowed by CORS. Local Vite dev by default.
    allowed_origins: str = "http://localhost:5173"


settings = Settings()