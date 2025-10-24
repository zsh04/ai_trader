from pathlib import Path

from dotenv import load_dotenv

__version__ = "0.1.0"

load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")
