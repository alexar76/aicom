"""
ai.market MCP Server Configuration
==================================

Configuration management for the MCP server.
Supports environment variables and .env files.
"""

import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

# Load .env file if present
load_dotenv()


@dataclass
class Config:
    """MCP Server configuration."""
    
    # API Configuration
    api_key: Optional[str] = None
    base_url: str = "https://ai-market-backend-production.up.railway.app/api/v1"
    sandbox_mode: bool = False
    
    # Timeouts
    request_timeout: int = 30
    
    @classmethod
    def from_env(cls) -> "Config":
        """Create config from environment variables."""
        return cls(
            api_key=os.getenv("AIMARKET_API_KEY"),
            base_url=os.getenv(
                "AIMARKET_BASE_URL",
                "https://ai-market-backend-production.up.railway.app/api/v1"
            ),
            sandbox_mode=os.getenv("AIMARKET_SANDBOX", "false").lower() == "true",
            request_timeout=int(os.getenv("AIMARKET_TIMEOUT", "30")),
        )
    
    @property
    def is_configured(self) -> bool:
        """Check if API key is configured."""
        return self.api_key is not None or self.sandbox_mode
    
    def get_headers(self) -> dict:
        """Get HTTP headers for API requests."""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "aimarket-mcp-server/0.1.0",
        }
        
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        
        if self.sandbox_mode:
            headers["X-Sandbox-Mode"] = "true"
        
        return headers


# Global config instance
config = Config.from_env()
