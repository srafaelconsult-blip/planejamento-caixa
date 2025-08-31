#!/bin/bash
# start.sh

echo "=== INICIANDO APLICAÇÃO ==="

# Criar tabelas do banco de dados
echo "Criando tabelas do banco de dados..."
python -c "
from app import db, app
with app.app_context():
    db.create_all()
    print('Tabelas criadas com sucesso!')
"

# Iniciar a aplicação
echo "Iniciando servidor..."
exec gunicorn --bind 0.0.0.0:5000 app:app
