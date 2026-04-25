import os
import re
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk
import fitz
import pdfplumber

from ..models import TranslationConfig
from ..config import AppConfig
from ..engine import processar
from ..engine.pdf_cutter import recortar_pdf
from .log_redirector import LogRedirector
from .preview_panel import PreviewPanel


# ── Tabela de idiomas suportados pelo Google Translate ──────────────────────
_LANGS: list[tuple[str, str]] = [
    ("auto",  "auto-detectar"),
    ("af",    "Africâner"),
    ("ar",    "Árabe"),
    ("hy",    "Armênio"),
    ("az",    "Azerbaijano"),
    ("eu",    "Basco"),
    ("bn",    "Bengali"),
    ("bg",    "Búlgaro"),
    ("ca",    "Catalão"),
    ("zh-CN", "Chinês (simpl.)"),
    ("zh-TW", "Chinês (trad.)"),
    ("ko",    "Coreano"),
    ("hr",    "Croata"),
    ("da",    "Dinamarquês"),
    ("sk",    "Eslovaco"),
    ("sl",    "Esloveno"),
    ("es",    "Espanhol"),
    ("et",    "Estoniano"),
    ("fi",    "Finlandês"),
    ("fr",    "Francês"),
    ("gl",    "Galego"),
    ("ka",    "Georgiano"),
    ("el",    "Grego"),
    ("gu",    "Gujarati"),
    ("he",    "Hebraico"),
    ("hi",    "Hindi"),
    ("nl",    "Holandês"),
    ("hu",    "Húngaro"),
    ("id",    "Indonésio"),
    ("en",    "Inglês"),
    ("it",    "Italiano"),
    ("ja",    "Japonês"),
    ("kn",    "Kannada"),
    ("kk",    "Cazaque"),
    ("km",    "Khmer"),
    ("lo",    "Laosiano"),
    ("la",    "Latim"),
    ("lv",    "Letão"),
    ("lt",    "Lituano"),
    ("mk",    "Macedônio"),
    ("ms",    "Malaio"),
    ("ml",    "Malaiala"),
    ("mi",    "Maori"),
    ("mr",    "Marathi"),
    ("mn",    "Mongol"),
    ("ne",    "Nepalês"),
    ("no",    "Norueguês"),
    ("fa",    "Persa"),
    ("pl",    "Polonês"),
    ("pt",    "Português"),
    ("pa",    "Punjabi"),
    ("ro",    "Romeno"),
    ("ru",    "Russo"),
    ("sr",    "Sérvio"),
    ("si",    "Cingalês"),
    ("so",    "Somali"),
    ("sv",    "Sueco"),
    ("sw",    "Suaíli"),
    ("tg",    "Tadjique"),
    ("ta",    "Tâmil"),
    ("te",    "Telugu"),
    ("th",    "Tailandês"),
    ("tr",    "Turco"),
    ("uk",    "Ucraniano"),
    ("ur",    "Urdu"),
    ("uz",    "Usbeque"),
    ("vi",    "Vietnamita"),
    ("cy",    "Galês"),
    ("yi",    "Iídiche"),
    ("zu",    "Zulu"),
]

_LANG_DISPLAY    = [f"{nome} ({cod})" for cod, nome in _LANGS]
_CODE_BY_DISPLAY = {f"{nome} ({cod})": cod for cod, nome in _LANGS}
_DISPLAY_BY_CODE = {cod: f"{nome} ({cod})" for cod, nome in _LANGS}


def _lang_code(display: str) -> str:
    """Extrai o código de 'Nome (cod)' ou devolve o valor como está (código direto)."""
    return _CODE_BY_DISPLAY.get(display, display)


# ── Constantes de layout ──────────────────────────────────────────────────────
_SIDEBAR_W   = 300

_FMT_ITEMS   = [("docx", "Word"), ("txt", "TXT"), ("md", "Markdown"), ("pdf", "PDF")]
_FMT_BY_LBL  = {lbl: val for val, lbl in _FMT_ITEMS}
_LBL_BY_FMT  = {val: lbl for val, lbl in _FMT_ITEMS}
_FMT_LABELS  = [lbl for _, lbl in _FMT_ITEMS]

_MODO_ITEMS  = [("novo", "Novo"), ("append", "Continuar"), ("replace", "Substituir")]
_MODO_BY_LBL = {lbl: val for val, lbl in _MODO_ITEMS}
_LBL_BY_MODO = {val: lbl for val, lbl in _MODO_ITEMS}
_MODO_LABELS = [lbl for _, lbl in _MODO_ITEMS]


