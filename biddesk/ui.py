import sys
from html import escape
from pathlib import Path

from PySide6.QtCore import Qt, QSettings, QUrl
from PySide6.QtGui import QDesktopServices, QColor, QPalette
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QStackedWidget, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox, QTabWidget, QTextBrowser,
    QLineEdit, QCheckBox, QFormLayout, QComboBox, QDoubleSpinBox, QInputDialog, QHeaderView, QAbstractItemView,
    QListWidgetItem, QFrame, QDialog, QDialogButtonBox, QSpinBox, QScrollArea)

from . import leads as L, documents as D, review as R, planning as P, package as K, ai
from .db import Project
from .job_walk_dialog import JobWalkDialog
from . import job_walk as JW
from .county_rss_dialog import CountyFeedDialog
from .county_rss import FEED as COUNTY_FEED

FONT_SIZES = (10, 11, 12, 14, 16)
DEFAULT_FONT = 11
FONT_KEY = "appearance_font_pt"
QSS = """
* { font-family: 'Segoe UI', 'Noto Sans', sans-serif; font-size: @body@pt; color: #1d2329; }
QMainWindow, QWidget#content, QDialog, QMessageBox, QInputDialog { background: #f6f4ef; }
QListWidget#nav { background: #1f2a33; border: none; padding-top: 12px; outline: 0; }
QListWidget#nav::item { color: #c9d3db; padding: 10px 18px; }
QListWidget#nav::item:selected { background: #2c3a46; color: white; border-left: 4px solid #e8590c; }
QLabel#h1 { font-size: @heading@pt; font-weight: 600; }
QLabel#muted { color: #485663; }
QFrame#next { background: #fff4ec; border: 1px solid #f2c19f; border-radius: 6px; }
QLabel#nextText { font-weight: 600; color: #8a3200; }
QPushButton { background: white; border: 1px solid #76838d; border-radius: 4px; padding: 6px 12px; }
QPushButton:hover { border-color: #8f3709; }
QPushButton#primary { background: #9a3b0b; color: white; border: none; font-weight: 600; padding: 8px 16px; }
QPushButton#primary:hover { background: #782c08; }
QPushButton:disabled, QComboBox:disabled, QSpinBox:disabled { color: #535e67; background: #e9e7e3; }
QLineEdit, QComboBox, QAbstractSpinBox, QTextBrowser, QPlainTextEdit {
    background: white; color: #1d2329; border: 1px solid #76838d;
    selection-background-color: #21466e; selection-color: white; padding: 4px;
}
QComboBox QAbstractItemView {
    background: white; color: #1d2329; border: 1px solid #76838d;
    selection-background-color: #21466e; selection-color: white;
}
QComboBox QAbstractItemView::item { padding: 4px 8px; }
QTableWidget { background: white; selection-background-color: #21466e; selection-color: white;
    gridline-color: #e6e2da; border: 1px solid #ddd8ce; }
QHeaderView::section { background: #ece8e0; color: #1d2329; border: none; padding: 5px; font-weight: 600; }
QTabWidget::pane { border: 1px solid #ddd8ce; background: white; }
QTabBar::tab { padding: 7px 14px; background: #ece8e0; color: #1d2329; margin-right: 2px; }
QTabBar::tab:selected { background: white; border-bottom: 2px solid #9a3b0b; }
QScrollArea#buttonBar { border: none; }
"""


def safe_font_size(value):
    try:
        points = int(value)
    except (TypeError, ValueError):
        return DEFAULT_FONT
    return points if points in FONT_SIZES else DEFAULT_FONT


def apply_appearance(app, points):
    points = safe_font_size(points)
    # A matched palette covers Qt's editor viewports, popup windows and native
    # fallback states; the stylesheet supplies explicit text/background pairs.
    app.setStyle("Fusion")
    pal = QPalette()
    for role, color in (
        (QPalette.Window, "#f6f4ef"), (QPalette.WindowText, "#1d2329"),
        (QPalette.Base, "#ffffff"), (QPalette.AlternateBase, "#f6f4ef"),
        (QPalette.Text, "#1d2329"), (QPalette.Button, "#ffffff"),
        (QPalette.ButtonText, "#1d2329"), (QPalette.PlaceholderText, "#485663"),
        (QPalette.Highlight, "#21466e"), (QPalette.HighlightedText, "#ffffff"),
        (QPalette.Link, "#15477b"), (QPalette.LinkVisited, "#563989"),
    ):
        pal.setColor(role, QColor(color))
    app.setPalette(pal)
    font = app.font()
    font.setPointSize(points)
    app.setFont(font)
    app.setStyleSheet(QSS.replace("@body@", str(points)).replace("@heading@", str(points + 7)))


