import hmac
import os
import calendar
from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone
from threading import Lock
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_admin import Admin, AdminIndexView, BaseView, expose
from flask_admin.contrib.sqla import ModelView
from flask_wtf import CSRFProtect, FlaskForm
from sqlalchemy import create_engine, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import scoped_session, sessionmaker
from werkzeug.security import check_password_hash
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Length

from common.database import models


def _required_secret(name: str, minimum_length: int = 1) -> str:
    value = os.getenv(name, "")
    if len(value) < minimum_length:
        raise RuntimeError(
            f"{name} must be set and contain at least {minimum_length} characters"
        )
    return value


app = Flask(__name__)
app.config.update(
    SECRET_KEY=_required_secret("SECRET_KEY", 32),
    WTF_CSRF_SECRET_KEY=os.getenv("WTF_CSRF_SECRET_KEY") or os.getenv("SECRET_KEY"),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Strict",
    SESSION_COOKIE_SECURE=os.getenv("ADMIN_COOKIE_SECURE", "false").lower() == "true",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    MAX_CONTENT_LENGTH=2 * 1024 * 1024,
)
CSRFProtect(app)

DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
DB_NAME = os.getenv("DB_NAME", "timetable")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    echo=os.getenv("SQLALCHEMY_ECHO", "false").lower() == "true",
)
SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