class _LangPicker(ctk.CTkFrame):
    """Entry editável + botão que abre popup scrollable com ~10 idiomas visíveis."""

    _ITEM_H  = 28   # altura de cada item
    _ITEMS_V = 10   # máximo de itens visíveis sem rolar

    def __init__(self, master, variable: tk.StringVar, width: int = 200, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self._var = variable
        self._popup: ctk.CTkToplevel | None = None
        self._entry = ctk.CTkEntry(self, textvariable=self._var, width=width - 34)
        self._entry.pack(side="left")
        ctk.CTkButton(self, text="▾", width=30, height=28,
                      command=self._toggle).pack(side="left", padx=(2, 0))

    def _toggle(self) -> None:
        if self._popup and self._popup.winfo_exists():
            self._popup.destroy()
            self._popup = None
            return
        self._open_popup()

    def _open_popup(self) -> None:
        popup = ctk.CTkToplevel(self)
        popup.wm_overrideredirect(True)
        popup.attributes("-topmost", True)

        popup_w = self._entry.winfo_width() + 34
        popup_h = self._ITEM_H * self._ITEMS_V + 6
        scroll = ctk.CTkScrollableFrame(popup, width=popup_w - 20,
                                        height=popup_h)
        scroll.pack(fill="both", expand=True, padx=0, pady=0)

        for display in _LANG_DISPLAY:
            ctk.CTkButton(
                scroll, text=display, anchor="w", height=self._ITEM_H,
                fg_color="transparent", hover_color=("gray80", "gray30"),
                command=lambda d=display: self._select(d, popup),
            ).pack(fill="x", pady=1, padx=2)

        self.update_idletasks()
        x = self._entry.winfo_rootx()
        y = self._entry.winfo_rooty() + self._entry.winfo_height() + 2
        popup.geometry(f"+{x}+{y}")
        popup.focus_set()
        popup.bind("<FocusOut>",
                   lambda e: popup.destroy() if popup.winfo_exists() else None)
        self._popup = popup

    def _select(self, display: str, popup: ctk.CTkToplevel) -> None:
        self._var.set(display)
        popup.destroy()
        self._popup = None


class SibylaApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("SibylaTranslate")
        self.geometry("1120x720")
        self.minsize(900, 580)
        self.resizable(True, True)

        self._config = AppConfig.load()
        self._log_queue: queue.Queue = queue.Queue()
        self._log_redirector = LogRedirector(self._log_queue)
        self._cancel_event = threading.Event()
        self._worker: threading.Thread | None = None

        # vars initialized before _build_ui so helpers can reference them
        self._tema_var = tk.StringVar(value=self._config.get("tema", "dark"))
        self._fmt_var  = tk.StringVar(value=_LBL_BY_FMT.get(self._config.get("fmt",  "docx"), "Word"))
        self._modo_var = tk.StringVar(value=_LBL_BY_MODO.get(self._config.get("modo", "novo"), "Novo"))

        self._build_ui()
        self._after_flush = self.after(100, self._flush_log)

    # ── Build UI ──────────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=0)   # sidebar — fixed
        self.columnconfigure(1, weight=1)   # main — expands
        self.rowconfigure(0, weight=1)
        self._build_sidebar()
        self._build_main_area()
        ctk.set_appearance_mode(self._tema_var.get())
        if self._pdf_var.get():
            self.after(200, self._atualizar_total_paginas)

    # ── Sidebar ───────────────────────────────────────────────────────────────
    def _build_sidebar(self) -> None:
        sb = ctk.CTkFrame(self, width=_SIDEBAR_W, corner_radius=0)
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_propagate(False)
        sb.columnconfigure(0, weight=1)
        sb.rowconfigure(1, weight=1)   # scroll area expands

        # ── Header ────────────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(sb, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(18, 8))
        hdr.columnconfigure(0, weight=1)

        title_row = ctk.CTkFrame(hdr, fg_color="transparent")
        title_row.pack(fill="x")
        ctk.CTkLabel(title_row, text="SibylaTranslate",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(side="left")
        self._tema_btn = ctk.CTkButton(
            title_row, text=self._tema_var.get(), width=64, height=26,
            font=ctk.CTkFont(size=11), fg_color="gray25", hover_color="gray35",
            command=self._toggle_tema)
        self._tema_btn.pack(side="right")

        self._subtitle_lbl = ctk.CTkLabel(
            hdr, text=self._fmt_subtitle(),
            font=ctk.CTkFont(size=11), text_color="gray50", anchor="w")
        self._subtitle_lbl.pack(fill="x", pady=(2, 0))

        # ── Scrollable content ────────────────────────────────────────────────
        scroll = ctk.CTkScrollableFrame(sb, fg_color="transparent")
        scroll.grid(row=1, column=0, sticky="nsew")
        scroll.columnconfigure(0, weight=1)
        self._build_fields(scroll)

        # ── Progress + status ─────────────────────────────────────────────────
        self._progress = ctk.CTkProgressBar(sb, height=6)
        self._progress.set(0)
        self._progress.grid(row=2, column=0, sticky="ew", padx=16, pady=(6, 2))

        stat_row = ctk.CTkFrame(sb, fg_color="transparent")
        stat_row.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 4))
        self._lbl_status = ctk.CTkLabel(
            stat_row, text="Pronto para traduzir",
            text_color="gray50", font=ctk.CTkFont(size=11), anchor="w")
        self._lbl_status.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(stat_row, text="limpar", width=52, height=22,
                      fg_color="transparent", text_color="gray50",
                      hover_color=("gray80", "gray30"), font=ctk.CTkFont(size=11),
                      command=self._limpar_log).pack(side="right")

        # ── Action buttons ────────────────────────────────────────────────────
        btn_row = ctk.CTkFrame(sb, fg_color="transparent")
        btn_row.grid(row=4, column=0, sticky="ew", padx=16, pady=(4, 18))
        btn_row.columnconfigure(0, weight=1)
        btn_row.columnconfigure(1, weight=1)

        self._btn_traduzir = ctk.CTkButton(
            btn_row, text="▶  Traduzir", height=40,
            font=ctk.CTkFont(size=13, weight="bold"), command=self._iniciar)
        self._btn_traduzir.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self._btn_cancelar = ctk.CTkButton(
            btn_row, text="✕  Cancelar", height=40,
            fg_color="#8B0000", hover_color="#600000",
            command=self._cancelar, state="disabled")
        self._btn_cancelar.grid(row=0, column=1, sticky="ew", padx=(4, 0))

    def _section_header(self, parent, text: str) -> None:
        """Rótulo de seção em maiúsculas + linha divisória."""
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(fill="x", padx=16, pady=(14, 6))
        ctk.CTkLabel(f, text=text, font=ctk.CTkFont(size=10, weight="bold"),
                     text_color="gray50").pack(side="left")
        ctk.CTkFrame(f, height=1, fg_color="gray25").pack(
            side="left", fill="x", expand=True, padx=(8, 0))

    def _build_fields(self, parent) -> None:
        """Campos de configuração dentro da área rolável."""

        # ── ARQUIVO DE ENTRADA ────────────────────────────────────────────────
        self._section_header(parent, "ARQUIVO DE ENTRADA")
        pdf_card = ctk.CTkFrame(parent)
        pdf_card.pack(fill="x", padx=16, pady=(0, 4))
        pdf_card.columnconfigure(1, weight=1)

        self._pdf_var = tk.StringVar(value=self._config.get("ultimo_pdf", ""))
        ctk.CTkLabel(pdf_card, text="📄", font=ctk.CTkFont(size=18),
                     width=36).grid(row=0, column=0, rowspan=2, padx=(10, 2), pady=8)
        ctk.CTkEntry(pdf_card, textvariable=self._pdf_var,
                     placeholder_text="Selecione o PDF…").grid(
            row=0, column=1, sticky="ew", padx=(0, 4), pady=(8, 2))
        ctk.CTkButton(pdf_card, text="…", width=32, height=28,
                      command=self._selecionar_pdf).grid(
            row=0, column=2, padx=(0, 10), pady=(8, 2))

        self._total_var = tk.StringVar(value="")
        ctk.CTkLabel(pdf_card, textvariable=self._total_var,
                     text_color="gray50", font=ctk.CTkFont(size=10),
                     anchor="w").grid(row=1, column=1, sticky="w", pady=(0, 8))

        # ── PÁGINAS ───────────────────────────────────────────────────────────
        self._section_header(parent, "PÁGINAS")
        pag_row = ctk.CTkFrame(parent, fg_color="transparent")
        pag_row.pack(fill="x", padx=16, pady=(0, 4))

        self._pag_ini_var = tk.StringVar(value="1")
        self._pag_fim_var = tk.StringVar(value="5")
        ctk.CTkEntry(pag_row, textvariable=self._pag_ini_var,
                     width=64, justify="center").pack(side="left")
        ctk.CTkLabel(pag_row, text="até",
                     text_color="gray50").pack(side="left", padx=8)
        ctk.CTkEntry(pag_row, textvariable=self._pag_fim_var,
                     width=64, justify="center").pack(side="left")
        ctk.CTkButton(pag_row, text="Todas", width=68, height=28,
                      command=self._todas_paginas).pack(side="left", padx=(12, 0))

        # ── IDIOMA ────────────────────────────────────────────────────────────
        self._section_header(parent, "IDIOMA")
        lang_row = ctk.CTkFrame(parent, fg_color="transparent")
        lang_row.pack(fill="x", padx=16, pady=(0, 4))
        lang_row.columnconfigure(0, weight=1)
        lang_row.columnconfigure(2, weight=1)

        saved_src = self._config.get("lang_src", "en")
        saved_dst = self._config.get("lang_dst", "pt")
        self._lang_src_var = tk.StringVar(
            value=_DISPLAY_BY_CODE.get(saved_src, saved_src))
        self._lang_dst_var = tk.StringVar(
            value=_DISPLAY_BY_CODE.get(saved_dst, saved_dst))

        _LangPicker(lang_row, variable=self._lang_src_var, width=118).grid(
            row=0, column=0, sticky="ew")
        ctk.CTkButton(lang_row, text="⇌", width=34, height=28,
                      fg_color="transparent", hover_color=("gray80", "gray30"),
                      font=ctk.CTkFont(size=14),
                      command=self._swap_languages).grid(row=0, column=1, padx=4)
        _LangPicker(lang_row, variable=self._lang_dst_var, width=118).grid(
            row=0, column=2, sticky="ew")

        # ── MODO DE SAÍDA ─────────────────────────────────────────────────────
        self._section_header(parent, "MODO DE SAÍDA")
        self._modo_seg = ctk.CTkSegmentedButton(
            parent, values=_MODO_LABELS, variable=self._modo_var,
            command=self._on_modo_change, font=ctk.CTkFont(size=11))
        self._modo_seg.pack(fill="x", padx=16, pady=(0, 4))

        # base frame (hidden until append/replace)
        self._base_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self._base_var = tk.StringVar(value=self._config.get("ultimo_docx", ""))
        bf_inner = ctk.CTkFrame(self._base_frame)
        bf_inner.pack(fill="x")
        bf_inner.columnconfigure(1, weight=1)
        ctk.CTkLabel(bf_inner, text="📄", width=28,
                     font=ctk.CTkFont(size=14)).grid(row=0, column=0, padx=(8, 2), pady=6)
        ctk.CTkEntry(bf_inner, textvariable=self._base_var,
                     placeholder_text="Selecione o .docx base…").grid(
            row=0, column=1, sticky="ew", padx=(0, 4), pady=6)
        ctk.CTkButton(bf_inner, text="…", width=30, height=26,
                      command=self._selecionar_base).grid(
            row=0, column=2, padx=(0, 8), pady=6)
        self._base_visible = False

        # ── FORMATO DE SAÍDA ──────────────────────────────────────────────────
        self._section_header(parent, "FORMATO DE SAÍDA")
        ctk.CTkSegmentedButton(
            parent, values=_FMT_LABELS, variable=self._fmt_var,
            command=self._on_fmt_change, font=ctk.CTkFont(size=11),
        ).pack(fill="x", padx=16, pady=(0, 4))

        # ── ARQUIVO DE SAÍDA ──────────────────────────────────────────────────
        self._section_header(parent, "ARQUIVO DE SAÍDA")
        out_card = ctk.CTkFrame(parent)
        out_card.pack(fill="x", padx=16, pady=(0, 16))
        out_card.columnconfigure(0, weight=1)

        self._saida_var = tk.StringVar(value=self._config.get("ultima_saida", ""))
        ctk.CTkEntry(out_card, textvariable=self._saida_var,
                     placeholder_text="nome automático se vazio").grid(
            row=0, column=0, sticky="ew", padx=(10, 4), pady=8)
        ctk.CTkButton(out_card, text="…", width=32, height=28,
                      command=self._selecionar_saida).grid(
            row=0, column=1, padx=(0, 10), pady=8)

    # ── Main area (tabbed) ────────────────────────────────────────────────────
    def _build_main_area(self) -> None:
        self._tabview = ctk.CTkTabview(self, anchor="nw")
        self._tabview.grid(row=0, column=1, sticky="nsew", padx=(0, 16), pady=16)

        self._tabview.add("Original")
        self._tabview.add("Log")
        self._tabview.add("✂ Recortar")

        # Preview tab
        tab_orig = self._tabview.tab("Original")
        tab_orig.columnconfigure(0, weight=1)
        tab_orig.rowconfigure(0, weight=1)
        self._preview = PreviewPanel(tab_orig)
        self._preview.grid(row=0, column=0, sticky="nsew")

        # Log tab
        tab_log = self._tabview.tab("Log")
        tab_log.columnconfigure(0, weight=1)
        tab_log.rowconfigure(1, weight=1)

        log_hdr = ctk.CTkFrame(tab_log, fg_color="transparent")
        log_hdr.grid(row=0, column=0, sticky="ew", padx=8, pady=(4, 2))
        ctk.CTkLabel(log_hdr, text="Log de execução",
                     font=ctk.CTkFont(size=12), text_color="gray60").pack(side="left")
        ctk.CTkButton(log_hdr, text="Limpar", width=70, height=24,
                      command=self._limpar_log).pack(side="right")

        self._log_box = ctk.CTkTextbox(
            tab_log, font=ctk.CTkFont(family="Courier", size=11),
            wrap="word", state="disabled")
        self._log_box.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

        # Recortar tab
        self._build_cutter_tab(self._tabview.tab("✂ Recortar"))

    # ── Recortar PDF tab ──────────────────────────────────────────────────────
    def _build_cutter_tab(self, tab) -> None:
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)

        # Scrollable inner area so it works at any height
        inner = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        inner.grid(row=0, column=0, sticky="nsew")
        inner.columnconfigure(0, weight=1)

        # Header
        hdr_row = ctk.CTkFrame(inner, fg_color="transparent")
        hdr_row.pack(fill="x", padx=16, pady=(18, 4))
        ctk.CTkLabel(hdr_row, text="Recortar PDF",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")
        ctk.CTkLabel(hdr_row, text="— extraia páginas para um novo arquivo",
                     font=ctk.CTkFont(size=11), text_color="gray50").pack(
            side="left", padx=8)

        # ── ARQUIVO PDF ───────────────────────────────────────────────────────
        self._section_header(inner, "ARQUIVO PDF")
        c_pdf_card = ctk.CTkFrame(inner)
        c_pdf_card.pack(fill="x", padx=16, pady=(0, 4))
        c_pdf_card.columnconfigure(1, weight=1)

        self._cut_pdf_var   = tk.StringVar()
        self._cut_total_var = tk.StringVar(value="")
        ctk.CTkLabel(c_pdf_card, text="📄", font=ctk.CTkFont(size=18),
                     width=36).grid(row=0, column=0, rowspan=2, padx=(10, 2), pady=8)
        ctk.CTkEntry(c_pdf_card, textvariable=self._cut_pdf_var,
                     placeholder_text="Selecione o PDF…").grid(
            row=0, column=1, sticky="ew", padx=(0, 4), pady=(8, 2))
        ctk.CTkButton(c_pdf_card, text="…", width=32, height=28,
                      command=self._cut_sel_pdf).grid(
            row=0, column=2, padx=(0, 10), pady=(8, 2))
        ctk.CTkLabel(c_pdf_card, textvariable=self._cut_total_var,
                     text_color="gray50", font=ctk.CTkFont(size=10),
                     anchor="w").grid(row=1, column=1, sticky="w", pady=(0, 8))

        # ── PÁGINAS A EXTRAIR ─────────────────────────────────────────────────
        self._section_header(inner, "PÁGINAS A EXTRAIR")
        self._cut_pag_var = tk.StringVar()
        ctk.CTkEntry(inner, textvariable=self._cut_pag_var,
                     placeholder_text='Ex.: "1-3, 5, 7-9"  ou  "2"').pack(
            fill="x", padx=16, pady=(0, 4))
        hint_row = ctk.CTkFrame(inner, fg_color="transparent")
        hint_row.pack(fill="x", padx=16, pady=(0, 4))
        for hint in ["1-5 → intervalo", "1, 3, 5 → páginas isoladas",
                     "1-3, 6, 8-10 → misto"]:
            ctk.CTkLabel(hint_row, text=hint, font=ctk.CTkFont(size=10),
                         text_color="gray50").pack(side="left", padx=(0, 16))

        # ── ARQUIVO DE SAÍDA ──────────────────────────────────────────────────
        self._section_header(inner, "ARQUIVO DE SAÍDA")
        c_out_card = ctk.CTkFrame(inner)
        c_out_card.pack(fill="x", padx=16, pady=(0, 4))
        c_out_card.columnconfigure(0, weight=1)

        self._cut_saida_var = tk.StringVar()
        ctk.CTkEntry(c_out_card, textvariable=self._cut_saida_var,
                     placeholder_text="nome automático se vazio").grid(
            row=0, column=0, sticky="ew", padx=(10, 4), pady=8)
        ctk.CTkButton(c_out_card, text="…", width=32, height=28,
                      command=self._cut_sel_saida).grid(
            row=0, column=1, padx=(0, 10), pady=8)

        # ── Botão + status ────────────────────────────────────────────────────
        ctk.CTkFrame(inner, height=1, fg_color="gray25").pack(
            fill="x", padx=16, pady=(10, 0))

        act_row = ctk.CTkFrame(inner, fg_color="transparent")
        act_row.pack(fill="x", padx=16, pady=14)

        self._btn_cortar = ctk.CTkButton(
            act_row, text="✂  Recortar", height=40, width=160,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._iniciar_corte)
        self._btn_cortar.pack(side="left")

        self._cut_status_lbl = ctk.CTkLabel(
            act_row, text="", font=ctk.CTkFont(size=11),
            text_color="gray50", anchor="w", wraplength=380)
        self._cut_status_lbl.pack(side="left", padx=16, fill="x", expand=True)

    def _cut_sel_pdf(self) -> None:
        path = filedialog.askopenfilename(
            title="Selecionar PDF para recortar",
            filetypes=[("PDF", "*.pdf"), ("Todos", "*.*")],
            initialdir=os.path.dirname(self._cut_pdf_var.get()) or os.getcwd(),
        )
        if not path:
            return
        self._cut_pdf_var.set(path)
        try:
            doc = fitz.open(path)
            n = len(doc)
            doc.close()
            self._cut_total_var.set(f"{n} página{'s' if n != 1 else ''}")
        except Exception:
            self._cut_total_var.set("(não foi possível ler o PDF)")
        # espelha no preview principal
        self._preview.abrir(path)

    def _cut_sel_saida(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Salvar recorte como…",
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf"), ("Todos", "*.*")],
            initialdir=os.path.dirname(self._cut_saida_var.get()) or os.getcwd(),
        )
        if path:
            self._cut_saida_var.set(path)

    def _iniciar_corte(self) -> None:
        pdf = self._cut_pdf_var.get().strip()
        if not pdf:
            messagebox.showerror("Erro", "Selecione um arquivo PDF.")
            return
        if not os.path.isfile(pdf):
            messagebox.showerror("Erro", f"PDF não encontrado:\n{pdf}")
            return
        pag_str = self._cut_pag_var.get().strip()
        if not pag_str:
            messagebox.showerror("Erro", "Informe as páginas a extrair.")
            return

        saida = self._cut_saida_var.get().strip()
        if not saida:
            base = os.path.splitext(os.path.basename(pdf))[0]
            saida = os.path.join(os.path.dirname(pdf),
                                 f"{base}_recorte.pdf")
            self._cut_saida_var.set(saida)

        self._btn_cortar.configure(state="disabled")
        self._cut_status_lbl.configure(text="Recortando…", text_color="gray50")
        threading.Thread(target=self._run_corte,
                         args=(pdf, pag_str, saida), daemon=True).start()

    def _run_corte(self, pdf: str, pag_str: str, saida: str) -> None:
        try:
            n = recortar_pdf(pdf, pag_str, saida)
            msg  = f"✅ {n} página{'s' if n != 1 else ''} salva{'s' if n != 1 else ''} em: {saida}"
            color = ("green3", "#4CAF50")
        except Exception as e:
            msg   = f"❌ {e}"
            color = ("#cc4444", "#ff6666")
        self.after(0, lambda: self._finalizar_corte(msg, color))

    def _finalizar_corte(self, msg: str, color) -> None:
        self._btn_cortar.configure(state="normal")
        self._cut_status_lbl.configure(text=msg, text_color=color)

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _fmt_subtitle(self) -> str:
        fmt = _FMT_BY_LBL.get(self._fmt_var.get(), "docx")
        nomes = {"docx": "Word (.docx)", "txt": "Texto (.txt)",
                 "md": "Markdown (.md)", "pdf": "PDF (.pdf)"}
        return f"PDF → {nomes.get(fmt, fmt)}"

    def _toggle_tema(self) -> None:
        nxt = "light" if self._tema_var.get() == "dark" else "dark"
        self._tema_var.set(nxt)
        self._tema_btn.configure(text=nxt)
        ctk.set_appearance_mode(nxt)
        self._config.set("tema", nxt)

    def _swap_languages(self) -> None:
        src = self._lang_src_var.get()
        self._lang_src_var.set(self._lang_dst_var.get())
        self._lang_dst_var.set(src)

    # ── Seletores de arquivo ──────────────────────────────────────────────────
    def _selecionar_pdf(self) -> None:
        path = filedialog.askopenfilename(
            title="Selecionar PDF",
            filetypes=[("PDF", "*.pdf"), ("Todos", "*.*")],
            initialdir=os.path.dirname(self._pdf_var.get()) or os.getcwd(),
        )
        if path:
            self._pdf_var.set(path)
            self._config.set("ultimo_pdf", path)
            self._atualizar_total_paginas()

    def _selecionar_base(self) -> None:
        path = filedialog.askopenfilename(
            title="Selecionar .docx base",
            filetypes=[("Word", "*.docx"), ("Todos", "*.*")],
            initialdir=os.path.dirname(self._base_var.get()) or os.getcwd(),
        )
        if path:
            self._base_var.set(path)
            self._config.set("ultimo_docx", path)

    def _selecionar_saida(self) -> None:
        fmt = _FMT_BY_LBL.get(self._fmt_var.get(), "docx")
        ext_map = {"docx": (".docx", "Word", "*.docx"),
                   "txt":  (".txt",  "Texto", "*.txt"),
                   "md":   (".md",   "Markdown", "*.md"),
                   "pdf":  (".pdf",  "PDF", "*.pdf")}
        def_ext, tipo_nome, tipo_glob = ext_map.get(fmt, (".docx", "Word", "*.docx"))
        path = filedialog.asksaveasfilename(
            title="Salvar como…",
            defaultextension=def_ext,
            filetypes=[(tipo_nome, tipo_glob), ("Todos", "*.*")],
            initialdir=os.path.dirname(self._saida_var.get()) or os.getcwd(),
        )
        if path:
            self._saida_var.set(path)
            self._config.set("ultima_saida", path)

    def _atualizar_total_paginas(self) -> None:
        pdf = self._pdf_var.get()
        if not pdf or not os.path.isfile(pdf):
            self._total_var.set("")
            return
        try:
            with pdfplumber.open(pdf) as p:
                total = len(p.pages)
            self._total_var.set(f"{total} páginas")
            self._pag_fim_var.set(str(total))
        except Exception:
            self._total_var.set("(não foi possível ler o PDF)")
            return
        self._preview.abrir(pdf)

    def _todas_paginas(self) -> None:
        pdf = self._pdf_var.get()
        if not pdf or not os.path.isfile(pdf):
            return
        try:
            with pdfplumber.open(pdf) as p:
                self._pag_fim_var.set(str(len(p.pages)))
            self._pag_ini_var.set("1")
        except Exception:
            pass

    # ── Modo / Formato / Tema ─────────────────────────────────────────────────
    def _on_modo_change(self, value: str = None) -> None:
        modo_lbl = self._modo_var.get()
        if modo_lbl in ("Continuar", "Substituir"):
            if not self._base_visible:
                self._base_frame.pack(fill="x", padx=16, pady=(0, 8),
                                      after=self._modo_seg)
                self._base_visible = True
        else:
            if self._base_visible:
                self._base_frame.pack_forget()
                self._base_visible = False

    def _on_fmt_change(self, value: str = None) -> None:
        fmt = _FMT_BY_LBL.get(self._fmt_var.get(), "docx")
        self._config.set("fmt", fmt)
        saida = self._saida_var.get().strip()
        if saida:
            base = os.path.splitext(saida)[0]
            ext  = {"docx": ".docx", "txt": ".txt", "md": ".md", "pdf": ".pdf"}.get(fmt, ".docx")
            self._saida_var.set(base + ext)
        if hasattr(self, "_subtitle_lbl"):
            self._subtitle_lbl.configure(text=self._fmt_subtitle())

    # ── Log ───────────────────────────────────────────────────────────────────
    def _flush_log(self) -> None:
        try:
            while True:
                texto = self._log_queue.get_nowait()
                self._log_box.configure(state="normal")
                self._log_box.insert("end", texto)
                self._log_box.see("end")
                self._log_box.configure(state="disabled")
                m = re.search(r"\[(\d+)/(\d+)\]", texto)
                if m:
                    atual, total = int(m.group(1)), int(m.group(2))
                    self._progress.set(atual / total)
                    self._lbl_status.configure(text=f"Página {atual} de {total}")
        except queue.Empty:
            pass
        self._after_flush = self.after(100, self._flush_log)

    def _log(self, msg: str) -> None:
        self._log_box.configure(state="normal")
        self._log_box.insert("end", msg + "\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _limpar_log(self) -> None:
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

    # ── Validação e coleta ────────────────────────────────────────────────────
    def _collect_config(self) -> TranslationConfig | None:
        pdf = self._pdf_var.get().strip()
        if not pdf:
            messagebox.showerror("Erro", "Selecione um arquivo PDF.")
            return None
        if not os.path.isfile(pdf):
            messagebox.showerror("Erro", f"PDF não encontrado:\n{pdf}")
            return None
        try:
            ini = int(self._pag_ini_var.get())
            fim = int(self._pag_fim_var.get())
            if ini < 1 or fim < ini:
                raise ValueError
        except ValueError:
            messagebox.showerror("Erro", "Intervalo de páginas inválido.")
            return None

        modo = _MODO_BY_LBL.get(self._modo_var.get(), "novo")
        base: str | None = None
        if modo in ("append", "replace"):
            base = self._base_var.get().strip() or None
            if not base:
                messagebox.showerror("Erro", "Selecione o arquivo .docx base.")
                return None
            if not os.path.isfile(base):
                messagebox.showerror("Erro", f"Arquivo base não encontrado:\n{base}")
                return None

        fmt   = _FMT_BY_LBL.get(self._fmt_var.get(), "docx")
        saida = self._saida_var.get().strip()
        ext   = {"docx": ".docx", "txt": ".txt", "md": ".md", "pdf": ".pdf"}.get(fmt, ".docx")
        if not saida:
            nome_base = os.path.splitext(os.path.basename(pdf))[0]
            saida = (
                os.path.join(os.path.dirname(pdf),
                             f"{nome_base}_p{ini}-p{fim}{ext}")
                if modo == "novo" else base
            )

        lang_src = _lang_code(self._lang_src_var.get().strip()) or "en"
        lang_dst = _lang_code(self._lang_dst_var.get().strip()) or "pt"
        self._config.set("lang_src", lang_src)
        self._config.set("lang_dst", lang_dst)
        self._config.set("fmt", fmt)
        self._config.set("modo", modo)
        return TranslationConfig(pdf=pdf, pag_ini=ini, pag_fim=fim,
                                 modo=modo, base=base, saida=saida,
                                 lang_src=lang_src, lang_dst=lang_dst, fmt=fmt)

    # ── Execução ──────────────────────────────────────────────────────────────
    def _iniciar(self) -> None:
        cfg = self._collect_config()
        if cfg is None:
            return

        self._tabview.set("Log")
        self._log(f"▶ Iniciando tradução: páginas {cfg.pag_ini}–{cfg.pag_fim}"
                  f"  |  modo: {cfg.modo.upper()}  |  {cfg.lang_src} → {cfg.lang_dst}"
                  f"  |  {cfg.fmt.upper()}")
        self._log(f"  Saída: {cfg.saida}\n")
        self._progress.set(0)
        self._lbl_status.configure(text="Iniciando…")
        self._btn_traduzir.configure(state="disabled")
        self._btn_cancelar.configure(state="normal")
        self._cancel_event.clear()
        self._log_redirector.install()

        self._worker = threading.Thread(target=self._run_worker, args=(cfg,), daemon=True)
        self._worker.start()

    def _run_worker(self, cfg: TranslationConfig) -> None:
        try:
            processar(cfg.pdf, cfg.pag_ini, cfg.pag_fim, cfg.saida, cfg.modo, cfg.base,
                      cancel_event=self._cancel_event,
                      lang_src=cfg.lang_src, lang_dst=cfg.lang_dst, fmt=cfg.fmt)
            self._log_queue.put(f"\n✅ Concluído! Arquivo salvo em:\n   {cfg.saida}\n")
        except Exception as e:
            self._log_queue.put(f"\n❌ Erro: {e}\n")
        finally:
            self._log_redirector.uninstall()
            self.after(0, self._finalizar)

    def _finalizar(self) -> None:
        self._btn_traduzir.configure(state="normal")
        self._btn_cancelar.configure(state="disabled")
        self._progress.set(1)
        self._lbl_status.configure(
            text="Concluído" if not self._cancel_event.is_set() else "Cancelado")

    def _cancelar(self) -> None:
        self._cancel_event.set()
        self._log("\n⚠️  Cancelamento solicitado — aguardando fim da página atual…\n")
        self._btn_cancelar.configure(state="disabled")
        self._lbl_status.configure(text="Cancelando…")

    # ── Encerramento ──────────────────────────────────────────────────────────
    def on_close(self) -> None:
        self._cancel_event.set()
        self._preview.fechar()
        self.after_cancel(self._after_flush)
        self.destroy()


