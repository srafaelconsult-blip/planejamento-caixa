FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

RUN mkdir -p templates

EXPOSE 5000

CMD ["python", "app.py"]
