FROM python:3.12-slim

WORKDIR /app
COPY . /app

ENV DEMO_MODE=true \
    APP_HOST=0.0.0.0 \
    APP_PORT=7860 \
    SQLITE_DB_PATH=/tmp/demo_edtech.db

EXPOSE 7860
CMD ["python3", "src/app.py"]
