FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

RUN mkdir -p templates

# Instalar dependências do sistema para SQLite (se necessário)
RUN apt-get update && apt-get install -y \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

EXPOSE 5000

# Comando para criar o banco de dados e iniciar a aplicação
CMD ["sh", "-c", "python -c 'from app import db; db.create_all()' && python app.py"]
