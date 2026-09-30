"""completa el profesional de los diagnósticos cargados sin él"""

from alembic import op

revision = "20260923_0032"
down_revision = "20260923_0031"
branch_labels = None
depends_on = None


def upgrade():
    # Desde ahora la API exige quién indicó cada diagnóstico. A los cargados antes se les
    # asigna el que la historia ya dice: el médico responsable de la admisión para los de
    # ingreso y el que firmó el alta para los de egreso. Los que no tienen de dónde sacarlo
    # quedan sin profesional, y se muestran así.
    op.execute(
        """
        UPDATE hospitalization_diagnoses AS d
        SET diagnosed_by_id = a.responsible_physician_id
        FROM admissions AS a
        WHERE a.hospitalization_id = d.hospitalization_id
          AND d.stage = 'ADMISSION'
          AND d.diagnosed_by_id IS NULL
          AND a.responsible_physician_id IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE hospitalization_diagnoses AS d
        SET diagnosed_by_id = x.ordered_by_practitioner_id
        FROM discharges AS x
        WHERE x.hospitalization_id = d.hospitalization_id
          AND d.stage = 'DISCHARGE'
          AND d.diagnosed_by_id IS NULL
          AND x.ordered_by_practitioner_id IS NOT NULL
        """
    )


def downgrade():
    # Es un dato completado, no un cambio de esquema: no hay forma de saber cuáles se
    # completaron acá y cuáles se cargaron con profesional.
    pass