ADMIN_USERNAME = _required_secret("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "")
if not ADMIN_PASSWORD and not ADMIN_PASSWORD_HASH:
    raise RuntimeError("ADMIN_PASSWORD or ADMIN_PASSWORD_HASH must be set")

ADMIN_URL_SECRET = _required_secret("ADMIN_URL_SECRET", 32)
if not ADMIN_URL_SECRET.replace("-", "").replace("_", "").isalnum():
    raise RuntimeError(
        "ADMIN_URL_SECRET may contain only letters, digits, hyphens and underscores"
    )
ADMIN_BASE_PATH = f"/{ADMIN_URL_SECRET}/admin"

MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW = timedelta(minutes=15)
login_attempts = defaultdict(deque)
login_attempts_lock = Lock()


class LoginForm(FlaskForm):
    username = StringField(
        "Логин",
        validators=[DataRequired(), Length(max=128)],
        render_kw={"autocomplete": "username"},
    )
    password = PasswordField(
        "Пароль",
        validators=[DataRequired(), Length(max=512)],
        render_kw={"autocomplete": "current-password"},
    )
    submit = SubmitField("Войти")


class AdminModelForm(FlaskForm):
    """Flask-Admin form with CSRF and the edited object kept for validators."""

    def __init__(self, *args, **kwargs):
        # Flask-Admin's Unique validator must know which existing row is being
        # edited. Plain FlaskForm does not retain obj, so an unchanged unique
        # value is otherwise mistaken for a duplicate of itself.
        self._obj = kwargs.get("obj")
        super().__init__(*args, **kwargs)


def _client_key() -> str:
    # Не доверяем X-Forwarded-For без явно настроенного ProxyFix.
    return request.remote_addr or "unknown"


def _is_rate_limited(client_key: str) -> bool:
    now = datetime.now(timezone.utc)
    with login_attempts_lock:
        attempts = login_attempts[client_key]
        while attempts and now - attempts[0] > LOGIN_WINDOW:
            attempts.popleft()
        return len(attempts) >= MAX_LOGIN_ATTEMPTS


def _password_matches(password: str) -> bool:
    if ADMIN_PASSWORD_HASH:
        return check_password_hash(ADMIN_PASSWORD_HASH, password)
    return hmac.compare_digest(ADMIN_PASSWORD, password)


def check_auth(username: str, password: str) -> bool:
    username_ok = hmac.compare_digest(ADMIN_USERNAME, username)
    password_ok = _password_matches(password)
    return username_ok and password_ok


def _safe_next_url(target: str | None) -> str:
    if target:
        parsed = urlsplit(target)
        if not parsed.scheme and not parsed.netloc and target.startswith("/"):
            return target
    return url_for("admin.index")


@app.route(f"{ADMIN_BASE_PATH}/login", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_authenticated"):
        return redirect(url_for("admin.index"))

    form = LoginForm()
    client_key = _client_key()
    if form.validate_on_submit():
        if _is_rate_limited(client_key):
            flash("Слишком много попыток. Повторите вход через 15 минут.", "danger")
            return render_template("admin/login.html", form=form), 429

        if check_auth(form.username.data, form.password.data):
            with login_attempts_lock:
                login_attempts.pop(client_key, None)
            session.clear()
            session["admin_authenticated"] = True
            session.permanent = True
            return redirect(_safe_next_url(request.args.get("next")))

        with login_attempts_lock:
            login_attempts[client_key].append(datetime.now(timezone.utc))
        flash("Неверный логин или пароль.", "danger")

    return render_template("admin/login.html", form=form)


@app.post(f"{ADMIN_BASE_PATH}/logout")
def admin_logout():
    session.clear()
    flash("Вы вышли из админки.", "success")
    return redirect(url_for("admin_login"))


class SecureAdminIndexView(AdminIndexView):
    def is_accessible(self):
        return bool(session.get("admin_authenticated"))

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("admin_login", next=request.full_path))

    @expose("/")
    def index(self):
        if not self.is_accessible():
            return self.inaccessible_callback("index")

        counts = {
            "Расписаний": SessionLocal.query(models.Dayboard).count(),
            "Групп": SessionLocal.query(models.Group).count(),
            "Преподавателей": SessionLocal.query(models.Teacher).count(),
            "Пользователей": SessionLocal.query(models.User).count(),
        }
        return self.render("admin/dashboard.html", counts=counts)

    @expose("/search/")
    def search(self):
        if not self.is_accessible():
            return self.inaccessible_callback("search")

        query = request.args.get("q", "").strip()[:100]
        results = {}
        if len(query) >= 2:
            pattern = f"%{query}%"
            results = {
                "Расписание": (
                    SessionLocal.query(models.Dayboard)
                    .join(models.Dayboard.subject_rel)
                    .join(models.Dayboard.group_rel)
                    .join(models.Dayboard.teacher_rel)
                    .join(models.Dayboard.place_rel)
                    .filter(
                        or_(
                            models.Subject.name.ilike(pattern),
                            models.Group.name.ilike(pattern),
                            models.Teacher.full_name.ilike(pattern),
                            models.Place.name.ilike(pattern),
                        )
                    )
                    .limit(30)
                    .all()
                ),
                "Группы": SessionLocal.query(models.Group)
                .filter(models.Group.name.ilike(pattern)).limit(20).all(),
                "Преподаватели": SessionLocal.query(models.Teacher)
                .filter(models.Teacher.full_name.ilike(pattern)).limit(20).all(),
                "Предметы": SessionLocal.query(models.Subject)
                .filter(models.Subject.name.ilike(pattern)).limit(20).all(),
                "Аудитории": SessionLocal.query(models.Place)
                .filter(models.Place.name.ilike(pattern)).limit(20).all(),
                "Пользователи": SessionLocal.query(models.User)
                .filter(models.User.username.ilike(pattern)).limit(20).all(),
            }
        return self.render("admin/search.html", query=query, results=results)


class SecureModelView(ModelView):
    form_base_class = AdminModelForm
    page_size = 50
    can_view_details = True
    column_display_pk = True
    column_hide_backrefs = True
    can_set_page_size = True
    edit_modal = True
    details_modal = True

    def is_accessible(self):
        return bool(session.get("admin_authenticated"))

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("admin_login", next=request.full_path))


class GroupAdmin(SecureModelView):
    column_list = ["id", "name"]
    column_searchable_list = ["name"]
    column_default_sort = "name"
    column_labels = {"name": "Название группы"}


class TeacherAdmin(SecureModelView):
    column_list = ["id", "full_name"]
    column_searchable_list = ["full_name"]
    column_default_sort = "full_name"
    column_labels = {"full_name": "ФИО преподавателя"}


