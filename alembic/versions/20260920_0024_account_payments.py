"""pagos del paciente y responsable de cada cargo"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260920_0024"
down_revision = "20260919_0023"
branch_labels = None
depends_on = None

RESPONSIBLE_PARTIES = ("PAYER", "PATIENT")
PAYMENT_METHODS = ("CASH", "DEBIT_CARD", "CREDIT_CARD", "BANK_TRANSFER", "CHECK", "OTHER")
PAYMENT_STATUSES = ("CONFIRMED", "VOID")
NEW_EVENTS = ("PAYMENT_REGISTERED", "PAYMENT_VOIDED")


def upgrade():
    bind = op.get_bind()
    responsible_party = postgresql.ENUM(
        *RESPONSIBLE_PARTIES, name="responsible_party", create_type=False
    )
    responsible_party.create(bind, checkfirst=True)
    method = postgresql.ENUM(*PAYMENT_METHODS, name="payment_method", create_type=False)
    method.create(bind, checkfirst=True)
    status = postgresql.ENUM(*PAYMENT_STATUSES, name="payment_status", create_type=False)
    status.create(bind, checkfirst=True)
    for event in NEW_EVENTS:
        op.execute(
            f"ALTER TYPE hospitalization_event_type ADD VALUE IF NOT EXISTS '{event}'"
        )

    # Lo ya cargado se factura como hasta ahora: al financiador.
    op.add_column(
        "charge_items",
        sa.Column(
            "responsible_party",
            responsible_party,
            server_default="PAYER",
            nullable=False,
        ),
    )
    # Las cuentas sin cobertura son de pacientes particulares: eso lo paga el paciente.
    op.execute(
        """
        UPDATE charge_items
           SET responsible_party = 'PATIENT'
          FROM accounts
         WHERE accounts.id = charge_items.account_id
           AND accounts.coverage_id IS NULL
        """
    )
    # Los copagos son del afiliado aunque la cuenta tenga cobertura.
    op.execute(
        "UPDATE charge_items SET responsible_party = 'PATIENT' "
        "WHERE description LIKE 'Copago %'"
    )

    op.create_table(
        "payments",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("method", method, nullable=False),
        sa.Column("status", status, server_default="CONFIRMED", nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_by", sa.String(length=150), nullable=True),
        sa.Column("reference", sa.String(length=100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_by", sa.String(length=150), nullable=True),
        sa.Column("void_reason", sa.String(length=500), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint("amount > 0", name=op.f("ck_payments_positive_amount")),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_payments_account_id_accounts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
    )
    op.create_index(op.f("ix_payments_account_id"), "payments", ["account_id"])


def downgrade():
    op.drop_index(op.f("ix_payments_account_id"), table_name="payments")
    op.drop_table("payments")
    op.drop_column("charge_items", "responsible_party")
    bind = op.get_bind()
    postgresql.ENUM(name="payment_status").drop(bind, checkfirst=True)
    postgresql.ENUM(name="payment_method").drop(bind, checkfirst=True)
    postgresql.ENUM(name="responsible_party").drop(bind, checkfirst=True)
