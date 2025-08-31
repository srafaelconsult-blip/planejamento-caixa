FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

RUN mkdir -p templates

EXPOSE 5000

# Comando corrigido - separar a criação do banco e a execução do app
CMD ["sh", "-c", "python -c 'from app import db, app; db.create_all()' && exec gunicorn --bind 0.0.0.0:5000 app:app"]
