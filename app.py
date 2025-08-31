import pandas as pd
import numpy as np
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import json
import os
import psycopg2
from urllib.parse import urlparse

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-12345')

# Configuração do banco de dados
database_url = os.environ.get('DATABASE_URL')

if database_url:
    # Parse da URL do PostgreSQL
    parsed_url = urlparse(database_url)
    app.config['SQLALCHEMY_DATABASE_URI'] = f"postgresql+psycopg2://{parsed_url.username}:{parsed_url.password}@{parsed_url.hostname}:{parsed_url.port}{parsed_url.path}"
else:
    # Fallback para SQLite (desenvolvimento local)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_recycle': 300,
    'pool_pre_ping': True,
}

db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    subscription_end = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def has_active_subscription(self):
        if not self.subscription_end:
            return False
        return self.subscription_end > datetime.utcnow()

    def add_subscription_days(self, days=30):
        if self.subscription_end and self.subscription_end > datetime.utcnow():
            self.subscription_end += timedelta(days=days)
        else:
            self.subscription_end = datetime.utcnow() + timedelta(days=days)

class PlanejamentoCaixa:
    def __init__(self, num_meses=24):
        self.num_meses = num_meses
        
        # Valores padrão dos SETUPS
        self.setup = {
            'vendas_vista': 0.3,
            'vendas_parcelamento': 5,
            'plus_vendas': 0,
            'cmv': 0.425,
            'percent_compras': 0.2,
            'compras_vista': 0.2,
            'compras_parcelamento': 6,
            'comissoes': 0.0761,
            'desp_variaveis_impostos': 0.085
        }
        
        # Previsão de vendas inicial
        self.previsao_vendas = [1200] * self.num_meses
        
        # Valores manuais para os campos adicionais
        self.contas_receber_anteriores = [0] * self.num_meses
        self.comissoes_anteriores = [0] * self.num_meses
        self.contas_pagar_anteriores = [0] * self.num_meses
        self.desp_fixas_manuais = [438] * self.num_meses
        
    def calcular(self, dados):
        # Atualizar valores com os dados recebidos
        for key in self.setup:
            if key in dados.get('setup', {}):
                self.setup[key] = float(dados['setup'][key])
        
        if 'previsao_vendas' in dados:
            self.previsao_vendas = [float(x) for x in dados['previsao_vendas']]
        
        if 'contas_receber_anteriores' in dados:
            self.contas_receber_anteriores = [float(x) for x in dados['contas_receber_anteriores']]
        
        if 'comissoes_anteriores' in dados:
            self.comissoes_anteriores = [float(x) for x in dados['comissoes_anteriores']]
        
        if 'contas_pagar_anteriores' in dados:
            self.contas_pagar_anteriores = [float(x) for x in dados['contas_pagar_anteriores']]
        
        if 'desp_fixas_manuais' in dados:
            self.desp_fixas_manuais = [float(x) for x in dados['desp_fixas_manuais']]
        
        # 1. Escalonamento das Vendas com Plus
        plus = self.setup['plus_vendas']
        self.vendas_escalonadas = [
            venda * (1 + plus) if plus > 0 else venda
            for venda in self.previsao_vendas
        ]
        
        # 2. Fluxo de recebimentos
        n_parcelas = int(self.setup['vendas_parcelamento'])
        
        # Vendas a vista
        self.vendas_vista = [
            venda * self.setup['vendas_vista'] 
            for venda in self.vendas_escalonadas
        ]
        
        # Duplicatas a receber
        self.duplicatas_receber = [[0] * self.num_meses for _ in range(n_parcelas)]
        
        for mes in range(self.num_meses):
            valor_parcelado = (self.vendas_escalonadas[mes] - self.vendas_vista[mes]) / n_parcelas
            
            for parcela_idx in range(n_parcelas):
                mes_recebimento = mes + parcela_idx
                if mes_recebimento < self.num_meses:
                    self.duplicatas_receber[parcela_idx][mes_recebimento] += valor_parcelado
        
        # Total recebimentos
        self.total_recebimentos = []
        for mes in range(self.num_meses):
            total = self.vendas_vista[mes]
            
            for p in range(n_parcelas):
                total += self.duplicatas_receber[p][mes]
            
            total += self.contas_receber_anteriores[mes]
            self.total_recebimentos.append(total)
        
        # 3. Comissões
        self.comissoes_mes = [
            venda * self.setup['comissoes'] 
            for venda in self.vendas_escalonadas
        ]
        
        # Comissões a pagar (parceladas)
        n_parcelas_comissoes = 4
        self.comissoes_pagar = [[0] * self.num_meses for _ in range(n_parcelas_comissoes)]
        
        for mes in range(self.num_meses):
            valor_comissao = self.comissoes_mes[mes]
            valor_parcelado = valor_comissao / n_parcelas_comissoes
            
            for parcela_idx in range(n_parcelas_comissoes):
                mes_pagamento = mes + parcela_idx
                if mes_pagamento < self.num_meses:
                    self.comissoes_pagar[parcela_idx][mes_pagamento] += valor_parcelado
        
        # Total comissões
        self.total_comissoes = []
        for mes in range(self.num_meses):
            total = self.comissoes_anteriores[mes]
            
            for p in range(n_parcelas_comissoes):
                total += self.comissoes_pagar[p][mes]
                
            self.total_comissoes.append(total)
        
        # 4. Planejamento de Compras
        self.compras_planejadas = [
            venda * self.setup['cmv'] * self.setup['percent_compras'] 
            for venda in self.vendas_escalonadas
        ]
        
        self.compras_vista = [
            compra * self.setup['compras_vista'] 
            for compra in self.compras_planejadas
        ]
        
        n_parcelas_compras = int(self.setup['compras_parcelamento'])
        self.duplicatas_pagar = [[0] * self.num_meses for _ in range(n_parcelas_compras)]
        
        for mes in range(self.num_meses):
            valor_parcelado = (self.compras_planejadas[mes] - self.compras_vista[mes]) / n_parcelas_compras
            
            for parcela_idx in range(n_parcelas_compras):
                mes_pagamento = mes + parcela_idx
                if mes_pagamento < self.num_meses:
                    self.duplicatas_pagar[parcela_idx][mes_pagamento] += valor_parcelado
        
        self.total_pagamento_compras = []
        for mes in range(self.num_meses):
            total = self.compras_vista[mes]
            
            for p in range(n_parcelas_compras):
                total += self.duplicatas_pagar[p][mes]
            
            total += self.contas_pagar_anteriores[mes]
            self.total_pagamento_compras.append(total)
        
        # 5. Despesas variáveis
        self.desp_variaveis = [
            venda * self.setup['desp_variaveis_impostos'] 
            for venda in self.vendas_escalonadas
        ]
        
        # 6. Despesas fixas
        self.desp_fixas = self.desp_fixas_manuais
        
        # 7. Saldo operacional
        self.saldo_operacional = []
        for mes in range(self.num_meses):
            saldo = (self.total_recebimentos[mes] - 
                    self.total_comissoes[mes] - 
                    self.total_pagamento_compras[mes] - 
                    self.desp_variaveis[mes] - 
                    self.desp_fixas[mes])
            self.saldo_operacional.append(saldo)
        
        # 8. Saldo final de caixa
        self.saldo_final_caixa = [self.saldo_operacional[0]]
        for mes in range(1, self.num_meses):
            self.saldo_final_caixa.append(self.saldo_final_caixa[-1] + self.saldo_operacional[mes])
        
        return self.gerar_resultados()
    
    def gerar_resultados(self):
        meses = [f'Mês {i+1}' for i in range(self.num_meses)] + ['TOTAL']
        
        # Preparar dados na ordem específica solicitada
        dados_ordenados = {}
        
        # 1. Previsão das Vendas
        dados_ordenados['Previsão das Vendas'] = self.previsao_vendas + [sum(self.previsao_vendas)]
        
        # 2. Escalonamento das Vendas com Plus
        dados_ordenados['Escalonamento das Vendas com Plus'] = self.vendas_escalonadas + [sum(self.vendas_escalonadas)]
        
        # 3. Fluxo de recebimentos - Separador
        dados_ordenados['--- FLUXO DE RECEBIMENTOS ---'] = [''] * (self.num_meses + 1)
        
        # 4. Vendas à vista
        dados_ordenados['Vendas à vista'] = self.vendas_vista + [sum(self.vendas_vista)]
        
        # 5. Parcelas de duplicatas a receber
        n_parcelas = int(self.setup['vendas_parcelamento'])
        for p in range(n_parcelas):
            parcelas = []
            for mes in range(self.num_meses):
                parcelas.append(self.duplicatas_receber[p][mes])
            dados_ordenados[f'{p+1}º mês duplicatas a receber'] = parcelas + [sum(parcelas)]
        
        # 6. Contas a receber de vendas anteriores
        dados_ordenados['(+) Contas a receber referente a vendas anteriores'] = self.contas_receber_anteriores + [sum(self.contas_receber_anteriores)]
        
        # 7. Total recebimentos
        dados_ordenados['Total recebimentos'] = self.total_recebimentos + [sum(self.total_recebimentos)]
        
        # 8. Comissões - Separador
        dados_ordenados['--- COMISSÕES ---'] = [''] * (self.num_meses + 1)
        
        # 9. Comissões a vista (%)
        comissoes_vista = [venda * self.setup['comissoes'] * 0.3 for venda in self.vendas_escalonadas]
        dados_ordenados['Comissões à vista (30%)'] = comissoes_vista + [sum(comissoes_vista)]
        
        # 10. Comissões parceladas
        n_parcelas_comissoes = 4
        for p in range(n_parcelas_comissoes):
            parcelas = []
            for mes in range(self.num_meses):
                parcelas.append(self.comissoes_pagar[p][mes])
            dados_ordenados[f'{p+1}º mês comissões a pagar'] = parcelas + [sum(parcelas)]
        
        # 11. Comissões anteriores
        dados_ordenados['(+) Comissões a pagar referente a vendas anteriores'] = self.comissoes_anteriores + [sum(self.comissoes_anteriores)]
        
        # 12. Total comissões
        dados_ordenados['Total de Comissões a pagar'] = self.total_comissoes + [sum(self.total_comissoes)]
        
        # 13. Planejamento de Compras - Separador
        dados_ordenados['--- PLANEJAMENTO DE COMPRAS ---'] = [''] * (self.num_meses + 1)
        
        # 14. Compras a vista
        dados_ordenados['Compras à vista'] = self.compras_vista + [sum(self.compras_vista)]
        
        # 15. Parcelas de duplicatas a pagar
        n_parcelas_compras = int(self.setup['compras_parcelamento'])
        for p in range(n_parcelas_compras):
            parcelas = []
            for mes in range(self.num_meses):
                parcelas.append(self.duplicatas_pagar[p][mes])
            dados_ordenados[f'{p+1}º mês duplicatas a pagar'] = parcelas + [sum(parcelas)]
        
        # 16. Contas a pagar de compras anteriores
        dados_ordenados['(-) Contas a pagar de fornecedores referente à compras anteriores'] = self.contas_pagar_anteriores + [sum(self.contas_pagar_anteriores)]
        
        # 17. Total pagamento compras
        dados_ordenados['Total Pagamento de Fornecedores'] = self.total_pagamento_compras + [sum(self.total_pagamento_compras)]
        
        # 18. Despesas - Separador
        dados_ordenados['--- DESPESAS ---'] = [''] * (self.num_meses + 1)
        
        # 19. Despesas variáveis
        dados_ordenados['(-) Despesas variáveis'] = self.desp_variaveis + [sum(self.desp_variaveis)]
        
        # 20. Despesas fixas
        dados_ordenados['(-) Despesas fixas'] = self.desp_fixas + [sum(self.desp_fixas)]
        
        # 21. Saldo - Separador
        dados_ordenados['--- SALDO ---'] = [''] * (self.num_meses + 1)
        
        # 22. Saldo operacional
        dados_ordenados['SALDO OPERACIONAL'] = self.saldo_operacional + [sum(self.saldo_operacional)]
        
        # 23. Saldo final de caixa
        dados_ordenados['SALDO FINAL DE CAIXA PREVISTO MAIS PROVÁVEL'] = self.saldo_final_caixa + [self.saldo_final_caixa[-1]]
        
        # Formatar números para exibição
        resultados_formatados = {}
        for key, values in dados_ordenados.items():
            if '---' in key:
                resultados_formatados[key] = values
            else:
                resultados_formatados[key] = [f"R$ {x:,.0f}" if isinstance(x, (int, float)) and not isinstance(x, bool) else x for x in values]
        
        # Indicadores financeiros
        indicadores = {
            'Total de Vendas': f"R$ {sum(self.previsao_vendas):,.0f}",
            'Total de Recebimentos': f"R$ {sum(self.total_recebimentos):,.0f}",
            'Total de Despesas': f"R$ {sum(self.total_comissoes) + sum(self.total_pagamento_compras) + sum(self.desp_variaveis) + sum(self.desp_fixas):,.0f}",
            'Saldo Final Acumulado': f"R$ {self.saldo_final_caixa[-1]:,.0f}",
            'Margem Líquida': f"{(sum(self.saldo_operacional) / sum(self.total_recebimentos)) * 100:.1f}%" if sum(self.total_recebimentos) > 0 else "0%"
        }
        
        # Dados para gráficos
        dados_graficos = {
            'meses': [f'Mês {i+1}' for i in range(min(12, self.num_meses))],
            'saldo_final_caixa': self.saldo_final_caixa[:12],
            'receitas': self.total_recebimentos[:12],
            'despesas': [
                a + b + c + d for a, b, c, d in zip(
                    self.total_comissoes[:12], 
                    self.total_pagamento_compras[:12], 
                    self.desp_variaveis[:12], 
                    self.desp_fixas[:12]
                )
            ]
        }
        
        return {
            'resultados': resultados_formatados,
            'indicadores': indicadores,
            'graficos': dados_graficos,
            'meses': meses
        }

