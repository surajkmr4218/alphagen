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
        "max_notional": 5.0,      # FR5: per-trade position cap, USD (one order <= $5)
        "max_exposure": 50.0,     # FR5: total account exposure cap, USD (no margin)
        "min_conf": 0.60,         # confidence floor (SOFT — logs a warning, doesn't block)
        "allowlist": [            # only these tickers may ever trade (HARD)
            "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "PG", "SPY", 
        ],
        "max_per_day": 3,         # FR5: rate-limit / cooldown — trades opened per day (HARD)
        "max_daily_loss": 5.0,    # FR5: daily kill-switch — halt if today's PnL <= -$5 (HARD)
    }

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # DB — psycopg v3 driver string
    database_url: str = "postgresql+psycopg://app:app@localhost:5432/alphagen"

    # External services (most consumed in later weeks)
    gemini_api_key: str = ""
    fmp_api_key: str = ""

    # SEC REQUIRES a descriptive User-Agent with contact info, or it 403s you.
    sec_user_agent: str = "AlphaGen your-name your@email.com"

    # Set in Week 6 (token encryption) and Week 6 (Clerk auth) — defaults keep boot working.
    fernet_key: str = ""
    clerk_jwks_url: str = ""

    # Week 7: the live Robinhood Agentic account (agentic_allowed=true) orders place against.
    robinhood_account_number: str = ""

    # Week 7 dashboard: tenant key of the seeded demo account (scripts/seed_demo.py).
    # Non-owner (public) users read this tenant's rows on the dashboard endpoints.
    demo_user_id: str = "demo"


settings = Settings()