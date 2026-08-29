import os
import re
import unittest
from datetime import date

# Admin tests must never connect to the configured working PostgreSQL database.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from common.database.base import Base

import app as admin_app


class AdminSecurityTests(unittest.TestCase):
    base_path = admin_app.ADMIN_BASE_PATH

    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(admin_app.engine)

    @classmethod
    def tearDownClass(cls):
        admin_app.SessionLocal.remove()
        Base.metadata.drop_all(admin_app.engine)

    def setUp(self):
        admin_app.login_attempts.clear()
        self.client = admin_app.app.test_client()

    def _csrf_token(self, path=None):
        path = path or f"{self.base_path}/login"
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        match = re.search(
            rb'name="csrf_token"[^>]*value="([^"]+)"', response.data
        )
        self.assertIsNotNone(match)
        return match.group(1).decode()

    def _login(self):
        token = self._csrf_token()
        return self.client.post(
            f"{self.base_path}/login",
            data={
                "username": admin_app.ADMIN_USERNAME,
                "password": admin_app.ADMIN_PASSWORD,
                "csrf_token": token,
            },
        )

    def test_direct_model_url_requires_login(self):
        response = self.client.get(f"{self.base_path}/group/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.startswith(f"{self.base_path}/login"))

    def test_old_predictable_admin_path_is_not_available(self):
        self.assertEqual(self.client.get("/admin/").status_code, 404)
        self.assertEqual(self.client.get("/admin/login").status_code, 404)

    def test_login_dashboard_search_and_model_list(self):
        response = self._login()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, f"{self.base_path}/")

        for suffix in ("/", "/search/?q=test", "/group/"):
            path = f"{self.base_path}{suffix}"
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["X-Frame-Options"], "DENY")
                self.assertIn("Content-Security-Policy", response.headers)

    def test_login_requires_csrf_token(self):
        response = self.client.post(
            f"{self.base_path}/login",
            data={"username": admin_app.ADMIN_USERNAME, "password": "wrong"},
        )
        self.assertEqual(response.status_code, 400)

    def test_model_create_form_uses_csrf_and_saves(self):
        self._login()
        token = self._csrf_token(f"{self.base_path}/group/new/")
        response = self.client.post(
            f"{self.base_path}/group/new/",
            data={"name": "TEST-CSRF-GROUP", "csrf_token": token},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        saved = (
            admin_app.SessionLocal.query(admin_app.models.Group)
            .filter_by(name="TEST-CSRF-GROUP")
            .one_or_none()
        )
        self.assertIsNotNone(saved)
        admin_app.SessionLocal.delete(saved)
        admin_app.SessionLocal.commit()

    def test_user_group_can_be_edited_without_changing_unique_telegram_id(self):
        group = admin_app.models.Group(name="TEST-USER-EDIT-GROUP")
        user = admin_app.models.User(
            tg_id=987654321,
            username="test_user_edit",
            title="private",
            is_active=0,
        )
        admin_app.SessionLocal.add_all([group, user])
        admin_app.SessionLocal.commit()
        user_id = user.id
        group_id = group.id
        telegram_id = user.tg_id
        username = user.username
        title = user.title

        self._login()
        edit_path = f"{self.base_path}/user/edit/?id={user_id}"
        token = self._csrf_token(edit_path)
        response = self.client.post(
            edit_path,
            data={
                "group_rel": str(group_id),
                "tg_id": str(telegram_id),
                "username": username,
                "is_active": "0",
                "title": title,
                "notification_mode": "same_day",
                "notification_time": "08:00:00",
                "last_notification_date": "",
                "csrf_token": token,
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        admin_app.SessionLocal.expire_all()
        saved_user = admin_app.SessionLocal.get(admin_app.models.User, user_id)
        self.assertEqual(saved_user.tg_id, 987654321)
        self.assertEqual(saved_user.group_id, group_id)

        admin_app.SessionLocal.delete(saved_user)
        saved_group = admin_app.SessionLocal.get(admin_app.models.Group, group_id)
        admin_app.SessionLocal.delete(saved_group)
        admin_app.SessionLocal.commit()

    def test_user_edit_still_rejects_another_users_telegram_id(self):
        first = admin_app.models.User(
            tg_id=987654322,
            username="test_unique_first",
            title="private",
            is_active=0,
        )
        second = admin_app.models.User(
            tg_id=987654323,
            username="test_unique_second",
            title="private",
            is_active=0,
        )
        admin_app.SessionLocal.add_all([first, second])
        admin_app.SessionLocal.commit()
        first_id = first.id
        first_telegram_id = first.tg_id
        second_id = second.id

        self._login()
        edit_path = f"{self.base_path}/user/edit/?id={second_id}"
        token = self._csrf_token(edit_path)
        response = self.client.post(
            edit_path,
            data={
                "group_rel": "",
                "tg_id": str(first_telegram_id),
                "username": "test_unique_second",
                "is_active": "0",
                "title": "private",
                "notification_mode": "same_day",
                "notification_time": "08:00:00",
                "last_notification_date": "",
                "csrf_token": token,
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Already exists.", response.data)
        admin_app.SessionLocal.expire_all()
        saved_second = admin_app.SessionLocal.get(admin_app.models.User, second_id)
        self.assertEqual(saved_second.tg_id, 987654323)

        saved_first = admin_app.SessionLocal.get(admin_app.models.User, first_id)
        admin_app.SessionLocal.delete(saved_first)
        admin_app.SessionLocal.delete(saved_second)
        admin_app.SessionLocal.commit()

    def test_external_next_url_is_rejected(self):
        token = self._csrf_token(f"{self.base_path}/login?next=https://example.com")
        response = self.client.post(
            f"{self.base_path}/login?next=https://example.com",
            data={
                "username": admin_app.ADMIN_USERNAME,
                "password": admin_app.ADMIN_PASSWORD,
                "csrf_token": token,
            },
        )
        self.assertEqual(response.location, f"{self.base_path}/")

    def test_day_off_calendar_adds_and_removes_exact_date(self):
        self._login()
        target_date = date(2026, 9, 7)
        token = self._csrf_token(f"{self.base_path}/days_off/?month=2026-09")

        response = self.client.post(
            f"{self.base_path}/days_off/toggle/",
            data={
                "date": target_date.isoformat(),
                "month": "2026-09",
                "csrf_token": token,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(
            admin_app.SessionLocal.query(admin_app.models.DayOff)
            .filter_by(date=target_date)
            .one_or_none()
        )

        token = self._csrf_token(f"{self.base_path}/days_off/?month=2026-09")
        response = self.client.post(
            f"{self.base_path}/days_off/toggle/",
            data={
                "date": target_date.isoformat(),
                "month": "2026-09",
                "csrf_token": token,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(
            admin_app.SessionLocal.query(admin_app.models.DayOff)
            .filter_by(date=target_date)
            .one_or_none()
        )


if __name__ == "__main__":
    unittest.main()
