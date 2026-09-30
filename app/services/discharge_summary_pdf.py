"""El resumen de alta impreso: una hoja que se lee de arriba abajo.

Los diagnósticos van codificados en CIE-10 y con el texto que tenían cuando se asentaron,
que es lo que después se factura y lo que va a la estadística.
"""

from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.models.diagnosis import HospitalizationDiagnosis
from app.models.prescription import PrescriptionKind
from app.services.discharge_summary import (
    DischargeSummary,
    PerformedPractice,
    TreatmentLine,
)
from app.services.prescription_pdf import BOTTOM, LEFT, LINE, RIGHT, TOP, _local, _wrap

ROLE_LABELS = {
    "PRINCIPAL": "principal",
    "SECONDARY": "secundario",
    "COMORBIDITY": "comorbilidad",
    "COMPLICATION": "complicacion",
}
DISCHARGE_TYPE_LABELS = {
    "MEDICAL": "Alta medica",
    "VOLUNTARY": "Alta voluntaria",
    "TRANSFER": "Derivacion",
    "DECEASED": "Fallecimiento",
    "ABSCONDED": "Retiro sin alta",
    "OTHER": "Otra",
}
ROUTE_LABELS = {
    "ORAL": "via oral",
    "INTRAVENOUS": "endovenosa",
    "INTRAMUSCULAR": "intramuscular",
    "SUBCUTANEOUS": "subcutanea",
    "INHALATORY": "inhalatoria",
    "TOPICAL": "topica",
    "RECTAL": "rectal",
    "OTHER": "otra via",
}
NOTE_LABELS = {
    "EVOLUTION": "Evolucion",
    "OBSERVATION": "Observacion",
    "INTERCONSULTATION": "Interconsulta",
    "NURSING": "Enfermeria",
}
TREATMENT_STATUS_LABELS = {
    "ACTIVE": "en curso al alta",
    "SUSPENDED": "suspendida",
    "COMPLETED": "cumplida",
}
DESTINATION_LABELS = {
    "HOME": "Domicilio",
    "OTHER_FACILITY": "Otro centro",
    "HOME_CARE": "Internacion domiciliaria",
    "REHABILITATION": "Rehabilitacion",
    "OTHER": "Otro",
}


class _Sheet:
    """Cursor de escritura: sabe en qué renglón va y cuándo pasar de hoja."""

    def __init__(self, pdf: canvas.Canvas, summary: DischargeSummary):
        self.pdf = pdf
        self.summary = summary
        self.y = TOP
        self._header()

    def _header(self) -> None:
        pdf, doc = self.pdf, self.summary
        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(LEFT, self.y, doc.facility_name)
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawRightString(RIGHT, self.y, "RESUMEN DE ALTA")
        self.y -= 7 * mm
        pdf.line(LEFT, self.y, RIGHT, self.y)
        self.y -= 7 * mm

        if doc.draft:
            # Sin alta médica el papel no es el definitivo, y tiene que decirlo.
            pdf.setFont("Helvetica-Bold", 9)
            pdf.drawString(
                LEFT,
                self.y,
                "DOCUMENTO PROVISORIO: la internacion todavia no tiene alta medica.",
            )
            self.y -= LINE + 2 * mm

        coverage = doc.coverage or "Particular"
        if doc.member_number:
            coverage = f"{coverage} - afiliado {doc.member_number}"
        stay = doc.length_of_stay_days
        rows = [
            ("Paciente", doc.patient_name),
            ("Documento", doc.patient_document),
            ("Cobertura", coverage),
            ("Servicio", doc.service_name or "-"),
            ("Ubicacion", doc.bed_label or "-"),
            ("Ingreso", _local(doc.admitted_at)),
            ("Egreso", _local(doc.discharged_at)),
            ("Estadia", f"{stay} dias" if stay is not None else "-"),
        ]
        for label, value in rows:
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

    def section(self, title: str) -> None:
        self._space(4)
        # Aire antes del título: sin esto el bloque anterior queda pegado al siguiente.
        self.y -= 3 * mm
        self.pdf.setFont("Helvetica-Bold", 10)
        self.pdf.drawString(LEFT, self.y, title.upper())
        self.y -= LINE * 0.7
        self.pdf.line(LEFT, self.y, RIGHT, self.y)
        self.y -= LINE

    def paragraph(self, text: str, *, italic: bool = False) -> None:
        font = "Helvetica-Oblique" if italic else "Helvetica"
        lines = _wrap(self.pdf, text, RIGHT - LEFT, font, 9)
        self._space(len(lines) + 1)
        self.pdf.setFont(font, 9)
        for line in lines:
            self.pdf.drawString(LEFT, self.y, line)
            self.y -= LINE
        self.y -= 2 * mm

    def bullet(self, title: str, detail: str | None = None) -> None:
        lines = _wrap(self.pdf, title, RIGHT - LEFT - 6 * mm, "Helvetica-Bold", 9)
        self._space(len(lines) + (1 if detail else 0))
        self.pdf.setFont("Helvetica-Bold", 9)
        for index, line in enumerate(lines):
            self.pdf.drawString(LEFT + (2 * mm if index == 0 else 6 * mm), self.y, line)
            self.y -= LINE
        if detail:
            self.pdf.setFont("Helvetica", 8.5)
            for line in _wrap(self.pdf, detail, RIGHT - LEFT - 6 * mm, "Helvetica", 8.5):
                self.pdf.drawString(LEFT + 6 * mm, self.y, line)
                self.y -= LINE

    def signature(self) -> None:
        y = max(self.y - 10 * mm, BOTTOM + 18 * mm)
        self.pdf.line(RIGHT - 70 * mm, y, RIGHT, y)
        self.pdf.setFont("Helvetica", 9)
        self.pdf.drawCentredString(RIGHT - 35 * mm, y - 5 * mm, self.summary.physician)
        self.pdf.setFont("Helvetica-Oblique", 8)
        self.pdf.drawCentredString(RIGHT - 35 * mm, y - 10 * mm, "Firma y sello")


