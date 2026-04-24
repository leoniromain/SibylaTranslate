import io
import fitz  # PyMuPDF
from PIL import Image, ImageFont

IMG_DPI   = 180    # DPI para renderizar páginas-imagem
MAX_IMG_W = 5.5    # largura máxima da imagem no Word (polegadas)

_FONT_PATHS = [
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\calibri.ttf",
    r"C:\Windows\Fonts\times.ttf",
    r"C:\Windows\Fonts\verdana.ttf",
]


def pagina_para_imagem_bytes(fitz_doc, page_index: int) -> bytes:
    """Renderiza uma página inteira como PNG e retorna bytes."""
    page = fitz_doc[page_index]
    mat = fitz.Matrix(IMG_DPI / 72, IMG_DPI / 72)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    return pix.tobytes("png")


def para_png_bytes(raw_bytes: bytes, colorspace: str = "") -> bytes | None:
    """
    Converte qualquer imagem (CMYK, paleta, etc.) para PNG RGB via Pillow.
    Retorna None se não conseguir converter.
    """
    try:
        img = Image.open(io.BytesIO(raw_bytes))
        if img.mode in ("CMYK", "P", "L", "LA"):
            img = img.convert("RGB")
        elif img.mode == "RGBA":
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3])
            img = bg
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None


def _carregar_fonte(tamanho: int) -> ImageFont.FreeTypeFont:
    """Tenta carregar uma fonte TTF do sistema. Fallback para fonte padrão."""
    for path in _FONT_PATHS:
        try:
            return ImageFont.truetype(path, max(6, tamanho))
        except Exception:
            pass
    return ImageFont.load_default()


def _cor_contraste(r: int, g: int, b: int) -> tuple:
    """Retorna preto ou branco dependendo da luminância do fundo."""
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    return (0, 0, 0) if lum > 128 else (255, 255, 255)


def _quebrar_texto(texto: str, fonte: ImageFont.FreeTypeFont, largura_max: int) -> list[str]:
    """Quebra o texto em linhas que caibam dentro de largura_max pixels."""
    palavras = texto.split()
    linhas: list[str] = []
    linha_atual = ""
    for palavra in palavras:
        teste = (linha_atual + " " + palavra).strip()
        bb = fonte.getbbox(teste)
        if bb[2] - bb[0] <= largura_max:
            linha_atual = teste
        else:
            if linha_atual:
                linhas.append(linha_atual)
            linha_atual = palavra
    if linha_atual:
        linhas.append(linha_atual)
    return linhas if linhas else [texto]


def _autofit_fonte(texto: str, box_w: int, box_h: int, tam_inicial: int) -> tuple:
    """
    Reduz tamanho da fonte até o texto caber no box com quebra de linha.
    Retorna (fonte, linhas, tamanho, padding).
    """
    PAD = 4
    w_util = max(box_w - PAD * 2, 10)
    h_util = max(box_h - PAD * 2, 6)

    for tamanho in range(min(tam_inicial, 120), 5, -1):
        fonte = _carregar_fonte(tamanho)
        linhas = _quebrar_texto(texto, fonte, w_util)
        line_h = fonte.getbbox("Ay")[3] - fonte.getbbox("Ay")[1]
        altura_total = line_h * len(linhas) + 2 * max(0, len(linhas) - 1)
        if altura_total <= h_util:
            return fonte, linhas, tamanho, PAD

    fonte = _carregar_fonte(6)
    linhas = _quebrar_texto(texto, fonte, w_util)
    return fonte, linhas, 6, PAD
