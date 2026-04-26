import os
import sys
import re
import threading
from datetime import datetime, timezone

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton,
    QLineEdit, QSpinBox, QComboBox, QScrollArea, QSplitter, QSizePolicy,
    QFileDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QStackedWidget,
    QProgressBar, QButtonGroup, QMessageBox, QDialog, QDialogButtonBox,
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QUrl, QSize
from PyQt6.QtGui import QFont, QAction, QDragEnterEvent, QDropEvent, QCursor

BG_APP      = "#F0F0F0"
BG_SURFACE  = "#FFFFFF"
BG_INPUT    = "#FAFAFA"
BG_DROPZONE = "#F5F9FF"
BORDER      = "#DDDDDD"
BORDER_BLUE = "#B8D4F0"
PRIMARY     = "#185FA5"
PRIMARY_HOV = "#0C447C"
TEXT_MAIN   = "#1A1A1A"
TEXT_SEC    = "#666666"
TEXT_LABEL  = "#185FA5"
SUCCESS     = "#1D9E75"
WARNING     = "#BA7517"
DANGER      = "#E24B4A"

STYLESHEET = f"""
QMainWindow, QWidget {{ background-color: {BG_APP}; color: {TEXT_MAIN}; }}
QMenuBar {{ background-color: {BG_SURFACE}; border-bottom: 1px solid {BORDER}; }}
QMenuBar::item {{ padding: 4px 10px; background: transparent; }}
QMenuBar::item:selected {{ background-color: {BG_APP}; }}
QMenu {{ background-color: {BG_SURFACE}; border: 1px solid {BORDER}; }}
QMenu::item {{ padding: 6px 20px; }}
QMenu::item:selected {{ background-color: #EEF4FF; color: {PRIMARY}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 2px 0; }}
QScrollBar:vertical {{ background: transparent; width: 8px; border: none; }}
QScrollBar::handle:vertical {{ background: #CCCCCC; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #AAAAAA; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; border: none; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QLineEdit, QComboBox, QSpinBox {{
    background-color: {BG_SURFACE}; border: 1px solid {BORDER};
    border-radius: 6px; padding: 5px 8px;
    selection-background-color: #D0E8FF;
}}
QComboBox::drop-down {{ border: none; }}
QProgressBar {{
    background-color: #E8E8E8; border: none; border-radius: 3px;
    text-align: center;
}}
QProgressBar::chunk {{ background-color: {PRIMARY}; border-radius: 3px; }}
QToolTip {{ background-color: {BG_SURFACE}; border: 1px solid {BORDER}; color: {TEXT_MAIN}; padding: 4px; }}
"""

LANG_SRC = [("Inglês", "en"), ("Espanhol", "es"), ("Francês", "fr"),
            ("Alemão", "de"), ("Italiano", "it"), ("Português", "pt"),
            ("Auto-detectar", "auto")]
LANG_DST = [("Português (pt-BR)", "pt"), ("Português (pt-PT)", "pt-PT"),
            ("Espanhol", "es"), ("Inglês", "en"), ("Francês", "fr"),
            ("Alemão", "de"), ("Italiano", "it")]
FMT_MAP  = {"Word": "docx", "TXT": "txt", "Markdown": "md", "PDF": "pdf"}
MODO_MAP = {"Novo arquivo": "novo", "Continuar": "append", "Substituir": "replace"}


