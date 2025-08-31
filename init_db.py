# init_db.py
from app import db, app

print("🔄 Criando tabelas do banco de dados...")
with app.app_context():
    db.create_all()
    print("✅ Tabelas criadas com sucesso!")
