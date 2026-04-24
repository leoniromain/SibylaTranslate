import sys
import queue


class LogRedirector:
    """Redireciona sys.stdout para uma queue, permitindo leitura segura na UI."""

    def __init__(self, q: queue.Queue):
        self._q = q
        self._orig = sys.stdout

    def write(self, text: str) -> None:
        self._q.put(text)
        self._orig.write(text)  # mantém saída no terminal também

    def flush(self) -> None:
        self._orig.flush()

    def install(self) -> None:
        sys.stdout = self  # type: ignore[assignment]

    def uninstall(self) -> None:
        sys.stdout = self._orig
