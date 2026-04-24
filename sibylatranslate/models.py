from dataclasses import dataclass


@dataclass
class TranslationConfig:
    pdf: str
    pag_ini: int
    pag_fim: int
    modo: str
    base: str | None
    saida: str