# Rotas de autenticação
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if not user:
        session.pop('user_id', None)
        return redirect(url_for('login'))
    
    if not user.has_active_subscription():
        return redirect(url_for('payment'))
    
    return render_template('calculadora.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            session['user_id'] = user.id
            if user.has_active_subscription():
                return redirect(url_for('index'))
            else:
                return redirect(url_for('payment'))
        
        return render_template('login.html', error='Email ou senha inválidos')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(email=email).first():
            return render_template('register.html', error='Email já cadastrado')
        
        user = User(email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        session['user_id'] = user.id
        return redirect(url_for('payment'))
    
    return render_template('register.html')

@app.route('/payment')
def payment():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if user and user.has_active_subscription():
        return redirect(url_for('index'))
    
    return render_template('payment.html')

@app.route('/process_payment', methods=['POST'])
def process_payment():
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Usuário não autenticado'})
        
        user = User.query.get(session['user_id'])
        if not user:
            return jsonify({'success': False, 'message': 'Usuário não encontrado'})
        
        # Simular processamento de pagamento
        user.add_subscription_days(30)
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': 'Pagamento processado com sucesso!',
            'redirect_url': '/'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Erro no servidor: {str(e)}'})

@app.route('/check_subscription')
def check_subscription():
    if 'user_id' not in session:
        return jsonify({'active': False})
    
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'active': False})
    
    return jsonify({'active': user.has_active_subscription()})

@app.route('/subscription_info')
def subscription_info():
    if 'user_id' not in session:
        return jsonify({'active': False})
    
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'active': False})
    
    return jsonify({
        'active': user.has_active_subscription(),
        'end_date': user.subscription_end.isoformat() if user.subscription_end else None
    })

@app.route('/logout', methods=['GET'])
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

@app.route('/calcular', methods=['POST'])
def calcular():
    if 'user_id' not in session:
        return jsonify({'error': 'Usuário não autenticado'}), 401
    
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'error': 'Usuário não encontrado'}), 401
    
    if not user.has_active_subscription():
        return jsonify({
            'error': 'Assinatura expirada',
            'redirect_url': '/payment'
        }), 403
    
    try:
        dados = request.get_json()
        planejamento = PlanejamentoCaixa()
        resultados = planejamento.calcular(dados)
        return jsonify(resultados)
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# Criar tabelas do banco de dados
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
