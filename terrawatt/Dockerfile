FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python -m backend.manage train
ENV TERRAWATT_ENV=production PORT=8000
EXPOSE 8000
# SECRET_KEY must be provided at runtime. Mount a volume at /app/instance to persist the SQLite DB.
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8000", "backend.app:create_app()"]
