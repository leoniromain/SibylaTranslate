"""Shim de compatibilidade — use: python main.py <args>
O motor foi movido para sibylatranslate/engine/
"""
from sibylatranslate.engine.core import processar  # noqa: F401

if __name__ == "__main__":
    import main as _main
    _main._run_cli()

