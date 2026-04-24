"""
SibylaTranslate — Interface gráfica
Requer: customtkinter, traduzir_pdf.py na mesma pasta
"""

import sys
import os
import re
import json
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from dataclasses import dataclass
from PIL import Image, ImageTk
import customtkinter as ctk
import fitz  # PyMuPDF

# ── Aparência ──────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")

# ── Redirecionador de stdout thread-safe ───────────────────────────────────────
class LogRedirector:
    """Redireciona sys.stdout para uma queue, permitindo leitura segura na UI."""
    def __init__(self, q: queue.Queue):
        self._q = q
        self._orig = sys.stdout

    def write(self, text):
        self._q.put(text)
        self._orig.write(text)   # mantém saída no terminal também

    def flush(self):
        self._orig.flush()

    def install(self):
        sys.stdout = self

    def uninstall(self):
        sys.stdout = self._orig


# ── Configuração de tradução ───────────────────────────────────────────────────────
@dataclass
class TranslationConfig:
    pdf: str
    pag_ini: int
    pag_fim: int
    modo: str
    base: str | None
    saida: str


# ── App principal ──────────────────────────────────────────────────────────────
class SibylaApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("SibylaTranslate")
        self.geometry("1200x700")
        self.minsize(960, 600)
        self.resizable(True, True)

        self._config = self._carregar_config()
        self._log_queue: queue.Queue = queue.Queue()
        self._log_redirector = LogRedirector(self._log_queue)
        self._cancel_event = threading.Event()
        self._worker: threading.Thread | None = None

        # Estado do preview
        self._preview_fitz: fitz.Document | None = None
        self._preview_total: int = 0
        self._preview_page: int = 1
        self._preview_ctk_img = None  # mantém referência para evitar GC

        self._build_ui()
        self._after_flush = self.after(100, self._flush_log)

    # ── Config ──────────────────────────────────────────────────────────────────
    def _carregar_config(self) -> dict:
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _salvar_config(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    # ── Build UI ────────────────────────────────────────────────────────────────
    def _build_ui(self):
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

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=20, pady=(16, 4))
        ctk.CTkLabel(header, text="SibylaTranslate",
                     font=ctk.CTkFont(size=22, weight="bold")).pack(side="left")
        ctk.CTkLabel(header, text="PDF → Word (PT-BR)",
                     font=ctk.CTkFont(size=13), text_color="gray60").pack(side="left", padx=12)

    def _build_config_panel(self):
        cfg = ctk.CTkFrame(self)
        cfg.grid(row=1, column=0, sticky="ew", padx=(20, 6), pady=6)
        cfg.columnconfigure(1, weight=1)

        # PDF
        ctk.CTkLabel(cfg, text="PDF de entrada:", anchor="w").grid(
            row=0, column=0, sticky="w", padx=(14, 6), pady=(12, 4))
        self._pdf_var = tk.StringVar(value=self._config.get("ultimo_pdf", ""))
        pdf_entry = ctk.CTkEntry(cfg, textvariable=self._pdf_var, placeholder_text="Selecione o arquivo PDF…")
        pdf_entry.grid(row=0, column=1, sticky="ew", padx=4, pady=(12, 4))
        ctk.CTkButton(cfg, text="…", width=36,
                      command=self._selecionar_pdf).grid(row=0, column=2, padx=(4, 14), pady=(12, 4))

        # Total de páginas (info)
        self._total_var = tk.StringVar(value="")
        ctk.CTkLabel(cfg, textvariable=self._total_var,
                     text_color="gray60", font=ctk.CTkFont(size=11)).grid(
            row=1, column=1, sticky="w", padx=4, pady=(0, 6))

        # Páginas
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

        # Separador visual
        ctk.CTkFrame(cfg, height=1, fg_color="gray30").grid(
            row=3, column=0, columnspan=3, sticky="ew", padx=14, pady=8)

        # Modo
        modo_frame = ctk.CTkFrame(cfg, fg_color="transparent")
        modo_frame.grid(row=4, column=0, columnspan=3, sticky="ew", padx=14, pady=4)
        ctk.CTkLabel(modo_frame, text="Modo:").pack(side="left")
        self._modo_var = tk.StringVar(value="novo")
        for val, txt in [("novo", "Novo arquivo"), ("append", "Continuar (Append)"), ("replace", "Substituir páginas (Replace)")]:
            ctk.CTkRadioButton(modo_frame, text=txt,
                               variable=self._modo_var, value=val,
                               command=self._on_modo_change).pack(side="left", padx=12)

        # Arquivo base (append/replace)
        self._base_frame = ctk.CTkFrame(cfg, fg_color="transparent")
        self._base_frame.grid(row=5, column=0, columnspan=3, sticky="ew", padx=14, pady=(2, 4))
        ctk.CTkLabel(self._base_frame, text="Arquivo .docx base:").pack(side="left")
        self._base_var = tk.StringVar(value=self._config.get("ultimo_docx", ""))
        ctk.CTkEntry(self._base_frame, textvariable=self._base_var,
                     placeholder_text="Selecione o .docx existente…", width=420).pack(side="left", padx=6)
        ctk.CTkButton(self._base_frame, text="…", width=36,
                      command=self._selecionar_base).pack(side="left", padx=4)
        self._base_frame.grid_remove()  # visível só em append/replace

        # Saída
        ctk.CTkLabel(cfg, text="Arquivo de saída:", anchor="w").grid(
            row=6, column=0, sticky="w", padx=(14, 6), pady=4)
        self._saida_var = tk.StringVar(value=self._config.get("ultima_saida", ""))
        ctk.CTkEntry(cfg, textvariable=self._saida_var,
                     placeholder_text="saida.docx  (deixe vazio para nome automático)").grid(
            row=6, column=1, sticky="ew", padx=4, pady=4)
        ctk.CTkButton(cfg, text="…", width=36,
                      command=self._selecionar_saida).grid(row=6, column=2, padx=(4, 14), pady=4)

    def _build_action_bar(self):
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=2, column=0, sticky="ew", padx=(20, 6), pady=6)

        self._btn_traduzir = ctk.CTkButton(
            btn_frame, text="▶  Traduzir", width=150, height=38,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._iniciar)
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

    def _build_log_panel(self):
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

    # ── Seletores de arquivo ────────────────────────────────────────────────────
    def _selecionar_pdf(self):
        path = filedialog.askopenfilename(
            title="Selecionar PDF",
            filetypes=[("PDF", "*.pdf"), ("Todos", "*.*")],
            initialdir=os.path.dirname(self._pdf_var.get()) or os.getcwd()
        )
        if path:
            self._pdf_var.set(path)
            self._config["ultimo_pdf"] = path
            self._salvar_config()
            self._atualizar_total_paginas()

    def _selecionar_base(self):
        path = filedialog.askopenfilename(
            title="Selecionar .docx base",
            filetypes=[("Word", "*.docx"), ("Todos", "*.*")],
            initialdir=os.path.dirname(self._base_var.get()) or os.getcwd()
        )
        if path:
            self._base_var.set(path)
            self._config["ultimo_docx"] = path
            self._salvar_config()

    def _selecionar_saida(self):
        path = filedialog.asksaveasfilename(
            title="Salvar como…",
            defaultextension=".docx",
            filetypes=[("Word", "*.docx")],
            initialdir=os.path.dirname(self._saida_var.get()) or os.getcwd()
        )
        if path:
            self._saida_var.set(path)
            self._config["ultima_saida"] = path
            self._salvar_config()

    def _atualizar_total_paginas(self):
        pdf = self._pdf_var.get()
        if not pdf or not os.path.isfile(pdf):
            self._total_var.set("")
            return
        try:
            import pdfplumber
            with pdfplumber.open(pdf) as p:
                total = len(p.pages)
            self._total_var.set(f"{total} páginas")
            self._pag_fim_var.set(str(total))
        except Exception:
            self._total_var.set("(não foi possível ler o PDF)")
            return
        # Abre documento no preview
        self._preview_abrir(pdf)

    def _todas_paginas(self):
        pdf = self._pdf_var.get()
        if not pdf or not os.path.isfile(pdf):
            return
        try:
            import pdfplumber
            with pdfplumber.open(pdf) as p:
                self._pag_fim_var.set(str(len(p.pages)))
            self._pag_ini_var.set("1")
        except Exception:
            pass

    # ── Modo ────────────────────────────────────────────────────────────────────
    def _on_modo_change(self):
        modo = self._modo_var.get()
        if modo in ("append", "replace"):
            self._base_frame.grid()
        else:
            self._base_frame.grid_remove()

    def _on_tema_change(self, valor):
        ctk.set_appearance_mode(valor)
        self._config["tema"] = valor
        self._salvar_config()

    # ── Log ─────────────────────────────────────────────────────────────────────
    def _flush_log(self):
        """Drena a queue de log e atualiza o TextBox (roda na thread principal)."""
        updated = False
        try:
            while True:
                texto = self._log_queue.get_nowait()
                self._log_box.configure(state="normal")
                self._log_box.insert("end", texto)
                self._log_box.see("end")
                self._log_box.configure(state="disabled")
                updated = True
                # Atualiza barra de progresso a partir das linhas [N/TOTAL]
                m = re.search(r"\[(\d+)/(\d+)\]", texto)
                if m:
                    atual, total = int(m.group(1)), int(m.group(2))
                    self._progress.set(atual / total)
                    self._lbl_status.configure(text=f"Página {atual} de {total}")
        except queue.Empty:
            pass
        self._after_flush = self.after(100, self._flush_log)

    def _log(self, msg: str):
        self._log_box.configure(state="normal")
        self._log_box.insert("end", msg + "\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _limpar_log(self):
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

    # ── Validação e coleta de dados ───────────────────────────────────────────
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
                messagebox.showerror("Erro", "Selecione o arquivo .docx base para o modo Append/Replace.")
                return None
            if not os.path.isfile(base):
                messagebox.showerror("Erro", f"Arquivo base não encontrado:\n{base}")
                return None
        saida = self._saida_var.get().strip()
        if not saida:
            nome_base = os.path.splitext(os.path.basename(pdf))[0]
            saida = (os.path.join(os.path.dirname(pdf), f"{nome_base}_pt_p{ini}-p{fim}.docx")
                     if modo == "novo" else base)
        return TranslationConfig(pdf=pdf, pag_ini=ini, pag_fim=fim, modo=modo, base=base, saida=saida)

    # ── Execução ─────────────────────────────────────────────────────────────────
    def _iniciar(self):
        cfg = self._collect_config()
        if cfg is None:
            return

        self._log(f"▶ Iniciando tradução: páginas {cfg.pag_ini}–{cfg.pag_fim}  |  modo: {cfg.modo.upper()}")
        self._log(f"  Saída: {cfg.saida}\n")

        self._progress.set(0)
        self._lbl_status.configure(text="Iniciando…")
        self._btn_traduzir.configure(state="disabled")
        self._btn_cancelar.configure(state="normal")
        self._cancel_event.clear()
        self._log_redirector.install()

        self._worker = threading.Thread(
            target=self._run_worker, args=(cfg,), daemon=True
        )
        self._worker.start()

    def _run_worker(self, cfg: TranslationConfig):
        """Roda na thread de background — não acessa widgets diretamente."""
        try:
            import traduzir_pdf as tp
            tp.processar(cfg.pdf, cfg.pag_ini, cfg.pag_fim, cfg.saida, cfg.modo, cfg.base,
                         cancel_event=self._cancel_event)
            self._log_queue.put(f"\n✅ Concluído! Arquivo salvo em:\n   {cfg.saida}\n")
        except Exception as e:
            self._log_queue.put(f"\n❌ Erro: {e}\n")
        finally:
            self._log_redirector.uninstall()
            self.after(0, self._finalizar)

    def _finalizar(self):
        self._btn_traduzir.configure(state="normal")
        self._btn_cancelar.configure(state="disabled")
        self._progress.set(1)
        self._lbl_status.configure(text="Concluído" if not self._cancel_event.is_set() else "Cancelado")

    def _cancelar(self):
        self._cancel_event.set()
        self._log("\n⚠️  Cancelamento solicitado — aguardando fim da página atual…\n")
        self._btn_cancelar.configure(state="disabled")
        self._lbl_status.configure(text="Cancelando…")

    # ── Preview ──────────────────────────────────────────────────────────────────
    def _build_preview_panel(self):
        pv = ctk.CTkFrame(self)
        pv.grid(row=1, column=1, rowspan=3, sticky="nsew", padx=(6, 20), pady=(6, 14))
        pv.columnconfigure(0, weight=1)
        pv.rowconfigure(1, weight=1)

        # Cabeçalho do painel
        ctk.CTkLabel(pv, text="Pré-visualização",
                     font=ctk.CTkFont(size=12), text_color="gray60").grid(
            row=0, column=0, sticky="w", padx=10, pady=(8, 2))

        # Área da imagem (scrollável via Canvas)
        self._preview_canvas = tk.Canvas(pv, bg="#2b2b2b", highlightthickness=0)
        self._preview_canvas.grid(row=1, column=0, sticky="nsew", padx=6, pady=4)
        self._preview_canvas_img_id = None

        # Bind para redimensionamento
        self._preview_canvas.bind("<Configure>", lambda e: self._preview_renderizar())

        # Navegação
        nav = ctk.CTkFrame(pv, fg_color="transparent")
        nav.grid(row=2, column=0, pady=(2, 8))

        self._btn_prev = ctk.CTkButton(nav, text="◀", width=36,
                                       command=self._preview_anterior)
        self._btn_prev.pack(side="left", padx=4)

        self._preview_lbl_pag = ctk.CTkLabel(nav, text="—",
                                              font=ctk.CTkFont(size=11), width=110)
        self._preview_lbl_pag.pack(side="left", padx=4)

        self._btn_next = ctk.CTkButton(nav, text="▶", width=36,
                                       command=self._preview_proxima)
        self._btn_next.pack(side="left", padx=4)

        # Campo de salto direto
        self._preview_goto_var = tk.StringVar()
        goto_entry = ctk.CTkEntry(nav, textvariable=self._preview_goto_var,
                                  width=52, placeholder_text="ir")
        goto_entry.pack(side="left", padx=(10, 2))
        goto_entry.bind("<Return>", lambda e: self._preview_goto())
        ctk.CTkButton(nav, text="→", width=30,
                      command=self._preview_goto).pack(side="left")

    def _preview_abrir(self, pdf_path: str):
        """Abre (ou reabre) o documento fitz para o preview."""
        if self._preview_fitz:
            try:
                self._preview_fitz.close()
            except Exception:
                pass
        try:
            self._preview_fitz = fitz.open(pdf_path)
            self._preview_total = len(self._preview_fitz)
            self._preview_page = 1
            self._preview_renderizar()
        except Exception as e:
            self._preview_fitz = None
            self._preview_total = 0

    def _preview_renderizar(self):
        """Renderiza a página atual no canvas, ajustando ao tamanho disponível."""
        if not self._preview_fitz or self._preview_total == 0:
            return

        page = self._preview_fitz[self._preview_page - 1]
        cw = self._preview_canvas.winfo_width()
        ch = self._preview_canvas.winfo_height()
        if cw < 10 or ch < 10:
            return

        # Calcula scale para caber no canvas
        pr = page.rect
        scale = min(cw / pr.width, ch / pr.height) * 0.97
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, alpha=False)

        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        self._preview_ctk_img = ImageTk.PhotoImage(img)

        # Centraliza no canvas
        cx, cy = cw // 2, ch // 2
        if self._preview_canvas_img_id:
            self._preview_canvas.itemconfig(self._preview_canvas_img_id,
                                            image=self._preview_ctk_img)
            self._preview_canvas.coords(self._preview_canvas_img_id, cx, cy)
        else:
            self._preview_canvas_img_id = self._preview_canvas.create_image(
                cx, cy, anchor="center", image=self._preview_ctk_img)

        self._preview_lbl_pag.configure(
            text=f"Página {self._preview_page} / {self._preview_total}")

    def _preview_anterior(self):
        if self._preview_page > 1:
            self._preview_page -= 1
            self._preview_renderizar()

    def _preview_proxima(self):
        if self._preview_page < self._preview_total:
            self._preview_page += 1
            self._preview_renderizar()

    def _preview_goto(self):
        try:
            num = int(self._preview_goto_var.get())
            if 1 <= num <= self._preview_total:
                self._preview_page = num
                self._preview_renderizar()
        except ValueError:
            pass
        self._preview_goto_var.set("")

    # ── Encerramento ─────────────────────────────────────────────────────────────
    def on_close(self):
        self._cancel_event.set()
        if self._preview_fitz:
            try:
                self._preview_fitz.close()
            except Exception:
                pass
        self.after_cancel(self._after_flush)
        self.destroy()


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = SibylaApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
