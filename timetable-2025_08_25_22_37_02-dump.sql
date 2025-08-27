--
-- PostgreSQL database dump
--

\restrict qOWc7AH26q3b3m3AhGm3clfc62fuPZhGoAaD4lLzyhrjoywOZuryxJBMjkVQ4ce

-- Dumped from database version 17.6 (Debian 17.6-1.pgdg13+1)
-- Dumped by pg_dump version 17.6 (Debian 17.6-1.pgdg13+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Data for Name: alembic_version; Type: TABLE DATA; Schema: public; Owner: timetable_root
--

INSERT INTO public.alembic_version VALUES ('ac02c9118eb0');


--
-- Data for Name: days; Type: TABLE DATA; Schema: public; Owner: timetable_root
--

INSERT INTO public.days VALUES (12, 'Saturday', 0);
INSERT INTO public.days VALUES (11, 'Saturday', 1);
INSERT INTO public.days VALUES (10, 'Friday', 0);
INSERT INTO public.days VALUES (9, 'Friday', 1);
INSERT INTO public.days VALUES (8, 'Thursday', 0);
INSERT INTO public.days VALUES (7, 'Thursday', 1);
INSERT INTO public.days VALUES (6, 'Wednesday', 0);
INSERT INTO public.days VALUES (5, 'Wednesday', 1);
INSERT INTO public.days VALUES (4, 'Tuesday', 0);
INSERT INTO public.days VALUES (3, 'Tuesday', 1);
INSERT INTO public.days VALUES (2, 'Monday', 0);
INSERT INTO public.days VALUES (1, 'Monday', 1);


--
-- Data for Name: groups; Type: TABLE DATA; Schema: public; Owner: timetable_root
--

INSERT INTO public.groups VALUES (1, 'uik2-32b');
INSERT INTO public.groups VALUES (2, 'uik2-51b');
INSERT INTO public.groups VALUES (3, 'uik2-52b');
INSERT INTO public.groups VALUES (4, 'uik2-53b');


--
-- Data for Name: places; Type: TABLE DATA; Schema: public; Owner: timetable_root
--

INSERT INTO public.places VALUES (1, 'Не указано');
INSERT INTO public.places VALUES (2, '2.424');
INSERT INTO public.places VALUES (3, '2.257');
INSERT INTO public.places VALUES (4, '1.210');
INSERT INTO public.places VALUES (5, '1.252');
INSERT INTO public.places VALUES (6, '2.209');
INSERT INTO public.places VALUES (7, '1.245');
INSERT INTO public.places VALUES (8, '3.260');
INSERT INTO public.places VALUES (9, '3.406');
INSERT INTO public.places VALUES (10, '2.258');
INSERT INTO public.places VALUES (11, '3.157');
INSERT INTO public.places VALUES (12, '2.309');
INSERT INTO public.places VALUES (13, '1.426');
INSERT INTO public.places VALUES (14, 'каф. ИУК10');


--
-- Data for Name: subjects; Type: TABLE DATA; Schema: public; Owner: timetable_root
--

INSERT INTO public.subjects VALUES (1, 'КП');
INSERT INTO public.subjects VALUES (2, 'Функциональные узлы и компоненты информационно-вычислительных систем');
INSERT INTO public.subjects VALUES (3, 'Платформы виртуальной реальности');
INSERT INTO public.subjects VALUES (4, 'Сети и телекоммуникации');
INSERT INTO public.subjects VALUES (5, 'Социология');
INSERT INTO public.subjects VALUES (6, 'Операционные системы');
INSERT INTO public.subjects VALUES (7, 'Экология');
INSERT INTO public.subjects VALUES (8, 'Иностранный язык');
INSERT INTO public.subjects VALUES (9, 'Элективные дисциплины по физической культуре и спорту');
INSERT INTO public.subjects VALUES (10, 'ВП');


--
-- Data for Name: teachers; Type: TABLE DATA; Schema: public; Owner: timetable_root
--

INSERT INTO public.teachers VALUES (2, 'Трешневская В. О.');
INSERT INTO public.teachers VALUES (3, 'Онуфриева Т. А.');
INSERT INTO public.teachers VALUES (4, 'Крысин И. А.');
INSERT INTO public.teachers VALUES (1, 'Не указан');
INSERT INTO public.teachers VALUES (5, 'Вершинин Е. В.');
INSERT INTO public.teachers VALUES (6, 'Чернышева Т. Е.');
INSERT INTO public.teachers VALUES (7, 'Федоров В. О.');
INSERT INTO public.teachers VALUES (8, 'Морозенко М. И.');
INSERT INTO public.teachers VALUES (9, 'Белова Е. В.');


--
-- Data for Name: timeslots; Type: TABLE DATA; Schema: public; Owner: timetable_root
--

INSERT INTO public.timeslots VALUES (5, '16:05', '17:40');
INSERT INTO public.timeslots VALUES (4, '14:15', '15:50');
INSERT INTO public.timeslots VALUES (3, '12:10', '13:45');
INSERT INTO public.timeslots VALUES (2, '10:20', '11:55');
INSERT INTO public.timeslots VALUES (1, '08:30', '10:05');


--
-- Data for Name: types; Type: TABLE DATA; Schema: public; Owner: timetable_root
--

INSERT INTO public.types VALUES (3, 'Лабораторная работа');
INSERT INTO public.types VALUES (2, 'Семинар');
INSERT INTO public.types VALUES (1, 'Лекция');
INSERT INTO public.types VALUES (4, 'Спец. занятие');


--
-- Data for Name: dayboard; Type: TABLE DATA; Schema: public; Owner: timetable_root
--

INSERT INTO public.dayboard VALUES (4, 4, 3, 2, 2, 2, 4, 2);
INSERT INTO public.dayboard VALUES (3, 3, 3, 1, 1, 2, 3, 3);
INSERT INTO public.dayboard VALUES (2, 2, 3, 1, 2, 1, 3, 2);
INSERT INTO public.dayboard VALUES (1, 2, 3, 1, 1, 1, 2, 3);
INSERT INTO public.dayboard VALUES (5, 2, 3, 3, 3, 3, 4, 1);
INSERT INTO public.dayboard VALUES (8, 3, 3, 4, 4, 4, 5, 1);
INSERT INTO public.dayboard VALUES (6, 3, 3, 4, 4, 3, 5, 1);
INSERT INTO public.dayboard VALUES (7, 2, 3, 3, 3, 4, 4, 1);
INSERT INTO public.dayboard VALUES (9, 4, 3, 5, 2, 5, 6, 1);
INSERT INTO public.dayboard VALUES (10, 5, 3, 6, 3, 5, 7, 1);
INSERT INTO public.dayboard VALUES (11, 1, 3, 1, 4, 5, 1, 4);
INSERT INTO public.dayboard VALUES (12, 4, 3, 5, 2, 6, 6, 1);
INSERT INTO public.dayboard VALUES (13, 5, 3, 6, 3, 6, 7, 1);
INSERT INTO public.dayboard VALUES (14, 1, 3, 1, 4, 6, 1, 4);
INSERT INTO public.dayboard VALUES (15, 6, 3, 7, 2, 7, 8, 1);
INSERT INTO public.dayboard VALUES (16, 7, 3, 8, 3, 7, 9, 2);
INSERT INTO public.dayboard VALUES (17, 6, 3, 7, 1, 8, 10, 2);
INSERT INTO public.dayboard VALUES (18, 6, 3, 7, 2, 8, 8, 1);
INSERT INTO public.dayboard VALUES (19, 7, 3, 8, 3, 9, 11, 1);
INSERT INTO public.dayboard VALUES (20, 3, 3, 4, 4, 9, 12, 2);
INSERT INTO public.dayboard VALUES (21, 7, 3, 8, 3, 10, 11, 1);
INSERT INTO public.dayboard VALUES (22, 6, 3, 7, 4, 10, 10, 3);
INSERT INTO public.dayboard VALUES (23, 8, 3, 9, 2, 11, 13, 2);
INSERT INTO public.dayboard VALUES (24, 9, 3, 1, 3, 11, 14, 2);
INSERT INTO public.dayboard VALUES (25, 8, 3, 9, 2, 12, 13, 2);
INSERT INTO public.dayboard VALUES (26, 9, 3, 1, 3, 12, 14, 2);


--
-- Data for Name: settings; Type: TABLE DATA; Schema: public; Owner: timetable_root
--

INSERT INTO public.settings VALUES (1, 'daily_timetable_hour', '8');
INSERT INTO public.settings VALUES (2, 'daily_timetable_minute', '0');


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: timetable_root
--

INSERT INTO public.users VALUES (3, 667163609, 'vladmav_11', 3, 1, 'private');
INSERT INTO public.users VALUES (4, -4815121203, 'vladmav_11', 4, 1, 'group');


--
-- Name: dayboard_id_seq; Type: SEQUENCE SET; Schema: public; Owner: timetable_root
--

SELECT pg_catalog.setval('public.dayboard_id_seq', 1, false);


--
-- Name: days_id_seq; Type: SEQUENCE SET; Schema: public; Owner: timetable_root
--

SELECT pg_catalog.setval('public.days_id_seq', 1, false);


--
-- Name: groups_id_seq; Type: SEQUENCE SET; Schema: public; Owner: timetable_root
--

SELECT pg_catalog.setval('public.groups_id_seq', 1, false);


--
-- Name: places_id_seq; Type: SEQUENCE SET; Schema: public; Owner: timetable_root
--

SELECT pg_catalog.setval('public.places_id_seq', 1, false);


--
-- Name: settings_id_seq; Type: SEQUENCE SET; Schema: public; Owner: timetable_root
--

SELECT pg_catalog.setval('public.settings_id_seq', 1, false);


--
-- Name: subjects_id_seq; Type: SEQUENCE SET; Schema: public; Owner: timetable_root
--

SELECT pg_catalog.setval('public.subjects_id_seq', 1, false);


--
-- Name: teachers_id_seq; Type: SEQUENCE SET; Schema: public; Owner: timetable_root
--

SELECT pg_catalog.setval('public.teachers_id_seq', 1, false);


--
-- Name: timeslots_id_seq; Type: SEQUENCE SET; Schema: public; Owner: timetable_root
--

SELECT pg_catalog.setval('public.timeslots_id_seq', 1, false);


--
-- Name: types_id_seq; Type: SEQUENCE SET; Schema: public; Owner: timetable_root
--

SELECT pg_catalog.setval('public.types_id_seq', 1, false);


--
-- Name: users_id_seq; Type: SEQUENCE SET; Schema: public; Owner: timetable_root
--

SELECT pg_catalog.setval('public.users_id_seq', 4, true);


--
-- PostgreSQL database dump complete
--

\unrestrict qOWc7AH26q3b3m3AhGm3clfc62fuPZhGoAaD4lLzyhrjoywOZuryxJBMjkVQ4ce