class DropZone(QWidget):
    file_dropped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._current_file = ""
        self._layout = QVBoxLayout(self)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._build_empty()

    def _clear(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _build_empty(self):
        self._clear()
        self.setStyleSheet(f"DropZone {{ border: 2px dashed {BORDER_BLUE}; border-radius: 8px; background: {BG_DROPZONE}; }}")
        for text, size, color in [
            ("🗎", 52, "#BBBBBB"),
            ("Arraste um PDF aqui", 13, "#555555"),
            ("ou clique para abrir", 11, PRIMARY),
        ]:
            lbl = QLabel(text)
            lbl.setFont(QFont("Segoe UI", size))
            lbl.setStyleSheet(f"color: {color}; border: none; background: transparent;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if text == "ou clique para abrir":
                lbl.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                lbl.mousePressEvent = lambda _e: self._open_dialog()
            self._layout.addWidget(lbl)

    def _build_loaded(self, path: str):
        self._clear()
        self.setStyleSheet(f"DropZone {{ border: 1px solid {BORDER}; border-radius: 8px; background: #F0F7FF; }}")
        row = QWidget()
        row.setStyleSheet("background: transparent; border: none;")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(16, 12, 16, 12)
        row_layout.setSpacing(12)
        icon = QLabel("📄")
        icon.setFont(QFont("Segoe UI", 28))
        icon.setStyleSheet("border: none; background: transparent;")
        row_layout.addWidget(icon)
        info = QVBoxLayout()
        info.setSpacing(2)
        name = os.path.basename(path)
        name = (name[:38] + "…") if len(name) > 40 else name
        name_lbl = QLabel(name)
        name_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        name_lbl.setStyleSheet(f"color: {TEXT_MAIN}; border: none; background: transparent;")
        info.addWidget(name_lbl)
        try:
            import fitz
            doc = fitz.open(path)
            n_pages = doc.page_count
            doc.close()
        except Exception:
            n_pages = "?"
        size_str = ""
        try:
            size_str = f"{os.path.getsize(path) / 1024 / 1024:.1f} MB"
        except Exception:
            pass
        meta = QLabel(f"{n_pages} páginas · {size_str}")
        meta.setFont(QFont("Segoe UI", 10))
        meta.setStyleSheet(f"color: {TEXT_SEC}; border: none; background: transparent;")
        info.addWidget(meta)
        row_layout.addLayout(info)
        row_layout.addStretch()
        x_btn = QPushButton("×")
        x_btn.setFixedSize(24, 24)
        x_btn.setStyleSheet(f"QPushButton {{ background: #E8E8E8; border: none; border-radius: 12px; color: {TEXT_SEC}; font-size: 14pt; }} QPushButton:hover {{ background: #FFDDDD; color: {DANGER}; }}")
        x_btn.clicked.connect(self.reset)
        row_layout.addWidget(x_btn)
        self._layout.addWidget(row)

    def _open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Abrir PDF", "", "PDF (*.pdf);;Todos (*.*)")
        if path:
            self.load_file(path)

    def load_file(self, path: str):
        self._current_file = path
        self._build_loaded(path)
        self.file_dropped.emit(path)

    def reset(self):
        self._current_file = ""
        self._build_empty()
        self.file_dropped.emit("")

    def get_file(self) -> str:
        return self._current_file

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".pdf"):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            p = url.toLocalFile()
            if p.lower().endswith(".pdf") and os.path.isfile(p):
                self.load_file(p)
                return

    def mousePressEvent(self, event):
        if not self._current_file:
            self._open_dialog()


class SectionCard(QWidget):
    def __init__(self, title: str, content: QWidget, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"SectionCard {{ background: {BG_SURFACE}; border: 1px solid {BORDER}; border-radius: 8px; }}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)
        title_lbl = QLabel(title.upper())
        title_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {TEXT_LABEL}; border: none; background: transparent;")
        layout.addWidget(title_lbl)
        layout.addWidget(content)


class SegmentedButton(QWidget):
    option_changed = pyqtSignal(str)

    def __init__(self, options: list, selected: str = "", parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"SegmentedButton {{ background: #F0F0F0; border: 1px solid {BORDER}; border-radius: 8px; padding: 3px; }}")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._btns: dict[str, QPushButton] = {}
        first = selected or options[0]
        for opt in options:
            btn = QPushButton(opt)
            btn.setCheckable(True)
            btn.setChecked(opt == first)
            self._apply_style(btn, opt == first)
            btn.toggled.connect(lambda chk, o=opt, b=btn: self._on_toggle(chk, o, b))
            self._group.addButton(btn)
            self._btns[opt] = btn
            layout.addWidget(btn)

    def _apply_style(self, btn: QPushButton, active: bool):
        if active:
            btn.setStyleSheet(f"QPushButton {{ background: {BG_SURFACE}; border: 1px solid {BORDER}; border-radius: 6px; font-weight: 500; padding: 4px 12px; color: {TEXT_MAIN}; }}")
        else:
            btn.setStyleSheet(f"QPushButton {{ background: transparent; border: none; border-radius: 6px; padding: 4px 12px; color: {TEXT_SEC}; }} QPushButton:hover {{ background: #E8E8E8; }}")

    def _on_toggle(self, checked: bool, option: str, btn: QPushButton):
        self._apply_style(btn, checked)
        if checked:
            self.option_changed.emit(option)

    def get_selected(self) -> str:
        for opt, btn in self._btns.items():
            if btn.isChecked():
                return opt
        return ""

    def set_selected(self, option: str):
        if option in self._btns:
            self._btns[option].setChecked(True)


class GlossaryWidget(QWidget):
    def __init__(self, initial_terms: list = None, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        self._terms: list = list(initial_terms or [])
        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(6)
        entry_row = QHBoxLayout()
        entry_row.setSpacing(4)
        self._entry = QLineEdit()
        self._entry.setPlaceholderText("Adicionar termo...")
        self._entry.returnPressed.connect(self._add_tag)
        entry_row.addWidget(self._entry)
        add_btn = QPushButton("+")
        add_btn.setFixedSize(32, 32)
        add_btn.setStyleSheet(f"QPushButton {{ background: {PRIMARY}; color: white; border: none; border-radius: 4px; font-size: 16pt; }} QPushButton:hover {{ background: {PRIMARY_HOV}; }}")
        add_btn.clicked.connect(self._add_tag)
        entry_row.addWidget(add_btn)
        main.addLayout(entry_row)
        self._pills_widget = QWidget()
        self._pills_widget.setStyleSheet("background: transparent; border: none;")
        self._pills_layout = QVBoxLayout(self._pills_widget)
        self._pills_layout.setContentsMargins(0, 0, 0, 0)
        self._pills_layout.setSpacing(4)
        main.addWidget(self._pills_widget)
        self._render_pills()

    def _add_tag(self):
        term = self._entry.text().strip()
        if term and term not in self._terms:
            self._terms.append(term)
            self._entry.clear()
            self._render_pills()

    def _remove_tag(self, term: str):
        if term in self._terms:
            self._terms.remove(term)
            self._render_pills()

    def _render_pills(self):
        while self._pills_layout.count():
            item = self._pills_layout.takeAt(0)
            if item.layout():
                sub = item.layout()
                while sub.count():
                    it = sub.takeAt(0)
                    if it.widget():
                        it.widget().deleteLater()
            elif item.widget():
                item.widget().deleteLater()
        for i in range(0, max(len(self._terms), 1), 3):
            row = QHBoxLayout()
            row.setSpacing(4)
            row.setAlignment(Qt.AlignmentFlag.AlignLeft)
            for term in self._terms[i:i + 3]:
                pill = QFrame()
                pill.setStyleSheet("QFrame { background: #EEF4FF; border: 1px solid #C5D8F5; border-radius: 12px; }")
                pl = QHBoxLayout(pill)
                pl.setContentsMargins(8, 2, 4, 2)
                pl.setSpacing(2)
                lbl = QLabel(term)
                lbl.setFont(QFont("Segoe UI", 11))
                lbl.setStyleSheet(f"color: {PRIMARY}; border: none; background: transparent;")
                pl.addWidget(lbl)
                rem = QPushButton("×")
                rem.setFixedSize(16, 16)
                rem.setFlat(True)
                rem.setStyleSheet(f"QPushButton {{ background: transparent; border: none; color: #888888; }} QPushButton:hover {{ color: {DANGER}; }}")
                rem.clicked.connect(lambda _, t=term: self._remove_tag(t))
                pl.addWidget(rem)
                row.addWidget(pill)
            row.addStretch()
            self._pills_layout.addLayout(row)

    def get_terms(self) -> list:
        return list(self._terms)


class EstimateBar(QFrame):
    def __init__(self, duration="—", words="—", pages="—", parent=None):
        super().__init__(parent)
        self.setFixedHeight(64)
        self.setStyleSheet("EstimateBar { background: #F8F8F8; border: 1px solid #E0E0E0; border-radius: 6px; }")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._val_labels = []
        for i, (val, key) in enumerate([(duration, "Duração est."), (words, "Palavras"), (pages, "Páginas")]):
            if i > 0:
                sep = QFrame()
                sep.setFixedWidth(1)
                sep.setStyleSheet("background: #E0E0E0; border: none;")
                layout.addWidget(sep)
            cell = QWidget()
            cell.setStyleSheet("background: transparent; border: none;")
            cl = QVBoxLayout(cell)
            cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cl.setSpacing(2)
            cl.setContentsMargins(12, 4, 12, 4)
            val_lbl = QLabel(val)
            val_lbl.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
            val_lbl.setStyleSheet(f"color: {TEXT_MAIN}; border: none; background: transparent;")
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            key_lbl = QLabel(key.upper())
            key_lbl.setFont(QFont("Segoe UI", 9))
            key_lbl.setStyleSheet("color: #888888; border: none; background: transparent;")
            key_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cl.addWidget(val_lbl)
            cl.addWidget(key_lbl)
            layout.addWidget(cell, stretch=1)
            self._val_labels.append(val_lbl)

    def update_values(self, duration: str, words: str, pages: str):
        self._val_labels[0].setText(duration)
        self._val_labels[1].setText(words)
        self._val_labels[2].setText(pages)


class DocumentPanel(QScrollArea):
    def __init__(self, header_text: str, header_bg: str, translated: bool = False, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self._peer: "DocumentPanel | None" = None
        self._syncing = False
        self._translated = translated
        self._container = QWidget()
        self._container.setStyleSheet("background-color: #E8E8E8;")
        self._cl = QVBoxLayout(self._container)
        self._cl.setContentsMargins(16, 16, 16, 16)
        self._cl.setSpacing(16)
        self._placeholder = QLabel("Nenhum conteúdo.\nInicie uma tradução para visualizar.")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet("color: #AAAAAA; border: none; background: transparent;")
        self._cl.addStretch()
        self._cl.addWidget(self._placeholder, alignment=Qt.AlignmentFlag.AlignCenter)
        self._cl.addStretch()
        self.setWidget(self._container)

    def populate(self, pages: list, ins_indices: set = None, mod_indices: set = None):
        ins_indices = ins_indices or set()
        mod_indices = mod_indices or set()
        while self._cl.count():
            item = self._cl.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for i, text in enumerate(pages):
            page = QFrame()
            page.setStyleSheet("QFrame { background: #FFFFFF; border: 0.5px solid #CCCCCC; border-radius: 2px; }")
            page.setFixedWidth(520)
            pl = QVBoxLayout(page)
            pl.setContentsMargins(24, 24, 24, 24)
            lbl = QLabel(text)
            lbl.setWordWrap(True)
            lbl.setFont(QFont("Segoe UI", 11))
            if i in ins_indices:
                lbl.setStyleSheet("border: none; background: #E8F5E9; border-radius: 2px; padding: 2px; color: #1A1A1A;")
            elif i in mod_indices:
                lbl.setStyleSheet("border: none; background: #FFF8E1; border-radius: 2px; padding: 2px; color: #1A1A1A;")
            else:
                lbl.setStyleSheet("border: none; background: transparent; color: #1A1A1A;")
            pl.addWidget(lbl)
            self._cl.addWidget(page, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._cl.addStretch()

    def set_peer(self, peer: "DocumentPanel"):
        self._peer = peer

    def wheelEvent(self, event):
        if self._syncing:
            event.ignore()
            return
        super().wheelEvent(event)
        if self._peer and not self._peer._syncing:
            self._syncing = True
            self._peer._syncing = True
            self._peer.verticalScrollBar().setValue(self.verticalScrollBar().value())
            self._peer._syncing = False
            self._syncing = False


class ActionPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(200)
        self.setStyleSheet(f"ActionPanel {{ background: #FAFAFA; border-left: 1px solid {BORDER}; }}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(4)
        title = QLabel("Ações")
        title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {TEXT_MAIN}; border: none; background: transparent; margin-bottom: 8px;")
        layout.addWidget(title)
        for text in ["💾  Salvar Word", "📄  Exportar PDF", "📋  Copiar texto", "📋  Ver log completo"]:
            layout.addWidget(self._ghost(text))
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {BORDER}; border: none; border-top: 1px solid {BORDER}; background: transparent;")
        layout.addWidget(sep)
        self._back_btn = self._ghost("←  Nova tradução")
        layout.addWidget(self._back_btn)
        layout.addStretch()

    def _ghost(self, text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setStyleSheet(f"QPushButton {{ background: transparent; border: none; text-align: left; padding: 8px 12px; color: #333333; font-size: 11pt; border-radius: 6px; }} QPushButton:hover {{ background: #F0F0F0; }}")
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return btn

    def connect_back(self, cb):
        self._back_btn.clicked.connect(cb)


class DiffBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(32)
        self.setStyleSheet(f"DiffBar {{ background: #F5F5F5; border-top: 1px solid {BORDER}; }}")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(16)
        self._lbl_ins = QLabel("—")
        self._lbl_ins.setFont(QFont("Segoe UI", 11))
        self._lbl_ins.setStyleSheet(f"color: {SUCCESS}; border: none; background: transparent;")
        layout.addWidget(self._lbl_ins)
        self._lbl_mod = QLabel("—")
        self._lbl_mod.setFont(QFont("Segoe UI", 11))
        self._lbl_mod.setStyleSheet(f"color: {WARNING}; border: none; background: transparent;")
        layout.addWidget(self._lbl_mod)
        self._lbl_rem = QLabel("—")
        self._lbl_rem.setFont(QFont("Segoe UI", 11))
        self._lbl_rem.setStyleSheet(f"color: {DANGER}; border: none; background: transparent;")
        layout.addWidget(self._lbl_rem)
        layout.addStretch()
        sync = QLabel("⟳ Scroll sincronizado")
        sync.setFont(QFont("Segoe UI", 10))
        sync.setStyleSheet("color: #888888; border: none; background: transparent;")
        layout.addWidget(sync)

    def update(self, ins: int, mod: int, rem: int):
        self._lbl_ins.setText(f"● {ins} inserções")
        self._lbl_mod.setText(f"● {mod} modificações")
        self._lbl_rem.setText(f"● {rem} remoções")


class ConfigPage(QWidget):
    translate_requested = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pdf_path = ""
        main = QHBoxLayout(self)
        main.setContentsMargins(16, 16, 16, 16)
        main.setSpacing(12)

        left = QWidget()
        left.setStyleSheet("background: transparent; border: none;")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(10)
        self._drop_zone = DropZone()
        self._drop_zone.setMinimumHeight(320)
        self._drop_zone.file_dropped.connect(self._on_file)
        ll.addWidget(SectionCard("ARQUIVO", self._drop_zone))

        pag_hdr = QLabel("INTERVALO DE PÁGINAS")
        pag_hdr.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        pag_hdr.setStyleSheet(f"color: {TEXT_LABEL}; background: transparent; border: none;")
        ll.addWidget(pag_hdr)
        pag_row = QHBoxLayout()
        pag_row.setSpacing(6)
        for w in [QLabel("De")]:
            w.setStyleSheet("border: none; background: transparent;")
            pag_row.addWidget(w)
        self._spin_ini = QSpinBox()
        self._spin_ini.setMinimum(1)
        self._spin_ini.setFixedWidth(70)
        pag_row.addWidget(self._spin_ini)
        lbl_ate = QLabel("até")
        lbl_ate.setStyleSheet("border: none; background: transparent;")
        pag_row.addWidget(lbl_ate)
        self._spin_fim = QSpinBox()
        self._spin_fim.setMinimum(1)
        self._spin_fim.setFixedWidth(70)
        pag_row.addWidget(self._spin_fim)
        todas = QPushButton("Todas")
        todas.setStyleSheet(f"QPushButton {{ background: {BG_SURFACE}; border: 1px solid #CCCCCC; border-radius: 6px; padding: 5px 12px; color: #333333; }} QPushButton:hover {{ background: #F5F5F5; }}")
        todas.clicked.connect(lambda: (self._spin_ini.setValue(1), self._spin_fim.setValue(self._spin_fim.maximum())))
        pag_row.addWidget(todas)
        self._pag_lbl = QLabel("1 página selecionada")
        self._pag_lbl.setStyleSheet(f"color: {TEXT_SEC}; border: none; background: transparent;")
        pag_row.addWidget(self._pag_lbl)
        pag_row.addStretch()
        self._spin_ini.valueChanged.connect(self._upd_pag)
        self._spin_fim.valueChanged.connect(self._upd_pag)
        ll.addLayout(pag_row)
        ll.addStretch()
        main.addWidget(left, stretch=1)

        right = QWidget()
        right.setStyleSheet("background: transparent; border: none;")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(10)

        lang_w = QWidget()
        lang_w.setStyleSheet("background: transparent; border: none;")
        lang_l = QVBoxLayout(lang_w)
        lang_l.setContentsMargins(0, 0, 0, 0)
        lang_l.setSpacing(4)
        lang_row = QHBoxLayout()
        lang_row.setSpacing(8)
        self._combo_src = QComboBox()
        self._combo_src.setFixedWidth(180)
        for name, code in LANG_SRC:
            self._combo_src.addItem(f"{name} ({code})", code)
        self._combo_src.setCurrentText("Inglês (en)")
        lang_row.addWidget(self._combo_src)
        arr = QLabel("→")
        arr.setStyleSheet("border: none; background: transparent; color: #888888;")
        lang_row.addWidget(arr)
        self._combo_dst = QComboBox()
        self._combo_dst.setFixedWidth(180)
        for name, code in LANG_DST:
            self._combo_dst.addItem(name, code)
        lang_row.addWidget(self._combo_dst)
        lang_row.addStretch()
        lang_l.addLayout(lang_row)
        self._detect_lbl = QLabel("● Idioma detectado: Inglês (99%)")
        self._detect_lbl.setFont(QFont("Segoe UI", 10))
        self._detect_lbl.setStyleSheet(f"color: {SUCCESS}; border: none; background: transparent;")
        self._detect_lbl.setVisible(False)
        lang_l.addWidget(self._detect_lbl)
        rl.addWidget(SectionCard("IDIOMA", lang_w))

        self._fmt_seg = SegmentedButton(["Word", "TXT", "Markdown", "PDF"], "Word")
        rl.addWidget(SectionCard("FORMATO DE SAÍDA", self._fmt_seg))
        self._modo_seg = SegmentedButton(["Novo arquivo", "Continuar", "Substituir"], "Novo arquivo")
        rl.addWidget(SectionCard("MODO", self._modo_seg))

        saida_w = QWidget()
        saida_w.setStyleSheet("background: transparent; border: none;")
        saida_l = QHBoxLayout(saida_w)
        saida_l.setContentsMargins(0, 0, 0, 0)
        saida_l.setSpacing(4)
        self._saida_entry = QLineEdit("output.docx")
        saida_l.addWidget(self._saida_entry)
        browse = QPushButton("...")
        browse.setFixedSize(32, 32)
        browse.setStyleSheet(f"QPushButton {{ background: {BG_SURFACE}; border: 1px solid #CCCCCC; border-radius: 4px; color: {TEXT_SEC}; }} QPushButton:hover {{ background: #F5F5F5; }}")
        browse.clicked.connect(self._browse_saida)
        saida_l.addWidget(browse)
        rl.addWidget(SectionCard("ARQUIVO DE SAÍDA", saida_w))

        self._gloss = GlossaryWidget()
        rl.addWidget(SectionCard("GLOSSÁRIO", self._gloss))
        self._estimate = EstimateBar("—", "—", "—")
        rl.addWidget(self._estimate)

        self._translate_btn = QPushButton("▶   Traduzir")
        self._translate_btn.setFixedHeight(42)
        self._translate_btn.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self._translate_btn.setStyleSheet(f"QPushButton {{ background: {PRIMARY}; color: white; border: none; border-radius: 8px; }} QPushButton:hover {{ background: {PRIMARY_HOV}; }} QPushButton:disabled {{ background: #AAAAAA; }}")
        self._translate_btn.clicked.connect(self._on_translate)
        rl.addWidget(self._translate_btn)
        main.addWidget(right, stretch=1)

    def _on_file(self, path: str):
        self._pdf_path = path
        if path:
            try:
                import fitz
                doc = fitz.open(path)
                n = doc.page_count
                doc.close()
                self._spin_ini.setMaximum(n)
                self._spin_fim.setMaximum(n)
                self._spin_fim.setValue(n)
            except Exception:
                n = 0
            fmt = FMT_MAP.get(self._fmt_seg.get_selected(), "docx")
            self._saida_entry.setText(os.path.splitext(path)[0] + "." + fmt)
            threading.Thread(target=self._detect_lang, args=(path,), daemon=True).start()
            threading.Thread(
                target=self._compute_estimate,
                args=(path, self._spin_ini.value(), self._spin_fim.value()),
                daemon=True,
            ).start()
        else:
            self._estimate.update_values("—", "—", "—")
        self._upd_pag()

    def _detect_lang(self, path: str):
        try:
            from langdetect import detect, DetectorFactory
            DetectorFactory.seed = 0
            import pdfplumber
            with pdfplumber.open(path) as p:
                txt = (p.pages[0].extract_text() or "")[:2000]
            if len(txt.strip()) > 20:
                code = detect(txt)
                names = {"en": "Inglês", "pt": "Português", "es": "Espanhol", "fr": "Francês", "de": "Alemão"}
                name = names.get(code, code)
                QTimer.singleShot(0, lambda: (
                    self._detect_lbl.setText(f"● Idioma detectado: {name}"),
                    self._detect_lbl.setVisible(True)
                ))
        except Exception:
            pass

    def _compute_estimate(self, path: str, ini: int, fim: int):
        try:
            import pdfplumber
            words = 0
            with pdfplumber.open(path) as p:
                for i in range(ini - 1, min(fim, len(p.pages))):
                    words += len((p.pages[i].extract_text() or "").split())
            pages = fim - ini + 1
            mins = max(1, round(pages / 3.0))
            dur_str = f"~{mins} min"
            words_str = f"{words / 1000:.1f}k" if words >= 1000 else str(words)
            pages_str = str(pages)
        except Exception:
            pages = fim - ini + 1
            dur_str = f"~{max(1, round(pages / 3.0))} min"
            words_str = "—"
            pages_str = str(pages)
        QTimer.singleShot(0, lambda: self._estimate.update_values(dur_str, words_str, pages_str))

    def _upd_pag(self):
        ini, fim = self._spin_ini.value(), self._spin_fim.value()
        if fim < ini:
            self._spin_fim.setValue(ini)
            fim = ini
        n = fim - ini + 1
        self._pag_lbl.setText(f"{n} página{'s' if n > 1 else ''} selecionada{'s' if n > 1 else ''}")
        if self._pdf_path:
            threading.Thread(
                target=self._compute_estimate,
                args=(self._pdf_path, ini, fim),
                daemon=True,
            ).start()

    def _browse_saida(self):
        fmt = FMT_MAP.get(self._fmt_seg.get_selected(), "docx")
        filt = {"docx": "Word (*.docx)", "txt": "TXT (*.txt)", "md": "Markdown (*.md)", "pdf": "PDF (*.pdf)"}.get(fmt, "Word (*.docx)")
        path, _ = QFileDialog.getSaveFileName(self, "Salvar como", self._saida_entry.text(), filt)
        if path:
            self._saida_entry.setText(path)

    def _on_translate(self):
        from sibylatranslate.models import TranslationConfig
        if not self._pdf_path:
            QMessageBox.warning(self, "Aviso", "Selecione um arquivo PDF primeiro.")
            return
        fmt  = FMT_MAP.get(self._fmt_seg.get_selected(), "docx")
        modo = MODO_MAP.get(self._modo_seg.get_selected(), "novo")
        saida = self._saida_entry.text().strip() or (os.path.splitext(self._pdf_path)[0] + "." + fmt)
        src = self._combo_src.currentData() or "en"
        dst = self._combo_dst.currentData() or "pt"
        cfg = TranslationConfig(
            pdf=self._pdf_path, pag_ini=self._spin_ini.value(),
            pag_fim=self._spin_fim.value(), modo=modo, base=None,
            saida=saida, lang_src=src if src != "auto" else "en",
            lang_dst=dst, fmt=fmt, glossario=self._gloss.get_terms(),
        )
        self.translate_requested.emit(cfg)

    def set_translating(self, active: bool):
        self._translate_btn.setEnabled(not active)
        self._translate_btn.setText("Traduzindo..." if active else "▶   Traduzir")

    def restore_from_history(self, entry: dict):
        pdf = entry.get("pdf", "")
        if os.path.isfile(pdf):
            self._drop_zone.load_file(pdf)
        self._spin_ini.setValue(entry.get("pag_ini", 1))
        self._spin_fim.setValue(entry.get("pag_fim", 1))
        saida = entry.get("saida", "")
        if saida:
            self._saida_entry.setText(saida)


class ResultPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        content_row = QHBoxLayout()
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(0)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(6)
        splitter.setStyleSheet(f"QSplitter::handle {{ background: {BORDER}; }}")

        for header_text, header_bg, translated in [
            ("  Original · EN", "#F5F5F5", False),
            ("  Traduzido · PT-BR", "#EBF4FF", True),
        ]:
            panel_w = QWidget()
            panel_w.setStyleSheet("background: transparent; border: none;")
            pl = QVBoxLayout(panel_w)
            pl.setContentsMargins(0, 0, 0, 0)
            pl.setSpacing(0)
            hdr = QFrame()
            hdr.setFixedHeight(36)
            hdr.setStyleSheet(f"background: {header_bg}; border-bottom: 1px solid {BORDER};")
            hdrl = QHBoxLayout(hdr)
            hdrl.setContentsMargins(8, 0, 8, 0)
            hdr_lbl = QLabel(header_text)
            hdr_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            hdr_lbl.setStyleSheet(f"color: {'#0C447C' if translated else TEXT_SEC}; border: none; background: transparent;")
            hdrl.addWidget(hdr_lbl)
            hdrl.addStretch()
            pl.addWidget(hdr)
            doc_panel = DocumentPanel(header_text, header_bg, translated)
            pl.addWidget(doc_panel)
            splitter.addWidget(panel_w)
            if translated:
                self._trad_doc = doc_panel
            else:
                self._orig_doc = doc_panel

        self._orig_doc.set_peer(self._trad_doc)
        self._trad_doc.set_peer(self._orig_doc)
        content_row.addWidget(splitter, stretch=1)
        self._action_panel = ActionPanel()
        content_row.addWidget(self._action_panel)
        outer.addLayout(content_row, stretch=1)
        self._diff_bar = DiffBar()
        outer.addWidget(self._diff_bar)

    def connect_back(self, cb):
        self._action_panel.connect_back(cb)

    def populate(self, orig_pages: list, trad_pages: list, toolbar_total_lbl: "QLabel"):
        import difflib
        sm = difflib.SequenceMatcher(None, orig_pages, trad_pages, autojunk=False)
        ins = mod = rem = 0
        ins_idx: set = set()
        mod_idx: set = set()
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "insert":
                ins += j2 - j1
                ins_idx.update(range(j1, j2))
            elif tag == "replace":
                mod += max(i2 - i1, j2 - j1)
                mod_idx.update(range(j1, j2))
            elif tag == "delete":
                rem += i2 - i1
        self._orig_doc.populate(orig_pages)
        self._trad_doc.populate(trad_pages, ins_idx, mod_idx)
        self._diff_bar.update(ins, mod, rem)
        toolbar_total_lbl.setText(f"/ {len(orig_pages)}")


class Toolbar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(48)
        self.setStyleSheet(f"Toolbar {{ background: {BG_SURFACE}; border-bottom: 1px solid {BORDER}; }}")
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(12, 0, 12, 0)
        self._layout.setSpacing(4)
        self.open_btn     = self._secondary("📂  Abrir")
        self.traduzir_btn = self._primary("▶  Traduzir")
        self.hist_btn     = self._secondary("🕐  Histórico")
        for w in [self.open_btn, self._vsep(), self.traduzir_btn, self._vsep(), self.hist_btn]:
            self._layout.addWidget(w)
        self._result_grp = QWidget()
        self._result_grp.setStyleSheet("background: transparent; border: none;")
        rg = QHBoxLayout(self._result_grp)
        rg.setContentsMargins(0, 0, 0, 0)
        rg.setSpacing(4)
        self.prev_btn = self._secondary("‹")
        self.prev_btn.setFixedWidth(32)
        self.next_btn = self._secondary("›")
        self.next_btn.setFixedWidth(32)
        self.page_edit = QLineEdit("1")
        self.page_edit.setFixedWidth(48)
        self.page_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.total_lbl = QLabel("/ —")
        self.total_lbl.setStyleSheet(f"color: {TEXT_SEC}; border: none; background: transparent;")
        self.zoom_combo = QComboBox()
        self.zoom_combo.addItems(["75%", "100%", "125%", "150%"])
        self.zoom_combo.setCurrentText("100%")
        self.zoom_combo.setFixedWidth(72)
        self.save_btn = self._primary("💾  Salvar resultado")
        for w in [self._vsep(), self.prev_btn, self.page_edit, self.total_lbl,
                  self.next_btn, self._vsep(), self.zoom_combo, self._vsep(), self.save_btn]:
            rg.addWidget(w)
        self._result_grp.setVisible(False)
        self._layout.addWidget(self._result_grp)
        self._layout.addStretch()

    def _vsep(self) -> QFrame:
        f = QFrame()
        f.setFixedSize(1, 28)
        f.setStyleSheet(f"background: {BORDER}; border: none;")
        return f

    def _primary(self, text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setStyleSheet(f"QPushButton {{ background: {PRIMARY}; color: white; border: none; border-radius: 6px; padding: 6px 18px; font-size: 11pt; }} QPushButton:hover {{ background: {PRIMARY_HOV}; }} QPushButton:disabled {{ background: #AAAAAA; }}")
        return btn

    def _secondary(self, text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setStyleSheet(f"QPushButton {{ background: {BG_SURFACE}; border: 1px solid #CCCCCC; border-radius: 6px; padding: 5px 12px; color: #333333; font-size: 11pt; }} QPushButton:hover {{ background: #F5F5F5; }}")
        return btn

    def show_result_mode(self):
        self._result_grp.setVisible(True)

    def show_config_mode(self):
        self._result_grp.setVisible(False)


class StatusBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self.setStyleSheet(f"StatusBar {{ background: #F5F5F5; border-top: 1px solid {BORDER}; }}")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(8)
        self._status_lbl = QLabel("Pronto")
        self._status_lbl.setFont(QFont("Segoe UI", 9))
        self._status_lbl.setStyleSheet("color: #444444; border: none; background: transparent;")
        layout.addWidget(self._status_lbl)
        layout.addStretch()
        self._progress = QProgressBar()
        self._progress.setFixedSize(200, 6)
        self._progress.setTextVisible(False)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)
        self._est_lbl = QLabel("")
        self._est_lbl.setFont(QFont("Segoe UI", 9))
        self._est_lbl.setStyleSheet("color: #666666; border: none; background: transparent;")
        layout.addWidget(self._est_lbl)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._tick_val = 0

    def start_progress(self):
        self._tick_val = 0
        self._progress.setValue(0)
        self._progress.setVisible(True)
        self._status_lbl.setText("Traduzindo...")
        self._timer.start(80)

    def _tick(self):
        self._tick_val = min(self._tick_val + 1, 95)
        self._progress.setValue(self._tick_val)

    def finish_progress(self):
        self._timer.stop()
        self._progress.setValue(100)
        QTimer.singleShot(400, lambda: self._progress.setVisible(False))
        self._status_lbl.setText("Concluído")

    def set_text(self, text: str):
        self._status_lbl.setText(text)

    def set_estimate(self, text: str):
        self._est_lbl.setText(text)

    def show_progress_value(self, val: int):
        self._timer.stop()
        self._progress.setVisible(True)
        self._progress.setValue(val)

    def reset(self):
        self._timer.stop()
        self._progress.setVisible(False)
        self._progress.setValue(0)
        self._status_lbl.setText("Pronto")
        self._est_lbl.setText("")


class TranslationWorker(QThread):
    log_line       = pyqtSignal(str)
    finished       = pyqtSignal(bool, str)

    def __init__(self, cfg):
        super().__init__()
        self._cfg    = cfg
        self._cancel = threading.Event()

    def cancel(self):
        self._cancel.set()

    def run(self):
        import sys as _sys
        from sibylatranslate.engine import processar
        orig = _sys.stdout
        sig  = self.log_line
        class _Cap:
            def write(self, t):
                if t.strip(): sig.emit(t.strip())
                orig.write(t)
            def flush(self): orig.flush()
        _sys.stdout = _Cap()
        try:
            processar(
                self._cfg.pdf, self._cfg.pag_ini, self._cfg.pag_fim,
                self._cfg.saida, self._cfg.modo, self._cfg.base,
                cancel_event=self._cancel,
                lang_src=self._cfg.lang_src, lang_dst=self._cfg.lang_dst,
                fmt=self._cfg.fmt, glossario=self._cfg.glossario,
            )
            _sys.stdout = orig
            self.finished.emit(True, self._cfg.saida)
        except Exception as e:
            _sys.stdout = orig
            self.finished.emit(False, str(e))


class SibylaApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SibylaTranslate")
        self._worker: TranslationWorker | None = None
        self._log_lines: list = []
        self._build_ui()
        self.showMaximized()

    def _build_ui(self):
        self._build_menubar()
        central = QWidget()
        central.setStyleSheet("background: transparent; border: none;")
        v = QVBoxLayout(central)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self._toolbar = Toolbar()
        self._toolbar.open_btn.clicked.connect(self._cmd_open)
        self._toolbar.traduzir_btn.clicked.connect(self._cmd_translate)
        self._toolbar.hist_btn.clicked.connect(self._show_history)
        v.addWidget(self._toolbar)
        self._stack = QStackedWidget()
        self._config_page = ConfigPage()
        self._config_page.translate_requested.connect(self._start_translation)
        self._result_page = ResultPage()
        self._result_page.connect_back(self.switch_to_config)
        self._stack.addWidget(self._config_page)
        self._stack.addWidget(self._result_page)
        v.addWidget(self._stack, stretch=1)
        self._status_bar_widget = StatusBar()
        v.addWidget(self._status_bar_widget)
        self.setCentralWidget(central)

    def _build_menubar(self):
        mb = self.menuBar()
        mb.setStyleSheet(f"QMenuBar {{ background: {BG_SURFACE}; border-bottom: 1px solid {BORDER}; }} QMenuBar::item {{ padding: 4px 10px; background: transparent; color: {TEXT_MAIN}; }} QMenuBar::item:selected {{ background: {BG_APP}; }}")
        file_m = mb.addMenu("Arquivo")
        open_a = QAction("Abrir PDF", self)
        open_a.setShortcut("Ctrl+O")
        open_a.triggered.connect(self._cmd_open)
        file_m.addAction(open_a)
        file_m.addSeparator()
        quit_a = QAction("Sair", self)
        quit_a.triggered.connect(self.close)
        file_m.addAction(quit_a)
        view_m = mb.addMenu("Visualizar")
        theme_a = QAction("Tema claro/escuro", self)
        theme_a.triggered.connect(lambda: QMessageBox.information(self, "Tema", "Alternância de tema disponível na próxima versão."))
        view_m.addAction(theme_a)
        help_m = mb.addMenu("Ajuda")
        about_a = QAction("Sobre", self)
        about_a.triggered.connect(self._show_about)
        help_m.addAction(about_a)

    def switch_to_result(self):
        self._stack.setCurrentIndex(1)
        self._toolbar.show_result_mode()

    def switch_to_config(self):
        self._stack.setCurrentIndex(0)
        self._toolbar.show_config_mode()
        self._status_bar_widget.reset()

    def _cmd_open(self):
        path, _ = QFileDialog.getOpenFileName(self, "Abrir PDF", "", "PDF (*.pdf);;Todos (*.*)")
        if path:
            self._config_page._drop_zone.load_file(path)
            if self._stack.currentIndex() != 0:
                self.switch_to_config()

    def _cmd_translate(self):
        if self._stack.currentIndex() == 0:
            self._config_page._on_translate()

    def _start_translation(self, cfg):
        self._log_lines = []
        self._config_page.set_translating(True)
        self._status_bar_widget.start_progress()
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(2000)
        self._worker = TranslationWorker(cfg)
        self._worker.log_line.connect(self._on_log)
        self._worker.finished.connect(self._on_done)
        self._worker.start()
        QTimer.singleShot(600, lambda: self.switch_to_result() if self._stack.currentIndex() == 0 else None)

    def _on_log(self, line: str):
        self._log_lines.append(line)
        self._status_bar_widget.set_text(line[:80])
        m = re.search(r"\[(\d+)/(\d+)\]", line)
        if m:
            cur, tot = int(m.group(1)), int(m.group(2))
            self._status_bar_widget.show_progress_value(int(cur / tot * 100))
            elapsed_hint = f"Pág {cur}/{tot}"
            self._status_bar_widget.set_estimate(elapsed_hint)

    def _on_done(self, success: bool, msg: str):
        self._config_page.set_translating(False)
        if success:
            self._status_bar_widget.finish_progress()
            self._status_bar_widget.set_text(f"Concluído · {os.path.basename(msg)}")
            self._save_history()
            self._populate_result(msg)
            self.switch_to_result()
        else:
            self._status_bar_widget.set_text(f"Erro: {msg[:60]}")
            self._status_bar_widget.reset()
            QMessageBox.critical(self, "Erro na tradução", msg)

    def _populate_result(self, saida: str):
        if not self._worker:
            return
        cfg = self._worker._cfg
        orig_pages: list = []
        try:
            import fitz
            doc = fitz.open(cfg.pdf)
            for i in range(cfg.pag_ini - 1, cfg.pag_fim):
                orig_pages.append(doc[i].get_text("text") or f"[Página {i + 1} — sem texto extraível]")
            doc.close()
        except Exception:
            orig_pages = [f"[Erro ao ler PDF original]"]
        trad_pages: list = []
        try:
            if cfg.fmt == "docx":
                from docx import Document as _Doc
                d = _Doc(saida)
                block, blocks = [], []
                for p in d.paragraphs:
                    if p.text.strip():
                        block.append(p.text)
                    elif block:
                        blocks.append("\n".join(block))
                        block = []
                if block:
                    blocks.append("\n".join(block))
                trad_pages = blocks or ["(documento vazio)"]
            elif cfg.fmt in ("txt", "md"):
                with open(saida, encoding="utf-8") as f:
                    raw = f.read()
                trad_pages = [b.strip() for b in raw.split("\n\n") if b.strip()]
            elif cfg.fmt == "pdf":
                import pdfplumber
                with pdfplumber.open(saida) as p:
                    trad_pages = [pg.extract_text() or "" for pg in p.pages]
        except Exception as e:
            trad_pages = [f"[Erro ao ler arquivo de saída: {e}]"]
        self._result_page.populate(orig_pages, trad_pages, self._toolbar.total_lbl)

    def _save_history(self):
        if not self._worker:
            return
        from sibylatranslate.config import AppConfig
        cfg = self._worker._cfg
        config = AppConfig.load()
        entry = {
            "pdf": cfg.pdf, "saida": cfg.saida, "fmt": cfg.fmt,
            "lang_src": cfg.lang_src, "lang_dst": cfg.lang_dst,
            "pag_ini": cfg.pag_ini, "pag_fim": cfg.pag_fim,
            "data_iso": datetime.now(timezone.utc).isoformat(),
        }
        hist = config.get("historico", [])
        hist.insert(0, entry)
        config.set("historico", hist[:10])

    def _show_history(self):
        from sibylatranslate.config import AppConfig
        hist = AppConfig.load().get("historico", [])
        dlg = QDialog(self)
        dlg.setWindowTitle("Histórico de traduções")
        dlg.resize(540, 420)
        layout = QVBoxLayout(dlg)
        if not hist:
            layout.addWidget(QLabel("Nenhuma tradução registrada."))
        else:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            inner = QWidget()
            il = QVBoxLayout(inner)
            for entry in hist[:10]:
                card = QFrame()
                card.setStyleSheet(f"QFrame {{ background: {BG_SURFACE}; border: 1px solid {BORDER}; border-radius: 6px; }}")
                cl = QHBoxLayout(card)
                cl.setContentsMargins(12, 8, 12, 8)
                info = QVBoxLayout()
                nome = os.path.basename(entry.get("pdf", "—"))
                n_lbl = QLabel(nome)
                n_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                n_lbl.setStyleSheet(f"color: {TEXT_MAIN}; border: none; background: transparent;")
                info.addWidget(n_lbl)
                meta = f"{entry.get('lang_src','?')} → {entry.get('lang_dst','?')}  ·  págs {entry.get('pag_ini','?')}–{entry.get('pag_fim','?')}"
                m_lbl = QLabel(meta)
                m_lbl.setStyleSheet(f"color: {TEXT_SEC}; border: none; background: transparent;")
                info.addWidget(m_lbl)
                cl.addLayout(info)
                cl.addStretch()
                reopen = QPushButton("Reabrir")
                reopen.setStyleSheet(f"QPushButton {{ background: {BG_SURFACE}; border: 1px solid #CCCCCC; border-radius: 6px; padding: 4px 12px; color: #333333; }} QPushButton:hover {{ background: #F5F5F5; }}")
                reopen.clicked.connect(lambda _, e=entry: (dlg.accept(), self._config_page.restore_from_history(e), self.switch_to_config()))
                cl.addWidget(reopen)
                il.addWidget(card)
            il.addStretch()
            scroll.setWidget(inner)
            layout.addWidget(scroll)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(dlg.reject)
        layout.addWidget(bb)
        dlg.exec()

    def _show_about(self):
        QMessageBox.information(self, "Sobre SibylaTranslate",
            "SibylaTranslate\n\nTradução de PDFs via Google Translate.\n"
            "Gratuito, sem API key, sem tokens.\n\nPython + PyQt6 + PyMuPDF")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    app.setFont(QFont("Segoe UI", 11))
    window = SibylaApp()
    window.show()
    sys.exit(app.exec())