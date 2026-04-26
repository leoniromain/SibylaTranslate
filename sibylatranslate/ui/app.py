import os
import re
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

from PIL import Image, ImageTk
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

    # ── Sidebar ───────────────────────────────────────────────────────────────
    def _build_sidebar(self) -> None:
        sb = ctk.CTkFrame(self, width=_SIDEBAR_W, corner_radius=0)
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_propagate(False)
        sb.columnconfigure(0, weight=1)
        sb.rowconfigure(1, weight=1)

        # ── App name + tema toggle (topo) ─────────────────────────────────────
        app_hdr = ctk.CTkFrame(sb, fg_color="transparent")
        app_hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 0))
        ctk.CTkLabel(app_hdr, text="SibylaTranslate",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")
        self._tema_btn = ctk.CTkButton(
            app_hdr, text=self._tema_var.get(), width=56, height=24,
            font=ctk.CTkFont(size=10), fg_color="gray20", hover_color="gray30",
            corner_radius=6, command=self._toggle_tema)
        self._tema_btn.pack(side="right")

        # ── Scrollable fields ─────────────────────────────────────────────────
        scroll = ctk.CTkScrollableFrame(sb, fg_color="transparent", scrollbar_button_color="gray25")
        scroll.grid(row=1, column=0, sticky="nsew")
        scroll.columnconfigure(0, weight=1)
        self._build_fields(scroll)

        # ── Progress bar ──────────────────────────────────────────────────────
        self._progress = ctk.CTkProgressBar(sb, height=4, corner_radius=2)
        self._progress.set(0)
        self._progress.grid(row=2, column=0, sticky="ew", padx=16, pady=(8, 2))

        # ── Status + limpar ───────────────────────────────────────────────────
        stat_row = ctk.CTkFrame(sb, fg_color="transparent")
        stat_row.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 6))
        self._lbl_status = ctk.CTkLabel(
            stat_row, text="Pronto para traduzir",
            text_color="gray50", font=ctk.CTkFont(size=11), anchor="w")
        self._lbl_status.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(stat_row, text="limpar", width=46, height=20,
                      fg_color="transparent", text_color="gray50",
                      hover_color=("gray80", "gray30"), font=ctk.CTkFont(size=11),
                      command=self._limpar_log).pack(side="right")

        # ── Traduzir / Cancelar ───────────────────────────────────────────────
        btn_row = ctk.CTkFrame(sb, fg_color="transparent")
        btn_row.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 16))
        btn_row.columnconfigure(0, weight=1)
        btn_row.columnconfigure(1, weight=1)

        self._btn_traduzir = ctk.CTkButton(
            btn_row, text="▶  Traduzir", height=42,
            font=ctk.CTkFont(size=13, weight="bold"), command=self._iniciar)
        self._btn_traduzir.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self._btn_cancelar = ctk.CTkButton(
            btn_row, text="✕  Cancelar", height=42,
            fg_color="#7a1010", hover_color="#5e0c0c",
            command=self._cancelar, state="disabled")
        self._btn_cancelar.grid(row=0, column=1, sticky="ew", padx=(4, 0))

    def _section_header(self, parent, text: str, icon: str = "") -> None:
        """Seção: ícone + rótulo + linha."""
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(fill="x", padx=14, pady=(14, 5))
        lbl_text = f"{icon} {text}" if icon else text
        ctk.CTkLabel(f, text=lbl_text,
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color="gray55").pack(side="left")
        ctk.CTkFrame(f, height=1, fg_color="gray22").pack(
            side="left", fill="x", expand=True, padx=(8, 0))

    def _build_fields(self, parent) -> None:

        # ══ ARQUIVO ══════════════════════════════════════════════════════════
        self._section_header(parent, "ARQUIVO", "📁")

        # Card com miniatura + nome + info + toggle open/close
        pdf_card = ctk.CTkFrame(parent, corner_radius=8)
        pdf_card.pack(fill="x", padx=14, pady=(0, 6))
        pdf_card.columnconfigure(1, weight=1)

        self._pdf_var = tk.StringVar(value="")

        # Ícone PDF (miniatura simples)
        ctk.CTkLabel(pdf_card, text="📄", font=ctk.CTkFont(size=28),
                     width=44).grid(row=0, column=0, rowspan=2,
                                    padx=(10, 4), pady=(10, 10))

        # Nome truncado + info
        self._pdf_name_lbl = ctk.CTkLabel(
            pdf_card, text=self._pdf_short_name(),
            font=ctk.CTkFont(size=12, weight="bold"), anchor="w")
        self._pdf_name_lbl.grid(row=0, column=1, sticky="ew",
                                padx=(0, 4), pady=(10, 0))

        self._total_var = tk.StringVar(value="")
        ctk.CTkLabel(pdf_card, textvariable=self._total_var,
                     text_color="gray50", font=ctk.CTkFont(size=10),
                     anchor="w").grid(row=1, column=1, sticky="ew",
                                      padx=(0, 4), pady=(0, 10))

        # Botão … para abrir
        ctk.CTkButton(pdf_card, text="…", width=30, height=26,
                      command=self._selecionar_pdf).grid(
            row=0, column=2, rowspan=2, padx=(0, 10))

        # Entry oculto (usado internamente, não exibido)
        self._pdf_entry_hidden = ctk.CTkEntry(parent, textvariable=self._pdf_var,
                                              height=0, width=0, fg_color="transparent",
                                              border_width=0)
        # não é packed — apenas mantém o StringVar

        # Intervalo de páginas
        ctk.CTkLabel(parent, text="Intervalo de páginas",
                     font=ctk.CTkFont(size=10), text_color="gray55",
                     anchor="w").pack(fill="x", padx=14, pady=(2, 4))

        pag_row = ctk.CTkFrame(parent, fg_color="transparent")
        pag_row.pack(fill="x", padx=14, pady=(0, 4))

        self._pag_ini_var = tk.StringVar(value="1")
        self._pag_fim_var = tk.StringVar(value="5")
        ctk.CTkEntry(pag_row, textvariable=self._pag_ini_var,
                     width=60, justify="center",
                     font=ctk.CTkFont(size=12)).pack(side="left")
        ctk.CTkLabel(pag_row, text="até",
                     text_color="gray50", font=ctk.CTkFont(size=11)).pack(
            side="left", padx=8)
        ctk.CTkEntry(pag_row, textvariable=self._pag_fim_var,
                     width=60, justify="center",
                     font=ctk.CTkFont(size=12)).pack(side="left")
        ctk.CTkButton(pag_row, text="Todas", width=72, height=30,
                      fg_color=("gray85", "gray25"), text_color=("gray10", "gray90"),
                      hover_color=("gray75", "gray35"),
                      font=ctk.CTkFont(size=11),
                      command=self._todas_paginas).pack(side="left", padx=(10, 0))

        # ══ IDIOMA ═══════════════════════════════════════════════════════════
        self._section_header(parent, "IDIOMA", "🌐")

        lang_row = ctk.CTkFrame(parent, fg_color="transparent")
        lang_row.pack(fill="x", padx=14, pady=(0, 2))
        lang_row.columnconfigure(0, weight=1)
        lang_row.columnconfigure(2, weight=1)

        saved_src = self._config.get("lang_src", "en")
        saved_dst = self._config.get("lang_dst", "pt")
        self._lang_src_var = tk.StringVar(
            value=_DISPLAY_BY_CODE.get(saved_src, saved_src))
        self._lang_dst_var = tk.StringVar(
            value=_DISPLAY_BY_CODE.get(saved_dst, saved_dst))

        _LangPicker(lang_row, variable=self._lang_src_var, width=110).grid(
            row=0, column=0, sticky="ew")
        ctk.CTkButton(lang_row, text="⇌", width=32, height=28,
                      fg_color="transparent", hover_color=("gray75", "gray30"),
                      font=ctk.CTkFont(size=14),
                      command=self._swap_languages).grid(row=0, column=1, padx=4)
        _LangPicker(lang_row, variable=self._lang_dst_var, width=110).grid(
            row=0, column=2, sticky="ew")

        # Label "Idioma detectado" (placeholder; pode ser atualizado após análise)
        self._lang_detect_lbl = ctk.CTkLabel(
            parent, text="", font=ctk.CTkFont(size=10),
            text_color=("#2db862", "#3dcf76"), anchor="w")
        self._lang_detect_lbl.pack(fill="x", padx=14, pady=(3, 2))

        # ══ ESTIMATIVA ═══════════════════════════════════════════════════════
        self._section_header(parent, "ESTIMATIVA", "⚡")

        est_card = ctk.CTkFrame(parent, corner_radius=8)
        est_card.pack(fill="x", padx=14, pady=(0, 6))
        est_card.columnconfigure(0, weight=1)
        est_card.columnconfigure(1, weight=1)

        self._est_duracao_var = tk.StringVar(value="—")
        self._est_palavras_var = tk.StringVar(value="—")
        self._est_tokens_var  = tk.StringVar(value="—")
        self._est_custo_var   = tk.StringVar(value="—")

        for r, (lbl, var, accent) in enumerate([
            ("Duração",    self._est_duracao_var,  False),
            ("Palavras",   self._est_palavras_var, True),
            ("Tokens",     self._est_tokens_var,   False),
            ("Custo est.", self._est_custo_var,    True),
        ]):
            col = r % 2
            row = r // 2
            cell = ctk.CTkFrame(est_card, fg_color="transparent")
            cell.grid(row=row, column=col, sticky="ew",
                      padx=12, pady=(10 if row == 0 else 0, 10 if row == 1 else 0))
            ctk.CTkLabel(cell, text=lbl, font=ctk.CTkFont(size=10),
                         text_color="gray50", anchor="w").pack(anchor="w")
            tc = ("#1a8cff", "#5EB3FF") if accent else ("gray80", "gray80")
            ctk.CTkLabel(cell, textvariable=var,
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color=tc, anchor="w").pack(anchor="w")

        # ══ SAÍDA ════════════════════════════════════════════════════════════
        self._section_header(parent, "SAÍDA", "📤")

        # Modo
        ctk.CTkLabel(parent, text="Modo", font=ctk.CTkFont(size=10),
                     text_color="gray55", anchor="w").pack(fill="x", padx=14, pady=(0, 3))
        self._modo_seg = ctk.CTkSegmentedButton(
            parent, values=_MODO_LABELS, variable=self._modo_var,
            command=self._on_modo_change, font=ctk.CTkFont(size=11), height=30)
        self._modo_seg.pack(fill="x", padx=14, pady=(0, 8))

        # base frame (hidden until append/replace)
        self._base_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self._base_var = tk.StringVar(value=self._config.get("ultimo_docx", ""))
        bf_inner = ctk.CTkFrame(self._base_frame, corner_radius=8)
        bf_inner.pack(fill="x")
        bf_inner.columnconfigure(1, weight=1)
        ctk.CTkLabel(bf_inner, text="📄", width=28,
                     font=ctk.CTkFont(size=13)).grid(row=0, column=0, padx=(8, 2), pady=6)
        ctk.CTkEntry(bf_inner, textvariable=self._base_var,
                     placeholder_text="Selecione o .docx base…").grid(
            row=0, column=1, sticky="ew", padx=(0, 4), pady=6)
        ctk.CTkButton(bf_inner, text="…", width=28, height=24,
                      command=self._selecionar_base).grid(
            row=0, column=2, padx=(0, 8), pady=6)
        self._base_visible = False

        # Formato
        ctk.CTkLabel(parent, text="Formato", font=ctk.CTkFont(size=10),
                     text_color="gray55", anchor="w").pack(fill="x", padx=14, pady=(0, 3))
        ctk.CTkSegmentedButton(
            parent, values=_FMT_LABELS, variable=self._fmt_var,
            command=self._on_fmt_change, font=ctk.CTkFont(size=11), height=30,
        ).pack(fill="x", padx=14, pady=(0, 8))

        # Arquivo de saída
        ctk.CTkLabel(parent, text="Arquivo de saída", font=ctk.CTkFont(size=10),
                     text_color="gray55", anchor="w").pack(fill="x", padx=14, pady=(0, 3))
        out_card = ctk.CTkFrame(parent, corner_radius=8)
        out_card.pack(fill="x", padx=14, pady=(0, 6))
        out_card.columnconfigure(0, weight=1)

        self._saida_var = tk.StringVar(value=self._config.get("ultima_saida", ""))
        self._saida_name_lbl = ctk.CTkLabel(
            out_card, text=self._saida_short_name(),
            font=ctk.CTkFont(size=11), anchor="w", text_color="gray80")
        self._saida_name_lbl.grid(row=0, column=0, sticky="ew",
                                   padx=(10, 4), pady=8)
        ctk.CTkButton(out_card, text="…", width=28, height=24,
                      command=self._selecionar_saida).grid(
            row=0, column=1, padx=(0, 10), pady=8)
        self._saida_var.trace_add("write", lambda *_: self._saida_name_lbl.configure(
            text=self._saida_short_name()))

        # ══ GLOSSÁRIO ════════════════════════════════════════════════════════
        self._section_header(parent, "GLOSSÁRIO", "✏️")

        gloss_row = ctk.CTkFrame(parent, fg_color="transparent")
        gloss_row.pack(fill="x", padx=14, pady=(0, 6))
        gloss_row.columnconfigure(0, weight=1)

        self._gloss_entry_var = tk.StringVar()
        ctk.CTkEntry(gloss_row, textvariable=self._gloss_entry_var,
                     placeholder_text="ex: Sibyla1",
                     height=30).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(gloss_row, text="+ Add", width=64, height=30,
                      command=self._gloss_add).grid(row=0, column=1)

        # chips container
        self._gloss_chips_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self._gloss_chips_frame.pack(fill="x", padx=14, pady=(0, 8))

        self._gloss_terms: list[str] = self._config.get("glossario", [])
        self._gloss_chip_widgets: dict[str, ctk.CTkFrame] = {}
        for term in self._gloss_terms:
            self._gloss_render_chip(term)


    # ── Main area (tabbed) ────────────────────────────────────────────────────
    def _build_main_area(self) -> None:
        self._tabview = ctk.CTkTabview(self, anchor="nw",
                                       command=self._on_tab_change)
        self._tabview.grid(row=0, column=1, sticky="nsew", padx=(0, 12), pady=(12, 12))

        for tab_name in ("Comparar", "Original", "Traduzido", "Log", "Histórico", "✂ Recortar"):
            self._tabview.add(tab_name)

        # ── Comparar ──────────────────────────────────────────────────────────
        self._build_compare_tab(self._tabview.tab("Comparar"))

        # ── Original (preview PDF) ────────────────────────────────────────────
        tab_orig = self._tabview.tab("Original")
        tab_orig.columnconfigure(0, weight=1)
        tab_orig.rowconfigure(0, weight=1)
        self._preview = PreviewPanel(tab_orig)
        self._preview.grid(row=0, column=0, sticky="nsew")

        # ── Traduzido (placeholder) ───────────────────────────────────────────
        tab_trad = self._tabview.tab("Traduzido")
        tab_trad.columnconfigure(0, weight=1)
        tab_trad.rowconfigure(0, weight=1)
        self._trad_box = ctk.CTkTextbox(
            tab_trad, font=ctk.CTkFont(family="Georgia", size=12),
            wrap="word", state="disabled")
        self._trad_box.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        # ── Log ───────────────────────────────────────────────────────────────
        tab_log = self._tabview.tab("Log")
        tab_log.columnconfigure(0, weight=1)
        tab_log.rowconfigure(1, weight=1)

        log_hdr = ctk.CTkFrame(tab_log, fg_color="transparent")
        log_hdr.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 2))
        ctk.CTkLabel(log_hdr, text="Log de execução",
                     font=ctk.CTkFont(size=12), text_color="gray60").pack(side="left")
        ctk.CTkButton(log_hdr, text="Limpar", width=70, height=24,
                      command=self._limpar_log).pack(side="right")

        self._log_box = ctk.CTkTextbox(
            tab_log, font=ctk.CTkFont(family="Courier", size=11),
            wrap="word", state="disabled")
        self._log_box.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

        # ── Histórico (placeholder) ───────────────────────────────────────────
        tab_hist = self._tabview.tab("Histórico")
        tab_hist.columnconfigure(0, weight=1)
        tab_hist.rowconfigure(0, weight=1)
        ctk.CTkLabel(tab_hist, text="Histórico de traduções",
                     font=ctk.CTkFont(size=13), text_color="gray50").grid(
            row=0, column=0)

        # ── Recortar ─────────────────────────────────────────────────────────
        self._build_cutter_tab(self._tabview.tab("✂ Recortar"))

    # ── Comparar tab ──────────────────────────────────────────────────────────
    def _build_compare_tab(self, tab) -> None:
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(1, weight=1)

        # ── Headers ────────────────────────────────────────────────────────
        orig_hdr = ctk.CTkFrame(tab, fg_color="transparent")
        orig_hdr.grid(row=0, column=0, sticky="ew", padx=(8, 4), pady=(6, 2))
        self._cmp_orig_lbl = ctk.CTkLabel(
            orig_hdr, text="ORIGINAL · EN",
            font=ctk.CTkFont(size=10, weight="bold"), text_color="gray55")
        self._cmp_orig_lbl.pack(side="left")

        trad_hdr = ctk.CTkFrame(tab, fg_color="transparent")
        trad_hdr.grid(row=0, column=1, sticky="ew", padx=(4, 8), pady=(6, 2))
        self._cmp_trad_lbl = ctk.CTkLabel(
            trad_hdr, text="TRADUZIDO · PT",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=("#1a8cff", "#5EB3FF"))
        self._cmp_trad_lbl.pack(side="left")

        # ── PDF canvases ────────────────────────────────────────────────────
        bg = "#1e1e1e"
        self._cmp_orig_canvas = tk.Canvas(tab, bg=bg, highlightthickness=0)
        self._cmp_orig_canvas.grid(row=1, column=0, sticky="nsew",
                                   padx=(8, 4), pady=(0, 0))
        self._cmp_orig_canvas.bind("<Configure>", lambda _e: self._cmp_render())

        self._cmp_trad_canvas = tk.Canvas(tab, bg=bg, highlightthickness=0)
        self._cmp_trad_canvas.grid(row=1, column=1, sticky="nsew",
                                   padx=(4, 8), pady=(0, 0))
        self._cmp_trad_canvas.bind("<Configure>", lambda _e: self._cmp_render())

        # ── Shared navigation + status bar ─────────────────────────────────
        bottom = ctk.CTkFrame(tab, height=36, corner_radius=0,
                              fg_color=("gray90", "gray15"))
        bottom.grid(row=2, column=0, columnspan=2, sticky="ew")
        bottom.columnconfigure(0, weight=1)
        bottom.columnconfigure(2, weight=1)

        ctk.CTkButton(bottom, text="◀", width=32, height=26,
                      command=lambda: self._cmp_nav(-1)).grid(
            row=0, column=0, sticky="e", padx=(12, 4), pady=5)
        self._cmp_pag_lbl = ctk.CTkLabel(
            bottom, text="— / —", font=ctk.CTkFont(size=11), width=70)
        self._cmp_pag_lbl.grid(row=0, column=1)
        ctk.CTkButton(bottom, text="▶", width=32, height=26,
                      command=lambda: self._cmp_nav(1)).grid(
            row=0, column=2, sticky="w", padx=(4, 12), pady=5)

        self._cmp_status_lbl = ctk.CTkLabel(
            bottom, text="Pronto.",
            font=ctk.CTkFont(size=10), text_color="gray50")
        self._cmp_status_lbl.grid(row=0, column=3, sticky="e", padx=16)

        # ── Internal state ─────────────────────────────────────────────────
        self._cmp_page        = 1
        self._cmp_total       = 0
        self._cmp_fitz_orig   = None   # fitz.Document original
        self._cmp_fitz_trad   = None   # fitz.Document traduzido (se PDF)
        self._cmp_pages_trad: list[str] = []  # fallback texto
        self._cmp_photo_orig  = None   # evita GC
        self._cmp_photo_trad  = None
        self._cmp_orig_img_id = None
        self._cmp_trad_img_id = None

    def _cmp_nav(self, delta: int) -> None:
        if not self._cmp_total:
            return
        self._cmp_page = max(1, min(self._cmp_total, self._cmp_page + delta))
        self._cmp_render()

    def _cmp_render(self) -> None:
        t = self._cmp_total
        p = self._cmp_page
        self._cmp_pag_lbl.configure(text=f"{p} / {t}" if t else "— / —")

        self._cmp_render_side(
            self._cmp_orig_canvas,
            self._cmp_fitz_orig, p,
            "_cmp_photo_orig", "_cmp_orig_img_id",
            fallback=None)

        trad_text = (self._cmp_pages_trad[p - 1]
                     if self._cmp_pages_trad and p <= len(self._cmp_pages_trad)
                     else None)
        self._cmp_render_side(
            self._cmp_trad_canvas,
            self._cmp_fitz_trad, p,
            "_cmp_photo_trad", "_cmp_trad_img_id",
            fallback=trad_text)

    def _cmp_render_side(self, canvas: tk.Canvas, doc, page_num: int,
                         photo_attr: str, img_id_attr: str,
                         fallback: str | None) -> None:
        cw = canvas.winfo_width()
        ch = canvas.winfo_height()
        if cw < 10 or ch < 10:
            return
        canvas.delete("all")
        setattr(self, img_id_attr, None)

        if doc and self._cmp_total and page_num <= len(doc):
            # Render PDF page
            page = doc[page_num - 1]
            pr = page.rect
            scale = min(cw / pr.width, ch / pr.height) * 0.97
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            photo = ImageTk.PhotoImage(img)
            setattr(self, photo_attr, photo)
            img_id = canvas.create_image(cw // 2, ch // 2, anchor="center",
                                         image=photo)
            setattr(self, img_id_attr, img_id)
        elif fallback is not None:
            # Render text fallback
            pad = 20
            canvas.create_text(pad, pad, anchor="nw", text=fallback,
                                fill="#cccccc", font=("Georgia", 12),
                                width=max(10, cw - pad * 2))
        else:
            # Empty placeholder
            canvas.create_text(cw // 2, ch // 2, anchor="center",
                                text="Sem conteúdo", fill="#555555",
                                font=("Helvetica", 11))

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
    def _pdf_short_name(self) -> str:
        p = self._pdf_var.get()
        if not p:
            return "Nenhum arquivo selecionado"
        name = os.path.basename(p)
        return name[:28] + "…" if len(name) > 30 else name

    def _saida_short_name(self) -> str:
        p = self._saida_var.get()
        if not p:
            return "nome automático"
        name = os.path.basename(p)
        return name[:28] + "…" if len(name) > 30 else name

    def _pdf_size_str(self) -> str:
        try:
            sz = os.path.getsize(self._pdf_var.get())
            if sz >= 1_048_576:
                return f"{sz/1_048_576:.1f} MB"
            return f"{sz/1024:.0f} KB"
        except Exception:
            return ""

    def _fmt_subtitle(self) -> str:
        fmt = _FMT_BY_LBL.get(self._fmt_var.get(), "docx")
        nomes = {"docx": "Word (.docx)", "txt": "Texto (.txt)",
                 "md": "Markdown (.md)", "pdf": "PDF (.pdf)"}
        return f"PDF → {nomes.get(fmt, fmt)}"

    # ── Glossário ─────────────────────────────────────────────────────────────
    def _gloss_add(self) -> None:
        term = self._gloss_entry_var.get().strip()
        if not term or term in self._gloss_terms:
            self._gloss_entry_var.set("")
            return
        self._gloss_terms.append(term)
        self._config.set("glossario", self._gloss_terms)
        self._gloss_render_chip(term)
        self._gloss_entry_var.set("")

    def _gloss_render_chip(self, term: str) -> None:
        chip = ctk.CTkFrame(self._gloss_chips_frame, corner_radius=12,
                            fg_color=("gray80", "gray25"))
        chip.pack(side="left", padx=(0, 4), pady=2)
        ctk.CTkLabel(chip, text=term, font=ctk.CTkFont(size=10),
                     padx=8).pack(side="left")
        ctk.CTkButton(chip, text="×", width=18, height=18,
                      fg_color="transparent", text_color="gray50",
                      hover_color=("gray70", "gray35"),
                      font=ctk.CTkFont(size=11),
                      command=lambda t=term: self._gloss_remove(t)).pack(side="left", padx=(0, 4))
        self._gloss_chip_widgets[term] = chip

    def _gloss_remove(self, term: str) -> None:
        if term in self._gloss_terms:
            self._gloss_terms.remove(term)
            self._config.set("glossario", self._gloss_terms)
        w = self._gloss_chip_widgets.pop(term, None)
        if w:
            w.destroy()

    def _update_estimativa(self) -> None:
        """Dispara cálculo de estimativa em thread de fundo para não travar a UI."""
        pdf = self._pdf_var.get()
        if not pdf or not os.path.isfile(pdf):
            return
        try:
            ini = int(self._pag_ini_var.get())
            fim = int(self._pag_fim_var.get())
        except ValueError:
            return
        self._est_duracao_var.set("calculando…")
        threading.Thread(
            target=self._calc_estimativa_bg,
            args=(pdf, ini, fim),
            daemon=True,
        ).start()

    def _calc_estimativa_bg(self, pdf: str, ini: int, fim: int) -> None:
        """Executa em thread de fundo; atualiza widgets via after()."""
        try:
            with pdfplumber.open(pdf) as p:
                palavras = 0
                for pg in p.pages[ini - 1: fim]:
                    txt = pg.extract_text() or ""
                    palavras += len(txt.split())
        except Exception:
            self.after(0, lambda: self._est_duracao_var.set("erro"))
            return
        n_pag = max(1, fim - ini + 1)
        minutos = max(1, round(n_pag * 0.8))
        tokens  = round(palavras * 1.3 / 1000)
        custo   = tokens * 0.002
        def _apply() -> None:
            self._est_duracao_var.set(f"~{minutos} min")
            self._est_palavras_var.set(f"{palavras:,}".replace(",", "."))
            self._est_tokens_var.set(f"~{tokens}k")
            self._est_custo_var.set(f"~${custo:.2f}")
        self.after(0, _apply)

    def _on_tab_change(self) -> None:
        if self._tabview.get() == "Original":
            self.after(50, self._preview.renderizar)

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
            self._pdf_name_lbl.configure(text=self._pdf_short_name())
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
            self._total_var.set(f"{total} páginas  ·  {self._pdf_size_str()}")
            self._pag_fim_var.set(str(total))
        except Exception:
            self._total_var.set("(não foi possível ler o PDF)")
            return
        self._preview.abrir(pdf)
        self._tabview.set("Original")
        self.after(300, self._update_estimativa)

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
            # Populate compare view with original text
            self.after(0, lambda: self._populate_compare(cfg))
        except Exception as e:
            self._log_queue.put(f"\n❌ Erro: {e}\n")
        finally:
            self._log_redirector.uninstall()
            self.after(0, self._finalizar)

    def _populate_compare(self, cfg: TranslationConfig) -> None:
        """Abre original e traduzido como fitz docs e preenche o painel Comparar."""
        # Fecha docs anteriores
        for attr in ("_cmp_fitz_orig", "_cmp_fitz_trad"):
            doc = getattr(self, attr, None)
            if doc:
                try:
                    doc.close()
                except Exception:
                    pass
            setattr(self, attr, None)
        self._cmp_pages_trad = []

        # Abre original
        try:
            self._cmp_fitz_orig = fitz.open(cfg.pdf)
            self._cmp_total = len(self._cmp_fitz_orig)
        except Exception:
            self._cmp_fitz_orig = None
            self._cmp_total = 0

        # Abre traduzido (se for PDF) ou lê texto como fallback
        if cfg.fmt == "pdf" and os.path.isfile(cfg.saida):
            try:
                self._cmp_fitz_trad = fitz.open(cfg.saida)
            except Exception:
                self._cmp_fitz_trad = None
        else:
            self._cmp_pages_trad = self._read_translated_pages(cfg.saida, cfg.fmt)

        self._cmp_page = 1
        self._cmp_orig_lbl.configure(text=f"ORIGINAL · {cfg.lang_src.upper()}")
        self._cmp_trad_lbl.configure(text=f"TRADUZIDO · {cfg.lang_dst.upper()}")
        if self._cmp_total:
            self._cmp_status_lbl.configure(text=f"{self._cmp_total} páginas")

        # Preenche aba Traduzido com texto
        full_trad_pages = self._read_translated_pages(cfg.saida, cfg.fmt)
        full_trad = "\n\n".join(full_trad_pages)
        self._trad_box.configure(state="normal")
        self._trad_box.delete("1.0", "end")
        self._trad_box.insert("1.0", full_trad)
        self._trad_box.configure(state="disabled")

        self._tabview.set("Comparar")
        self.after(80, self._cmp_render)

    def _read_translated_pages(self, saida: str, fmt: str) -> list[str]:
        """Lê o arquivo de saída e retorna lista de páginas (melhor esforço)."""
        if not saida or not os.path.isfile(saida):
            return []
        try:
            if fmt in ("txt", "md"):
                text = open(saida, encoding="utf-8").read()
                # Separa por form-feed (\x0c) que alguns geradores inserem
                parts = [p.strip() for p in text.split("\x0c") if p.strip()]
                return parts if parts else [text.strip()]
            elif fmt == "pdf":
                with pdfplumber.open(saida) as p:
                    return [pg.extract_text() or "" for pg in p.pages]
            elif fmt == "docx":
                from docx import Document  # já é dependência do projeto
                doc = Document(saida)
                paragraphs = [par.text for par in doc.paragraphs]
                # Tenta quebrar em "páginas" por parágrafos em branco duplos
                pages, current = [], []
                for line in paragraphs:
                    if line.strip() == "":
                        if current:
                            pages.append("\n".join(current))
                            current = []
                    else:
                        current.append(line)
                if current:
                    pages.append("\n".join(current))
                return pages if pages else ["\n".join(paragraphs)]
        except Exception:
            pass
        return []

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
        for attr in ("_cmp_fitz_orig", "_cmp_fitz_trad"):
            doc = getattr(self, attr, None)
            if doc:
                try:
                    doc.close()
                except Exception:
                    pass
        self.after_cancel(self._after_flush)
        self.destroy()


