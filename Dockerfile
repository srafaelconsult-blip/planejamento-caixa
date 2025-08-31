FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

RUN mkdir -p templates

EXPOSE 5000

# Comando corrigido - executar em duas etapas separadas
CMD python -c "from app import db, app; with app.app_context(): db.create_all()" && \
    gunicorn --bind 0.0.0.0:5000 app:app
