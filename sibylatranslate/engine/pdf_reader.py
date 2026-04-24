from .image_utils import para_png_bytes
from .ocr import ocr_traduzir_imagem

LINE_GAP_PT = 8  # gap vertical (pts) que separa parágrafos distintos


def extrair_imagens_da_pagina(fitz_doc, page_index: int,
                             src: str = "en", dst: str = "pt") -> list:
    """
    Retorna lista de dicts {bytes, y_top} com imagens embutidas na página,
    ordenadas por posição vertical. Converte tudo para PNG e aplica OCR/tradução.
    """
    page = fitz_doc[page_index]
    imagens = []
    for img_info in page.get_images(full=True):
        xref = img_info[0]
        try:
            bbox = page.get_image_bbox(img_info)
            y_top = bbox.y0
        except Exception:
            y_top = 0
        try:
            base_img = fitz_doc.extract_image(xref)
            raw = base_img["image"]
            cs  = base_img.get("colorspace", "")
            png = para_png_bytes(raw, cs)
            if png:
                png = ocr_traduzir_imagem(png, src, dst)
                imagens.append({"bytes": png, "y_top": y_top})
        except Exception:
            pass
    imagens.sort(key=lambda x: x["y_top"])
    return imagens


def extrair_blocos_pagina(page) -> list:
    """
    Extrai blocos de texto agrupando linhas próximas em parágrafos.
    Cada bloco: {texto, tamanho, negrito, italico, x0, y_top, y_bot}
    """
    words = page.extract_words(
        x_tolerance=3,
        y_tolerance=3,
        keep_blank_chars=False,
        use_text_flow=True,
        extra_attrs=["size", "fontname"],
    )
    if not words:
        return []

    linhas_dict: dict = {}
    for w in words:
        y_key = round(w["top"] / 3) * 3
        linhas_dict.setdefault(y_key, []).append(w)

    linhas = []
    for y_key in sorted(linhas_dict.keys()):
        ws = sorted(linhas_dict[y_key], key=lambda w: w["x0"])
        primeiro = ws[0]
        tamanho  = primeiro.get("size", 11) or 11
        fontname = (primeiro.get("fontname") or "").lower()
        linhas.append({
            "texto":   " ".join(w["text"] for w in ws),
            "tamanho": tamanho,
            "negrito": "bold" in fontname or "heavy" in fontname,
            "italico": "italic" in fontname or "oblique" in fontname,
            "x0":      primeiro["x0"],
            "y_top":   primeiro["top"],
            "y_bot":   ws[-1].get("bottom", primeiro["top"] + tamanho),
        })

    if not linhas:
        return []

    blocos = []
    atual = dict(linhas[0])

    for prox in linhas[1:]:
        gap = prox["y_top"] - atual["y_bot"]
        mesmo_estilo = (
            abs(prox["tamanho"] - atual["tamanho"]) < 1.5
            and prox["negrito"] == atual["negrito"]
            and prox["italico"] == atual["italico"]
            and abs(prox["x0"] - atual["x0"]) < 30
        )
        if gap <= LINE_GAP_PT and mesmo_estilo:
            atual["texto"] += " " + prox["texto"]
            atual["y_bot"] = prox["y_bot"]
        else:
            blocos.append(atual)
            atual = dict(prox)

    blocos.append(atual)
    return blocos
