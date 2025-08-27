from sqlalchemy import Column, Integer, String, ForeignKey, BigInteger
from sqlalchemy.orm import relationship

from .base import Base


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)

    users = relationship("User", back_populates="group_rel")
    dayboards = relationship("Dayboard", back_populates="group_rel")

    def __str__(self):
        return self.name


class Teacher(Base):
    __tablename__ = "teachers"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    full_name = Column(String, nullable=False) 

    dayboards = relationship("Dayboard", back_populates="teacher_rel")

    def __str__(self):
        return self.full_name


class TimeSlot(Base):
    __tablename__ = "timeslots"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    start_time = Column(String, nullable=False) 
    end_time = Column(String, nullable=False)

    dayboards = relationship("Dayboard", back_populates="time_rel")

    def __str__(self):
        return f"{self.start_time} - {self.end_time}"


class Day(Base):
    __tablename__ = "days"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, nullable=False)  # Monday, Tuesday и т.д.
    ord = Column(Integer, nullable=False)  # 0 - знаменатель, 1 - числитель

    dayboards = relationship("Dayboard", back_populates="day_rel")

    def __str__(self):
        return f"{self.name}, {self.ord}"


class Subject(Base):
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, nullable=False) 

    dayboards = relationship("Dayboard", back_populates="subject_rel")

    def __str__(self):
        return self.name


class Place(Base):
    __tablename__ = "places"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)

    dayboards = relationship("Dayboard", back_populates="place_rel")

    def __str__(self):
        return self.name


class Type(Base):
    __tablename__ = "types"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)

    dayboards = relationship("Dayboard", back_populates="type_rel")

    def __str__(self):
        return self.name


class Dayboard(Base):
    __tablename__ = "dayboard"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=False)
    time_id = Column(Integer, ForeignKey("timeslots.id"), nullable=False)
    day_id = Column(Integer, ForeignKey("days.id"), nullable=False)
    place_id = Column(Integer, ForeignKey("places.id"), nullable=False)
    type_id = Column(Integer, ForeignKey("types.id"), nullable=False)
    podgroup = Column(Integer, nullable=False, default=0)

    # ===== связи =====
    subject_rel = relationship("Subject", back_populates="dayboards")
    group_rel = relationship("Group", back_populates="dayboards")
    teacher_rel = relationship("Teacher", back_populates="dayboards")
    time_rel = relationship("TimeSlot", back_populates="dayboards")
    day_rel = relationship("Day", back_populates="dayboards")
    place_rel = relationship("Place", back_populates="dayboards")
    type_rel = relationship("Type", back_populates="dayboards")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tg_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String, unique=False, nullable=False)

    group_id = Column(Integer, ForeignKey("groups.id"), nullable=True)
    group_rel = relationship("Group", back_populates="users")

    is_active = Column(Integer, default=1)
    title = Column(String, nullable=False)


class Settings(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    key = Column(String, unique=True, nullable=False)
    value = Column(String, nullable=False)
