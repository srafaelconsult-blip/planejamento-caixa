import os
import re
import logging
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-12345')

# --- Função de formatação de moeda robusta que não depende do 'locale' do servidor ---
def format_currency_brl(value):
    """Formata um número como moeda brasileira (R$ 1.234,56) de forma segura."""
    if not isinstance(value, (int, float)):
        return "R$ 0,00"
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# --- Configuração do Banco de Dados para Produção ---
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

if not database_url:
    logging.warning("DATABASE_URL não encontrado. Usando SQLite local.")
    database_url = 'sqlite:///users.db'

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_recycle': 280, 'pool_pre_ping': True}

db = SQLAlchemy(app)

# --- Modelos do Banco de Dados ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    subscription_end = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)
    def has_active_subscription(self): return self.subscription_end and self.subscription_end > datetime.utcnow()
    def add_subscription_days(self, days=30):
        if self.subscription_end and self.subscription_end > datetime.utcnow(): self.subscription_end += timedelta(days=days)
        else: self.subscription_end = datetime.utcnow() + timedelta(days=days)

# --- Lógica de Negócio ---
class PlanejamentoCaixa:
    def __init__(self, num_meses=5):
        self.num_meses = num_meses
        self.setup = {}
        self.previsao_vendas = [0.0] * num_meses
        self.contas_receber_anteriores = [0.0] * num_meses
        self.comissoes_anteriores = [0.0] * num_meses
        self.fornecedores_anteriores = [0.0] * num_meses
        self.desp_fixas_manuais = [0.0] * num_meses

    def calcular(self, dados):
        self.setup.update(dados.get('setup', {}))
        self.previsao_vendas = [float(v) for v in dados.get('previsao_vendas', [0]*self.num_meses)]
        self.contas_receber_anteriores = [float(v) for v in dados.get('contas_receber_anteriores', [0]*self.num_meses)]
        self.comissoes_anteriores = [float(v) for v in dados.get('comissoes_anteriores', [0]*self.num_meses)]
        self.fornecedores_anteriores = [float(v) for v in dados.get('fornecedores_anteriores', [0]*self.num_meses)]
        self.desp_fixas_manuais = [float(v) for v in dados.get('desp_fixas_manuais', [0]*self.num_meses)]

        plus = float(self.setup.get('plus_vendas', 0))
        self.vendas_escalonadas = [v * (1 + plus) for v in self.previsao_vendas]
        
        n_parcelas_vendas = int(self.setup.get('vendas_parcelamento', 1))
        self.vendas_vista = [v * float(self.setup.get('vendas_vista', 0)) for v in self.vendas_escalonadas]
        self.duplicatas_receber = [[0.0] * self.num_meses for _ in range(n_parcelas_vendas)]
        for mes, venda in enumerate(self.vendas_escalonadas):
            valor_parcela = (venda - self.vendas_vista[mes]) / n_parcelas_vendas if n_parcelas_vendas > 0 else 0
            for p_idx in range(n_parcelas_vendas):
                mes_recebimento = mes + p_idx + 1
                if mes_recebimento < self.num_meses: self.duplicatas_receber[p_idx][mes_recebimento] += valor_parcela

        self.comissoes_mes = [v * float(self.setup.get('comissoes', 0)) for v in self.vendas_escalonadas]
        self.comissoes_pagas_vista = [c * 0.3 for c in self.comissoes_mes]
        n_parcelas_comissoes = 4
        self.comissoes_pagar_parcelado = [[0.0] * self.num_meses for _ in range(n_parcelas_comissoes)]
        for mes, comissao in enumerate(self.comissoes_mes):
            valor_parcela = (comissao * 0.7) / n_parcelas_comissoes if n_parcelas_comissoes > 0 else 0
            for p_idx in range(n_parcelas_comissoes):
                mes_pagamento = mes + p_idx + 1
                if mes_pagamento < self.num_meses: self.comissoes_pagar_parcelado[p_idx][mes_pagamento] += valor_parcela
        
        comissoes_parceladas_mes = [sum(p[m] for p in self.comissoes_pagar_parcelado) for m in range(self.num_meses)]
        self.total_comissoes = [self.comissoes_pagas_vista[m] + comissoes_parceladas_mes[m] + self.comissoes_anteriores[m] for m in range(self.num_meses)]

        self.compras_planejadas = [v * float(self.setup.get('cmv', 0)) * float(self.setup.get('percent_compras', 0)) for v in self.vendas_escalonadas]
        self.compras_vista = [c * float(self.setup.get('compras_vista', 0)) for c in self.compras_planejadas]
        n_parcelas_compras = int(self.setup.get('compras_parcelamento', 1))
        self.duplicatas_pagar = [[0.0] * self.num_meses for _ in range(n_parcelas_compras)]
        for mes, compra in enumerate(self.compras_planejadas):
            valor_parcela = (compra - self.compras_vista[mes]) / n_parcelas_compras if n_parcelas_compras > 0 else 0
            for p_idx in range(n_parcelas_compras):
                mes_pagamento = mes + p_idx + 1
                if mes_pagamento < self.num_meses: self.duplicatas_pagar[p_idx][mes_pagamento] += valor_parcela

        self.total_pagamento_compras = [self.compras_vista[m] + sum(self.duplicatas_pagar[p][m] for p in range(n_parcelas_compras)) + self.fornecedores_anteriores[m] for m in range(self.num_meses)]
        
        self.desp_variaveis = [v * float(self.setup.get('desp_variaveis_impostos', 0)) for v in self.vendas_escalonadas]
        self.desp_fixas = self.desp_fixas_manuais

        self.saldo_operacional = []
        for m in range(self.num_meses):
            recebimentos = self.vendas_vista[m] + sum(self.duplicatas_receber[p][m] for p in range(n_parcelas_vendas)) + self.contas_receber_anteriores[m]
            despesas = self.total_comissoes[m] + self.total_pagamento_compras[m] + self.desp_variaveis[m] + self.desp_fixas[m]
            self.saldo_operacional.append(recebimentos - despesas)

        self.saldo_final_caixa = []
        saldo_acumulado = 0.0
        for saldo_mes in self.saldo_operacional:
            saldo_acumulado += saldo_mes
            self.saldo_final_caixa.append(saldo_acumulado)
        
        return self.gerar_resultados()

    def gerar_resultados(self):
        meses_header = [f'Mês {i+1}' for i in range(self.num_meses)]
        contas_receber_parcelado = [sum(p[m] for p in self.duplicatas_receber) for m in range(self.num_meses)]
        comissoes_parceladas = [sum(p[m] for p in self.comissoes_pagar_parcelado) for m in range(self.num_meses)]
        fornecedores_parcelados = [sum(p[m] for p in self.duplicatas_pagar) for m in range(self.num_meses)]
        
        def format_row(label, values):
            total = sum(values) if 'SALDO FINAL' not in label else (values[-1] if values else 0)
            return [label] + [format_currency_brl(v) for v in values] + [format_currency_brl(total)]

        resultados_ordenados = [
            format_row('Escalonamento das Vendas com Plus', self.vendas_escalonadas), [''],
            format_row('(+) Recebimento de vendas à vista', self.vendas_vista),
            format_row('(+) Contas a receber Parcelado', contas_receber_parcelado),
            format_row('(+) Contas a receber anteriores', self.contas_receber_anteriores), [''],
            format_row('(-) Pagamento de comissões à vista', self.comissoes_pagas_vista),
            format_row('(-) Comissões parceladas', comissoes_parceladas),
            format_row('(-) Comissões a pagar anteriores', self.comissoes_anteriores),
            format_row('(=) Total de Comissões a pagar', self.total_comissoes), [''],
            format_row('(-) Compras à vista', self.compras_vista),
            format_row('(-) Fornecedores Parcelados', fornecedores_parcelados),
            format_row('(-) Fornecedores a pagar anteriores', self.fornecedores_anteriores),
            format_row('(=) Total Pagamento de Fornecedores', self.total_pagamento_compras), [''],
            format_row('(-) Despesas variáveis', self.desp_variaveis),
            format_row('(-) Despesas fixas', self.desp_fixas), [''],
            format_row('(=) SALDO OPERACIONAL', self.saldo_operacional),
            format_row('(=) SALDO FINAL DE CAIXA PREVISTO', self.saldo_final_caixa)
        ]
        total_recebimentos = sum(self.vendas_vista) + sum(contas_receber_parcelado) + sum(self.contas_receber_anteriores)
        indicadores = {
            'Total de Vendas': format_currency_brl(sum(self.previsao_vendas)),
            'Total de Recebimentos': format_currency_brl(total_recebimentos),
            'Total de Despesas': format_currency_brl(sum(self.total_comissoes) + sum(self.total_pagamento_compras) + sum(self.desp_variaveis) + sum(self.desp_fixas)),
            'Saldo Final Acumulado': format_currency_brl(self.saldo_final_caixa[-1] if self.saldo_final_caixa else 0),
            'Margem Líquida': f"{(sum(self.saldo_operacional) / total_recebimentos * 100):.2f}%".replace(".", ",") if total_recebimentos > 0 else "0,00%"
        }
        dados_graficos = {
            'meses': meses_header,
            'saldo_final_caixa': self.saldo_final_caixa,
            'receitas': [self.vendas_vista[i] + contas_receber_parcelado[i] + self.contas_receber_anteriores[i] for i in range(self.num_meses)],
            'despesas': [self.total_comissoes[i] + self.total_pagamento_compras[i] + self.desp_variaveis[i] + self.desp_fixas[i] for i in range(self.num_meses)]
        }
        return { 'resultados': resultados_ordenados, 'indicadores': indicadores, 'graficos': dados_graficos, 'meses': meses_header + ['TOTAL'] }

