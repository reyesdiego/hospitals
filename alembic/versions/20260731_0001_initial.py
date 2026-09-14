"""initial schema"""
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision="20260731_0001"; down_revision=None; branch_labels=None; depends_on=None
def upgrade():
    hs=postgresql.ENUM("PENDING_BED","IN_PROGRESS","CLINICALLY_DISCHARGED","CLOSED","CANCELLED",name="hospitalization_status",create_type=False)
    bs=postgresql.ENUM("AVAILABLE","RESERVED","OCCUPIED","PENDING_CLEANING","BLOCKED","MAINTENANCE",name="bed_status",create_type=False)
    rs=postgresql.ENUM("AVAILABLE","RESERVED","OCCUPIED","PENDING_CLEANING","BLOCKED","MAINTENANCE",name="room_status",create_type=False)
    hs.create(op.get_bind(),checkfirst=True); bs.create(op.get_bind(),checkfirst=True); rs.create(op.get_bind(),checkfirst=True)
    op.create_table("patients",sa.Column("first_name",sa.String(100),nullable=False),sa.Column("last_name",sa.String(100),nullable=False),sa.Column("document_type",sa.String(30),nullable=False),sa.Column("document_number",sa.String(50),nullable=False),sa.Column("birth_date",sa.Date()),sa.Column("id",sa.Uuid(),primary_key=True),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now()),sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.func.now()),sa.UniqueConstraint("document_type","document_number",name="uq_patients_document"))
    op.create_table("facilities",sa.Column("name",sa.String(150),nullable=False),sa.Column("code",sa.String(30),nullable=False,unique=True),sa.Column("id",sa.Uuid(),primary_key=True),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now()),sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.func.now()))
    op.create_table("services",sa.Column("name",sa.String(150),nullable=False),sa.Column("code",sa.String(30),nullable=False,unique=True),sa.Column("id",sa.Uuid(),primary_key=True),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now()),sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.func.now()))
    services=sa.table("services",sa.Column("id",sa.Uuid(),primary_key=True),sa.Column("name",sa.String),sa.Column("code",sa.String))
    op.bulk_insert(services,[
        {"id":uuid.UUID("00000000-0000-4000-8000-000000000001"),"name":"Laboratorio","code":"LAB"},
        {"id":uuid.UUID("00000000-0000-4000-8000-000000000002"),"name":"Imágenes","code":"IMG"},
        {"id":uuid.UUID("00000000-0000-4000-8000-000000000003"),"name":"Hemoterapia","code":"HEM"},
        {"id":uuid.UUID("00000000-0000-4000-8000-000000000004"),"name":"Anatomía patológica","code":"ANP"},
        {"id":uuid.UUID("00000000-0000-4000-8000-000000000005"),"name":"Kinesiología","code":"KIN"},
        {"id":uuid.UUID("00000000-0000-4000-8000-000000000006"),"name":"Nutrición","code":"NUT"},
        {"id":uuid.UUID("00000000-0000-4000-8000-000000000007"),"name":"Salud mental","code":"SM"},
        {"id":uuid.UUID("00000000-0000-4000-8000-000000000008"),"name":"Trabajo social","code":"TS"},
        {"id":uuid.UUID("00000000-0000-4000-8000-000000000009"),"name":"Terapia ocupacional","code":"TO"},
    ])
    op.create_table("hospitalizations",sa.Column("patient_id",sa.Uuid(),sa.ForeignKey("patients.id",ondelete="RESTRICT"),nullable=False),sa.Column("status",hs,nullable=False),sa.Column("admission_reason",sa.String(500),nullable=False),sa.Column("admitted_at",sa.DateTime(timezone=True)),sa.Column("discharged_at",sa.DateTime(timezone=True)),sa.Column("id",sa.Uuid(),primary_key=True),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now()),sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.func.now()))
    op.create_table("rooms",
                    sa.Column("id",sa.Uuid(),primary_key=True),
                    sa.Column("facility_id",sa.Uuid(),sa.ForeignKey("facilities.id",ondelete="RESTRICT"),nullable=False),
                    sa.Column("code",sa.String(50),nullable=False),
                    sa.Column("ward",sa.String(100),nullable=False),
                    sa.Column("status",rs,nullable=False),
                    sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now()),
                    sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.func.now())
                    )
    op.create_table("beds",
                    sa.Column("id",sa.Uuid(),primary_key=True),
                    sa.Column("facility_id",sa.Uuid(),sa.ForeignKey("facilities.id",ondelete="RESTRICT"),nullable=False),
                    sa.Column("code",sa.String(50),nullable=False),
                    sa.Column("ward",sa.String(100),nullable=False),
                    sa.Column("room_id",sa.Uuid(),sa.ForeignKey("rooms.id",ondelete="RESTRICT"),nullable=False),
                    sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now()),
                    sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.func.now())
                    )
    op.create_index("uq_beds_facility_code","beds",["facility_id","code"],unique=True)
    op.create_table("bed_assignments",
                    sa.Column("id",sa.Uuid(),primary_key=True),
                    sa.Column("hospitalization_id",sa.Uuid(),sa.ForeignKey("hospitalizations.id",ondelete="RESTRICT"),nullable=True),
                    sa.Column("bed_id",sa.Uuid(),sa.ForeignKey("beds.id",ondelete="RESTRICT"),nullable=False),
                    sa.Column("started_at",sa.DateTime(timezone=True),nullable=False),
                    sa.Column("ended_at",sa.DateTime(timezone=True)),
                    sa.Column("status",bs,nullable=False),
                    sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now()),
                    sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.func.now())
                    )
    op.create_index("uq_active_assignment_per_bed","bed_assignments",["bed_id"],unique=True,postgresql_where=sa.text("ended_at IS NULL"))
    op.create_index("uq_active_bed_per_hospitalization","bed_assignments",["hospitalization_id"],unique=True,postgresql_where=sa.text("hospitalization_id IS NOT NULL AND ended_at IS NULL"))

def downgrade():
    op.drop_table("bed_assignments"); op.drop_table("beds"); op.drop_table("rooms"); op.drop_table("hospitalizations"); op.drop_table("services"); op.drop_table("facilities"); op.drop_table("patients")
    postgresql.ENUM(name="room_status").drop(op.get_bind(),checkfirst=True); postgresql.ENUM(name="bed_status").drop(op.get_bind(),checkfirst=True); postgresql.ENUM(name="hospitalization_status").drop(op.get_bind(),checkfirst=True)
