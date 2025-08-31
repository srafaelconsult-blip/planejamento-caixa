#!/bin/bash
# start.sh

# Criar tabelas do banco de dados
python -c "from app import db, app; with app.app_context(): db.create_all()"

# Iniciar a aplicação
exec gunicorn --bind 0.0.0.0:5000 app:app
