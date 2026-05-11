"""
App Configuration
=================
Manages application configuration with hot-reload support.
Loads from config.yaml and data/config/*.yaml files.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


class AppConfig:
    """
    Application configuration manager.
    
    Features:
    - Load from YAML files
    - Hot-reload support
    - Theme management
    - Provider configuration
    """

    def __init__(self, config_path: str = "/app/config.yaml"):
        self.config_path = config_path
        self._config: dict = {}
        self._last_load: float = 0
        self._load_config()

    def _load_config(self):
        """Load configuration from file."""
        try:
            with open(self.config_path, "r") as f:
                self._config = yaml.safe_load(f)
            self._last_load = time.time()
            logger.info("Configuration loaded successfully")
        except FileNotFoundError:
            logger.warning(f"Config file not found: {self.config_path}")
            self._config = {}
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            self._config = {}

    def reload(self):
        """Hot-reload configuration."""
        self._load_config()
        logger.info("Configuration hot-reloaded")

    def get(self, key: str, default=None):
        """Get a config value by dot-notation key."""
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default

    def get_theme(self) -> dict:
        """Get the active storefront theme."""
        active_theme = self.get("storefront.active_theme", "cyberpunk")
        themes = self.get("storefront.themes", {})
        return themes.get(active_theme, themes.get("cyberpunk", {}))

    def set_theme(self, theme_name: str) -> bool:
        """Set the active theme."""
        themes = self.get("storefront.themes", {})
        if theme_name in themes:
            # Update config in memory
            if "storefront" not in self._config:
                self._config["storefront"] = {}
            self._config["storefront"]["active_theme"] = theme_name
            self._save_config()
            return True
        return False

    def update_theme_colors(self, theme_name: str, colors: dict) -> bool:
        """Update colors for a theme."""
        themes = self.get("storefront.themes", {})
        if theme_name in themes:
            themes[theme_name].update(colors)
            self._save_config()
            return True
        return False

    def _save_config(self):
        """Save configuration back to file."""
        try:
            # Preserve original file structure with comments by re-writing
            with open(self.config_path, "w") as f:
                yaml.dump(self._config, f, default_flow_style=False, allow_unicode=True)
            logger.info("Configuration saved to file")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

    def set(self, key: str, value):
        """Set a config value by dot-notation key and persist to file."""
        keys = key.split(".")
        target = self._config
        for k in keys[:-1]:
            if k not in target or not isinstance(target[k], dict):
                target[k] = {}
            target = target[k]
        target[keys[-1]] = value
        self._save_config()
        logger.info(f"Config updated: {key} = {value}")

    def set_multi(self, updates: dict):
        """Set multiple values at once (flat dot-notation dict)."""
        for key, value in updates.items():
            keys = key.split(".")
            target = self._config
            for k in keys[:-1]:
                if k not in target or not isinstance(target[k], dict):
                    target[k] = {}
                target = target[k]
            target[keys[-1]] = value
        self._save_config()
        logger.info(f"Config updated: {len(updates)} keys")

    def get_all(self) -> dict:
        """Get the entire configuration."""
        return dict(self._config)

    @property
    def web_config(self) -> dict:
        return self.get("web", {})

    @property
    def security_config(self) -> dict:
        return self.get("security", {})

    @property
    def crypto_config(self) -> dict:
        return self.get("crypto", {})

    @property
    def director_config(self) -> dict:
        return self.get("director", {})
