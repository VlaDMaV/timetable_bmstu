FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir pip==26.2.1 && \
    pip install --no-cache-dir -r requirements.txt

COPY . ./schedule_monitor

CMD ["python", "-m", "schedule_monitor.main"]