class DocumentKindDialog(QDialog):
    def __init__(self, parent, doc):
        super().__init__(parent)
        self.setObjectName("documentKindDialog")
        self.setWindowTitle("Document kind")
        self.setMinimumWidth(415)
        layout = QVBoxLayout(self)
        layout.addWidget(label("Change kind for the attached copy"))
        filename = label("", "muted")
        filename.setTextFormat(Qt.PlainText)
        filename.setText(doc["filename"])
        layout.addWidget(filename)
        form = QFormLayout()
        self.kind = QComboBox(self)
        self.kind.setAccessibleName("Document kind")
        self.kind.addItems([item.capitalize() for item in D.KINDS])
        current = doc["kind"]
        self.kind.setCurrentIndex(D.KINDS.index(current) if current in D.KINDS else D.KINDS.index("other"))
        self.number = QSpinBox(self)
        self.number.setAccessibleName("Addendum number")
        self.number.setRange(1, 99)
        self.number.setValue(doc["addendum_no"] or 1)
        form.addRow("Kind", self.kind)
        form.addRow("Addendum number", self.number)
        layout.addLayout(form)
        suggested, _ = D.guess_kind(doc["filename"])
        if current == "other" and suggested == "solicitation":
            layout.addWidget(label("This filename looks like an RFQ or solicitation. Choose Solicitation if it is the main bid document.", "muted"))
        layout.addWidget(label("Changes only this document’s classification. The attached file remains in place.", "muted"))
        self.kind.currentIndexChanged.connect(self.update_number)
        self.update_number()
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def update_number(self):
        self.number.setEnabled(self.kind.currentIndex() == D.KINDS.index("addendum"))

    def choice(self):
        kind = D.KINDS[self.kind.currentIndex()]
        return kind, self.number.value() if kind == "addendum" else None

STATUS_COLORS = {"pass": "#e3f4e6", "fail": "#fde2e0", "you": "#fff2cc", "conflict": "#fde2e0",
                 "verified": "#e3f4e6", "draft": "#fff8e6", "rejected": "#eeeeee"}


def btn(text, slot, primary=False, tid=None):
    b = QPushButton(text)
    b.clicked.connect(slot)
    if primary:
        b.setObjectName("primary")
    b.setAccessibleName(tid or text)
    return b


class ButtonBar(QScrollArea):
    def __init__(self, content, layout):
        super().__init__()
        self.content_layout = layout
        self.setObjectName("buttonBar")
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWidget(content)
        self.refit()

    def refit(self):
        content = self.widget()
        self.content_layout.invalidate()
        self.content_layout.activate()
        content.setMinimumWidth(self.content_layout.minimumSize().width())
        height = content.sizeHint().height() + self.horizontalScrollBar().sizeHint().height() + 4
        self.setFixedHeight(height)


def row(*widgets):
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    for x in widgets:
        h.addWidget(x) if x is not None else h.addStretch()
    return ButtonBar(w, h) if sum(isinstance(x, QPushButton) for x in widgets) >= 3 else w


