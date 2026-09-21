"""Horarios de medicación: cuándo toca la próxima toma y cuáles se pasaron de hora.

El cálculo vive acá, separado de la base, porque es la parte que hay que poder razonar y
probar sola: dada una indicación, sus tomas y una ventana de tiempo, qué se dio, qué falta
y qué está vencido.

Dos esquemas generan horarios de distinta manera, y la diferencia importa:

* **por intervalo** ("cada 8 horas") la próxima toma se cuenta desde la última que se dio,
  no desde un reloj fijo: si una se atrasó, las siguientes se corren con ella;
* **por horarios** (08:00, 14:00, 20:00) los horarios son del día y no se mueven: una toma
  que no se dio a las 14 queda vencida aunque después se dé otra.
"""

import enum
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.models.treatment import (
    AdministrationStatus,
    HospitalizationTreatment,
    ScheduleKind,
    TreatmentAdministration,
    TreatmentStatus,
)

#: Cuánto puede atrasarse una toma antes de considerarse vencida. Media hora es lo que
#: tarda una vuelta de sala: marcar en rojo antes de eso sería ruido.
GRACE = timedelta(minutes=30)

#: Cuánto puede alejarse una toma de su horario y seguir siendo esa toma. Con horarios
#: muy espaciados se agranda hasta la mitad de la distancia entre dos: la de las 8 dada a
#: las 11 sigue siendo la de las 8, y no una de más con la de las 8 vencida.
MATCH_TOLERANCE = timedelta(hours=2)


def _tolerance(treatment: HospitalizationTreatment) -> timedelta:
    """Se calcula sobre el esquema y no sobre la ventana: una toma diaria tolera medio
    día de atraso y sigue siendo la del día."""

    if treatment.schedule_kind == ScheduleKind.INTERVAL and treatment.interval_hours:
        return max(MATCH_TOLERANCE, timedelta(hours=treatment.interval_hours) / 2)
    if treatment.schedule_kind == ScheduleKind.TIMES and treatment.times_of_day:
        minutes = sorted(
            moment.hour * 60 + moment.minute for moment in treatment.times_of_day
        )
        # La distancia al horario siguiente, dando la vuelta al día. Con un solo horario
        # el siguiente es el de mañana.
        gaps = (
            [24 * 60]
            if len(minutes) == 1
            else [
                (later - earlier) % (24 * 60)
                for earlier, later in zip(minutes, minutes[1:] + minutes[:1], strict=True)
            ]
        )
        return max(MATCH_TOLERANCE, timedelta(minutes=min(gaps) / 2))
    return MATCH_TOLERANCE

#: Tope de horarios proyectados por indicación: una ventana larga con un intervalo corto
#: llenaría la pantalla sin decir nada.
MAX_SLOTS = 60


class DoseState(str, enum.Enum):
    GIVEN = "GIVEN"
    OMITTED = "OMITTED"
    #: Todavía no toca, o toca dentro de la tolerancia.
    PENDING = "PENDING"
    #: Pasó su hora y nadie la registró.
    OVERDUE = "OVERDUE"


@dataclass(frozen=True)
class DoseSlot:
    """Un punto en la línea de tiempo: una toma que ocurrió o una que tiene que ocurrir."""

    due_at: datetime
    state: DoseState
    administration_id: object | None = None
    dose: str | None = None
    reason: str | None = None

    @property
    def planned(self) -> bool:
        return self.state in {DoseState.PENDING, DoseState.OVERDUE}


def frequency_label(
    kind: ScheduleKind,
    *,
    interval_hours: int | None = None,
    times_of_day: list[time] | None = None,
) -> str:
    """Cómo se lee el esquema en el papel, para no escribirlo dos veces."""

    if kind == ScheduleKind.INTERVAL and interval_hours:
        return f"cada {interval_hours} horas" if interval_hours != 1 else "cada hora"
    if kind == ScheduleKind.TIMES and times_of_day:
        return " - ".join(moment.strftime("%H:%M") for moment in sorted(times_of_day))
    return {
        ScheduleKind.ONCE: "única vez",
        ScheduleKind.AS_NEEDED: "a demanda",
        ScheduleKind.CONTINUOUS: "continuo",
    }.get(kind, "")


