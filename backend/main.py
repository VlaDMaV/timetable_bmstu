import os
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload, aliased
from sqlalchemy import or_
from sqlalchemy import asc
from pydantic import BaseModel, ConfigDict

from common.database import models
from database.database import engine, SessionLocal
from database.connect import wait_for_db


app = FastAPI()

DB_ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

wait_for_db()
models.Base.metadata.create_all(bind=engine)


class DayboardCreate(BaseModel):
    subject_id: int
    group_id: int
    teacher_id: int
    time_id: int
    day_id: int
    place: int
    type: int
    admin_password: str


class DayboardWithAll(BaseModel):
    id: int
    subject_name: str
    group_name: str
    teacher_name: str
    day_name: str
    ord: int
    start_time: str
    end_time: str
    place: str
    type: str
    podgroup: int

    class Config:
        orm_mode = True


class GroupOut(BaseModel):
    id: int
    name: str

    class Config:
        orm_mode = True


class TeacherOut(BaseModel):
    id: int
    full_name: str

    model_config = ConfigDict(from_attributes=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/subjects")
def get_subjects(db: Session = Depends(get_db)):
    return db.query(models.Subject).all()


@app.get("/groups", response_model=List[GroupOut])
def get_groups(
    kind: Optional[str] = Query(
        default=None,
        description="Фильтр по типу группы: 'uik' или 'mk'",
        regex="^(uik|mk)$"
    ),
    db: Session = Depends(get_db),
):
    query = db.query(models.Group)

    if kind:
        k = kind.lower()
        if k == "uik":
            query = query.filter(
                or_(
                    models.Group.name.ilike("УИК%"),
                    models.Group.name.ilike("UIK%")
                )
            )
        elif k == "mk":
            query = query.filter(
                or_(
                    models.Group.name.ilike("МК%"),
                    models.Group.name.ilike("MK%")
                )
            )

    groups = query.order_by(models.Group.name.asc()).all()
    return [GroupOut(id=g.id, name=g.name) for g in groups]


@app.post("/dayboard")
def create_dayboard(dayboard: DayboardCreate, db: Session = Depends(get_db)):
    if dayboard.admin_password != DB_ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="Ошибка: неверный пароль администратора")
    
    for model, field, value in [
        (models.Subject, "subject_id", dayboard.subject_id),
        (models.Group, "group_id", dayboard.group_id),
        (models.Teacher, "teacher_id", dayboard.teacher_id),
        (models.TimeSlot, "time_id", dayboard.time_id),
        (models.Day, "day_id", dayboard.day_id),
    ]:
        exists = db.query(model).filter(model.id == value).first()
        if not exists:
            raise HTTPException(status_code=404, detail=f"{field}={value} not found")
    
    data = dayboard.dict()
    data.pop("admin_password")

    new_entry = models.Dayboard(**data)
    db.add(new_entry)
    db.commit()
    db.refresh(new_entry)
    return new_entry


@app.get("/dayboard/filter", response_model=List[DayboardWithAll])
def filter_dayboard(
    day: Optional[str] = Query(None),      # по имени дня
    group: Optional[str] = Query(None),    # по названию группы
    ord: Optional[int] = Query(None),      # знаменатель/числитель
    podgroup: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    DayAlias = aliased(models.Day)
    
    query = db.query(models.Dayboard).options(
        joinedload(models.Dayboard.subject_rel),
        joinedload(models.Dayboard.group_rel),
        joinedload(models.Dayboard.teacher_rel),
        joinedload(models.Dayboard.time_rel),
        joinedload(models.Dayboard.day_rel),
        joinedload(models.Dayboard.place_rel),
        joinedload(models.Dayboard.type_rel),
    )

    if day is not None:
        query = query.join(DayAlias, models.Dayboard.day_rel).filter(DayAlias.name == day)
    if ord is not None:
        query = query.join(DayAlias, models.Dayboard.day_rel).filter(DayAlias.ord == ord)
    if group is not None:
        query = query.join(models.Group, models.Dayboard.group_rel).filter(models.Group.name == group)
    if podgroup is not None:
        query = query.filter(models.Dayboard.podgroup == podgroup)


    results = query.all()

    output = []
    for d in results:
        obj = DayboardWithAll(
            id=d.id,
            subject_name=d.subject_rel.name,
            group_name=d.group_rel.name,
            teacher_name=d.teacher_rel.full_name,
            day_name=d.day_rel.name,
            ord=d.day_rel.ord,
            start_time=d.time_rel.start_time,
            end_time=d.time_rel.end_time,
            place=d.place_rel.name, 
            type=d.type_rel.name, 
            podgroup=d.podgroup,
        )
        output.append(obj)

    return output


@app.get("/dayboard/teacher/{full_name}")
def get_teacher_dayboard(full_name: str, db: Session = Depends(get_db)):
    teacher = db.query(models.Teacher).filter(models.Teacher.full_name == full_name).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Преподаватель не найден")

    lessons = []
    for l in teacher.dayboards:
        lessons.append({
            "day_name": l.day_rel.name,
            "ord": l.day_rel.ord,
            "start_time": l.time_rel.start_time,
            "end_time": l.time_rel.end_time,
            "subject_name": l.subject_rel.name,
            "type": l.type_rel.name,
            "place": l.place_rel.name,
            "teacher_name": l.teacher_rel.full_name,
            "group": l.group_rel.name,
            "podgroup": l.podgroup,
        })

    return lessons


@app.get("/teachers", response_model=List[TeacherOut])
def list_teachers(
    q: Optional[str] = Query(None, min_length=1, description="Поиск по подстроке ФИО"),
    include_unknown: bool = Query(False, description="Включать 'Не указан'"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(models.Teacher)

    if not include_unknown:
        query = query.filter(models.Teacher.full_name != "Не указан")

    if q:
        query = query.filter(models.Teacher.full_name.ilike(f"%{q}%"))

    teachers = (
        query.order_by(asc(models.Teacher.full_name))
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [TeacherOut.model_validate(t, from_attributes=True) for t in teachers]