def table(headers, rows, editable=False, colors=None):
    t = QTableWidget(len(rows), len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(max(25, t.fontMetrics().height()+9))
    t.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    t.horizontalHeader().setStretchLastSection(True)
    if not editable:
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    for i, r in enumerate(rows):
        for j, v in enumerate(r):
            it = QTableWidgetItem("" if v is None else str(v))
            if colors and colors[i]:
                it.setBackground(QColor(colors[i]))
            t.setItem(i, j, it)
    t.resizeColumnsToContents()
    return t


def selected_row(t):
    r = t.selectionModel().selectedRows()
    return r[0].row() if r else None


def label(text, name=None, wrap=True):
    l = QLabel(text)
    l.setWordWrap(wrap)
    l.setTextInteractionFlags(Qt.TextBrowserInteraction)
    l.setOpenExternalLinks(True)
    if name:
        l.setObjectName(name)
    return l


class Page(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(24, 20, 24, 20)

    @property
    def p(self):
        return self.app.project

    def clear(self):
        while self.lay.count():
            w = self.lay.takeAt(0).widget()
            if w:
                w.deleteLater()

    def info(self, msg):
        QMessageBox.information(self, "BidDesk", msg)


class Dashboard(Page):
    def refresh(self):
        self.clear()
        self.lay.addWidget(label("Dashboard", "h1"))
        bids = self.p.q("SELECT * FROM leads WHERE stage='pipeline' ORDER BY id")
        self.lay.addWidget(label("Bids in progress - next action", "muted"))
        rows = []
        for b in bids:
            cl = P.checklist(self.p, b["id"])
            done = sum(1 for c in cl if c["status"] in ("done", "na"))
            rows.append((b["solicitation_no"], b["title"], f"{done}/{len(cl)}", R.next_decision(self.p, b["id"])))
        t = table(["Solicitation", "Title", "Checklist", "Next action"], rows)
        t.cellDoubleClicked.connect(lambda r, c: self.app.open_bid(bids[r]["id"]))
        self.lay.addWidget(t)
        self.lay.addWidget(label("Calendar - confirmed job walks and bid deadlines (local only, no invitations)", "muted"))
        ev = P.calendar_events(self.p)
        self.lay.addWidget(table(["When", "Event", "Bid", "As stated"],
                                 [(e["when"].strftime("%a %b %d %Y %I:%M %p"), e["label"], e["title"], e["value"]) for e in ev]))
        self.lay.addWidget(label("Open tasks", "muted"))
        self.lay.addWidget(table(["Due", "Task", "Bid"], [(t["due_date"], t["title"], t["lead_title"]) for t in P.tasks(self.p)]))
        self.lay.addWidget(label("Checklists - open items across bids", "muted"))
        items = [(b["solicitation_no"], "Form" if c["category"] == "form" else "Document", c["name"], c["status"])
                 for b in bids for c in P.checklist(self.p, b["id"]) if c["status"] == "open"]
        self.lay.addWidget(table(["Bid", "Type", "Item", "Status"], items))
        self.lay.addWidget(label("Double-click a bid to open it.", "muted"))


class LeadsPage(Page):
    def refresh(self):
        self.clear()
        self.lay.addWidget(label("Leads", "h1"))
        self.lay.addWidget(row(btn("Import CSV...", self.import_csv), btn("Preview LA County open bids...", self.import_rss),
                               btn("Import feed file...", self.import_rss_file), None))
        self.rows = self.p.q("SELECT * FROM leads WHERE stage='lead' ORDER BY decision='NEW' DESC, id DESC")
        rows = [(r["decision"], r["agency"], r["solicitation_no"], r["title"], r["location"],
                 f'<a href="{r["notice_url"]}">Official notice</a>') for r in self.rows]
        self.t = table(["Decision", "Agency", "Solicitation", "Title", "Location", "Notice"], [r[:5] + ("",) for r in rows])
        for i, r in enumerate(rows):
            self.t.setCellWidget(i, 5, label(r[5]))
        self.lay.addWidget(self.t)
        self.lay.addWidget(row(btn("GO - start bid", lambda: self.decide("GO"), True, "lead-go-btn"),
                               btn("HOLD", lambda: self.decide("HOLD")), btn("NO GO", lambda: self.decide("NO GO")), None))
        self.lay.addWidget(label("Importing never marks GO, creates calendar events, or sends anything.", "muted"))

    def import_csv(self):
        f, _ = QFileDialog.getOpenFileName(self, "Import leads CSV", "", "CSV (*.csv)")
        if f:
            a, d = L.import_csv(self.p, f)
            self.info(f"Imported {a} lead(s). Skipped {d} duplicate(s).")
            self.refresh()

    def import_rss(self):
        if self.p.setting("allow_network", "0") != "1":
            return self.info("County feed access is off. Enable internet connections in Settings and save.")
        dialog = CountyFeedDialog(self, self.p)
        dialog.exec()
        self.refresh()

    def import_rss_file(self):
        f, _ = QFileDialog.getOpenFileName(self, "Import RSS file", "", "Feed (*.xml *.rss)")
        if f:
            a, d = L.import_rss(self.p, f)
            self.info(f"Imported {a} lead(s). Skipped {d} duplicate(s).")
            self.refresh()

    def decide(self, d):
        i = selected_row(self.t)
        if i is None:
            return self.info("Select a lead first.")
        lid = self.rows[i]["id"]
        L.set_decision(self.p, lid, d)
        if d == "GO":
            self.app.open_bid(lid)
        else:
            self.refresh()


class StagePage(Page):
    def __init__(self, app, stage, title):
        super().__init__(app)
        self.stage, self.title = stage, title

    def refresh(self):
        self.clear()
        self.lay.addWidget(label(self.title, "h1"))
        self.rows = self.p.q("SELECT * FROM leads WHERE stage=? ORDER BY id DESC", (self.stage,))
        t = table(["Solicitation", "Title", "Agency", "Location"],
                  [(r["solicitation_no"], r["title"], r["agency"], r["location"]) for r in self.rows])
        t.cellDoubleClicked.connect(lambda r, c: self.app.open_bid(self.rows[r]["id"]))
        self.lay.addWidget(t)
        self.lay.addWidget(label("Double-click to open.", "muted"))


class SettingsPage(Page):
    def refresh(self):
        self.clear()
        self.lay.addWidget(label("Settings", "h1"))
        form = QWidget()
        f = QFormLayout(form)
        self.net = QCheckBox("Allow internet connections (feeds and official notice attachments)")
        self.net.setChecked(self.p.setting("allow_network", "0") == "1")
        self.ourl = QLineEdit(self.p.setting("ollama_url", ""))
        self.ourl.setPlaceholderText("http://localhost:11434  (leave blank for manual review only)")
        self.omodel = QLineEdit(self.p.setting("ollama_model", ""))
        self.omodel.setPlaceholderText("e.g. llama3.1:8b")
        self.font_size = QComboBox()
        self.font_size.setAccessibleName("App text size")
        for points in FONT_SIZES:
            self.font_size.addItem(f"{points} pt" + (" (default)" if points == DEFAULT_FONT else ""), points)
        self.font_size.setCurrentIndex(self.font_size.findData(self.app.font_points))
        self.font_size.currentIndexChanged.connect(lambda _index: self.app.set_font_size(self.font_size.currentData()))
        f.addRow("App text size (saves immediately)", self.font_size)
        f.addRow("Project folder", label(str(self.p.root)))
        f.addRow("", self.net)
        f.addRow("Official LA County open feed", label(COUNTY_FEED, "muted"))
        f.addRow("Ollama URL (local)", self.ourl)
        f.addRow("Ollama model", self.omodel)
        self.lay.addWidget(form)
        self.lay.addWidget(row(btn("Save", self.save, True), btn("Test Ollama", self.test),
                               btn("Back up database now", self.backup), None))
        self.lay.addStretch()

    def save(self):
        self.p.set_setting("allow_network", "1" if self.net.isChecked() else "0")
        self.p.set_setting("ollama_url", self.ourl.text().strip())
        self.p.set_setting("ollama_model", self.omodel.text().strip())
        self.info("Saved.")

    def test(self):
        self.save()
        self.info("Ollama is reachable." if ai.configured(self.p) and ai.ping(self.p) else
                  "Ollama is not reachable. First Review will use rule-based extraction and manual review.")

    def backup(self):
        self.info(f"Backup saved to {self.p.backup()}")


class BidPage(Page):
    """One opportunity: next action banner + tabs."""

    def show_bid(self, lid, tab=None):
        self.lid = lid
        self.refresh(tab)

    def refresh(self, tab=None):
        cur = tab if tab is not None else (self.tabs.currentIndex() if hasattr(self, "tabs") and self.tabs else 0)
        self.clear()
        lead = self.p.one("SELECT * FROM leads WHERE id=?", (self.lid,))
        self.lay.addWidget(label(lead["title"], "h1"))
        self.lay.addWidget(label(f'{lead["agency"]}  |  {lead["solicitation_no"]}  |  {lead["location"]}  |  '
                                 f'<a href="{lead["notice_url"]}">Official notice</a>  |  Stage: {lead["stage"]}', "muted"))
        nxt = QFrame()
        nxt.setObjectName("next")
        h = QHBoxLayout(nxt)
        has_docs = bool(D.docs(self.p, self.lid))
        h.addWidget(label("Next: " + (R.next_decision(self.p, self.lid) if has_docs else "Start the bid - attach the solicitation and addenda."), "nextText"), 1)
        h.addWidget(btn("Start Bid" if not has_docs else "Re-run First Review", self.start_bid, True, "start-bid-btn"))
        if lead["stage"] == "pipeline":
            h.addWidget(btn("Mark awarded", self.awarded))
        self.lay.addWidget(nxt)
        self.tabs = QTabWidget()
        self.tabs.tabBar().setUsesScrollButtons(True)
        for name, fn in (("First Review", self.tab_review), ("Documents", self.tab_docs), ("Checklist", self.tab_checklist),
                         ("Tasks", self.tab_tasks), ("Estimate (internal)", self.tab_estimate),
                         ("Bid Sheet", self.tab_bidsheet), ("Package", self.tab_package)):
            w = QWidget()
            v = QVBoxLayout(w)
            fn(v)
            self.tabs.addTab(w, name)
        self.tabs.setCurrentIndex(cur)
        self.lay.addWidget(self.tabs, 1)

    # --- actions
    def start_bid(self):
        if not D.docs(self.p, self.lid):
            files, _ = QFileDialog.getOpenFileNames(self, "Attach official solicitation, addenda and forms", "",
                                                    "Bid files (*.pdf *.docx *.txt *.xlsx *.xls *.csv *.png *.jpg *.tif);;All (*)")
            if not files and self.p.setting("allow_network", "0") == "1":
                return self.from_notice()
            for f in files:
                D.attach(self.p, self.lid, f)
        self.run_review()

    def run_review(self):
        extra = []
        if ai.configured(self.p) and ai.ping(self.p):
            try:
                extra = ai.review_with_ollama(self.p, self.lid)
            except Exception as e:
                self.info(f"Ollama review skipped: {e}")
        R.run_first_review(self.p, self.lid, extra)
        self.refresh(0)

    def awarded(self):
        L.mark_awarded(self.p, self.lid)
        self.app.go("Awarded")

    def from_notice(self):
        lead = self.p.one("SELECT notice_url FROM leads WHERE id=?", (self.lid,))
        try:
            links = D.list_notice_attachments(self.p, lead["notice_url"])
        except Exception as e:
            return self.info(str(e))
        if not links:
            return self.info("No attachments found on the notice page. Use 'Add files' instead.")
        pick, ok = QInputDialog.getItem(self, "Official notice attachments", "Attach which file? (repeat for more)", links, 0, False)
        if ok:
            D.download_attachment(self.p, self.lid, pick)
            self.run_review()

    # --- tabs
    def tab_review(self, v):
        ov = R.overview(self.p, self.lid)
        html = ["<h3>One-page overview</h3><table cellpadding=4>"]
        for k in R.OVERVIEW_FIELDS:
            vals = ov[k]
            cell = "<br>".join(f"{escape(str(x['value']))} <i style='color:#485663'>[{escape(str(x['cite']))}{' - ' + escape(str(x['note'])) if x['note'] else ''}; {escape(str(x['status']))}]</i>"
                               for x in vals) or "<span style='color:#a52024'>Not found - check manually</span>"
            if k == "job_walk":
                details = [JW.summary(JW.read(self.p, x["id"])) for x in vals]
                cell += "".join("<br>" + escape(t).replace("\n", "<br>") for t in details if t)
            html.append(f"<tr><td valign=top><b>{R.LABELS[k]}</b></td><td>{cell}</td></tr>")
        html.append("</table><h4>Flags</h4><ul>" + "".join(f"<li><b>{escape(str(k))}</b>: {escape(str(m))}</li>" for k, m in ov["flags"]) + "</ul>")
        html.append(f"<p><b>Next decision:</b> {escape(str(ov['next']))}</p>")
        tb = QTextBrowser()
        tb.setObjectName("firstReviewOverview")
        tb.document().setDefaultFont(self.font())
        tb.setHtml("".join(html))
        v.addWidget(tb, 1)
        self.f_rows = self.p.q("SELECT f.*, d.filename, d.kind, d.addendum_no FROM findings f LEFT JOIN documents d ON d.id=f.doc_id "
                               "WHERE f.lead_id=? AND f.field!='addendum_ref' ORDER BY f.applicable DESC, f.field", (self.lid,))
        self.ft = table(["Field", "Value", "Source", "Status", "Evidence", "Note"],
                        [(R.LABELS.get(f["field"], f["field"]), R.pretty(f), R.cite(f), f["status"] + ("" if f["applicable"] else " (n/a)"),
                          f["snippet"], {"rule": "Source text", "ollama": "Ollama", "manual": "Manual"}.get(f["source"], f["source"]) + (" / " + f["note"] if f["note"] else "")) for f in self.f_rows],
                        colors=[STATUS_COLORS.get(f["status"]) for f in self.f_rows])
        v.addWidget(self.ft, 1)
        v.addWidget(row(btn("Verify selected", lambda: self.f_status("verified")), btn("Reject selected", lambda: self.f_status("rejected")),
                        btn("Choose this one (conflict)", self.f_choose), btn("Verify all drafts", self.f_all, True),
                        btn("Add finding manually...", self.f_manual), btn("Add or edit job walk...", self.f_job_walk), btn("Open source file", self.f_open),
                        btn("Export overview PDF", self.export_overview), None))

    def _sel_finding(self):
        i = selected_row(self.ft)
        return self.f_rows[i] if i is not None else None

    def f_status(self, s):
        f = self._sel_finding()
        if f:
            R.set_finding_status(self.p, f["id"], s)
            R.run_first_review(self.p, self.lid)
            self.refresh()

    def f_choose(self):
        f = self._sel_finding()
        if f:
            R.resolve_conflict(self.p, f["id"])
            R.run_first_review(self.p, self.lid)
            self.refresh()

    def f_all(self):
        if any(k == "conflict" for k, _ in R.flags(self.p, self.lid)):
            self.info("Conflicts stay open until you choose one source for each.")
        R.verify_all_drafts(self.p, self.lid)
        R.run_first_review(self.p, self.lid)
        self.refresh()

    def f_manual(self):
        docs = D.docs(self.p, self.lid)
        field, ok = QInputDialog.getItem(self, "Manual finding", "Field", list(R.LABELS)[:-1], 0, False)
        if not ok:
            return
        if field == "job_walk":
            return self.f_job_walk()
        if not docs:
            return self.info("Attach a source document before saving this type of finding.")
        value, ok = QInputDialog.getText(self, "Manual finding", "Value (for bid items: NO|Description|Qty|Unit|0 or 1 for option)")
        if not ok or not value:
            return
        doc, ok = QInputDialog.getItem(self, "Manual finding", "Source document", [d["filename"] for d in docs], 0, False)
        page, ok2 = QInputDialog.getInt(self, "Manual finding", "Page", 1, 1, 9999)
        if ok and ok2:
            d = [x for x in docs if x["filename"] == doc][0]
            R.add_manual_finding(self.p, self.lid, field, value, d["id"], page, "Entered manually from source")
            R.run_first_review(self.p, self.lid)
            self.refresh()

    def f_job_walk(self):
        active = self._sel_finding()
        if not (active and active["field"] == "job_walk" and active["source"] == "manual"):
            previous = self.p.q("SELECT * FROM findings WHERE lead_id=? AND field='job_walk' AND source='manual' AND status!='rejected'", (self.lid,))
            if len(previous) > 1:
                return self.info("Select the exact existing manual job walk row to edit it.")
            active = previous[0] if previous else None
        dlg = JobWalkDialog(self, self.p, self.lid, D.docs(self.p, self.lid), active)
        if dlg.exec() == QDialog.Accepted:
            R.run_first_review(self.p, self.lid)
            self.refresh(0)

    def f_open(self):
        f = self._sel_finding()
        if f and f["doc_id"]:
            d = self.p.one("SELECT original_path FROM documents WHERE id=?", (f["doc_id"],))
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.p.root / d["original_path"])))
            self.info(f"Look on page {f['page']} for:\n\n{f['snippet']}")

    def export_overview(self):
        ov = R.overview(self.p, self.lid)
        lead = self.p.one("SELECT * FROM leads WHERE id=?", (self.lid,))
        lines = []
        for k in R.OVERVIEW_FIELDS:
            lines.append(f"{R.LABELS[k]}:")
            lines += [f"   {x['value']}   [{x['cite']}; {x['status']}]" for x in ov[k]] or ["   NOT FOUND - check manually"]
        for w in ov["job_walk"]:
            details = JW.summary(JW.read(self.p, w["id"]))
            if details:
                lines += ["", "Job walk details:", *details.splitlines()]
        lines += ["", "Flags:"] + [f"   {k}: {m}" for k, m in ov["flags"]] + ["", f"Next decision: {ov['next']}"]
        out = self.p.root / "generated" / str(self.lid) / "First_Review.pdf"
        out.parent.mkdir(parents=True, exist_ok=True)
        K._pdf(out, f"First Review - {lead['solicitation_no']} {lead['title']}", lines)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(out)))

    def tab_docs(self, v):
        self.d_rows = D.docs(self.p, self.lid)
        self.dt = table(["Kind", "Addendum", "File", "Pages", "Text", "Reviewed", "SHA-256"],
                        [(d["kind"], d["addendum_no"] or "", d["filename"], d["pages"], d["text_status"],
                          "yes" if d["reviewed"] or d["text_status"] == "ok" else "NO", d["sha256"][:12]) for d in self.d_rows])
        v.addWidget(self.dt)
        v.addWidget(row(btn("Add files...", self.add_files, True), btn("From official notice...", self.from_notice),
                        btn("Change kind...", self.doc_kind), btn("Mark reviewed", self.doc_reviewed), btn("Open", self.doc_open), None))
        v.addWidget(label("Originals are stored once, read-only, under originals/. Generated files go to generated/.", "muted"))

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Attach files", "", "All (*)")
        for f in files:
            D.attach(self.p, self.lid, f)
        if files:
            self.run_review()

    def _sel_doc(self):
        i = selected_row(self.dt)
        return self.d_rows[i] if i is not None else None

    def doc_kind(self):
        d = self._sel_doc()
        if not d:
            return
        dialog = DocumentKindDialog(self, d)
        if dialog.exec() != QDialog.Accepted:
            return
        kind, number = dialog.choice()
        try:
            if D.reclassify(self.p, self.lid, d["id"], kind, number):
                self.refresh()
                self.info("Document kind changed. The attachment is unchanged. Select Re-run First Review when ready.")
        except ValueError as error:
            self.info(str(error))

    def doc_reviewed(self):
        d = self._sel_doc()
        if d:
            D.mark_reviewed(self.p, d["id"])
            self.refresh()

    def doc_open(self):
        d = self._sel_doc()
        if d:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.p.root / d["original_path"])))

    def tab_checklist(self, v):
        self.c_rows = P.checklist(self.p, self.lid)
        for cat, title in (("form", "Forms to fill out"), ("document", "Documents to gather")):
            v.addWidget(label(f"<b>{title}</b>"))
            rows = [c for c in self.c_rows if c["category"] == cat]
            t = table(["Item", "Status", "File", "Signature"],
                      [(c["name"], c["status"], Path(c["file_path"]).name if c["file_path"] else "", "you sign" if c["needs_signature"] else "")
                       for c in rows], colors=["#e3f4e6" if c["status"] in ("done", "na") else None for c in rows])
            t.setProperty("rows", [c["id"] for c in rows])
            setattr(self, f"ct_{cat}", t)
            v.addWidget(t)
        v.addWidget(row(btn("Attach completed file...", self.c_attach, True), btn("Mark done", lambda: self.c_status("done")),
                        btn("Mark N/A", lambda: self.c_status("na")), btn("Reopen", lambda: self.c_status("open")),
                        btn("Add item...", self.c_add), None))
        self.sugg = P.suggest_checklist(self.p, self.lid)
        v.addWidget(label("<b>Suggested from verified requirements</b> - tick what to save", "muted"))
        self.sl = QListWidget()
        for s in self.sugg:
            it = QListWidgetItem(f"[{'Form' if s['category'] == 'form' else 'Document'}] {s['name']}   ({s['cite']})")
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked)
            self.sl.addItem(it)
        self.sl.setMaximumHeight(140)
        v.addWidget(self.sl)
        v.addWidget(row(btn("Save checked items", self.c_save, False, "save-checklist-btn"), None))

    def _sel_check(self):
        for cat in ("form", "document"):
            t = getattr(self, f"ct_{cat}")
            i = selected_row(t)
            if i is not None:
                return t.property("rows")[i]
        self.info("Select a checklist item first.")

    def c_attach(self):
        cid = self._sel_check()
        if cid:
            f, _ = QFileDialog.getOpenFileName(self, "Completed form or gathered document", "", "All (*)")
            if f:
                P.set_checklist_file(self.p, cid, f)
                self.refresh()

    def c_status(self, s):
        cid = self._sel_check()
        if cid:
            P.set_checklist_status(self.p, cid, s)
            self.refresh()

    def c_add(self):
        cat, ok = QInputDialog.getItem(self, "Checklist", "Type", ["form", "document"], 0, False)
        name, ok2 = QInputDialog.getText(self, "Checklist", "Item name")
        if ok and ok2 and name:
            P.save_checklist_item(self.p, self.lid, cat, name, 1 if cat == "form" else 0)
            self.refresh()

    def c_save(self):
        for i, s in enumerate(self.sugg):
            if self.sl.item(i).checkState() == Qt.Checked:
                P.save_checklist_item(self.p, self.lid, s["category"], s["name"], s["needs_signature"], s["finding_id"])
        self.refresh()

    def tab_tasks(self, v):
        saved = P.tasks(self.p, self.lid)
        v.addWidget(label("<b>Saved tasks</b> (internal only - no invitations or reminders are sent)"))
        self.tt = table(["Due", "Task", "Done"], [(t["due_date"], t["title"], "yes" if t["done"] else "") for t in saved])
        self.tt.setProperty("rows", [t["id"] for t in saved])
        v.addWidget(self.tt)
        v.addWidget(row(btn("Toggle done", self.t_done), None))
        self.tsugg = P.suggest_tasks(self.p, self.lid)
        v.addWidget(label("<b>Suggested</b> - draft internal dates before the official cutoffs. Edit the date, untick to skip.", "muted"))
        self.st = table(["Save", "Due (edit)", "Task", "Based on"], [("", t["due_date"], t["title"], t["cite"]) for t in self.tsugg], editable=True)
        for i in range(len(self.tsugg)):
            self.st.item(i, 0).setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            self.st.item(i, 0).setCheckState(Qt.Checked)
        v.addWidget(self.st)
        v.addWidget(row(btn("Save checked tasks", self.t_save, True), None))
        if not self.tsugg and not saved:
            v.addWidget(label("No suggestions yet: verify the bid due date and other deadlines in First Review.", "muted"))

    def t_done(self):
        i = selected_row(self.tt)
        if i is not None:
            self.p.x("UPDATE tasks SET done=1-done WHERE id=?", (self.tt.property("rows")[i],))
            self.refresh()

    def t_save(self):
        for i, t in enumerate(self.tsugg):
            if self.st.item(i, 0).checkState() == Qt.Checked:
                P.save_task(self.p, self.lid, t["title"], self.st.item(i, 1).text(), t["finding_id"])
        self.refresh()

    def tab_estimate(self, v):
        lines = P.estimate_lines(self.p, self.lid)
        v.addWidget(label("Internal only. Costs and markup never go into the customer package. Scope, assumptions and exclusions appear in the cover letter.", "muted"))
        self.et = table(["Category", "Description", "Qty", "Unit", "Unit cost", "Extended"],
                        [(l["category"], l["description"], l["qty"], l["unit"], l["unit_cost"],
                          f"{(l['qty'] or 0) * (l['unit_cost'] or 0):,.2f}" if l["category"] in P.COST_CATS else "") for l in lines])
        self.et.setProperty("rows", [l["id"] for l in lines])
        v.addWidget(self.et)
        self.cat = QComboBox()
        self.cat.addItems(list(P.TEXT_CATS[:1] + P.COST_CATS + P.TEXT_CATS[1:]))
        self.desc, self.qty, self.unit, self.cost = QLineEdit(), QDoubleSpinBox(), QLineEdit(), QDoubleSpinBox()
        self.desc.setPlaceholderText("Description")
        self.unit.setPlaceholderText("Unit")
        for s in (self.qty, self.cost):
            s.setMaximum(1e9)
            s.setDecimals(2)
        v.addWidget(row(self.cat, self.desc, self.qty, self.unit, self.cost, btn("Add line", self.e_add, True), btn("Delete selected", self.e_del)))
        s = P.estimate_summary(self.p, self.lid)
        self.mk = QDoubleSpinBox()
        self.mk.setValue(s["markup_pct"])
        self.mk.setSuffix(" % markup")
        v.addWidget(row(self.mk, btn("Apply markup", self.e_markup),
                        label(f"Cost {s['cost']:,.2f}  ->  target {s['target']:,.2f}   |   Bid sheet base total {s['bid_base_total']:,.2f}"), None))

    def e_add(self):
        if self.desc.text().strip():
            P.add_estimate_line(self.p, self.lid, self.cat.currentText(), self.desc.text().strip(), self.qty.value(), self.unit.text(), self.cost.value())
            self.refresh()

    def e_del(self):
        i = selected_row(self.et)
        if i is not None:
            self.p.x("DELETE FROM estimate_lines WHERE id=?", (self.et.property("rows")[i],))
            self.refresh()

    def e_markup(self):
        P.set_markup(self.p, self.lid, self.mk.value())
        self.refresh()

    def tab_bidsheet(self, v):
        items = P.bid_items(self.p, self.lid)
        v.addWidget(label("Customer-facing bid schedule, built from the applicable documents (addenda included). Enter unit prices; blanks block readiness.", "muted"))
        self.bt = table(["No", "Description", "Qty", "Unit", "Option?", "Unit price (edit)", "Extended"],
                        [(b["item_no"], b["description"], f"{b['qty']:g}", b["unit"], "option" if b["is_option"] else "",
                          "" if b["unit_price"] is None else f"{b['unit_price']:.2f}",
                          f"{b['qty'] * b['unit_price']:,.2f}" if b["unit_price"] else "") for b in items],
                        editable=True, colors=["#fde2e0" if not b["unit_price"] else None for b in items])
        self.bt.setProperty("rows", [b["id"] for b in items])
        v.addWidget(self.bt)
        base = sum(b["qty"] * (b["unit_price"] or 0) for b in items if not b["is_option"])
        v.addWidget(row(btn("Save prices", self.b_save, True), label(f"<b>Base bid total: ${base:,.2f}</b> (options priced separately)"), None))

    def b_save(self):
        for i, bid in enumerate(self.bt.property("rows")):
            txt = self.bt.item(i, 5).text().replace("$", "").replace(",", "").strip()
            try:
                P.set_unit_price(self.p, bid, float(txt) if txt else None)
            except ValueError:
                return self.info(f"Row {i + 1}: '{txt}' is not a number.")
        self.refresh()

    def tab_package(self, v):
        last = self.p.one("SELECT * FROM packages WHERE lead_id=? ORDER BY id DESC", (self.lid,))
        v.addWidget(row(btn("Generate draft package and inspect files", self.k_gen, True, "generate-package-btn"),
                        btn("Re-inspect last package", self.k_inspect), btn("Open package folder", self.k_open), None))
        if not last:
            v.addWidget(label("No package yet. BidDesk will build the cover letter, price sheet, addendum acknowledgment, forms and supporting documents from the live checklist, then open each exported file and check it.", "muted"))
            v.addStretch()
            return
        import json
        rep = json.loads(last["report"])
        verdict = "READY FOR YOUR REVIEW" if last["status"] == "ready_for_review" else "NOT READY - fix the open items below"
        v.addWidget(label(f"<b>{verdict}</b>  ({last['created_at']}, {last['folder']})", "nextText"))
        names = {"pass": "Passed", "fail": "OPEN", "you": "For you"}
        res = sorted(rep["results"], key=lambda r: ["fail", "you", "pass"].index(r["status"]))
        v.addWidget(table(["Result", "Check", "Why"], [(names[r["status"]], r["check"], r["detail"]) for r in res],
                          colors=[STATUS_COLORS[r["status"]] for r in res]), 1)
        v.addWidget(label("BidDesk never submits, emails, signs, or contacts anyone. Signatures and certifications are yours.", "muted"))

    def k_gen(self):
        K.generate_package(self.p, self.lid)
        self.refresh()

    def k_inspect(self):
        import json
        last = self.p.one("SELECT * FROM packages WHERE lead_id=? ORDER BY id DESC", (self.lid,))
        if last:
            rep = K.inspect_package(self.p, self.lid, self.p.root / last["folder"])
            self.p.x("UPDATE packages SET report=?, status=? WHERE id=?",
                     (json.dumps(rep), "ready_for_review" if rep["ready"] else "blocked", last["id"]))
            self.refresh()

    def k_open(self):
        last = self.p.one("SELECT * FROM packages WHERE lead_id=? ORDER BY id DESC", (self.lid,))
        if last:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.p.root / last["folder"])))


