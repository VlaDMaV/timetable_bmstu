--
-- PostgreSQL database dump
--

\restrict R2bMugFf5xdHLUoIbGqavzNTbZtFMFT1tazKQDBASkLoDRJSF9LOkx1AdA5ZcYs

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

INSERT INTO public.alembic_version VALUES ('d920e5d29d3f');
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
INSERT INTO public.groups VALUES (5, 'uik1-52b');


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
INSERT INTO public.places VALUES (15, '1.412');
INSERT INTO public.places VALUES (16, '2.555');
INSERT INTO public.places VALUES (17, '1.425');
INSERT INTO public.places VALUES (18, '1.251');
INSERT INTO public.places VALUES (19, '1.237');
INSERT INTO public.places VALUES (20, '3.303');
INSERT INTO public.places VALUES (21, '1.459');
INSERT INTO public.places VALUES (22, '3.415');
INSERT INTO public.places VALUES (23, '2.261');
INSERT INTO public.places VALUES (24, '1.458');
INSERT INTO public.places VALUES (25, '2.231');
INSERT INTO public.places VALUES (26, '2.255');


--
-- Data for Name: subjects; Type: TABLE DATA; Schema: public; Owner: timetable_root
--

INSERT INTO public.subjects VALUES (1, 'КП');
INSERT INTO public.subjects VALUES (2, 'Функциональные узлы и компоненты информационно-вычислительных систем');
INSERT INTO public.subjects VALUES (3, 'Платформы виртуальной реальности');
INSERT INTO public.subjects VALUES (5, 'Социология');
INSERT INTO public.subjects VALUES (6, 'Операционные системы');
INSERT INTO public.subjects VALUES (7, 'Экология');
INSERT INTO public.subjects VALUES (8, 'Иностранный язык');
INSERT INTO public.subjects VALUES (9, 'Элективные дисциплины по физической культуре и спорту');
INSERT INTO public.subjects VALUES (10, 'ВП');
INSERT INTO public.subjects VALUES (11, 'Физика');
INSERT INTO public.subjects VALUES (12, 'Дискретная математика');
INSERT INTO public.subjects VALUES (13, 'Основы электроники');
INSERT INTO public.subjects VALUES (4, 'Сети и телекоммуникации');
INSERT INTO public.subjects VALUES (14, 'Языки программирования с упра');
INSERT INTO public.subjects VALUES (15, 'Философия');
INSERT INTO public.subjects VALUES (16, 'Теория информационных систем');
INSERT INTO public.subjects VALUES (17, 'Цифровые измерительные систе');
INSERT INTO public.subjects VALUES (18, 'Системное программирование');


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
INSERT INTO public.teachers VALUES (10, 'Буракова М. С.');
INSERT INTO public.teachers VALUES (11, 'Журавлева И. В.');
INSERT INTO public.teachers VALUES (12, 'Максимов А. В.');
INSERT INTO public.teachers VALUES (13, 'Чухраев И. В.');
INSERT INTO public.teachers VALUES (14, 'Амеличева К. А.');
INSERT INTO public.teachers VALUES (15, 'Ильин В. В.');
INSERT INTO public.teachers VALUES (17, 'Красавин Е. В.');
INSERT INTO public.teachers VALUES (18, 'Широкова Е. В.');
INSERT INTO public.teachers VALUES (19, 'Куликов А. Н.');
INSERT INTO public.teachers VALUES (20, 'Белова И. К.');
INSERT INTO public.teachers VALUES (21, 'Полпудников С. В.');
INSERT INTO public.teachers VALUES (22, 'Силаева Н. А.');
INSERT INTO public.teachers VALUES (23, 'Никитенко У. В.');


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
INSERT INTO public.dayboard VALUES (27, 10, 4, 1, 1, 2, 1, 4);
INSERT INTO public.dayboard VALUES (29, 10, 4, 1, 3, 2, 1, 4);
INSERT INTO public.dayboard VALUES (30, 10, 4, 1, 4, 2, 1, 4);
INSERT INTO public.dayboard VALUES (31, 10, 4, 1, 5, 2, 1, 4);
INSERT INTO public.dayboard VALUES (32, 10, 4, 1, 1, 1, 1, 4);
INSERT INTO public.dayboard VALUES (33, 10, 4, 1, 2, 1, 1, 4);
INSERT INTO public.dayboard VALUES (34, 10, 4, 1, 3, 1, 1, 4);
INSERT INTO public.dayboard VALUES (35, 10, 4, 1, 4, 1, 1, 4);
INSERT INTO public.dayboard VALUES (36, 10, 4, 1, 5, 1, 1, 4);
INSERT INTO public.dayboard VALUES (37, 2, 4, 3, 3, 4, 4, 1);
INSERT INTO public.dayboard VALUES (38, 2, 4, 3, 3, 3, 4, 1);
INSERT INTO public.dayboard VALUES (39, 3, 4, 4, 4, 4, 5, 1);
INSERT INTO public.dayboard VALUES (40, 3, 4, 4, 4, 3, 5, 1);
INSERT INTO public.dayboard VALUES (41, 2, 4, 1, 5, 3, 3, 2);
INSERT INTO public.dayboard VALUES (42, 2, 4, 1, 5, 4, 2, 3);
INSERT INTO public.dayboard VALUES (43, 4, 4, 5, 2, 6, 6, 1);
INSERT INTO public.dayboard VALUES (44, 4, 4, 5, 2, 5, 6, 1);
INSERT INTO public.dayboard VALUES (45, 5, 4, 6, 3, 6, 7, 1);
INSERT INTO public.dayboard VALUES (46, 5, 4, 6, 3, 5, 7, 1);
INSERT INTO public.dayboard VALUES (47, 3, 4, 1, 4, 5, 3, 3);
INSERT INTO public.dayboard VALUES (48, 6, 4, 7, 2, 8, 8, 1);
INSERT INTO public.dayboard VALUES (49, 6, 4, 7, 2, 7, 8, 1);
INSERT INTO public.dayboard VALUES (50, 7, 4, 8, 3, 8, 9, 2);
INSERT INTO public.dayboard VALUES (51, 3, 4, 4, 3, 7, 10, 2);
INSERT INTO public.dayboard VALUES (52, 1, 4, 1, 4, 8, 1, 4);
INSERT INTO public.dayboard VALUES (53, 1, 4, 1, 4, 7, 1, 4);
INSERT INTO public.dayboard VALUES (54, 4, 4, 10, 1, 10, 4, 2);
INSERT INTO public.dayboard VALUES (55, 6, 4, 7, 2, 10, 10, 3);
INSERT INTO public.dayboard VALUES (56, 6, 4, 7, 2, 9, 10, 2);
INSERT INTO public.dayboard VALUES (57, 7, 4, 8, 3, 10, 11, 1);
INSERT INTO public.dayboard VALUES (58, 7, 4, 8, 3, 9, 11, 1);
INSERT INTO public.dayboard VALUES (59, 8, 4, 11, 2, 12, 15, 2);
INSERT INTO public.dayboard VALUES (60, 8, 4, 11, 2, 11, 15, 2);
INSERT INTO public.dayboard VALUES (61, 9, 4, 1, 3, 12, 14, 2);
INSERT INTO public.dayboard VALUES (62, 9, 4, 1, 3, 11, 14, 2);
INSERT INTO public.dayboard VALUES (28, 10, 4, 1, 2, 2, 1, 4);
INSERT INTO public.dayboard VALUES (63, 17, 1, 12, 3, 2, 26, 3);
INSERT INTO public.dayboard VALUES (64, 8, 1, 1, 4, 2, 17, 2);
INSERT INTO public.dayboard VALUES (65, 17, 1, 12, 2, 1, 4, 1);
INSERT INTO public.dayboard VALUES (66, 17, 1, 12, 3, 1, 26, 3);
INSERT INTO public.dayboard VALUES (67, 8, 1, 1, 4, 1, 17, 2);
INSERT INTO public.dayboard VALUES (68, 13, 1, 13, 1, 4, 18, 1);
INSERT INTO public.dayboard VALUES (69, 13, 1, 13, 1, 3, 18, 1);
INSERT INTO public.dayboard VALUES (70, 18, 1, 14, 2, 4, 8, 1);
INSERT INTO public.dayboard VALUES (71, 18, 1, 14, 2, 3, 8, 1);
INSERT INTO public.dayboard VALUES (72, 18, 1, 17, 3, 4, 20, 2);
INSERT INTO public.dayboard VALUES (73, 15, 1, 15, 3, 3, 19, 2);