class NamedModelAdmin(SecureModelView):
    column_searchable_list = ["name"]
    column_default_sort = "name"


class TimeSlotAdmin(SecureModelView):
    column_list = ["id", "start_time", "end_time"]
    column_searchable_list = ["start_time", "end_time"]
    column_default_sort = "start_time"
    column_labels = {"start_time": "Начало", "end_time": "Окончание"}


class DayAdmin(SecureModelView):
    column_list = ["id", "name", "ord"]
    column_searchable_list = ["name"]
    column_filters = ["ord"]
    column_labels = {"name": "День недели", "ord": "Неделя (0/1)"}


class DayboardAdmin(SecureModelView):
    column_list = [
        "id", "subject_rel", "group_rel", "teacher_rel", "day_rel",
        "time_rel", "place_rel", "type_rel", "podgroup",
    ]
    column_default_sort = ("id", True)
    column_filters = ["group_rel", "teacher_rel", "day_rel", "type_rel", "podgroup"]
    column_labels = {
        "subject_rel": "Предмет", "group_rel": "Группа",
        "teacher_rel": "Преподаватель", "day_rel": "День",
        "time_rel": "Время", "place_rel": "Аудитория",
        "type_rel": "Тип занятия", "podgroup": "Подгруппа",
    }
    form_ajax_refs = {
        "subject_rel": {"fields": ["name"], "page_size": 20},
        "group_rel": {"fields": ["name"], "page_size": 20},
        "teacher_rel": {"fields": ["full_name"], "page_size": 20},
        "day_rel": {"fields": ["name"], "page_size": 20},
        "time_rel": {"fields": ["start_time", "end_time"], "page_size": 20},
        "place_rel": {"fields": ["name"], "page_size": 20},
        "type_rel": {"fields": ["name"], "page_size": 20},
    }


class UserAdmin(SecureModelView):
    column_list = [
        "id", "tg_id", "username", "group_rel", "is_active", "title",
        "notification_mode", "notification_time", "last_notification_date",
    ]
    column_searchable_list = ["username", "title"]
    column_filters = ["is_active", "group_rel", "notification_mode"]
    column_default_sort = ("id", True)
    column_labels = {
        "tg_id": "Telegram ID", "username": "Username", "group_rel": "Группа",
        "is_active": "Активен", "title": "Заголовок",
        "notification_mode": "Режим оповещения",
        "notification_time": "Время",
        "last_notification_date": "Последняя дата рассылки",
    }
    form_choices = {
        "notification_mode": [
            ("hour_before", "За час до первой пары"),
            ("same_day", "В день занятий"),
            ("day_before", "За день до занятий"),
        ]
    }
    form_ajax_refs = {"group_rel": {"fields": ["name"], "page_size": 20}}


class SettingsAdmin(SecureModelView):
    column_list = ["id", "key", "value"]
    column_searchable_list = ["key", "value"]
    column_default_sort = "key"
    column_labels = {"key": "Ключ", "value": "Значение"}


class ReadOnlyModelView(SecureModelView):
    can_create = False
    can_edit = False
    can_delete = False


MONTH_NAMES_RU = (
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
)


def _calendar_month(value: str | None) -> tuple[int, int]:
    today = datetime.now(ZoneInfo("Europe/Moscow")).date()
    if value:
        try:
            year, month = (int(part) for part in value.split("-", 1))
            if 2000 <= year <= 2100 and 1 <= month <= 12:
                return year, month
        except (TypeError, ValueError):
            pass
    return today.year, today.month


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + month - 1 + delta
    return divmod(index, 12)[0], divmod(index, 12)[1] + 1


