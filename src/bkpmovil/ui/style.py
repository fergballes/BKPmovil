"""Aspecto de la aplicación: paleta sobria y controles grandes."""

from __future__ import annotations

AZUL = "#2563eb"
AZUL_OSCURO = "#1d4ed8"
VERDE = "#16a34a"
VERDE_OSCURO = "#15803d"
ROJO = "#dc2626"
GRIS_TEXTO = "#334155"
GRIS_SUAVE = "#64748b"
BORDE = "#cbd5e1"
FONDO = "#f8fafc"

STYLESHEET = f"""
QWidget {{
    font-family: "Segoe UI", "Cantarell", "Noto Sans", sans-serif;
    font-size: 14px;
    color: {GRIS_TEXTO};
}}
QMainWindow, QDialog {{ background: {FONDO}; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}

QLabel#titulo {{ font-size: 22px; font-weight: 600; color: #0f172a; }}
QLabel#subtitulo {{ font-size: 14px; color: {GRIS_SUAVE}; }}
QLabel#numeroGrande {{ font-size: 30px; font-weight: 700; color: #0f172a; }}
QLabel#etiquetaNumero {{ font-size: 12px; color: {GRIS_SUAVE}; }}
QLabel#estadoOk {{ color: {VERDE_OSCURO}; font-weight: 600; }}
QLabel#estadoError {{ color: {ROJO}; font-weight: 600; }}
QLabel#aviso {{
    background: #fef9c3; border: 1px solid #fde047; border-radius: 8px; padding: 10px;
    color: #713f12;
}}

QFrame#tarjeta {{
    background: white; border: 1px solid {BORDE}; border-radius: 10px;
}}
QFrame#separador {{ background: {BORDE}; max-height: 1px; border: none; }}

QGroupBox {{
    background: white; border: 1px solid {BORDE}; border-radius: 10px;
    margin-top: 14px; padding: 14px 12px 12px 12px; font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #0f172a;
}}

QPushButton {{
    background: white; border: 1px solid {BORDE}; border-radius: 8px;
    padding: 9px 16px; color: {GRIS_TEXTO};
}}
QPushButton:hover {{ background: #f1f5f9; }}
QPushButton:disabled {{ color: #94a3b8; background: #f1f5f9; }}

QPushButton#primario {{
    background: {AZUL}; color: white; border: none; font-weight: 600;
}}
QPushButton#primario:hover {{ background: {AZUL_OSCURO}; }}
QPushButton#primario:disabled {{ background: #94a3b8; color: #e2e8f0; }}

QPushButton#accion {{
    background: {VERDE}; color: white; border: none;
    font-size: 17px; font-weight: 600; padding: 15px 26px; border-radius: 10px;
}}
QPushButton#accion:hover {{ background: {VERDE_OSCURO}; }}
QPushButton#accion:disabled {{ background: #94a3b8; color: #e2e8f0; }}

QPushButton#peligro {{ color: {ROJO}; border-color: #fecaca; }}
QPushButton#peligro:hover {{ background: #fef2f2; }}

QLineEdit, QComboBox, QSpinBox {{
    background: white; border: 1px solid {BORDE}; border-radius: 8px;
    padding: 8px 10px; selection-background-color: {AZUL};
}}
QLineEdit:focus, QComboBox:focus {{ border-color: {AZUL}; }}
QLineEdit[error="true"] {{ border-color: {ROJO}; background: #fef2f2; }}

QTableWidget {{
    background: white; border: 1px solid {BORDE}; border-radius: 10px;
    gridline-color: #e2e8f0;
}}
QTableWidget::item {{ padding: 6px; }}
QTableWidget::item:selected {{ background: #dbeafe; color: #0f172a; }}
QHeaderView::section {{
    background: #f1f5f9; border: none; border-bottom: 1px solid {BORDE};
    padding: 8px; font-weight: 600; color: {GRIS_SUAVE};
}}

QProgressBar {{
    border: 1px solid {BORDE}; border-radius: 9px; background: white;
    height: 20px; text-align: center; color: #0f172a; font-weight: 600;
}}
QProgressBar::chunk {{ background: {AZUL}; border-radius: 8px; }}
QProgressBar#secundaria::chunk {{ background: #93c5fd; }}

QTextBrowser, QPlainTextEdit {{
    background: white; border: 1px solid {BORDE}; border-radius: 10px; padding: 8px;
}}
QPlainTextEdit#log {{
    font-family: "JetBrains Mono", "Consolas", "DejaVu Sans Mono", monospace;
    font-size: 12px; color: {GRIS_SUAVE};
}}
QPlainTextEdit#informe {{
    font-family: "JetBrains Mono", "Consolas", "DejaVu Sans Mono", monospace;
    font-size: 12px; color: #0f172a;
}}
QCheckBox::indicator {{ width: 18px; height: 18px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #cbd5e1; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
"""

PASOS = ("1 · Conectar", "2 · Carpetas", "3 · Copiando", "4 · Resumen")


def paso_html(activo: int) -> str:
    """Migas de pan de los cuatro pasos, con el actual resaltado."""
    trozos = []
    for i, texto in enumerate(PASOS):
        if i < activo:
            trozos.append(f'<span style="color:{VERDE_OSCURO};">✓ {texto}</span>')
        elif i == activo:
            trozos.append(f'<b style="color:{AZUL};">{texto}</b>')
        else:
            trozos.append(f'<span style="color:#94a3b8;">{texto}</span>')
    return '<span style="color:#cbd5e1;"> &nbsp;›&nbsp; </span>'.join(trozos)


def lista_html(items: list[str], ordenada: bool = False) -> str:
    etiqueta = "ol" if ordenada else "ul"
    cuerpo = "".join(f"<li style='margin-bottom:7px;'>{i}</li>" for i in items)
    return f"<{etiqueta} style='margin:6px 0 10px 0; padding-left:20px;'>{cuerpo}</{etiqueta}>"
