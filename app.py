"""Shim de compatibilidade — use: python main.py
O código foi movido para sibylatranslate/ui/app.py
"""
if __name__ == "__main__":
    import main as _main
    _main._run_gui()

