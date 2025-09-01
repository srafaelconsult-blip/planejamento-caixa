import os
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse
import logging

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

# Configuração de logging para melhor depuração em produção
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-12345')

# --- Configuração do Banco de Dados ---
database_url = os.environ.get('DATABASE_URL')

if database_url:
    # Corrige o dialeto para o Heroku/Render que usa 'postgres://'
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_recycle': 280,  # Um pouco menos que o timeout do servidor de DB
    'pool_pre_ping': True,
}

db = SQLAlchemy(app)

# --- Modelos do Banco de Dados ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False) # Aumentado para hashes mais modernos
    subscription_end = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def has_active_subscription(self):
        return self.subscription_end and self.subscription_end > datetime.utcnow()

    def add_subscription_days(self, days=30):
        if self.subscription_end and self.subscription_end > datetime.utcnow():
            self.subscription_end += timedelta(days=days)
        else:
            self.subscription_end = datetime.utcnow() + timedelta(days=days)

# --- Lógica de Negócio ---
class PlanejamentoCaixa:
    def __init__(self, num_meses=5):
        self.num_meses = num_meses
        self.setup = {
            'vendas_vista': 0.3, 'vendas_parcelamento': 5, 'plus_vendas': 0,
            'cmv': 0.425, 'percent_compras': 0.2, 'compras_vista': 0.2,
            'compras_parcelamento': 6, 'comissoes': 0.0761, 'desp_variaveis_impostos': 0.085
        }
        self.previsao_vendas = [0] * num_meses
        self.contas_receber_anteriores = [0] * num_meses
        self.comissoes_anteriores = [0] * num_meses
        self.contas_pagar_anteriores = [0] * num_meses
        self.desp_fixas_manuais = [0] * num_meses

    def calcular(self, dados):
        # Carregar e validar dados de entrada
        self.setup.update(dados.get('setup', {}))
        self.previsao_vendas = [float(v) for v in dados.get('previsao_vendas', [0]*self.num_meses)]
        self.contas_receber_anteriores = [float(v) for v in dados.get('contas_receber_anteriores', [0]*self.num_meses)]
        self.comissoes_anteriores = [float(v) for v in dados.get('comissoes_anteriores', [0]*self.num_meses)]
        self.contas_pagar_anteriores = [float(v) for v in dados.get('contas_pagar_anteriores', [0]*self.num_meses)]
        self.desp_fixas_manuais = [float(v) for v in dados.get('desp_fixas_manuais', [0]*self.num_meses)]

        # --- Cálculos ---
        # (A lógica interna dos cálculos permanece a mesma, pois já estava correta)
        plus = float(self.setup['plus_vendas'])
        self.vendas_escalonadas = [v * (1 + plus) for v in self.previsao_vendas]
        
        n_parcelas_vendas = int(self.setup['vendas_parcelamento'])
        self.vendas_vista = [v * float(self.setup['vendas_vista']) for v in self.vendas_escalonadas]
        
        self.duplicatas_receber = [[0] * self.num_meses for _ in range(n_parcelas_vendas)]
        for mes, venda in enumerate(self.vendas_escalonadas):
            valor_parcelado = (venda - self.vendas_vista[mes]) / n_parcelas_vendas if n_parcelas_vendas > 0 else 0
            for p_idx in range(n_parcelas_vendas):
                if mes + p_idx < self.num_meses:
                    self.duplicatas_receber[p_idx][mes + p_idx] += valor_parcelado

        self.comissoes_mes = [v * float(self.setup['comissoes']) for v in self.vendas_escalonadas]
        n_parcelas_comissoes = 4
        self.comissoes_pagar = [[0] * self.num_meses for _ in range(n_parcelas_comissoes)]
        for mes, comissao in enumerate(self.comissoes_mes):
            valor_parcelado = comissao / n_parcelas_comissoes if n_parcelas_comissoes > 0 else 0
            for p_idx in range(n_parcelas_comissoes):
                if mes + p_idx < self.num_meses:
                    self.comissoes_pagar[p_idx][mes + p_idx] += valor_parcelado
        
        self.total_comissoes = [self.comissoes_anteriores[m] + sum(self.comissoes_pagar[p][m] for p in range(n_parcelas_comissoes)) for m in range(self.num_meses)]

        self.compras_planejadas = [v * float(self.setup['cmv']) * float(self.setup['percent_compras']) for v in self.vendas_escalonadas]
        self.compras_vista = [c * float(self.setup['compras_vista']) for c in self.compras_planejadas]
        
        n_parcelas_compras = int(self.setup['compras_parcelamento'])
        self.duplicatas_pagar = [[0] * self.num_meses for _ in range(n_parcelas_compras)]
        for mes, compra in enumerate(self.compras_planejadas):
            valor_parcelado = (compra - self.compras_vista[mes]) / n_parcelas_compras if n_parcelas_compras > 0 else 0
            for p_idx in range(n_parcelas_compras):
                if mes + p_idx < self.num_meses:
                    self.duplicatas_pagar[p_idx][mes + p_idx] += valor_parcelado

        self.total_pagamento_compras = [self.compras_vista[m] + self.contas_pagar_anteriores[m] + sum(self.duplicatas_pagar[p][m] for p in range(n_parcelas_compras)) for m in range(self.num_meses)]
        
        self.desp_variaveis = [v * float(self.setup['desp_variaveis_impostos']) for v in self.vendas_escalonadas]
        self.desp_fixas = self.desp_fixas_manuais

        self.saldo_operacional = []
        for m in range(self.num_meses):
            recebimentos = self.vendas_vista[m] + self.contas_receber_anteriores[m] + sum(self.duplicatas_receber[p][m] for p in range(n_parcelas_vendas))
            despesas = self.total_comissoes[m] + self.total_pagamento_compras[m] + self.desp_variaveis[m] + self.desp_fixas[m]
            self.saldo_operacional.append(recebimentos - despesas)

        self.saldo_final_caixa = [0] * self.num_meses
        saldo_acumulado = 0
        for m in range(self.num_meses):
            saldo_acumulado += self.saldo_operacional[m]
            self.saldo_final_caixa[m] = saldo_acumulado
        
        return self.gerar_resultados()

    def gerar_resultados(self):
        meses_header = [f'Mês {i+1}' for i in range(self.num_meses)]
        
        # Totais para tabela e indicadores
        contas_receber_parcelado = [sum(p[m] for p in self.duplicatas_receber) for m in range(self.num_meses)]
        comissoes_pagas_vista = [v * float(self.setup['comissoes']) * 0.3 for v in self.vendas_escalonadas] # Exemplo, ajuste se a regra for outra
        comissoes_parceladas = [sum(p[m] for p in self.comissoes_pagar) for m in range(self.num_meses)]
        fornecedores_parcelados = [sum(p[m] for p in self.duplicatas_pagar) for m in range(self.num_meses)]
        
        total_recebimentos = sum(self.vendas_vista) + sum(contas_receber_parcelado) + sum(self.contas_receber_anteriores)
        total_despesas = sum(self.total_comissoes) + sum(self.total_pagamento_compras) + sum(self.desp_variaveis) + sum(self.desp_fixas)
        saldo_op_total = sum(self.saldo_operacional)

        # **CORREÇÃO CRÍTICA**: Retornar uma lista de listas para garantir a ordem no frontend
        def format_row(label, values):
            total = sum(values) if label not in ['SALDO FINAL DE CAIXA PREVISTO'] else (values[-1] if values else 0)
            return [label] + [f"R$ {v:,.0f}".replace(",", ".") for v in values] + [f"R$ {total:,.0f}".replace(",", ".")]

        resultados_ordenados = [
            format_row('Escalonamento das Vendas com Plus', self.vendas_escalonadas),
            [''], # Linha em branco
            format_row('Recebimento de vendas à vista', self.vendas_vista),
            format_row('Contas a receber Parcelado', contas_receber_parcelado),
            format_row('Contas a receber anteriores', self.contas_receber_anteriores),
            [''],
            format_row('Pagamento de comissões à vista', comissoes_pagas_vista),
            format_row('Comissões parceladas', comissoes_parceladas),
            format_row('Comissões a pagar anteriores', self.comissoes_anteriores),
            format_row('Total de Comissões a pagar', self.total_comissoes),
            [''],
            format_row('Compras à vista', self.compras_vista),
            format_row('Fornecedores Parcelados', fornecedores_parcelados),
            format_row('Total Pagamento de Fornecedores', self.total_pagamento_compras),
            [''],
            format_row('Despesas variáveis', self.desp_variaveis),
            format_row('Despesas fixas', self.desp_fixas),
            [''],
            format_row('SALDO OPERACIONAL', self.saldo_operacional),
            format_row('SALDO FINAL DE CAIXA PREVISTO', self.saldo_final_caixa)
        ]

        indicadores = {
            'Total de Vendas': f"R$ {sum(self.previsao_vendas):,.0f}".replace(",", "."),
            'Total de Recebimentos': f"R$ {total_recebimentos:,.0f}".replace(",", "."),
            'Total de Despesas': f"R$ {total_despesas:,.0f}".replace(",", "."),
            'Saldo Final Acumulado': f"R$ {self.saldo_final_caixa[-1]:,.0f}".replace(",", "."),
            'Margem Líquida': f"{(saldo_op_total / total_recebimentos * 100):.1f}%".replace(".", ",") if total_recebimentos > 0 else "0%"
        }
        
        dados_graficos = {
            'meses': meses_header,
            'saldo_final_caixa': self.saldo_final_caixa,
            'receitas': [self.vendas_vista[i] + contas_receber_parcelado[i] + self.contas_receber_anteriores[i] for i in range(self.num_meses)],
            'despesas': [self.total_comissoes[i] + self.total_pagamento_compras[i] + self.desp_variaveis[i] + self.desp_fixas[i] for i in range(self.num_meses)]
        }
        
        return {
            'resultados': resultados_ordenados,
            'indicadores': indicadores,
            'graficos': dados_graficos,
            'meses': meses_header + ['TOTAL']
        }

