import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text


class GroupOwnerMigrationTests(unittest.TestCase):
    def test_only_unambiguous_legacy_owners_are_backfilled(self):
        path = Path(__file__).resolve().parents[1] / "alembic/versions/c42d91e7a650_add_group_settings_owner.py"
        spec = importlib.util.spec_from_file_location("owner_migration", path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        engine = create_engine("sqlite://")
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE users (tg_id BIGINT PRIMARY KEY, username VARCHAR NOT NULL)"))
            connection.execute(text("INSERT INTO users VALUES (:tg_id, :username)"), [
                {"tg_id": 10, "username": "Owner"},
                {"tg_id": 20, "username": "duplicate"},
                {"tg_id": 30, "username": "DUPLICATE"},
                {"tg_id": -100, "username": "owner"},
                {"tg_id": -200, "username": "duplicate"},
                {"tg_id": -300, "username": "unknown"},
                {"tg_id": -400, "username": "user_40"},
                {"tg_id": -500, "username": "user_999999999999999999999999999999"},
            ])
            with patch.object(migration, "op", Operations(MigrationContext.configure(connection))):
                migration.upgrade()
            owners = dict(connection.execute(text("SELECT tg_id, settings_owner_tg_id FROM users")).all())
            self.assertEqual(owners, {10: None, 20: None, 30: None, -100: 10, -200: None,
                                      -300: None, -400: 40, -500: None})
        engine.dispose()