def _diagnosis_line(entry: HospitalizationDiagnosis) -> str:
    role = ROLE_LABELS.get(entry.role.value, entry.role.value.lower())
    line = f"{entry.code} - {entry.description} ({role})"
    if entry.diagnosed_by_name:
        line = f"{line} - indicado por {entry.diagnosed_by_name}"
    return line


def _treatment_line(line: TreatmentLine) -> str:
    treatment = line.treatment
    title = treatment.description
    if treatment.presentation:
        title = f"{title} - {treatment.presentation}"
    return title


def _treatment_detail(line: TreatmentLine) -> str:
    """La dosis, el período y lo que efectivamente se le dio."""

    treatment = line.treatment
    parts = [
        treatment.dose,
        ROUTE_LABELS.get(treatment.route.value) if treatment.route else None,
        treatment.frequency,
        f"desde {_local(treatment.started_at)}",
        f"hasta {_local(treatment.ended_at)}" if treatment.ended_at else None,
        TREATMENT_STATUS_LABELS.get(treatment.status.value),
    ]
    doses = f"{line.given} toma(s) registrada(s)"
    if line.omitted:
        doses = f"{doses}, {line.omitted} no administrada(s)"
    parts.append(doses)
    return " · ".join(part for part in parts if part)


def _practice_line(practice: PerformedPractice) -> str:
    title = f"{practice.code} - {practice.name}"
    if practice.quantity and practice.quantity != 1:
        title = f"{title} (x{practice.quantity.normalize()})"
    return title


def render(summary: DischargeSummary) -> bytes:
    """Arma el PDF y lo devuelve en memoria: no se guarda en disco."""

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setTitle(f"Resumen de alta - {summary.patient_name}")
    sheet = _Sheet(pdf, summary)

    sheet.section("Motivo de internacion")
    sheet.paragraph(summary.admission_reason or "-")

    sheet.section("Diagnosticos de ingreso")
    if summary.admission_diagnoses:
        for entry in summary.admission_diagnoses:
            sheet.bullet(_diagnosis_line(entry), entry.notes)
    else:
        sheet.paragraph("Sin diagnosticos codificados al ingreso.", italic=True)

    sheet.section("Diagnosticos de egreso")
    if summary.discharge_diagnoses:
        for entry in summary.discharge_diagnoses:
            sheet.bullet(_diagnosis_line(entry), entry.notes)
    else:
        sheet.paragraph("Sin diagnosticos codificados al egreso.", italic=True)

    sheet.section("Practicas realizadas")
    if summary.practices:
        for practice in summary.practices:
            sheet.bullet(_practice_line(practice), _local(practice.performed_at))
    else:
        sheet.paragraph("Sin practicas registradas durante la internacion.", italic=True)

    sheet.section("Medicacion y tratamientos de la internacion")
    if summary.treatments:
        for line in summary.treatments:
            sheet.bullet(_treatment_line(line), _treatment_detail(line))
    else:
        sheet.paragraph(
            "Sin medicacion ni tratamientos registrados durante la internacion.",
            italic=True,
        )

    sheet.section("Evolucion e interconsultas")
    if summary.notes:
        for note in summary.notes:
            heading = " · ".join(
                part
                for part in (
                    NOTE_LABELS.get(note.kind.value, note.kind.value),
                    _local(note.noted_at),
                    note.recorded_by_user_name,
                )
                if part
            )
            sheet.bullet(heading, note.note)
    else:
        sheet.paragraph("Sin notas de evolucion registradas.", italic=True)

    sheet.section("Egreso")
    egreso = [
        DISCHARGE_TYPE_LABELS.get(summary.discharge_type or "", summary.discharge_type),
        DESTINATION_LABELS.get(summary.discharge_destination or "", None),
    ]
    detail = " - ".join(item for item in egreso if item) or "Sin alta medica registrada"
    sheet.paragraph(detail)
    if summary.discharge_reason:
        sheet.paragraph(f"Evolucion: {summary.discharge_reason}")

    medication = [
        item for item in summary.prescriptions if item.kind is PrescriptionKind.MEDICATION
    ]
    sheet.section("Medicacion al alta")
    if medication:
        for item in medication:
            title = item.description
            if item.presentation:
                title = f"{title} - {item.presentation}"
            sheet.bullet(title, item.dosage)
    else:
        sheet.paragraph("Sin medicacion indicada al alta.", italic=True)

    if summary.instructions:
        sheet.section("Indicaciones")
        sheet.paragraph(summary.instructions)

    sheet.signature()
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