# --- Rotas da Aplicação ---
def validate_email(email):
    return re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email)

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = db.session.get(User, session['user_id']) # Usar db.session.get para busca por PK
    if not user:
        session.clear()
        return redirect(url_for('login'))
    if not user.has_active_subscription():
        return redirect(url_for('payment'))
    return render_template('calculadora.html', user_email=user.email)

# ... (As rotas de login, register, payment, etc. podem permanecer as mesmas)
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        if not email or not password:
            return render_template('login.html', error='Email e senha são obrigatórios')
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            session['user_id'] = user.id
            return redirect(url_for('index'))
        
        return render_template('login.html', error='Email ou senha inválidos')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        if not email or not password or not validate_email(email):
            return render_template('register.html', error='Email e senha válidos são obrigatórios')
        
        if User.query.filter_by(email=email).first():
            return render_template('register.html', error='Email já cadastrado')
        
        try:
            new_user = User(email=email)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            
            session['user_id'] = new_user.id
            return redirect(url_for('payment'))
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Erro no registro: {e}")
            return render_template('register.html', error='Erro ao criar conta. Tente novamente.')
    
    return render_template('register.html')

@app.route('/payment')
def payment():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('payment.html')

@app.route('/process_payment', methods=['POST'])
def process_payment():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Usuário não autenticado'}), 401
    
    user = db.session.get(User, session['user_id'])
    if not user:
        return jsonify({'success': False, 'message': 'Usuário não encontrado'}), 404
        
    try:
        user.add_subscription_days(30)
        db.session.commit()
        return jsonify({'success': True, 'redirect_url': url_for('index')})
    except Exception as e:
        db.session.rollback()
        logging.error(f"Erro no processamento de pagamento: {e}")
        return jsonify({'success': False, 'message': 'Erro no servidor ao processar pagamento'}), 500

