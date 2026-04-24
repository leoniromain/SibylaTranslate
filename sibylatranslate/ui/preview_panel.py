import tkinter as tk
from PIL import Image, ImageTk
import customtkinter as ctk
import fitz  # PyMuPDF


class PreviewPanel(ctk.CTkFrame):
    """
    Painel de pré-visualização de PDF auto-contido.
    Uso:
        panel = PreviewPanel(parent)
        panel.grid(...)
        panel.abrir("caminho/para/arquivo.pdf")
        panel.fechar()   # no on_close da janela
    """

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._fitz_doc: fitz.Document | None = None
        self._total: int = 0
        self._page: int = 1
        self._photo_img = None        # mantém referência para evitar GC
        self._canvas_img_id: int | None = None

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._build()

    # ── Construção do painel ──────────────────────────────────────────────────
    def _build(self) -> None:
        ctk.CTkLabel(self, text="Pré-visualização",
                     font=ctk.CTkFont(size=12), text_color="gray60").grid(
            row=0, column=0, sticky="w", padx=10, pady=(8, 2))

        self._canvas = tk.Canvas(self, bg="#2b2b2b", highlightthickness=0)
        self._canvas.grid(row=1, column=0, sticky="nsew", padx=6, pady=4)
        self._canvas.bind("<Configure>", lambda _e: self.renderizar())

        nav = ctk.CTkFrame(self, fg_color="transparent")
        nav.grid(row=2, column=0, pady=(2, 8))

        ctk.CTkButton(nav, text="◀", width=36,
                      command=self._anterior).pack(side="left", padx=4)

        self._lbl_pag = ctk.CTkLabel(nav, text="—",
                                     font=ctk.CTkFont(size=11), width=110)
        self._lbl_pag.pack(side="left", padx=4)

        ctk.CTkButton(nav, text="▶", width=36,
                      command=self._proxima).pack(side="left", padx=4)

        self._goto_var = tk.StringVar()
        goto_entry = ctk.CTkEntry(nav, textvariable=self._goto_var,
                                  width=52, placeholder_text="ir")
        goto_entry.pack(side="left", padx=(10, 2))
        goto_entry.bind("<Return>", lambda _e: self._goto())
        ctk.CTkButton(nav, text="→", width=30,
                      command=self._goto).pack(side="left")

    # ── API pública ───────────────────────────────────────────────────────────
    def abrir(self, pdf_path: str) -> None:
        """Abre (ou reabre) um PDF para preview."""
        self.fechar()
        try:
            self._fitz_doc = fitz.open(pdf_path)
            self._total = len(self._fitz_doc)
            self._page = 1
            self.renderizar()
        except Exception:
            self._fitz_doc = None
            self._total = 0

    def renderizar(self) -> None:
        """Renderiza a página atual no canvas, ajustando ao tamanho disponível."""
        if not self._fitz_doc or self._total == 0:
            return
        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        if cw < 10 or ch < 10:
            return

        page = self._fitz_doc[self._page - 1]
        pr = page.rect
        scale = min(cw / pr.width, ch / pr.height) * 0.97
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)

        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        self._photo_img = ImageTk.PhotoImage(img)

        cx, cy = cw // 2, ch // 2
        if self._canvas_img_id:
            self._canvas.itemconfig(self._canvas_img_id, image=self._photo_img)
            self._canvas.coords(self._canvas_img_id, cx, cy)
        else:
            self._canvas_img_id = self._canvas.create_image(
                cx, cy, anchor="center", image=self._photo_img)

        self._lbl_pag.configure(text=f"Página {self._page} / {self._total}")

    def fechar(self) -> None:
        """Fecha o documento fitz aberto. Chamar no on_close da janela."""
        if self._fitz_doc:
            try:
                self._fitz_doc.close()
            except Exception:
                pass
            self._fitz_doc = None
            self._total = 0

    # ── Navegação (privada) ───────────────────────────────────────────────────
    def _anterior(self) -> None:
        if self._page > 1:
            self._page -= 1
            self.renderizar()

    def _proxima(self) -> None:
        if self._page < self._total:
            self._page += 1
            self.renderizar()

    def _goto(self) -> None:
        try:
            num = int(self._goto_var.get())
            if 1 <= num <= self._total:
                self._page = num
                self.renderizar()
        except ValueError:
            pass
        self._goto_var.set("")
