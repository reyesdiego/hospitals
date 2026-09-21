"""Lectura de la frecuencia escrita a mano: qué se entiende y qué no.

Sin base de datos: lo que se prueba es la interpretación del texto.
"""

from datetime import time

import pytest

from app.db.maintenance.treatment_schedules import parse_frequency
from app.models.treatment import ScheduleKind


@pytest.mark.parametrize(
    ("text", "hours"),
    [
        ("cada 8 horas", 8),
        ("Cada 8 Horas", 8),
        ("cada 12 hs", 12),
        ("c/6 h", 6),
        ("cada 24 hrs", 24),
        ("una vez por dia", 24),
        ("2 veces por dia", 12),
        ("tres veces al dia", 8),
        ("diario", 24),
    ],
)
def test_an_interval_is_read_from_the_text(text, hours):
    schedule = parse_frequency(text)

    assert schedule.kind == ScheduleKind.INTERVAL
    assert schedule.interval_hours == hours


def test_fixed_times_are_read_from_the_clock():
    schedule = parse_frequency("08:00 y 20:00")

    assert schedule.kind == ScheduleKind.TIMES
    assert schedule.times_of_day == (time(8, 0), time(20, 0))
    assert schedule.label == "08:00 - 20:00"


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("a demanda", ScheduleKind.AS_NEEDED),
        ("SOS", ScheduleKind.AS_NEEDED),
        ("si dolor", ScheduleKind.AS_NEEDED),
        ("continuo", ScheduleKind.CONTINUOUS),
        ("goteo permanente", ScheduleKind.CONTINUOUS),
        ("unica vez", ScheduleKind.ONCE),
        ("por unica dosis", ScheduleKind.ONCE),
    ],
)
def test_the_schemes_without_schedule_are_recognised(text, kind):
    schedule = parse_frequency(text)

    assert schedule.kind == kind
    assert schedule.interval_hours is None
    assert schedule.times_of_day is None


@pytest.mark.parametrize(
    "text",
    [
        None,
        "",
        "   ",
        "segun indicacion medica",
        "antes de las comidas",
        "cada 500 horas",
    ],
)
def test_what_is_not_understood_stays_unread(text):
    """Es preferible una indicación sin horarios a una con horarios que nadie indicó."""

    assert parse_frequency(text) is None
