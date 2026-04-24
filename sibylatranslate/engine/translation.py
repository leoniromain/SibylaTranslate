import re
import time
from deep_translator import GoogleTranslator

SOURCE_LANG = "en"
TARGET_LANG = "pt"
CHUNK_SIZE  = 4500   # caracteres por chunk (limite Google Translate: 5000)
DELAY_SEC   = 0.5    # pausa entre requisições

# Palavras/expressões que NUNCA devem ser traduzidas (nomes próprios fixos)
NOMES_PROTEGIDOS: set[str] = set()

# Padrão: sequências de palavras em Title Case (2+ palavras, 2+ letras cada)
_RE_NOME_PROPRIO = re.compile(
    r'\b([A-Z][a-záàâãéêíóôõúüçñ\'\-]{1,}(?:\s+[A-Z][a-záàâãéêíóôõúüçñ\'\-]{1,})+)\b'
)


def _proteger_nomes(texto: str) -> tuple[str, dict]:
    """
    Substitui nomes próprios detectados por placeholders únicos (§0§, §1§…).
    Retorna (texto_com_placeholders, mapa_de_restauração).
    """
    mapa: dict = {}
    idx = [0]

    def substituir(match):
        nome = match.group(0)
        placeholder = f"\u00a7{idx[0]}\u00a7"
        mapa[placeholder] = nome
        idx[0] += 1
        return placeholder

    for nome in sorted(NOMES_PROTEGIDOS, key=len, reverse=True):
        texto = re.sub(re.escape(nome), substituir, texto, flags=re.IGNORECASE)

    texto = _RE_NOME_PROPRIO.sub(substituir, texto)
    return texto, mapa


def _restaurar_nomes(texto: str, mapa: dict) -> str:
    for placeholder, nome in mapa.items():
        texto = texto.replace(placeholder, nome)
    return texto


def traduzir_texto(texto: str,
                   src: str = SOURCE_LANG,
                   dst: str = TARGET_LANG) -> str:
    """Traduz texto preservando nomes próprios e quebras de parágrafo."""
    if not texto.strip():
        return texto

    texto_protegido, mapa = _proteger_nomes(texto)
    translator = GoogleTranslator(source=src, target=dst)
    paragrafos = texto_protegido.split("\n")
    resultado = []
    buffer = ""

    for para in paragrafos:
        if len(buffer) + len(para) + 1 > CHUNK_SIZE:
            if buffer.strip():
                try:
                    resultado.extend(translator.translate(buffer).split("\n"))
                    time.sleep(DELAY_SEC)
                except Exception as e:
                    print(f"\n  [AVISO] {e} — mantendo original.")
                    resultado.extend(buffer.split("\n"))
            buffer = para
        else:
            buffer = (buffer + "\n" + para) if buffer else para

    if buffer.strip():
        try:
            resultado.extend(translator.translate(buffer).split("\n"))
            time.sleep(DELAY_SEC)
        except Exception as e:
            print(f"\n  [AVISO] {e} — mantendo original.")
            resultado.extend(buffer.split("\n"))

    return _restaurar_nomes("\n".join(resultado), mapa)
