"""Configuration management"""

from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings"""
    
    # Application
    app_name: str = "MOJI AI Agent"
    app_version: str = "1.0.0"
    debug: bool = False
    
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    
    # Database
    database_url: str = Field(
        default="postgresql://user:pass@localhost/moji",
        env="DATABASE_URL"
    )
    redis_url: str = Field(
        default="redis://localhost:6379",
        env="REDIS_URL"
    )
    
    # LLM Configuration
    llm_provider: str = Field(default="openai", env="LLM_PROVIDER")
    llm_model: str = Field(default="gpt-3.5-turbo", env="LLM_MODEL")
    llm_api_base: Optional[str] = Field(default=None, env="LLM_API_BASE")
    llm_api_key: str = Field(default="", env="LLM_API_KEY")
    
    # Additional API Keys
    openai_api_key: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    anthropic_api_key: Optional[str] = Field(default=None, env="ANTHROPIC_API_KEY")
    
    # Local Model URLs
    deepseek_local_url: Optional[str] = Field(default="http://localhost:11434/v1", env="DEEPSEEK_LOCAL_URL")
    exaone_local_url: Optional[str] = Field(default="http://localhost:11435/v1", env="EXAONE_LOCAL_URL")
    
    
    # Security
    secret_key: str = Field(
        default="your-secret-key-here-change-in-production",
        env="SECRET_KEY"
    )
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24
    
    # CORS
    cors_origins: list[str] = ["*"]
    
    # Rate Limiting
    rate_limit_requests: int = 100
    rate_limit_period: int = 3600  # 1 hour
    
    # Monday.com Configuration
    monday_api_key: Optional[str] = Field(default=None, env="MONDAY_API_KEY")
    monday_workspace_id: Optional[str] = Field(default=None, env="MONDAY_WORKSPACE_ID")
    monday_default_board_id: Optional[str] = Field(default=None, env="MONDAY_DEFAULT_BOARD_ID")
    
    # MCP Configuration
    mcp_monday_enabled: bool = Field(default=False, env="MCP_MONDAY_ENABLED")
    mcp_monday_server_url: str = Field(default="localhost:3001", env="MCP_MONDAY_SERVER_URL")
    
    # MCP System Configuration
    mcp_enabled: bool = Field(default=True, env="MCP_ENABLED")
    mcp_config_path: Optional[str] = Field(default=None, env="MCP_CONFIG_PATH")
    mcp_auto_discovery: bool = Field(default=True, env="MCP_AUTO_DISCOVERY")
    mcp_cache_ttl: int = Field(default=300, env="MCP_CACHE_TTL")  # 5분
    mcp_max_servers: int = Field(default=10, env="MCP_MAX_SERVERS")
    mcp_health_check_interval: int = Field(default=60, env="MCP_HEALTH_CHECK_INTERVAL")  # 1분
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Create settings instance
settings = Settings()