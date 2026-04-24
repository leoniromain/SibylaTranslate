import io
import numpy as np
from PIL import Image, ImageDraw

from .image_utils import _autofit_fonte, _cor_contraste
from .translation import traduzir_texto

OCR_MIN_CONF = 0.35  # confiança mínima do EasyOCR (0–1)

_ocr_reader = None


def get_ocr_reader():
    global _ocr_reader
    if _ocr_reader is None:
        import easyocr
        print("\n  [OCR] Carregando modelo EasyOCR (primeira vez pode demorar)...",
              end=" ", flush=True)
        _ocr_reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        print("pronto.")
    return _ocr_reader


def _agrupar_em_paragrafos(resultados: list, gap_max: int = 12) -> list:
    """
    Agrupa detecções EasyOCR linha a linha em blocos de parágrafo.
    Retorna lista de grupos: [{texto, x0, y0, x1, y1, conf_media}].
    """
    if not resultados:
        return []

    def bbox_bounds(bbox):
        xs = [int(p[0]) for p in bbox]
        ys = [int(p[1]) for p in bbox]
        return min(xs), min(ys), max(xs), max(ys)

    itens = []
    for (bbox, texto, conf) in resultados:
        x0, y0, x1, y1 = bbox_bounds(bbox)
        itens.append({"texto": texto, "conf": conf,
                      "x0": x0, "y0": y0, "x1": x1, "y1": y1})
    itens.sort(key=lambda i: (i["y0"], i["x0"]))

    grupos = []
    grupo_atual = [itens[0]]

    for item in itens[1:]:
        ultimo = grupo_atual[-1]
        gap_v = item["y0"] - ultimo["y1"]
        gap_x = abs(item["x0"] - grupo_atual[0]["x0"])
        if gap_v <= gap_max and gap_x <= 60:
            grupo_atual.append(item)
        else:
            grupos.append(grupo_atual)
            grupo_atual = [item]
    grupos.append(grupo_atual)

    resultado_grupos = []
    for g in grupos:
        resultado_grupos.append({
            "texto": " ".join(i["texto"] for i in g),
            "conf":  sum(i["conf"] for i in g) / len(g),
            "x0": min(i["x0"] for i in g),
            "y0": min(i["y0"] for i in g),
            "x1": max(i["x1"] for i in g),
            "y1": max(i["y1"] for i in g),
        })
    return resultado_grupos


def ocr_traduzir_imagem(img_bytes: bytes) -> bytes:
    """
    Faz OCR, agrupa em parágrafos, traduz e redesenha o texto em PT-BR.
    Retorna PNG bytes com o texto já traduzido.
    """
    reader = get_ocr_reader()
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    img_np = np.array(img)

    resultados_raw = reader.readtext(img_np, paragraph=False)
    if not resultados_raw:
        return img_bytes

    resultados_raw = [(b, t, c) for (b, t, c) in resultados_raw
                      if c >= OCR_MIN_CONF and t.strip()]
    if not resultados_raw:
        return img_bytes

    grupos = _agrupar_em_paragrafos(resultados_raw)
    draw = ImageDraw.Draw(img)

    for g in grupos:
        x0, y0, x1, y1 = g["x0"], g["y0"], g["x1"], g["y1"]
        box_w = max(x1 - x0, 30)
        box_h = max(y1 - y0, 12)

        regiao_arr = np.array(img.crop((x0, y0, x1, y1)))
        cor_fundo = tuple(int(np.median(regiao_arr[:, :, c])) for c in range(3))
        cor_texto = _cor_contraste(*cor_fundo)

        traduzido = traduzir_texto(g["texto"])
        n_linhas_orig = max(1, len(g["texto"].split("\n")))
        tam_inicial = max((box_h // n_linhas_orig) - 4, 8)

        fonte, linhas, _, pad = _autofit_fonte(traduzido, box_w, box_h, tam_inicial)
        draw.rectangle([x0, y0, x1, y1], fill=cor_fundo)

        line_h = fonte.getbbox("Ay")[3] - fonte.getbbox("Ay")[1]
        total_h = line_h * len(linhas) + 2 * max(0, len(linhas) - 1)
        y_cur = y0 + max(pad, (box_h - total_h) // 2)

        for linha in linhas:
            draw.text((x0 + pad, y_cur), linha, fill=cor_texto, font=fonte)
            y_cur += line_h + 2

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
