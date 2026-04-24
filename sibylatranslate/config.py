import os
import json

# config.json fica na raiz do projecto (um nível acima deste pacote)
_CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config.json",
)


class AppConfig:
    """Configuração persistida em JSON. Usa set() para salvar automaticamente."""

    def __init__(self, data: dict | None = None):
        self._data: dict = data or {}

    @classmethod
    def load(cls) -> "AppConfig":
        try:
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                return cls(json.load(f))
        except Exception:
            return cls({})

    def save(self):
        try:
            with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value) -> None:
        """Atualiza um valor e salva imediatamente."""
        self._data[key] = value
        self.save()