# --- Rotas da Aplicação ---
@app.teardown_appcontext
def shutdown_session(exception=None):
    db.session.remove()

@app.route('/')
def index():
    if 'user_id' not in session: return redirect(url_for('login'))
    user = db.session.get(User, session['user_id'])
    if not user or not user.has_active_subscription():
        session.clear()
        return redirect(url_for('login'))
    return render_template('calculadora.html')

@app.route('/calcular', methods=['POST'])
def calcular_route():
    if 'user_id' not in session: return jsonify({'error': 'Não autenticado'}), 401
    user = db.session.get(User, session['user_id'])
    if not user or not user.has_active_subscription(): return jsonify({'error': 'Assinatura inválida', 'redirect_url': url_for('payment')}), 403
    try:
        dados = request.get_json()
        if not dados: return jsonify({'error': 'Requisição inválida.'}), 400
        planejamento = PlanejamentoCaixa()
        resultados = planejamento.calcular(dados)
        return jsonify(resultados)
    except Exception as e:
        logging.error(f"Erro na rota /calcular: {e}", exc_info=True)
        return jsonify({'error': 'Ocorreu um erro interno ao processar o cálculo.'}), 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
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
        if not email or not password or not re.match(r'[^@]+@[^@]+\.[^@]+', email):
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
            logging.error(f"Erro no registro: {e}", exc_info=True)
            return render_template('register.html', error='Erro ao criar conta. Tente novamente.')
    return render_template('register.html')

@app.route('/payment')
def payment():
    if 'user_id' not in session: return redirect(url_for('login'))
    return render_template('payment.html')

@app.route('/process_payment', methods=['POST'])
def process_payment():
    if 'user_id' not in session: return jsonify({'success': False}), 401
    user = db.session.get(User, session['user_id'])
    if not user: return jsonify({'success': False}), 404
    try:
        user.add_subscription_days(30)
        db.session.commit()
        return jsonify({'success': True, 'redirect_url': url_for('index')})
    except Exception as e:
        db.session.rollback()
        logging.error(f"Erro no pagamento: {e}", exc_info=True)
        return jsonify({'success': False}), 500

@app.route('/subscription_info')
def subscription_info():
    if 'user_id' not in session: return jsonify({'active': False})
    user = db.session.get(User, session['user_id'])
    if not user: return jsonify({'active': False})
    return jsonify({
        'active': user.has_active_subscription(),
        'end_date': user.subscription_end.isoformat() if user.subscription_end else None,
        'email': user.email
    })

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# Removido o db.create_all() do escopo de execução principal.
# if __name__ == '__main__':
#     port = int(os.environ.get('PORT', 5000))
#     app.run(host='0.0.0.0', port=port, debug=True)
