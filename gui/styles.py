"""Application stylesheet and small visual helpers."""

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


STYLESHEET = """
QWidget { font-family: 'Segoe UI'; font-size: 13px; color: #243042; }
QMainWindow, QStackedWidget, QScrollArea { background: #eef2f7; }
QSplitter::handle { background: #d8e0eb; width: 1px; }
QFrame#sidebar { background: #101a2b; }
QLabel#brand { color: #ffffff; font-size: 23px; font-weight: 800; padding: 8px 10px 26px; }
QLabel#navSection { color: #8190a8; font-size: 10px; font-weight: 800; letter-spacing: 1.4px; padding: 6px 12px; }
QLabel#topbarTitle { color: #172033; font-size: 14px; font-weight: 700; }
QLabel#workspaceStatus { color: #75839a; font-size: 12px; padding-left: 12px; }
QLabel#modePill { background: #fff4dd; color: #a66b00; border: 1px solid #f1d79b; border-radius: 12px; padding: 5px 11px; font-size: 10px; font-weight: 800; letter-spacing: 1px; }
QLabel#feedback { background: #ffffff; border: 1px solid #d7e0ec; border-radius: 9px; color: #4f6078; padding: 11px 15px; }
QLabel#feedback[state="loading"] { background: #eaf3ff; border-color: #a9c8f5; color: #245bc5; }
QLabel#feedback[state="success"] { background: #e8f8ee; border-color: #a9dfbb; color: #21733b; }
QLabel#feedback[state="error"] { background: #fff0f0; border-color: #edb7b7; color: #a53c3c; }
QLabel#pageTitle { color: #162238; font-size: 30px; font-weight: 800; }
QLabel#muted { color: #718096; }
QPushButton#navButton { color: #bdc8d9; background: transparent; border: 0; border-radius: 8px; padding: 12px 14px; text-align: left; font-weight: 600; }
QPushButton#navButton:hover { background: #1c2a42; color: #ffffff; }
QPushButton#navButton:checked { background: #356ff0; color: #ffffff; }
QPushButton#primary { background: #356ff0; color: white; border: 0; border-radius: 8px; padding: 12px 18px; font-weight: 700; min-height: 20px; }
QPushButton#primary:hover { background: #2559c8; }
QPushButton#danger { background: #c94d4d; color: white; border: 0; border-radius: 8px; padding: 12px 18px; font-weight: 700; min-height: 20px; }
QPushButton#danger:hover { background: #a63d3d; }
QPushButton#heroAction { background: #ffffff; color: #245bc5; border: 0; border-radius: 8px; padding: 12px 18px; font-weight: 800; }
QPushButton#heroAction:hover { background: #e8f0ff; }
QPushButton#secondary, QToolButton { background: #ffffff; border: 1px solid #d4deeb; border-radius: 8px; padding: 10px 14px; min-height: 20px; }
QPushButton#secondary:hover, QToolButton:hover { border-color: #356ff0; color: #245bc5; }
QFrame#hero { background: #356ff0; border-radius: 14px; }
QLabel#heroTitle { color: #ffffff; font-size: 22px; font-weight: 800; }
QLabel#heroSubtitle { color: #dce8ff; font-size: 13px; padding-top: 5px; }
QFrame#card { background: #ffffff; border: 1px solid #dfe6f0; border-radius: 12px; }
QFrame#card:hover { border-color: #b8cbed; }
QLabel#cardLabel { color: #718096; font-size: 12px; font-weight: 700; }
QLabel#cardValue { font-size: 30px; font-weight: 800; color: #162238; padding-top: 4px; }
QLineEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: #ffffff; border: 1px solid #d4deeb; border-radius: 7px; padding: 10px; min-height: 20px; }
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus { border: 2px solid #6d96ee; padding: 9px; }
QTableWidget { background: #ffffff; border: 1px solid #dfe6f0; border-radius: 10px; gridline-color: #edf1f6; selection-background-color: #e4edff; selection-color: #172033; alternate-background-color: #f9fbfe; }
QHeaderView::section { background: #f6f8fc; border: 0; border-bottom: 1px solid #dfe6f0; padding: 11px; font-weight: 800; color: #53627a; }
QProgressBar { border: 0; border-radius: 5px; background: #dfe6f0; text-align: center; height: 10px; }
QProgressBar::chunk { background: #356ff0; border-radius: 5px; }
QStatusBar { background: #ffffff; color: #718096; border-top: 1px solid #dfe6f0; }
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#f5f7fb"))
    palette.setColor(QPalette.Base, QColor("#ffffff"))
    palette.setColor(QPalette.Text, QColor("#243042"))
    app.setPalette(palette)
    app.setStyleSheet(STYLESHEET)
