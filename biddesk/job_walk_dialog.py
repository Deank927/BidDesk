from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel,
                               QLineEdit, QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from . import job_walk as J, review as R, county_rss as C


class JobWalkDialog(QDialog):
    def __init__(self, parent, project, lead_id, docs, existing=None):
        super().__init__(parent)
        self.setWindowTitle("Job walk details")
        self.resize(720, 740)
        self.project, self.lead_id, self.existing = project, lead_id, existing
        self.docs = {r["id"]: r for r in docs if r["pages"] > 0}
        old = J.read(project, existing["id"]) if existing else {}
        layout = QVBoxLayout(self)
        tip = QLabel("Enter only what the notice states. Saving records a local finding. It does not RSVP, send a waiver or book anything.")
        tip.setWordWrap(True)
        layout.addWidget(tip)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        form = QFormLayout(body)
        scroll.setWidget(body)
        layout.addWidget(scroll)
        self.inputs = {}
        self.choice(form, "Attendance", "attendance", J.ATTENDANCE, old)
        self.entry(form, "Walk date", "walk_date", "YYYY-MM-DD", old)
        self.entry(form, "Walk time", "walk_time", "HH:MM (24-hour); blank if not stated", old)
        self.choice(form, "Walk time zone", "zone", J.ZONES, old)
        self.entry(form, "Location / full address", "address", "Site name, street, city, state, ZIP", old)
        self.choice(form, "RSVP", "rsvp", J.REQUIREMENT, old)
        self.choice(form, "Waiver / release form", "waiver", J.REQUIREMENT, old)
        self.entry(form, "RSVP / waiver cutoff date", "cutoff_date", "YYYY-MM-DD; blank if not stated", old)
        self.entry(form, "RSVP / waiver cutoff time", "cutoff_time", "HH:MM; blank if not stated", old)
        self.choice(form, "Cutoff time zone", "cutoff_zone", J.ZONES, old)
        self.entry(form, "Contact / instructions", "instructions", "Email or instructions as written in the notice", old)
        self.bid_due_reference(form)
        self.entry(form, "Bid due date (from source)", "bid_due_date", "YYYY-MM-DD; blank if not confirmed from source", old)
        self.entry(form, "Bid due time", "bid_due_time", "HH:MM; blank if not stated", old)
        self.choice(form, "Bid due time zone", "bid_due_zone", J.ZONES, old)
        self.doc = QComboBox()
        self.doc.addItem("Pasted notice / no attached document", None)
        for r in self.docs.values():
            self.doc.addItem(r["filename"], r["id"])
        self.page = QSpinBox()
        self.page.setRange(1, 1)
        form.addRow("Source document", self.doc)
        form.addRow("Physical PDF / source page", self.page)
        self.doc.currentIndexChanged.connect(self.update_pages)
        if existing and existing["doc_id"] in self.docs:
            self.doc.setCurrentIndex(self.doc.findData(existing["doc_id"]))
        self.update_pages()
        if existing and existing["page"]:
            self.page.setValue(existing["page"])
        self.entry(form, "Evidence / notice note", "evidence", "Paste the key source wording or identify the notice", old)
        self.error = QLabel("")
        self.error.setWordWrap(True)
        self.error.setTextFormat(Qt.PlainText)
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save_finding)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.inputs["walk_date"].setFocus()

    def bid_due_reference(self, form):
        official = R.applicable(self.project, self.lead_id, "bid_due")
        lines = ["Bid due fields here are a reference. Saving will not change verified deadlines or the calendar."]
        for f in official:
            lines.append(f"Existing finding: {f['value']} ({f['status']}; {R.cite(f)})")
        lead = self.project.one("SELECT * FROM leads WHERE id=?", (self.lead_id,))
        if lead and lead["source"] == "la_county_open_rss" and C.notice_key(lead["notice_url"]) == lead["solicitation_no"]:
            marker = " - Closing:"
            title = lead["title"] or ""
            if marker in title:
                close = C.closing_text(title.rsplit(marker, 1)[1])
                lines.append("County feed at import (unverified): " + close)
        self.due_reference = QLabel("\n".join(lines))
        self.due_reference.setTextFormat(Qt.PlainText)
        self.due_reference.setWordWrap(True)
        form.addRow("Bid due reference", self.due_reference)

    def entry(self, form, label, name, hint, old):
        field = QLineEdit(old.get(name, ""))
        field.setMaxLength(J.FIELDS[name])
        field.setPlaceholderText(hint)
        self.inputs[name] = field
        form.addRow(label, field)

    def choice(self, form, label, name, items, old):
        field = QComboBox()
        field.addItems(items)
        if old.get(name) in items:
            field.setCurrentText(old[name])
        self.inputs[name] = field
        form.addRow(label, field)

    def update_pages(self, *_):
        doc = self.docs.get(self.doc.currentData())
        self.page.setEnabled(doc is not None)
        self.page.setMaximum(doc["pages"] if doc else 1)

    def save_finding(self):
        data = {k: widget.currentText() if isinstance(widget, QComboBox) else widget.text()
                for k, widget in self.inputs.items()}
        try:
            J.save(self.project, self.lead_id, data, self.doc.currentData(), self.page.value(),
                   self.existing["id"] if self.existing else None)
        except ValueError as error:
            self.error.setText(str(error))
            return
        self.accept()
