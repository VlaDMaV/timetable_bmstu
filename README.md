# timetable_bmstu
Готовое решения для вашего расписание КФ МГТУ

## Разворот проекта

* Клонировать репозиторий
    ```bash
    git clone https://github.com/VlaDMaV/timetable_bmstu.git
    ```

## Деплой проекта

* Создать .env файл (можно полностью скопировать .env.example и заменить внутри данныке на свои)

* Запуск проекта
    ```bash
    docker-compose up --build -d
    ```
    
P.S. для просмотра логов контейнеров можно использовать:
```bash
    docker logs <container_id>
```
