from dataclasses import dataclass, field


@dataclass
class TranslationConfig:
    pdf: str
    pag_ini: int
    pag_fim: int
    modo: str
    base: str | None
    saida: str
    lang_src: str = "en"
    lang_dst: str = "pt"
