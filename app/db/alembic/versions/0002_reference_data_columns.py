"""reference data columns for the store.py replacement

Adds the columns and the doctor_affiliations table the repositories need to return the same shapes the
in-memory store did: policy network and covered diseases, provider contact and specialties, doctor code,
qualification and volume figures, short member code, and external claim and claimant references.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-19 10:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None

JSONType = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql')


def upgrade() -> None:
    with op.batch_alter_table('policies', schema=None) as batch_op:
        batch_op.add_column(sa.Column('holder_name', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('network_hospital_ids', JSONType, nullable=True))
        batch_op.add_column(sa.Column('covered_disease_ids', JSONType, nullable=True))

    with op.batch_alter_table('members', schema=None) as batch_op:
        batch_op.add_column(sa.Column('code', sa.String(length=32), nullable=True))
        batch_op.create_index(batch_op.f('ix_members_code'), ['code'], unique=True)

    with op.batch_alter_table('providers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('address', sa.String(length=300), nullable=True))
        batch_op.add_column(sa.Column('phone', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('specialties', JSONType, nullable=True))

    with op.batch_alter_table('doctors', schema=None) as batch_op:
        batch_op.add_column(sa.Column('code', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('qualification', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('registration_no', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('claims_per_month', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('flagged_claims_ratio', sa.Float(), nullable=True))
        batch_op.create_index(batch_op.f('ix_doctors_code'), ['code'], unique=True)

    with op.batch_alter_table('claims', schema=None) as batch_op:
        batch_op.add_column(sa.Column('claim_ref', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('claimant_ref', sa.String(length=64), nullable=True))
        batch_op.create_index(batch_op.f('ix_claims_claim_ref'), ['claim_ref'], unique=True)
        batch_op.create_index(batch_op.f('ix_claims_claimant_ref'), ['claimant_ref'], unique=False)

    op.create_table('doctor_affiliations',
    sa.Column('doctor_id', sa.Uuid(), nullable=False),
    sa.Column('provider_id', sa.Uuid(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['doctor_id'], ['doctors.id'], ),
    sa.ForeignKeyConstraint(['provider_id'], ['providers.id'], ),
    sa.PrimaryKeyConstraint('doctor_id', 'provider_id')
    )
    with op.batch_alter_table('doctor_affiliations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_doctor_affiliations_provider_id'), ['provider_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('doctor_affiliations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_doctor_affiliations_provider_id'))
    op.drop_table('doctor_affiliations')

    with op.batch_alter_table('claims', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_claims_claimant_ref'))
        batch_op.drop_index(batch_op.f('ix_claims_claim_ref'))
        batch_op.drop_column('claimant_ref')
        batch_op.drop_column('claim_ref')

    with op.batch_alter_table('doctors', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_doctors_code'))
        batch_op.drop_column('flagged_claims_ratio')
        batch_op.drop_column('claims_per_month')
        batch_op.drop_column('registration_no')
        batch_op.drop_column('qualification')
        batch_op.drop_column('code')

    with op.batch_alter_table('providers', schema=None) as batch_op:
        batch_op.drop_column('specialties')
        batch_op.drop_column('phone')
        batch_op.drop_column('address')

    with op.batch_alter_table('members', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_members_code'))
        batch_op.drop_column('code')

    with op.batch_alter_table('policies', schema=None) as batch_op:
        batch_op.drop_column('covered_disease_ids')
        batch_op.drop_column('network_hospital_ids')
        batch_op.drop_column('holder_name')
