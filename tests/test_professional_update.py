import uuid

from app.api.router import sync_professional_specialties
from app.models.professional import Professional, ProfessionalSpecialty
from app.schemas.domain import ProfessionalSpecialtyCreate


def professional_with_specialty(specialty_id: uuid.UUID, license_number: str) -> Professional:
    professional = Professional(
        id=uuid.uuid4(),
        first_name="Ana",
        last_name="Lopez",
        document_type="DNI",
        document_number="123",
    )
    professional.specialty_links = [
        ProfessionalSpecialty(
            id=uuid.uuid4(),
            specialty_id=specialty_id,
            license_number=license_number,
        )
    ]
    return professional


def test_sync_professional_specialties_reuses_unchanged_existing_link():
    specialty_id = uuid.uuid4()
    professional = professional_with_specialty(specialty_id, "MN-123")
    existing_link = professional.specialty_links[0]

    sync_professional_specialties(
        professional,
        [
            ProfessionalSpecialtyCreate(
                specialty_id=specialty_id,
                license_number="MN-123",
            )
        ],
    )

    assert professional.specialty_links == [existing_link]


def test_sync_professional_specialties_updates_existing_license_without_recreating_link():
    specialty_id = uuid.uuid4()
    professional = professional_with_specialty(specialty_id, "MN-123")
    existing_link = professional.specialty_links[0]

    sync_professional_specialties(
        professional,
        [
            ProfessionalSpecialtyCreate(
                specialty_id=specialty_id,
                license_number="MN-456",
            )
        ],
    )

    assert professional.specialty_links == [existing_link]
    assert existing_link.license_number == "MN-456"


def test_sync_professional_specialties_removes_absent_links_and_adds_new_links():
    old_specialty_id = uuid.uuid4()
    new_specialty_id = uuid.uuid4()
    professional = professional_with_specialty(old_specialty_id, "MN-123")

    sync_professional_specialties(
        professional,
        [
            ProfessionalSpecialtyCreate(
                specialty_id=new_specialty_id,
                license_number="MN-456",
            )
        ],
    )

    assert len(professional.specialty_links) == 1
    assert professional.specialty_links[0].specialty_id == new_specialty_id
    assert professional.specialty_links[0].license_number == "MN-456"
