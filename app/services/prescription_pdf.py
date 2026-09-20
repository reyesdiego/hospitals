"""El papel que el paciente se lleva: receta médica e indicaciones de prácticas.

Son dos documentos en un mismo PDF, cada uno en su hoja, porque en la farmacia se presenta
la receta y en el centro de diagnóstico la orden de prácticas.
"""

from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.core.config import settings
from app.models.prescription import DischargePrescription, PrescriptionKind

LEFT = 20 * mm
RIGHT = A4[0] - 20 * mm
TOP = A4[1] - 20 * mm
BOTTOM = 25 * mm
LINE = 5.5 * mm


@dataclass(frozen=True)
class PrescriptionDocument:
    """Todo lo que va impreso, ya resuelto: el PDF no consulta la base."""

    facility_name: str
    patient_name: str
    patient_document: str
    coverage: str | None
    member_number: str | None
    physician: str
    discharged_at: datetime | None
    prescriptions: list[DischargePrescription]

    @property
    def medications(self) -> list[DischargePrescription]:
        return [item for item in self.prescriptions if item.kind is PrescriptionKind.MEDICATION]

    @property
    def practices(self) -> list[DischargePrescription]:
        return [item for item in self.prescriptions if item.kind is PrescriptionKind.PRACTICE]


def _local(moment: datetime | None) -> str:
    if not moment:
        return "-"
    return moment.astimezone(ZoneInfo(settings.timezone)).strftime("%d/%m/%Y %H:%M")


def _wrap(pdf: canvas.Canvas, text: str, width: float, font: str, size: float) -> list[str]:
    """Corta el texto a mano: una indicación larga no puede salirse de la hoja."""

    words, lines, current = text.split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if pdf.stringWidth(candidate, font, size) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


class _Page:
    """Cursor de escritura: sabe en qué renglón va y cuándo pasar de hoja."""

    def __init__(self, pdf: canvas.Canvas, document: PrescriptionDocument, title: str):
        self.pdf = pdf
        self.document = document
        self.title = title
        self.y = TOP
        self._header()

    def _header(self) -> None:
        pdf, doc = self.pdf, self.document
        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(LEFT, self.y, doc.facility_name)
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawRightString(RIGHT, self.y, self.title)
        self.y -= 7 * mm
        pdf.line(LEFT, self.y, RIGHT, self.y)
        self.y -= 7 * mm

        coverage = doc.coverage or "Particular"
        if doc.member_number:
            coverage = f"{coverage} - afiliado {doc.member_number}"
        for label, value in (
            ("Paciente", doc.patient_name),
            ("Documento", doc.patient_document),
            ("Cobertura", coverage),
            ("Profesional", doc.physician),
            ("Fecha de alta", _local(doc.discharged_at)),
        ):
            pdf.setFont("Helvetica-Bold", 9)
            pdf.drawString(LEFT, self.y, f"{label}:")
            pdf.setFont("Helvetica", 9)
            pdf.drawString(LEFT + 25 * mm, self.y, value)
            self.y -= LINE
        self.y -= 3 * mm

    def _space(self, lines: int) -> None:
        if self.y - lines * LINE < BOTTOM:
            self.pdf.showPage()
            self.y = TOP
            self._header()

    def item(self, number: int, title: str, details: list[str]) -> None:
        self._space(len(details) + 2)
        self.pdf.setFont("Helvetica-Bold", 10)
        for line in _wrap(self.pdf, f"{number}. {title}", RIGHT - LEFT, "Helvetica-Bold", 10):
            self.pdf.drawString(LEFT, self.y, line)
            self.y -= LINE
        self.pdf.setFont("Helvetica", 9)
        for detail in details:
            for line in _wrap(self.pdf, detail, RIGHT - LEFT - 6 * mm, "Helvetica", 9):
                self.pdf.drawString(LEFT + 6 * mm, self.y, line)
                self.y -= LINE
        self.y -= 2 * mm

    def empty(self, message: str) -> None:
        self.pdf.setFont("Helvetica-Oblique", 10)
        self.pdf.drawString(LEFT, self.y, message)
        self.y -= LINE

    def signature(self) -> None:
        """La firma va al pie de la hoja, no debajo del último renglón."""

        y = BOTTOM + 18 * mm
        self.pdf.line(RIGHT - 70 * mm, y, RIGHT, y)
        self.pdf.setFont("Helvetica", 9)
        self.pdf.drawCentredString(RIGHT - 35 * mm, y - 5 * mm, self.document.physician)
        self.pdf.setFont("Helvetica-Oblique", 8)
        self.pdf.drawCentredString(RIGHT - 35 * mm, y - 10 * mm, "Firma y sello")


def _medication_details(item: DischargePrescription) -> list[str]:
    details = []
    if item.dosage:
        details.append(f"Posologia: {item.dosage}")
    if item.duration_days:
        details.append(f"Duracion: {item.duration_days} dias")
    if item.instructions:
        details.append(item.instructions)
    return details


def _practice_details(item: DischargePrescription) -> list[str]:
    details = []
    if item.quantity and item.quantity != 1:
        details.append(f"Cantidad: {item.quantity.normalize()}")
    if item.instructions:
        details.append(item.instructions)
    return details


def render(document: PrescriptionDocument) -> bytes:
    """Arma el PDF y lo devuelve en memoria: no se guarda en disco."""

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setTitle(f"Indicaciones de alta - {document.patient_name}")

    page = _Page(pdf, document, "RECETA MEDICA")
    if document.medications:
        for number, item in enumerate(document.medications, start=1):
            title = item.description
            if item.presentation:
                title = f"{title} - {item.presentation}"
            if item.quantity and item.quantity != 1:
                title = f"{title} (x{item.quantity.normalize()})"
            page.item(number, title, _medication_details(item))
    else:
        page.empty("Sin medicacion indicada al alta.")
    page.signature()

    pdf.showPage()
    page = _Page(pdf, document, "INDICACION DE PRACTICAS")
    if document.practices:
        for number, item in enumerate(document.practices, start=1):
            page.item(number, item.description, _practice_details(item))
    else:
        page.empty("Sin practicas indicadas al alta.")
    page.signature()

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
