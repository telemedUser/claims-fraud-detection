"""provider registry fields for the Provider Profile cross-checks

Adds hospital state code, bed count and network (empanelment) period, doctor licence expiry, and start/end
dates on doctor affiliations. All columns are nullable: a null value means "not on record" and the
corresponding check is skipped, never treated as a failure.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-20 10:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('providers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('state_code', sa.String(length=2), nullable=True))
        batch_op.add_column(sa.Column('bed_count', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('empanelled_from', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('empanelled_to', sa.Date(), nullable=True))

    with op.batch_alter_table('doctors', schema=None) as batch_op:
        batch_op.add_column(sa.Column('licence_valid_to', sa.Date(), nullable=True))

    with op.batch_alter_table('doctor_affiliations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('start_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('end_date', sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('doctor_affiliations', schema=None) as batch_op:
        batch_op.drop_column('end_date')
        batch_op.drop_column('start_date')

    with op.batch_alter_table('doctors', schema=None) as batch_op:
        batch_op.drop_column('licence_valid_to')

    with op.batch_alter_table('providers', schema=None) as batch_op:
        batch_op.drop_column('empanelled_to')
        batch_op.drop_column('empanelled_from')
        batch_op.drop_column('bed_count')
        batch_op.drop_column('state_code')
