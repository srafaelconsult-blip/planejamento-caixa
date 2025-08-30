from flask import Flask, render_template, request, session, redirect, url_for, jsonify
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from io import BytesIO
import base64
import json
import hashlib
from datetime import datetime, timedelta
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'sua-chave-secreta-aqui')

# Sistema de gerenciamento de usuários (em produção use banco de dados)
class UserManager:
    def __init__(self):
        self.users = {}
    
    def create_user(self, email, password):
        user_id = hashlib.md5(email.encode()).hexdigest()
        
        if user_id in self.users:
            return False, "Usuário já existe"
        
        self.users[user_id] = {
            'email': email,
            'password': hashlib.md5(password.encode()).hexdigest(),
            'signup_date': datetime.now().isoformat(),
            'subscription_status': 'trial',
            'trial_end_date': (datetime.now() + timedelta(days=30)).isoformat()
        }
        return True, "Conta criada com sucesso! 30 dias gratuitos"
    
    def verify_user(self, email, password):
        user_id = hashlib.md5(email.encode()).hexdigest()
        
        if user_id not in self.users:
            return False, "Usuário não encontrado"
        
        if self.users[user_id]['password'] != hashlib.md5(password.encode()).hexdigest():
            return False, "Senha incorreta"
        
        # Verificar status da assinatura
        trial_end = datetime.fromisoformat(self.users[user_id]['trial_end_date'])
        if self.users[user_id]['subscription_status'] == 'trial' and datetime.now() > trial_end:
            self.users[user_id]['subscription_status'] = 'expired'
            return False, "Período de teste expirado"
        
        if self.users[user_id]['subscription_status'] == 'expired':
            return False, "Assinatura expirada"
        
        return True, "Login bem-sucedido"

user_manager = UserManager()

# Rotas principais
@app.route('/')
def index():
    if 'user' not in session:
        return redirect('/login')
    return render_template('calculadora.html', username=session['user'])

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        success, message = user_manager.verify_user(email, password)
        if success:
            session['user'] = email
            return redirect('/')
        else:
            return render_template('login.html', error=message)
    
    return render_template('login.html')

@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if password != confirm_password:
            return render_template('cadastro.html', error="As senhas não coincidem")
        
        success, message = user_manager.create_user(email, password)
        if success:
            session['user'] = email
            return redirect('/')
        else:
            return render_template('cadastro.html', error=message)
    
    return render_template('cadastro.html')

@app.route('/assinatura')
def assinatura():
    if 'user' not in session:
        return redirect('/login')
    return render_template('assinatura.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/login')

# API para cálculos
@app.route('/api/calcular', methods=['POST'])
def api_calcular():
    try:
        data = request.json
        setup = data['setup']
        previsao_vendas = data['previsao_vendas']
        
        # Implemente seus cálculos aqui (igual no Streamlit)
        # ... seu código de cálculo ...
        
        # Exemplo simplificado:
        vendas_escalonadas = [v * (1 + setup['plus_vendas']) for v in previsao_vendas]
        total_vendas = sum(vendas_escalonadas)
        
        return jsonify({
            'success': True,
            'resultados': {
                'total_vendas': total_vendas,
                'vendas_escalonadas': vendas_escalonadas,
                # ... outros resultados ...
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
