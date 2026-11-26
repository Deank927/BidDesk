"""Read-only preview until a deliberate Import selected action."""
from queue import Empty, SimpleQueue
from sqlite3 import Error as DatabaseError
from threading import Thread

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout)

from . import county_rss as county

class CountyFeedDialog(QDialog):
    def __init__(self, parent, project):
        super().__init__(parent)
        self.project = project
        self.rows = ()
        self.known = set()
        self.setWindowTitle("LA County open bids")
        self.resize(1080, 640)
        layout = QVBoxLayout(self)
        tip = QLabel("The County feed is for discovery. Confirm closing dates and job walks in the notice. Importing creates NEW leads only.")
        tip.setWordWrap(True)
        layout.addWidget(tip)
        self.status = QLabel("Retrieving the public County feed...")
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.query = QLineEdit()
        self.query.setPlaceholderText("Filter by title, department or solicitation number")
        self.query.textChanged.connect(self.filter_rows)
        layout.addWidget(self.query)
        grid = self.grid = QTableWidget(0, 5)
        grid.setHorizontalHeaderLabels(("Solicitation", "Title", "Department", "Feed close (unverified)", "Import status"))
        grid.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        grid.setColumnWidth(0, 148); grid.setColumnWidth(2, 175); grid.setColumnWidth(3, 195); grid.setColumnWidth(4, 119)
        grid.verticalHeader().setDefaultSectionSize(max(26, grid.fontMetrics().height() + 8))
        grid.setSelectionBehavior(QAbstractItemView.SelectRows)
        grid.setSelectionMode(QAbstractItemView.ExtendedSelection)
        grid.setEditTriggers(QAbstractItemView.NoEditTriggers)
        grid.itemSelectionChanged.connect(self.update_buttons)
        layout.addWidget(grid, 1)
        buttons = QHBoxLayout()
        self.open_button = QPushButton("Open official notice")
        self.open_button.clicked.connect(self.open_notice)
        self.import_button = QPushButton("Import selected as NEW leads")
        self.import_button.clicked.connect(self.import_selected)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        buttons.addWidget(self.open_button)
        buttons.addStretch()
        buttons.addWidget(self.import_button)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self.import_button.setAutoDefault(False)
        self.open_button.setAutoDefault(False)
        close.setDefault(True)
        self.update_buttons()
        self.work = SimpleQueue()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(60)
        out = self.work
        def load():
            try:
                out.put((county.fetch_open(), None))
            except Exception as error:
                out.put((None, str(error)))
        Thread(target=load, daemon=True).start()

    def poll(self):
        try:
            result, error = self.work.get_nowait()
        except Empty:
            return
        self.timer.stop()
        if error is not None:
            self.status.setText("Could not read the official County feed. No leads imported. " + error[:240])
            return
        self.rows = result.notices
        self.known = county.existing_keys(self.project)
        self.grid.setRowCount(len(self.rows))
        for i, row in enumerate(self.rows):
            values = (row.key, row.title, row.department, row.closing,
                      "Already saved" if row.key in self.known else "New")
            for j, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setToolTip(val)
                self.grid.setItem(i, j, item)
        self.status.setText(f"{len(self.rows)} notice(s) in the official feed. {result.skipped} invalid or repeated entries skipped. Nothing imported yet.")
        self.filter_rows()

    def selected(self):
        if not self.grid.selectionModel():
            return []
        return [self.rows[i.row()] for i in self.grid.selectionModel().selectedRows()
                if i.row() < len(self.rows) and not self.grid.isRowHidden(i.row())]

    def filter_rows(self, *_):
        value = self.query.text().strip().casefold()
        self.grid.clearSelection()
        for i, row in enumerate(self.rows):
            self.grid.setRowHidden(i, bool(value) and value not in f"{row.key} {row.title} {row.department}".casefold())
        self.update_buttons()

    def update_buttons(self):
        selected = self.selected()
        self.open_button.setEnabled(len(selected) == 1)
        self.import_button.setEnabled(any(n.key not in self.known for n in selected))

    def open_notice(self):
        selected = self.selected()
        if len(selected) == 1:
            QDesktopServices.openUrl(QUrl(selected[0].url))

    def import_selected(self):
        selected = self.selected()
        if not selected:
            return
        try:
            a, d = county.import_selected(self.project, selected)
            self.known = county.existing_keys(self.project)
            for i, n in enumerate(self.rows):
                self.grid.item(i, 4).setText("Already saved" if n.key in self.known else "New")
            self.status.setText(f"Imported {a} NEW lead(s). Skipped {d} already saved. No GO decision or bid was created.")
            self.grid.clearSelection()
            self.update_buttons()
        except (ValueError, OSError, DatabaseError) as error:
            self.status.setText("Import could not finish: " + str(error)[:240])
