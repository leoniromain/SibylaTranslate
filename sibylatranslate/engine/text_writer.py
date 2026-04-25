"""
Escritores de texto plano (TXT) e Markdown (MD).

Cada função recebe a mesma estrutura de dados que word_writer usa:
  paginas: list[dict]  onde cada dict é:
    {
      "num":     int,
      "blocos":  list[{texto, tamanho, negrito, italico, x0, y_top, y_bot}],
      "imagens": list[{bytes, y_top}]   # imagens são ignoradas em TXT/MD
    }
"""
from __future__ import annotations

import os


# ── TXT ───────────────────────────────────────────────────────────────────────

def salvar_txt(paginas: list[dict], caminho: str) -> None:
    """Salva tradução como texto plano UTF-8."""
    linhas: list[str] = []

    for pag in paginas:
        num    = pag["num"]
        blocos = pag["blocos"]

        linhas.append(f"{'─' * 60}")
        linhas.append(f"  Página {num}")
        linhas.append(f"{'─' * 60}")
        linhas.append("")

        for bloco in blocos:
            texto = bloco["texto"].strip()
            if texto:
                linhas.append(texto)
                linhas.append("")

        linhas.append("")

    os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as fh:
        fh.write("\n".join(linhas))


# ── MD ────────────────────────────────────────────────────────────────────────

def _md_escape(texto: str) -> str:
    """Escapa caracteres especiais do Markdown."""
    for ch in ("\\", "`", "*", "_", "{", "}", "[", "]", "(", ")", "#", "+", "-", ".", "!"):
        texto = texto.replace(ch, "\\" + ch)
    return texto


def salvar_md(paginas: list[dict], caminho: str) -> None:
    """
    Salva tradução como Markdown.
    - Parágrafos com tamanho >= 14 e texto curto → heading H3
    - Negrito/itálico preservados com marcações MD
    - Imagens embutidas são ignoradas (registradas como comentário)
    """
    linhas: list[str] = []

    for pag in paginas:
        num    = pag["num"]
        blocos = pag["blocos"]
        imagens = pag.get("imagens", [])

        linhas.append(f"---")
        linhas.append(f"## Página {num}")
        linhas.append("")

        # Intercala blocos e marcadores de imagem por y_top
        itens: list[tuple[float, str, dict]] = []
        for b in blocos:
            itens.append((b["y_top"], "bloco", b))
        for i, img in enumerate(imagens):
            itens.append((img["y_top"], "img", {"idx": i + 1}))
        itens.sort(key=lambda x: x[0])

        for _, tipo, dado in itens:
            if tipo == "img":
                linhas.append(f"<!-- imagem {dado['idx']} -->")
                linhas.append("")
                continue

            texto = dado["texto"].strip()
            if not texto:
                linhas.append("")
                continue

            tamanho = dado.get("tamanho", 11)
            negrito = dado.get("negrito", False)
            italico = dado.get("italico", False)
            is_titulo = tamanho >= 14 and len(texto) < 120

            if is_titulo:
                # Headings não levam marcação inline de bold/italic
                nivel = "### " if tamanho < 18 else "## " if tamanho < 24 else "# "
                linhas.append(f"{nivel}{texto}")
            else:
                conteudo = _md_escape(texto)
                if negrito and italico:
                    conteudo = f"***{conteudo}***"
                elif negrito:
                    conteudo = f"**{conteudo}**"
                elif italico:
                    conteudo = f"*{conteudo}*"
                linhas.append(conteudo)

            linhas.append("")

        linhas.append("")

    os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as fh:
        fh.write("\n".join(linhas))