class DayOffCalendarView(BaseView):
    def is_accessible(self):
        return bool(session.get("admin_authenticated"))

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("admin_login", next=request.full_path))

    @expose("/")
    def index(self):
        year, month = _calendar_month(request.args.get("month"))
        weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(year, month)
        visible_start = weeks[0][0]
        visible_end = weeks[-1][-1]
        days_off = {
            row[0]
            for row in SessionLocal.query(models.DayOff.date)
            .filter(
                models.DayOff.date >= visible_start,
                models.DayOff.date <= visible_end,
            )
            .all()
        }
        previous_year, previous_month = _shift_month(year, month, -1)
        next_year, next_month = _shift_month(year, month, 1)
        return self.render(
            "admin/days_off_calendar.html",
            year=year,
            month=month,
            month_name=MONTH_NAMES_RU[month],
            month_value=f"{year:04d}-{month:02d}",
            weeks=weeks,
            days_off=days_off,
            today=datetime.now(ZoneInfo("Europe/Moscow")).date(),
            previous_month=f"{previous_year:04d}-{previous_month:02d}",
            next_month=f"{next_year:04d}-{next_month:02d}",
        )

    @expose("/toggle/", methods=("POST",))
    def toggle(self):
        year, month = _calendar_month(request.form.get("month"))
        month_value = f"{year:04d}-{month:02d}"
        try:
            target_date = date.fromisoformat(request.form.get("date", ""))
        except ValueError:
            flash("Некорректная дата.", "danger")
            return redirect(url_for("days_off.index", month=month_value))

        if not 2000 <= target_date.year <= 2100:
            flash("Дата находится вне допустимого диапазона.", "danger")
            return redirect(url_for("days_off.index", month=month_value))

        existing = (
            SessionLocal.query(models.DayOff)
            .filter(models.DayOff.date == target_date)
            .one_or_none()
        )
        try:
            if existing:
                SessionLocal.delete(existing)
                message = f"{target_date.strftime('%d.%m.%Y')} снова является учебным днём."
            else:
                SessionLocal.add(models.DayOff(date=target_date))
                message = f"{target_date.strftime('%d.%m.%Y')} отмечен как выходной."
            SessionLocal.commit()
            flash(message, "success")
        except IntegrityError:
            SessionLocal.rollback()
            flash("Не удалось изменить дату: календарь уже был обновлён.", "warning")

        return redirect(url_for("days_off.index", month=month_value))


admin = Admin(
    app,
    name="Расписание МГТУ",
    template_mode="bootstrap3",
    base_template="admin/custom_master.html",
    index_view=SecureAdminIndexView(name="Обзор", url=ADMIN_BASE_PATH),
)

admin.add_view(GroupAdmin(models.Group, SessionLocal, name="Группы", category="Справочники"))
admin.add_view(TeacherAdmin(models.Teacher, SessionLocal, name="Преподаватели", category="Справочники"))
admin.add_view(TimeSlotAdmin(models.TimeSlot, SessionLocal, name="Временные слоты", category="Справочники"))
admin.add_view(DayAdmin(models.Day, SessionLocal, name="Дни недели", category="Справочники"))
admin.add_view(NamedModelAdmin(models.Subject, SessionLocal, name="Предметы", category="Справочники"))
admin.add_view(NamedModelAdmin(models.Place, SessionLocal, name="Аудитории", category="Справочники"))
admin.add_view(NamedModelAdmin(models.Type, SessionLocal, name="Типы занятий", category="Справочники"))
admin.add_view(DayboardAdmin(models.Dayboard, SessionLocal, name="Расписание", category="Расписание"))
admin.add_view(UserAdmin(models.User, SessionLocal, name="Пользователи", category="Пользователи"))
admin.add_view(SettingsAdmin(models.Settings, SessionLocal, name="Настройки", category="Системные"))
admin.add_view(DayOffCalendarView(name="Календарь выходных", endpoint="days_off", category="Системные"))
admin.add_view(ReadOnlyModelView(models.ScheduleReview, SessionLocal, name="Проверки", category="Мониторинг"))
admin.add_view(ReadOnlyModelView(models.ScheduleReviewGroup, SessionLocal, name="Изменения групп", category="Мониторинг"))
admin.add_view(ReadOnlyModelView(models.ScheduleMonitorRun, SessionLocal, name="Запуски", category="Мониторинг"))


@app.after_request
def set_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:",
    )
    response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.teardown_appcontext
def shutdown_session(exception=None):
    SessionLocal.remove()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
