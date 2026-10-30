import os
from pathlib import Path

try:
    from dotenv import load_dotenv as _load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    def _load_dotenv(*args, **kwargs):
        return False


def resolve_project_root(start_file: str | os.PathLike | None = None) -> Path:
    if start_file is None:
        return Path(__file__).resolve().parent.parent

    return Path(start_file).resolve().parent if Path(start_file).resolve().parent.exists() else Path(__file__).resolve().parent.parent


def load_project_env(start_file: str | os.PathLike | None = None):
    project_root = resolve_project_root(start_file)
    env_path = project_root / "config.env"
    _load_dotenv(env_path)
    return env_path