def _given(administrations: list[TreatmentAdministration]) -> list[TreatmentAdministration]:
    """Las tomas que cuentan: una anulada no ocurrió."""

    return sorted(
        (item for item in administrations if item.status != AdministrationStatus.VOID),
        key=lambda item: item.administered_at,
    )


def _state_of_planned(due_at: datetime, now: datetime) -> DoseState:
    return DoseState.OVERDUE if due_at + GRACE < now else DoseState.PENDING


def _times_slots(
    treatment: HospitalizationTreatment,
    *,
    window_start: datetime,
    window_end: datetime,
    zone: ZoneInfo,
) -> list[datetime]:
    """Los horarios fijos del día que caen en la ventana."""

    if not treatment.times_of_day:
        return []
    start: date = window_start.astimezone(zone).date()
    end: date = window_end.astimezone(zone).date()
    slots: list[datetime] = []
    day = start
    while day <= end and len(slots) < MAX_SLOTS:
        for moment in sorted(treatment.times_of_day):
            due = datetime.combine(day, moment, tzinfo=zone)
            if window_start <= due <= window_end and due >= treatment.started_at:
                slots.append(due)
        day += timedelta(days=1)
    return slots


def _interval_slots(
    treatment: HospitalizationTreatment,
    administrations: list[TreatmentAdministration],
    *,
    window_end: datetime,
) -> list[datetime]:
    """Las próximas tomas, contadas desde la última que se dio."""

    if not treatment.interval_hours:
        return []
    step = timedelta(hours=treatment.interval_hours)
    last = administrations[-1].administered_at if administrations else None
    due = (last or treatment.started_at) + step
    slots: list[datetime] = []
    while due <= window_end and len(slots) < MAX_SLOTS:
        slots.append(due)
        due += step
    return slots


def plan_doses(
    treatment: HospitalizationTreatment,
    administrations: list[TreatmentAdministration],
    *,
    window_start: datetime,
    window_end: datetime,
    now: datetime,
    timezone: str = "UTC",
) -> list[DoseSlot]:
    """La línea de tiempo de una indicación dentro de la ventana pedida.

    Lo que ya pasó son hechos —las tomas registradas— y lo que viene son horarios
    calculados. Una indicación cerrada no proyecta nada hacia adelante: lo que quedó
    registrado es todo lo que hubo.
    """

    zone = ZoneInfo(timezone)
    given = _given(administrations)
    slots = [
        DoseSlot(
            due_at=item.administered_at,
            state=(
                DoseState.GIVEN
                if item.status == AdministrationStatus.GIVEN
                else DoseState.OMITTED
            ),
            administration_id=item.id,
            dose=item.dose,
            reason=item.omission_reason,
        )
        for item in given
        if window_start <= item.administered_at <= window_end
    ]

    planned: list[datetime] = []
    if treatment.status == TreatmentStatus.ACTIVE:
        if treatment.schedule_kind == ScheduleKind.TIMES:
            planned = _times_slots(
                treatment,
                window_start=window_start,
                window_end=window_end,
                zone=zone,
            )
        elif treatment.schedule_kind == ScheduleKind.INTERVAL:
            planned = _interval_slots(treatment, given, window_end=window_end)
        elif treatment.schedule_kind == ScheduleKind.ONCE and not given:
            planned = [treatment.started_at]

    # Un horario ya cubierto por una toma cercana no se muestra dos veces, y cada toma
    # cubre un solo horario.
    tolerance = _tolerance(treatment)
    unmatched = [item.administered_at for item in given]
    for due in planned:
        if due < window_start:
            continue
        near = [moment for moment in unmatched if abs(moment - due) <= tolerance]
        if near:
            unmatched.remove(min(near, key=lambda moment: abs(moment - due)))
            continue
        slots.append(DoseSlot(due_at=due, state=_state_of_planned(due, now)))

    return sorted(slots, key=lambda slot: slot.due_at)


def next_due(slots: list[DoseSlot]) -> datetime | None:
    """El horario que sigue: el más viejo sin dar, que es por donde se empieza."""

    pending = [slot.due_at for slot in slots if slot.planned]
    return min(pending) if pending else None


def is_overdue(slots: list[DoseSlot]) -> bool:
    return any(slot.state == DoseState.OVERDUE for slot in slots)
