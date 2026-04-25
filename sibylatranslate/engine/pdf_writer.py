"""
Escritor de PDF via ReportLab.

Recebe a mesma lista de páginas que text_writer:
  paginas: list[dict]  — cada item:
    {
      "num":     int,
      "blocos":  list[{texto, tamanho, negrito, italico, x0, y_top, y_bot}],
      "imagens": list[{bytes, y_top}]
    }
"""
from __future__ import annotations

import io
import os

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image as RLImage,
    PageBreak, HRFlowable,
)
from reportlab.platypus.flowables import KeepTogether

_PAGE_W, _PAGE_H = A4
_MARGIN = 56          # ~2 cm in points (1 pt = 1 ReportLab unit)
_MAX_IMG_W = _PAGE_W - 2 * _MARGIN

# ── Estilos ───────────────────────────────────────────────────────────────────

def _build_styles() -> dict:
    base = getSampleStyleSheet()

    normal = ParagraphStyle(
        "sibyla_normal",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        spaceAfter=6,
    )
    h1 = ParagraphStyle(
        "sibyla_h1",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=24,
        spaceBefore=10,
        spaceAfter=6,
        textColor=HexColor("#1a1a2e"),
    )
    h2 = ParagraphStyle(
        "sibyla_h2",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=20,
        spaceBefore=8,
        spaceAfter=4,
        textColor=HexColor("#16213e"),
    )
    h3 = ParagraphStyle(
        "sibyla_h3",
        parent=base["Normal"],
        fontName="Helvetica-BoldOblique",
        fontSize=12,
        leading=17,
        spaceBefore=6,
        spaceAfter=4,
    )
    page_header = ParagraphStyle(
        "sibyla_page_header",
        parent=base["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=8,
        leading=11,
        textColor=HexColor("#888888"),
        alignment=1,  # CENTER
        spaceAfter=4,
    )
    return {
        "normal": normal,
        "h1": h1,
        "h2": h2,
        "h3": h3,
        "page_header": page_header,
    }


def _estilo_bloco(bloco: dict, estilos: dict) -> ParagraphStyle:
    """Escolhe o estilo ReportLab adequado para o bloco."""
    tamanho = bloco.get("tamanho", 11)
    negrito = bloco.get("negrito", False)
    italico = bloco.get("italico", False)
    texto   = bloco.get("texto", "")

    if tamanho >= 22 and len(texto) < 120:
        return estilos["h1"]
    if tamanho >= 16 and len(texto) < 120:
        return estilos["h2"]
    if tamanho >= 13 and len(texto) < 120:
        return estilos["h3"]

    # Cria variação inline se necessário
    if negrito and italico:
        return ParagraphStyle(
            "_bi", parent=estilos["normal"], fontName="Helvetica-BoldOblique")
    if negrito:
        return ParagraphStyle(
            "_b", parent=estilos["normal"], fontName="Helvetica-Bold")
    if italico:
        return ParagraphStyle(
            "_i", parent=estilos["normal"], fontName="Helvetica-Oblique")
    return estilos["normal"]


def _img_flowable(img_bytes: bytes) -> RLImage | None:
    """Converte bytes PNG para flowable ReportLab com largura máxima."""
    try:
        from PIL import Image as PILImage
        pil = PILImage.open(io.BytesIO(img_bytes))
        w, h = pil.size
        ratio = min(_MAX_IMG_W / w, 1.0)
        rl_img = RLImage(io.BytesIO(img_bytes),
                         width=w * ratio, height=h * ratio)
        rl_img.hAlign = "CENTER"
        return rl_img
    except Exception:
        return None


# ── Escritor principal ────────────────────────────────────────────────────────

def salvar_pdf(paginas: list[dict], caminho: str) -> None:
    """Salva tradução como PDF usando ReportLab."""
    os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)

    doc = SimpleDocTemplate(
        caminho,
        pagesize=A4,
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        topMargin=_MARGIN,
        bottomMargin=_MARGIN,
        title="Tradução SibylaTranslate",
    )

    estilos = _build_styles()
    story: list = []

    for pag in paginas:
        num     = pag["num"]
        blocos  = pag["blocos"]
        imagens = pag.get("imagens", [])

        # Cabeçalho de página
        story.append(HRFlowable(width="100%", thickness=0.5,
                                color=HexColor("#cccccc"), spaceAfter=4))
        story.append(Paragraph(f"Página {num}", estilos["page_header"]))
        story.append(HRFlowable(width="100%", thickness=0.5,
                                color=HexColor("#cccccc"), spaceAfter=8))

        # Intercala blocos e imagens por y_top
        itens: list[tuple[float, str, dict]] = []
        for b in blocos:
            itens.append((b["y_top"], "bloco", b))
        for img in imagens:
            itens.append((img["y_top"], "img", img))
        itens.sort(key=lambda x: x[0])

        for _, tipo, dado in itens:
            if tipo == "img":
                fl = _img_flowable(dado["bytes"])
                if fl:
                    story.append(Spacer(1, 6))
                    story.append(fl)
                    story.append(Spacer(1, 6))
            else:
                texto = dado.get("texto", "").strip()
                if not texto:
                    story.append(Spacer(1, 4))
                    continue
                # Escapa caracteres especiais XML do ReportLab
                texto_esc = (texto
                             .replace("&", "&amp;")
                             .replace("<", "&lt;")
                             .replace(">", "&gt;"))
                estilo = _estilo_bloco(dado, estilos)
                story.append(Paragraph(texto_esc, estilo))

        story.append(PageBreak())

    # Remove PageBreak final excedente
    if story and isinstance(story[-1], PageBreak):
        story.pop()

    doc.build(story)
