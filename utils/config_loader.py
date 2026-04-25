import os
import re
import yaml
from pathlib import Path
from dotenv import load_dotenv

# Always load .env from the project root (where this repo lives)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=_PROJECT_ROOT / ".env")


def _resolve_env_vars(value):
    """Recursively resolve ${ENV_VAR} placeholders — missing vars use empty string fallback."""
    if isinstance(value, str):
        pattern = re.compile(r'\$\{(\w+)\}')
        def replacer(match):
            env_key = match.group(1)
            env_val = os.getenv(env_key, "")
            if not env_val:
                print(f"[config] WARNING: env variable '{env_key}' is not set")
            return env_val
        return pattern.sub(replacer, value)
    elif isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_resolve_env_vars(i) for i in value]
    return value


def load_config(path: str = None) -> dict:
    if path is None:
        path = _PROJECT_ROOT / "configs" / "config.yaml"
    with open(path, "r") as f:
        raw = yaml.safe_load(f)
    return _resolve_env_vars(raw)


# Singleton
_config = None

def get_config() -> dict:
    global _config
    if _config is None:
        _config = load_config()
    return _config