class Main(QMainWindow):
    NAV = ("Dashboard", "Leads", "Bids in progress", "Awarded", "Settings")

    def __init__(self, folder=None):
        super().__init__()
        self.setWindowTitle("BidDesk Emergent | Job Walk Test 4 source snapshot")
        self.resize(1360, 860)
        self.qs = QSettings("BidDesk", "Emergent Development Snapshot")
        self.font_points = safe_font_size(self.qs.value(FONT_KEY, DEFAULT_FONT))
        apply_appearance(QApplication.instance(), self.font_points)
        if folder is None:
            raise ValueError("Start BidDesk with an explicit development workspace.")
        self.open_project(folder)
        root = QWidget()
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.resize_nav()
        self.nav.addItems(self.NAV)
        self.stack = QStackedWidget()
        self.stack.setObjectName("content")
        self.pages = {"Dashboard": Dashboard(self), "Leads": LeadsPage(self),
                      "Bids in progress": StagePage(self, "pipeline", "Bids in progress"),
                      "Awarded": StagePage(self, "awarded", "Awarded work"), "Settings": SettingsPage(self)}
        self.bid = BidPage(self)
        for pg in list(self.pages.values()) + [self.bid]:
            self.stack.addWidget(pg)
        self.nav.currentTextChanged.connect(self.go)
        h.addWidget(self.nav)
        h.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self.nav.setCurrentRow(0)

    def resize_nav(self):
        self.nav.setFixedWidth(max(200, max(self.nav.fontMetrics().horizontalAdvance(item) for item in self.NAV) + 46))

    def set_font_size(self, value):
        self.font_points = safe_font_size(value)
        self.qs.setValue(FONT_KEY, self.font_points)
        self.qs.sync()
        apply_appearance(QApplication.instance(), self.font_points)
        self.resize_nav()
        for bar in self.findChildren(ButtonBar):
            bar.refit()
        for table in self.findChildren(QTableWidget):
            table.verticalHeader().setDefaultSectionSize(max(25, table.fontMetrics().height() + 9))
        if hasattr(self.bid, "tabs"):
            for browser in self.bid.findChildren(QTextBrowser):
                browser.document().setDefaultFont(browser.font())

    def open_project(self, folder):
        self.project = Project(folder)

    def go(self, name):
        pg = self.pages[name]
        pg.refresh()
        self.stack.setCurrentWidget(pg)
        if self.nav.currentItem() and self.nav.currentItem().text() != name:
            self.nav.blockSignals(True)
            self.nav.setCurrentRow(self.NAV.index(name))
            self.nav.blockSignals(False)

    def open_bid(self, lid, tab=0):
        self.bid.show_bid(lid, tab)
        self.stack.setCurrentWidget(self.bid)
        self.nav.blockSignals(True)
        self.nav.setCurrentRow(self.NAV.index("Awarded" if self.project.one("SELECT stage FROM leads WHERE id=?", (lid,))["stage"] == "awarded" else "Bids in progress"))
        self.nav.blockSignals(False)


def main():
    app = QApplication(sys.argv)
    w = Main(sys.argv[1] if len(sys.argv) > 1 else None)
    w.show()
    sys.exit(app.exec())
