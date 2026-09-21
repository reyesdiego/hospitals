"""Cálculo de horarios de medicación: qué toca, qué se dio y qué se venció.

Sin base de datos: es el cálculo lo que se está probando.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta

from app.models.treatment import (
    AdministrationStatus,
    ScheduleKind,
    TreatmentStatus,
)
from app.services.medication_schedule import (
    DoseState,
    frequency_label,
    is_overdue,
    next_due,
    plan_doses,
)

TZ = "America/Argentina/Buenos_Aires"
NOW = datetime(2026, 9, 21, 15, 0, tzinfo=UTC)  # 12:00 en Buenos Aires


@dataclass
class FakeTreatment:
    started_at: datetime
    schedule_kind: ScheduleKind
    interval_hours: int | None = None
    times_of_day: list[time] | None = None
    status: TreatmentStatus = TreatmentStatus.ACTIVE


@dataclass
class FakeAdministration:
    administered_at: datetime
    status: AdministrationStatus = AdministrationStatus.GIVEN
    dose: str | None = None
    omission_reason: str | None = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)


def window(hours_back: int = 12, hours_ahead: int = 12):
    return NOW - timedelta(hours=hours_back), NOW + timedelta(hours=hours_ahead)


def plan(treatment, administrations=(), **overrides):
    start, end = window(**overrides.pop("window", {}))
    return plan_doses(
        treatment,
        list(administrations),
        window_start=start,
        window_end=end,
        now=NOW,
        timezone=TZ,
    )


def test_an_interval_counts_from_the_last_dose_given():
    treatment = FakeTreatment(
        started_at=NOW - timedelta(hours=10),
        schedule_kind=ScheduleKind.INTERVAL,
        interval_hours=8,
    )
    # Se dio con dos horas de atraso: las siguientes se corren con ella.
    last = FakeAdministration(administered_at=NOW - timedelta(hours=2))

    slots = plan(treatment, [last])

    assert slots[0].state == DoseState.GIVEN
    assert [slot.due_at for slot in slots if slot.planned] == [
        NOW + timedelta(hours=6),
    ]
    assert not is_overdue(slots)


def test_an_interval_without_doses_is_overdue_from_the_start():
    treatment = FakeTreatment(
        started_at=NOW - timedelta(hours=10),
        schedule_kind=ScheduleKind.INTERVAL,
        interval_hours=4,
    )

    slots = plan(treatment)

    # La primera vencio hace seis horas; despues siguen las proyectadas.
    assert slots[0].due_at == NOW - timedelta(hours=6)
    assert slots[0].state == DoseState.OVERDUE
    assert is_overdue(slots)
    assert next_due(slots) == NOW - timedelta(hours=6)


def test_fixed_times_do_not_move_when_a_dose_is_missed():
    treatment = FakeTreatment(
        started_at=NOW - timedelta(days=1),
        schedule_kind=ScheduleKind.TIMES,
        # 08:00 y 14:00 locales: 11:00 y 17:00 UTC.
        times_of_day=[time(8, 0), time(14, 0)],
    )
    # La de las 08:00 se dio; la de ayer a las 14:00 quedo afuera de la ventana.
    given = FakeAdministration(administered_at=NOW - timedelta(hours=1))

    slots = plan(treatment, [given])
    planned = [slot for slot in slots if slot.planned]

    assert [slot.state for slot in slots if not slot.planned] == [DoseState.GIVEN]
    # La de las 14:00 locales todavia no toca: queda pendiente, no vencida.
    assert [slot.due_at.astimezone(UTC).hour for slot in planned] == [17]
    assert planned[0].state == DoseState.PENDING
    assert not is_overdue(slots)


def test_a_fixed_time_that_passed_is_overdue():
    treatment = FakeTreatment(
        started_at=NOW - timedelta(days=1),
        schedule_kind=ScheduleKind.TIMES,
        times_of_day=[time(8, 0)],
    )

    slots = plan(treatment)

    # Las 08:00 locales de hoy ya pasaron y nadie la registro.
    assert [slot.state for slot in slots] == [DoseState.OVERDUE]
    assert is_overdue(slots)


def test_an_omitted_dose_is_a_fact_and_does_not_leave_the_slot_pending():
    treatment = FakeTreatment(
        started_at=NOW - timedelta(days=1),
        schedule_kind=ScheduleKind.TIMES,
        times_of_day=[time(8, 0)],
    )
    omitted = FakeAdministration(
        administered_at=NOW - timedelta(hours=1),
        status=AdministrationStatus.OMITTED,
        omission_reason="Paciente en ayunas",
    )

    slots = plan(treatment, [omitted])

    assert [slot.state for slot in slots] == [DoseState.OMITTED]
    assert slots[0].reason == "Paciente en ayunas"
    assert not is_overdue(slots)


def test_a_voided_dose_leaves_the_slot_overdue_again():
    treatment = FakeTreatment(
        started_at=NOW - timedelta(days=1),
        schedule_kind=ScheduleKind.TIMES,
        times_of_day=[time(8, 0)],
    )
    voided = FakeAdministration(
        administered_at=NOW - timedelta(hours=1),
        status=AdministrationStatus.VOID,
    )

    slots = plan(treatment, [voided])

    assert [slot.state for slot in slots] == [DoseState.OVERDUE]


def test_on_demand_and_continuous_never_expire():
    for kind in (ScheduleKind.AS_NEEDED, ScheduleKind.CONTINUOUS):
        treatment = FakeTreatment(
            started_at=NOW - timedelta(days=2),
            schedule_kind=kind,
        )
        slots = plan(treatment)
        assert slots == []
        assert next_due(slots) is None
        assert not is_overdue(slots)


def test_a_single_dose_disappears_once_it_is_given():
    treatment = FakeTreatment(
        started_at=NOW - timedelta(hours=3),
        schedule_kind=ScheduleKind.ONCE,
    )

    pending = plan(treatment)
    done = plan(treatment, [FakeAdministration(administered_at=NOW - timedelta(hours=3))])

    assert [slot.state for slot in pending] == [DoseState.OVERDUE]
    assert [slot.state for slot in done] == [DoseState.GIVEN]


def test_a_closed_indication_does_not_project_anything():
    treatment = FakeTreatment(
        started_at=NOW - timedelta(hours=10),
        schedule_kind=ScheduleKind.INTERVAL,
        interval_hours=4,
        status=TreatmentStatus.SUSPENDED,
    )

    slots = plan(treatment, [FakeAdministration(administered_at=NOW - timedelta(hours=6))])

    assert [slot.state for slot in slots] == [DoseState.GIVEN]
    assert next_due(slots) is None


def test_the_frequency_label_is_written_from_the_schedule():
    assert frequency_label(ScheduleKind.INTERVAL, interval_hours=8) == "cada 8 horas"
    assert frequency_label(ScheduleKind.INTERVAL, interval_hours=1) == "cada hora"
    assert (
        frequency_label(ScheduleKind.TIMES, times_of_day=[time(14, 0), time(8, 0)])
        == "08:00 - 14:00"
    )
    assert frequency_label(ScheduleKind.AS_NEEDED) == "a demanda"
    assert frequency_label(ScheduleKind.CONTINUOUS) == "continuo"
    assert frequency_label(ScheduleKind.ONCE) == "única vez"
