"""
SibylaTranslate — entry point

  python main.py                                     → abre a GUI
  python main.py livro.pdf 1 5                       → CLI, modo novo
  python main.py livro.pdf 1 5 -o traducao.docx      → CLI, nome personalizado
  python main.py livro.pdf 6 10 --append trad.docx   → CLI, modo append
  python main.py livro.pdf 5 5  --replace trad.docx  → CLI, modo replace
"""

import sys


def _run_gui() -> None:
    import customtkinter as ctk
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    from sibylatranslate.ui.app import SibylaApp

    app = SibylaApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()


def _run_cli() -> None:
    import os
    import argparse
    from sibylatranslate.engine import processar

    parser = argparse.ArgumentParser(
        description="Traduz páginas de um PDF para PT-BR e salva em Word.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python main.py livro.pdf 1 5
  python main.py livro.pdf 1 5 -o minha_traducao.docx
  python main.py livro.pdf 6 10 --append minha_traducao.docx
  python main.py livro.pdf 5 5  --replace minha_traducao.docx
        """,
    )
    parser.add_argument("pdf",     help="Caminho para o arquivo PDF")
    parser.add_argument("pag_ini", type=int, help="Página inicial")
    parser.add_argument("pag_fim", type=int, help="Página final")
    parser.add_argument("-o", "--output", help="Nome do arquivo de saída .docx")

    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--append",  metavar="DOCX",
                       help="Continua adicionando páginas ao final do DOCX informado")
    grupo.add_argument("--replace", metavar="DOCX",
                       help="Substitui as páginas no DOCX informado (mantém posição)")

    args = parser.parse_args()

    if not os.path.isfile(args.pdf):
        print(f"Erro: arquivo '{args.pdf}' não encontrado.")
        sys.exit(1)
    if args.pag_ini < 1 or args.pag_fim < args.pag_ini:
        print("Erro: intervalo de páginas inválido.")
        sys.exit(1)

    if args.append:
        modo, arquivo_base = "append", args.append
        saida = args.output or args.append
    elif args.replace:
        modo, arquivo_base = "replace", args.replace
        saida = args.output or args.replace
    else:
        modo, arquivo_base = "novo", None
        nome = os.path.splitext(os.path.basename(args.pdf))[0]
        saida = args.output or f"{nome}_pt_p{args.pag_ini}-p{args.pag_fim}.docx"

    processar(args.pdf, args.pag_ini, args.pag_fim, saida, modo, arquivo_base)


if __name__ == "__main__":
    # Sem argumentos além do script → abre GUI
    if len(sys.argv) == 1:
        _run_gui()
    else:
        _run_cli()
