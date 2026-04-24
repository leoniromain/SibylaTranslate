import os
import re
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk
import pdfplumber

from ..models import TranslationConfig
from ..config import AppConfig
from ..engine import processar
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
        self.geometry("1200x700")
        self.minsize(960, 600)
        self.resizable(True, True)

        self._config = AppConfig.load()
        self._log_queue: queue.Queue = queue.Queue()
        self._log_redirector = LogRedirector(self._log_queue)
        self._cancel_event = threading.Event()
        self._worker: threading.Thread | None = None

        self._build_ui()
        self._after_flush = self.after(100, self._flush_log)

    # ── Build UI ────────────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=3)
        self.columnconfigure(1, weight=2)
        self.rowconfigure(3, weight=1)
        self._build_header()
        self._build_config_panel()
        self._build_action_bar()
        self._build_log_panel()
        self._build_preview_panel()
        ctk.set_appearance_mode(self._tema_var.get())
        if self._pdf_var.get():
            self.after(200, self._atualizar_total_paginas)

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=20, pady=(16, 4))
        ctk.CTkLabel(header, text="SibylaTranslate",
                     font=ctk.CTkFont(size=22, weight="bold")).pack(side="left")
        ctk.CTkLabel(header, text="PDF → Word (PT-BR)",
                     font=ctk.CTkFont(size=13), text_color="gray60").pack(side="left", padx=12)

    def _build_config_panel(self) -> None:
        cfg = ctk.CTkFrame(self)
        cfg.grid(row=1, column=0, sticky="ew", padx=(20, 6), pady=6)
        cfg.columnconfigure(1, weight=1)

        ctk.CTkLabel(cfg, text="PDF de entrada:", anchor="w").grid(
            row=0, column=0, sticky="w", padx=(14, 6), pady=(12, 4))
        self._pdf_var = tk.StringVar(value=self._config.get("ultimo_pdf", ""))
        ctk.CTkEntry(cfg, textvariable=self._pdf_var,
                     placeholder_text="Selecione o arquivo PDF…").grid(
            row=0, column=1, sticky="ew", padx=4, pady=(12, 4))
        ctk.CTkButton(cfg, text="…", width=36,
                      command=self._selecionar_pdf).grid(row=0, column=2, padx=(4, 14), pady=(12, 4))

        self._total_var = tk.StringVar(value="")
        ctk.CTkLabel(cfg, textvariable=self._total_var,
                     text_color="gray60", font=ctk.CTkFont(size=11)).grid(
            row=1, column=1, sticky="w", padx=4, pady=(0, 6))

        pag_frame = ctk.CTkFrame(cfg, fg_color="transparent")
        pag_frame.grid(row=2, column=0, columnspan=3, sticky="ew", padx=14, pady=4)
        ctk.CTkLabel(pag_frame, text="Página inicial:").pack(side="left")
        self._pag_ini_var = tk.StringVar(value="1")
        ctk.CTkEntry(pag_frame, textvariable=self._pag_ini_var, width=70).pack(side="left", padx=(6, 20))
        ctk.CTkLabel(pag_frame, text="Página final:").pack(side="left")
        self._pag_fim_var = tk.StringVar(value="5")
        ctk.CTkEntry(pag_frame, textvariable=self._pag_fim_var, width=70).pack(side="left", padx=6)
        ctk.CTkButton(pag_frame, text="Todas", width=70,
                      command=self._todas_paginas).pack(side="left", padx=(16, 0))

        lang_frame = ctk.CTkFrame(cfg, fg_color="transparent")
        lang_frame.grid(row=3, column=0, columnspan=3, sticky="ew", padx=14, pady=4)
        ctk.CTkLabel(lang_frame, text="Idioma:").pack(side="left")
        ctk.CTkLabel(lang_frame, text="Origem:").pack(side="left", padx=(12, 4))
        saved_src = self._config.get("lang_src", "en")
        saved_dst = self._config.get("lang_dst", "pt")
        self._lang_src_var = tk.StringVar(
            value=_DISPLAY_BY_CODE.get(saved_src, saved_src))
        self._lang_dst_var = tk.StringVar(
            value=_DISPLAY_BY_CODE.get(saved_dst, saved_dst))
        _LangPicker(lang_frame, variable=self._lang_src_var, width=200).pack(side="left")
        ctk.CTkLabel(lang_frame, text="→").pack(side="left", padx=8)
        ctk.CTkLabel(lang_frame, text="Destino:").pack(side="left", padx=(0, 4))
        _LangPicker(lang_frame, variable=self._lang_dst_var, width=200).pack(side="left")

        ctk.CTkFrame(cfg, height=1, fg_color="gray30").grid(
            row=4, column=0, columnspan=3, sticky="ew", padx=14, pady=8)

        modo_frame = ctk.CTkFrame(cfg, fg_color="transparent")
        modo_frame.grid(row=5, column=0, columnspan=3, sticky="ew", padx=14, pady=4)
        ctk.CTkLabel(modo_frame, text="Modo:").pack(side="left")
        self._modo_var = tk.StringVar(value="novo")
        for val, txt in [("novo", "Novo arquivo"),
                         ("append", "Continuar (Append)"),
                         ("replace", "Substituir páginas (Replace)")]:
            ctk.CTkRadioButton(modo_frame, text=txt, variable=self._modo_var, value=val,
                               command=self._on_modo_change).pack(side="left", padx=12)

        self._base_frame = ctk.CTkFrame(cfg, fg_color="transparent")
        self._base_frame.grid(row=6, column=0, columnspan=3, sticky="ew", padx=14, pady=(2, 4))
        ctk.CTkLabel(self._base_frame, text="Arquivo .docx base:").pack(side="left")
        self._base_var = tk.StringVar(value=self._config.get("ultimo_docx", ""))
        ctk.CTkEntry(self._base_frame, textvariable=self._base_var,
                     placeholder_text="Selecione o .docx existente…", width=420).pack(side="left", padx=6)
        ctk.CTkButton(self._base_frame, text="…", width=36,
                      command=self._selecionar_base).pack(side="left", padx=4)
        self._base_frame.grid_remove()

        ctk.CTkLabel(cfg, text="Arquivo de saída:", anchor="w").grid(
            row=7, column=0, sticky="w", padx=(14, 6), pady=4)
        self._saida_var = tk.StringVar(value=self._config.get("ultima_saida", ""))
        ctk.CTkEntry(cfg, textvariable=self._saida_var,
                     placeholder_text="saida.docx  (deixe vazio para nome automático)").grid(
            row=7, column=1, sticky="ew", padx=4, pady=4)
        ctk.CTkButton(cfg, text="…", width=36,
                      command=self._selecionar_saida).grid(row=7, column=2, padx=(4, 14), pady=4)

    def _build_action_bar(self) -> None:
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=2, column=0, sticky="ew", padx=(20, 6), pady=6)

        self._btn_traduzir = ctk.CTkButton(
            btn_frame, text="▶  Traduzir", width=150, height=38,
            font=ctk.CTkFont(size=14, weight="bold"), command=self._iniciar)
        self._btn_traduzir.pack(side="left", padx=(0, 10))

        self._btn_cancelar = ctk.CTkButton(
            btn_frame, text="✕  Cancelar", width=120, height=38,
            fg_color="#8B0000", hover_color="#600000",
            command=self._cancelar, state="disabled")
        self._btn_cancelar.pack(side="left")

        self._progress = ctk.CTkProgressBar(btn_frame, width=300)
        self._progress.set(0)
        self._progress.pack(side="left", padx=20)

        self._lbl_status = ctk.CTkLabel(btn_frame, text="", text_color="gray60",
                                        font=ctk.CTkFont(size=11))
        self._lbl_status.pack(side="left")

        ctk.CTkLabel(btn_frame, text="Tema:").pack(side="right", padx=(0, 4))
        self._tema_var = tk.StringVar(value=self._config.get("tema", "dark"))
        ctk.CTkOptionMenu(btn_frame, variable=self._tema_var,
                          values=["dark", "light", "system"],
                          width=90, command=self._on_tema_change).pack(side="right", padx=(0, 6))

    def _build_log_panel(self) -> None:
        log_frame = ctk.CTkFrame(self)
        log_frame.grid(row=3, column=0, sticky="nsew", padx=(20, 6), pady=(0, 14))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(1, weight=1)

        ctk.CTkLabel(log_frame, text="Log", font=ctk.CTkFont(size=12),
                     text_color="gray60").grid(row=0, column=0, sticky="w", padx=10, pady=(6, 2))
        ctk.CTkButton(log_frame, text="Limpar", width=70, height=24,
                      command=self._limpar_log).grid(row=0, column=1, sticky="e", padx=10, pady=(6, 2))

        self._log_box = ctk.CTkTextbox(log_frame, font=ctk.CTkFont(family="Courier", size=11),
                                       wrap="word", state="disabled")
        self._log_box.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=8, pady=(0, 8))

    def _build_preview_panel(self) -> None:
        self._preview = PreviewPanel(self)
        self._preview.grid(row=1, column=1, rowspan=3, sticky="nsew", padx=(6, 20), pady=(6, 14))

    # ── Seletores de arquivo ─────────────────────────────────────────────────
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
        path = filedialog.asksaveasfilename(
            title="Salvar como…",
            defaultextension=".docx",
            filetypes=[("Word", "*.docx")],
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

    # ── Modo / Tema ──────────────────────────────────────────────────────────
    def _on_modo_change(self) -> None:
        if self._modo_var.get() in ("append", "replace"):
            self._base_frame.grid()
        else:
            self._base_frame.grid_remove()

    def _on_tema_change(self, valor: str) -> None:
        ctk.set_appearance_mode(valor)
        self._config.set("tema", valor)

    # ── Log ──────────────────────────────────────────────────────────────────
    def _flush_log(self) -> None:
        """Drena a queue de log e atualiza o TextBox (roda na thread principal)."""
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

    # ── Validação e coleta ───────────────────────────────────────────────────
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
        modo = self._modo_var.get()
        base: str | None = None
        if modo in ("append", "replace"):
            base = self._base_var.get().strip() or None
            if not base:
                messagebox.showerror("Erro", "Selecione o arquivo .docx base.")
                return None
            if not os.path.isfile(base):
                messagebox.showerror("Erro", f"Arquivo base não encontrado:\n{base}")
                return None
        saida = self._saida_var.get().strip()
        if not saida:
            nome_base = os.path.splitext(os.path.basename(pdf))[0]
            saida = (
                os.path.join(os.path.dirname(pdf), f"{nome_base}_pt_p{ini}-p{fim}.docx")
                if modo == "novo" else base
            )
        lang_src = _lang_code(self._lang_src_var.get().strip()) or "en"
        lang_dst = _lang_code(self._lang_dst_var.get().strip()) or "pt"
        self._config.set("lang_src", lang_src)
        self._config.set("lang_dst", lang_dst)
        return TranslationConfig(pdf=pdf, pag_ini=ini, pag_fim=fim,
                                 modo=modo, base=base, saida=saida,
                                 lang_src=lang_src, lang_dst=lang_dst)

    # ── Execução ─────────────────────────────────────────────────────────────
    def _iniciar(self) -> None:
        cfg = self._collect_config()
        if cfg is None:
            return

        self._log(f"▶ Iniciando tradução: páginas {cfg.pag_ini}–{cfg.pag_fim}  |  modo: {cfg.modo.upper()}  |  {cfg.lang_src} → {cfg.lang_dst}")
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
        """Roda na thread de background — não acessa widgets diretamente."""
        try:
            processar(cfg.pdf, cfg.pag_ini, cfg.pag_fim, cfg.saida, cfg.modo, cfg.base,
                      cancel_event=self._cancel_event,
                      lang_src=cfg.lang_src, lang_dst=cfg.lang_dst)
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

    # ── Encerramento ─────────────────────────────────────────────────────────
    def on_close(self) -> None:
        self._cancel_event.set()
        self._preview.fechar()
        self.after_cancel(self._after_flush)
        self.destroy()