@app.route('/subscription_info')
def subscription_info():
    if 'user_id' not in session:
        return jsonify({'active': False})
    
    user = db.session.get(User, session['user_id'])
    if not user:
        return jsonify({'active': False})
    
    return jsonify({
        'active': user.has_active_subscription(),
        'end_date': user.subscription_end.isoformat() if user.subscription_end else None,
        'email': user.email
    })

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/calcular', methods=['POST'])
def calcular_route(): # Renomeado para evitar conflito com a função `calcular` do JS
    if 'user_id' not in session:
        return jsonify({'error': 'Usuário não autenticado'}), 401
    
    user = db.session.get(User, session['user_id'])
    if not user or not user.has_active_subscription():
        return jsonify({'error': 'Assinatura inválida ou expirada', 'redirect_url': url_for('payment')}), 403
    
    try:
        dados = request.get_json()
        if not dados or 'previsao_vendas' not in dados:
            return jsonify({'error': 'Dados inválidos ou ausentes na requisição.'}), 400
        
        planejamento = PlanejamentoCaixa()
        resultados = planejamento.calcular(dados)
        return jsonify(resultados)
        
    except Exception as e:
        logging.error(f"Erro na rota /calcular: {e}", exc_info=True)
        return jsonify({'error': 'Ocorreu um erro interno ao processar o cálculo.'}), 500

# --- Execução e Comandos ---
# Este bloco só será executado quando você rodar 'python app.py' localmente.
# Em produção (Render/Gunicorn), este bloco é ignorado.
if __name__ == '__main__':
    with app.app_context():
        logging.info("🔄 Verificando e criando tabelas do banco de dados (se necessário)...")
        db.create_all()
        logging.info("✅ Tabelas prontas!")

    port = int(os.environ.get('PORT', 5000))
    # app.run() é para desenvolvimento. NUNCA use debug=True em produção.
    app.run(host='0.0.0.0', port=port, debug=False)
