"""
Extração de páginas de um PDF — gera um novo PDF com as páginas selecionadas.

Uso:
    from sibylatranslate.engine.pdf_cutter import recortar_pdf

    recortar_pdf("entrada.pdf", "1-3, 5, 7-9", "saida.pdf")
    # → retorna o número de páginas no arquivo gerado
"""
from __future__ import annotations

import fitz  # PyMuPDF


def recortar_pdf(pdf_path: str, paginas_str: str, saida: str) -> int:
    """
    Extrai as páginas indicadas em *paginas_str* do PDF *pdf_path* e salva em *saida*.

    paginas_str aceita:
        "1-5"          → páginas 1 a 5
        "1, 3, 5"      → páginas 1, 3 e 5
        "1-3, 6-8, 10" → intervalo misto

    Retorna o número de páginas gravadas.
    Lança ValueError se nenhuma página válida for encontrada.
    """
    doc = fitz.open(pdf_path)
    total = len(doc)
    indices = _parse_paginas(paginas_str, total)
    if not indices:
        doc.close()
        raise ValueError(
            f"Nenhuma página válida em '{paginas_str}' "
            f"(o PDF tem {total} página(s))."
        )
    doc.select(indices)   # modifica in-place, descarta as demais
    doc.save(saida, garbage=4, deflate=True)
    doc.close()
    return len(indices)


def _parse_paginas(paginas_str: str, total: int) -> list[int]:
    """
    Converte a string de seleção em lista de índices 0-based, sem duplicatas,
    na ordem em que aparecem.
    """
    seen: set[int] = set()
    indices: list[int] = []

    for part in paginas_str.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a_s, b_s = part.split("-", 1)
            try:
                a, b = int(a_s.strip()), int(b_s.strip())
            except ValueError:
                continue
            for n in range(max(1, a), min(b, total) + 1):
                idx = n - 1
                if idx not in seen:
                    seen.add(idx)
                    indices.append(idx)
        else:
            try:
                n = int(part)
            except ValueError:
                continue
            if 1 <= n <= total:
                idx = n - 1
                if idx not in seen:
                    seen.add(idx)
                    indices.append(idx)

    return indices
