"""Guard against drift between the ORM models and the Alembic migration chain.

The ``engine`` fixture builds the test schema by running ``alembic upgrade head``,
so comparing that live schema against ``Base.metadata`` tells us whether the
migrations still describe the models.
"""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from src.db.base import Base
from src.db import models  # noqa: F401 ensures metadata is populated


def test_migration_chain_matches_orm_models(engine):
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        diff = compare_metadata(context, Base.metadata)

    # alembic_version is owned by Alembic itself and is not part of Base.metadata.
    diff = [
        entry
        for entry in diff
        if not (
            isinstance(entry, tuple)
            and entry[0] == "remove_table"
            and entry[1].name == "alembic_version"
        )
    ]

    assert diff == [], f"Alembic migrations have drifted from the ORM models: {diff}"