--
-- Data for Name: settings; Type: TABLE DATA; Schema: public; Owner: timetable_root
--

INSERT INTO public.settings VALUES (2, 'daily_timetable_minute', '0');
INSERT INTO public.settings VALUES (1, 'daily_timetable_hour', '8');


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: timetable_root
--

INSERT INTO public.users VALUES (5, 5108185765, 'user_5108185765', 3, 0, 'private');
INSERT INTO public.users VALUES (7, 1395282894, 'SkripTo28', 4, 0, 'private');
INSERT INTO public.users VALUES (6, -1003007292811, 'vladmav_11', 4, 1, 'supergroup');
INSERT INTO public.users VALUES (9, 1023011464, 'fifle', 2, 0, 'private');
INSERT INTO public.users VALUES (8, 529798989, 'aleksallen', 2, 0, 'private');
INSERT INTO public.users VALUES (3, 667163609, 'vladmav_11', 3, 1, 'private');


--
-- Name: dayboard_id_seq; Type: SEQUENCE SET; Schema: public; Owner: timetable_root
--

SELECT pg_catalog.setval('public.dayboard_id_seq', 73, true);


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

SELECT pg_catalog.setval('public.places_id_seq', 26, true);


--
-- Name: settings_id_seq; Type: SEQUENCE SET; Schema: public; Owner: timetable_root
--

SELECT pg_catalog.setval('public.settings_id_seq', 1, false);


--
-- Name: subjects_id_seq; Type: SEQUENCE SET; Schema: public; Owner: timetable_root
--

SELECT pg_catalog.setval('public.subjects_id_seq', 18, true);


--
-- Name: teachers_id_seq; Type: SEQUENCE SET; Schema: public; Owner: timetable_root
--

SELECT pg_catalog.setval('public.teachers_id_seq', 23, true);


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

SELECT pg_catalog.setval('public.users_id_seq', 9, true);


--
-- PostgreSQL database dump complete
--

\unrestrict R2bMugFf5xdHLUoIbGqavzNTbZtFMFT1tazKQDBASkLoDRJSF9LOkx1AdA5ZcYs

