"""
Central configuration management for Project Latency Looter.
Uses Pydantic for runtime type validation and environment variable parsing.
"""

import os
from pathlib import Path
from typing import Dict, List, Optional
from pydantic import BaseSettings, Field, validator
from pydantic.types import SecretStr
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class BaseSettings(BaseSettings):
    """Base configuration settings with validation."""
    
    # Environment
    ENVIRONMENT: str = Field(default="development", env="ENVIRONMENT")
    DEBUG: bool = Field(default=False, env="DEBUG")
    
    # Firebase Configuration
    FIREBASE_PROJECT_ID: str = Field(..., env="FIREBASE_PROJECT_ID")
    FIREBASE_CREDENTIALS_PATH: Path = Field(..., env="FIREBASE_CREDENTIALS_PATH")
    
    @validator('FIREBASE_CREDENTIALS_PATH')
    def validate_firebase_credentials(cls, v: Path) -> Path:
        if not v.exists():
            raise FileNotFoundError(f"Firebase credentials not found at: {v}")
        return v
    
    # Blockchain RPC Endpoints (Private nodes required for latency)
    BASE_RPC_WS_URL: str = Field(..., env="BASE_RPC_WS_URL")
    BASE_RPC_HTTP_URL: str = Field(..., env="BASE_RPC_HTTP_URL")
    FLASHBOTS_PROTECT_RPC: str = Field(..., env="FLASHBOTS_PROTECT_RPC")
    
    # Wallet Configuration
    PRIVATE_KEY: SecretStr = Field(..., env="PRIVATE_KEY")
    WALLET_ADDRESS: str = Field(..., env="WALLET_ADDRESS")
    
    @validator('WALLET_ADDRESS')
    def validate_address_format(cls, v: str) -> str:
        if not v.startswith('0x') or len(v) != 42:
            raise ValueError(f"Invalid Ethereum address format: {v}")
        return v.lower()
    
    # Trading Parameters
    MAX_TRADE_SIZE_ETH: float = Field(default=0.1, env="MAX_TRADE_SIZE_ETH")
    MIN_PROFIT_THRESHOLD_WEI: int = Field(default=1000000, env="MIN_PROFIT_THRESHOLD_WEI")  # 0.000001 ETH
    MAX_SLIPPAGE_BPS: int = Field(default=50, env="MAX_SLIPPAGE_BPS")  # 0.5%
    
    # Asset Filters
    MAX_ASSET_PRICE_USD: float = Field(default=1.0, env="MAX_ASSET_PRICE_USD")
    MIN_LIQUIDITY_USD: float = Field(default=10000, env="MIN_LIQUIDITY_USD")
    EXCLUDED_TOKENS: List[str] = Field(default=[], env="EXCLUDED_TOKENS")
    
    # Performance & Resilience
    BLOCK_CONFIRMATION_DEPTH: int = Field(default=6, env="BLOCK_CONFIRMATION_DEPTH")
    HEALTH_CHECK_INTERVAL: int = Field(default=30, env="HEALTH_CHECK_INTERVAL")
    CIRCUIT_BREAKER_THRESHOLD: int = Field(default=5, env="CIRCUIT_BREAKER_THRESHOLD")
    
    # Logging
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")
    LOG_FILE_PATH: Path = Field(default=Path("logs/curiosity.log"), env="LOG_FILE_PATH")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        validate_assignment = True


class DevelopmentSettings(BaseSettings):
    """Development-specific overrides."""
    DEBUG: bool = True
    LOG_LEVEL: str = "DEBUG"
    MAX_TRADE_SIZE_ETH: float = 0.01  # Smaller trades in dev


class ProductionSettings(BaseSettings):
    """Production-specific overrides."""
    DEBUG: bool = False
    LOG_LEVEL: str = "WARNING"
    HEALTH_CHECK_INTERVAL: int = 10  # More frequent checks in prod


def get_settings() -> BaseSettings:
    """Factory function to return appropriate settings based on environment."""
    env = os.getenv("ENVIRONMENT", "development").lower()
    
    if env == "production":
        return ProductionSettings()
    elif env == "development":
        return DevelopmentSettings()
    else:
        return BaseSettings()


# Global settings instance
settings = get_settings()


# Firebase Firestore collection names (constants, not config)
class FirestoreCollections:
    """Firestore collection names for consistent data organization."""
    SYSTEM_HEALTH = "system_health"
    PENDING_OPPORTUNITIES = "pending_opportunities"
    EXECUTIONS = "executions"
    LIQUIDITY_POSITIONS = "liquidity_positions"
    PROFIT_LEDGER = "profit_ledger"
    MARKET_DATA = "market_data"
    FAILED_TRANSACTIONS = "failed_transactions"
    

# DEX Contract Addresses (Base Network)
class ContractAddresses:
    """Hardcoded contract addresses for Base network."""
    UNISWAP_V3_FACTORY = "0x33128a8fC17869897dcE68Ed026d694621f6FDfD"
    AERODROME_V2_FACTORY = "0x420DD381b31aEf6683db6B902084cB0FFECe40Da"
    WRAPPED_ETH = "0x4200000000000000000000000000000000000006"
    
    # Chainlink Price Feeds (Base)
    CHAINLINK_ETH_USD = "0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70"
    CHAINLINK_BTC_USD = "0x4eD0b4720d3e9F8C2c8c5c5b5b5a5b5c5d5e5f5g"  # Placeholder
    
    @classmethod
    def get_dex_factories(cls) -> Dict[str, str]:
        return {
            "uniswap_v3": cls.UNISWAP_V3_FACTORY,
            "aerodrome_v2": cls.AERODROME_V2_FACTORY
        }