"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-17

Creates the full baseline schema directly from the ORM metadata so the DB always
matches app.models exactly. Subsequent changes use `alembic revision --autogenerate`.
"""
from alembic import op

from app.db import Base
from app import models  # noqa: F401

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
