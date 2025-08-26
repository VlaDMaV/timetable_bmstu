import os
from flask import Flask, request, Response
from flask_admin import Admin, expose, AdminIndexView
from flask_admin.contrib.sqla import ModelView
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from common.database import models

# Создаем Flask приложение
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "my_super_secret_key_123")

# Настройки БД
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
DB_NAME = os.getenv("DB_NAME", "timetable")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

# Создаем движок и scoped_session
engine = create_engine(DATABASE_URL, echo=True)  # echo=True для отладки SQL
SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

def check_auth(username, password):
    return username == 'admin' and password == os.getenv("SECRET_KEY", "secret")

def authenticate():
    return Response(
        'Введите логин и пароль', 401,
        {'WWW-Authenticate': 'Basic realm="Login Required"'}
    )

class MyAdminIndexView(AdminIndexView):
    @expose('/')
    def index(self):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate() 
        return super().index()

class MyModelView(ModelView):
    def is_accessible(self):
        auth = request.authorization
        return auth and check_auth(auth.username, auth.password)

    def inaccessible_callback(self, name, **kwargs):
        return authenticate()  

# Инициализируем админку
admin = Admin(app, name='Админка Расписания', template_mode='bootstrap3', index_view=MyAdminIndexView())

# Кастомные ModelView
class GroupAdmin(ModelView):
    column_list = ['id', 'name']
    column_searchable_list = ['name']
    column_labels = {'name': 'Название группы'}

class TeacherAdmin(ModelView):
    column_list = ['id', 'full_name']
    column_searchable_list = ['full_name']
    column_labels = {'full_name': 'ФИО преподавателя'}

class DayboardAdmin(ModelView):
    column_list = ['id', 'subject_rel', 'group_rel', 'teacher_rel', 'day_rel', 'time_rel', 'place_rel', 'type_rel']
    column_labels = {
        'subject_rel': 'Предмет',
        'group_rel': 'Группа', 
        'teacher_rel': 'Преподаватель',
        'day_rel': 'День',
        'time_rel': 'Время',
        'place_rel': 'Аудитория',
        'type_rel': 'Тип занятия'
    }
    form_ajax_refs = {
        'subject_rel': {'fields': ['name']},
        'group_rel': {'fields': ['name']},
        'teacher_rel': {'fields': ['full_name']},
        'day_rel': {'fields': ['name']},
        'time_rel': {'fields': ['start_time']},
        'place_rel': {'fields': ['name']},
        'type_rel': {'fields': ['name']}
    }

class UserAdmin(ModelView):
    column_list = ['id', 'tg_id', 'username', 'group_rel', 'is_active', 'title']
    column_labels = {
        'tg_id': 'Telegram ID',
        'username': 'Username',
        'group_rel': 'Группа',
        'is_active': 'Активен',
        'title': 'Заголовок'
    }
    column_filters = ['is_active', 'group_rel.name']

# Регистрируем модели в админке
admin.add_view(GroupAdmin(models.Group, SessionLocal, name='Группы', category='Основные'))
admin.add_view(TeacherAdmin(models.Teacher, SessionLocal, name='Преподаватели', category='Основные'))
admin.add_view(ModelView(models.TimeSlot, SessionLocal, name='Временные слоты', category='Основные'))
admin.add_view(ModelView(models.Day, SessionLocal, name='Дни недели', category='Основные'))
admin.add_view(ModelView(models.Subject, SessionLocal, name='Предметы', category='Основные'))
admin.add_view(DayboardAdmin(models.Dayboard, SessionLocal, name='Расписание', category='Основные'))
admin.add_view(ModelView(models.Place, SessionLocal, name='Аудитории', category='Основные'))
admin.add_view(ModelView(models.Type, SessionLocal, name='Типы занятий', category='Основные'))
admin.add_view(UserAdmin(models.User, SessionLocal, name='Пользователи', category='Пользователи'))
admin.add_view(ModelView(models.Settings, SessionLocal, name='Настройки', category='Системные'))


# Закрытие сессий после запроса
@app.teardown_appcontext
def shutdown_session(exception=None):
    SessionLocal.remove()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)