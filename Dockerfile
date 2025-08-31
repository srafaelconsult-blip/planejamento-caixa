# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Instalar dependências do sistema necessárias para pandas
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements primeiro (para cache de dependências)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar o resto da aplicação
COPY . .

# Expor a porta que o Flask vai usar
EXPOSE 5000

# Comando para rodar a aplicação
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
