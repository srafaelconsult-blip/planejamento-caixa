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
import re

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-12345")

# Configuração do banco de dados
database_url = os.environ.get("DATABASE_URL")

if database_url:
    parsed_url = urlparse(database_url)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"postgresql+psycopg2://{parsed_url.username}:{parsed_url.password}@{parsed_url.hostname}:{parsed_url.port}{parsed_url.path}"
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
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
    def __init__(self, num_meses=6):
        self.num_meses = num_meses
        self.setup = {
            "vendas_vista": 0.3,
            "vendas_parcelamento": 5,
            "plus_vendas": 0,
            "cmv": 0.425,
            "percent_compras": 0.2,
            "compras_vista": 0.2,
            "compras_parcelamento": 6,
            "comissoes": 0.0761,
            "desp_variaveis_impostos": 0.085
        }
        self.previsao_vendas = [0] * self.num_meses
        self.contas_receber_anteriores = [0] * self.num_meses
        self.comissoes_anteriores = [0] * self.num_meses
        self.contas_pagar_anteriores = [0] * self.num_meses
        self.desp_fixas_manuais = [0] * self.num_meses
        self.desp_variaveis_manuais = [0]

    def calcular(self, dados):
        for key in self.setup:
            if key in dados.get("setup", {}):
                self.setup[key] = float(dados["setup"][key])

        if "previsao_vendas" in dados:
            self.previsao_vendas = [float(x) for x in dados["previsao_vendas"]]
        if "contas_receber_anteriores" in dados:
            self.contas_receber_anteriores = [float(x) for x in dados["contas_receber_anteriores"]]
        if "comissoes_anteriores" in dados:
            self.comissoes_anteriores = [float(x) for x in dados["comissoes_anteriores"]]
        if "contas_pagar_anteriores" in dados:
            self.contas_pagar_anteriores = [float(x) for x in dados["contas_pagar_anteriores"]]
        if "desp_fixas_manuais" in dados:
            self.desp_fixas_manuais = [float(x) for x in dados["desp_fixas_manuais"]]
        if "desp_variaveis_manuais" in dados:
            self.desp_variaveis_manuais = [float(x) for x in dados["desp_variaveis_manuais"][:1]]

        # 1. Escalonamento das Vendas com Plus
        plus = self.setup["plus_vendas"]
        self.vendas_escalonadas = [
            venda * (1 + plus) if plus > 0 else venda
            for venda in self.previsao_vendas
        ]

        # 2. Fluxo de recebimentos
        n_parcelas = int(self.setup["vendas_parcelamento"])
        self.vendas_vista = [
            venda * self.setup["vendas_vista"]
            for venda in self.vendas_escalonadas
        ]

        self.duplicatas_receber = [[0] * self.num_meses for _ in range(n_parcelas)]

        for mes in range(self.num_meses):
            valor_parcelado = (self.vendas_escalonadas[mes] - self.vendas_vista[mes]) / n_parcelas
            for parcela_idx in range(n_parcelas):
                mes_recebimento = mes + parcela_idx + 1
                if mes_recebimento < self.num_meses:
                    self.duplicatas_receber[parcela_idx][mes_recebimento] += valor_parcelado

        self.total_recebimentos = []
        for mes in range(self.num_meses):
            total = self.vendas_vista[mes]
            for p in range(n_parcelas):
                total += self.duplicatas_receber[p][mes]
            total += self.contas_receber_anteriores[mes]
            self.total_recebimentos.append(total)

        # 3. Comissões
        self.comissoes_mes = [
            venda * self.setup["comissoes"]
            for venda in self.vendas_escalonadas
        ]

        n_parcelas_comissoes = 4
        self.comissoes_pagar = [[0] * self.num_meses for _ in range(n_parcelas_comissoes)]

        for mes in range(self.num_meses):
            valor_comissao = self.comissoes_mes[mes]
            valor_parcelado = valor_comissao / n_parcelas_comissoes
            for parcela_idx in range(n_parcelas_comissoes):
                mes_pagamento = mes + parcela_idx + 1
                if mes_pagamento < self.num_meses:
                    self.comissoes_pagar[parcela_idx][mes_pagamento] += valor_parcelado

        self.total_comissoes = []
        for mes in range(self.num_meses):
            total = self.comissoes_anteriores[mes]
            for p in range(n_parcelas_comissoes):
                total += self.comissoes_pagar[p][mes]
            self.total_comissoes.append(total)

        # 4. Planejamento de Compras
        self.compras_planejadas = [
            venda * self.setup["cmv"] * self.setup["percent_compras"]
            for venda in self.vendas_escalonadas
        ]

        self.compras_vista = [
            compra * self.setup["compras_vista"]
            for compra in self.compras_planejadas
        ]

        n_parcelas_compras = int(self.setup["compras_parcelamento"])
        self.duplicatas_pagar = [[0] * self.num_meses for _ in range(n_parcelas_compras)]

        for mes in range(self.num_meses):
            valor_parcelado = (self.compras_planejadas[mes] - self.compras_vista[mes]) / n_parcelas_compras
            for parcela_idx in range(n_parcelas_compras):
                mes_pagamento = mes + parcela_idx + 1
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
        self.desp_variaveis = [0] * self.num_meses
        if self.desp_variaveis_manuais:
            self.desp_variaveis[0] = self.desp_variaveis_manuais[0]
        for mes in range(1, self.num_meses):
            self.desp_variaveis[mes] = self.vendas_escalonadas[mes - 1] * self.setup["desp_variaveis_impostos"]

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
        meses = [f"Mês {i+1}" for i in range(self.num_meses)] + ["TOTAL"]

        # 1. Recebimento de vendas à vista
        resultados_ordenados = [
            ("Recebimento de vendas à vista", self.vendas_vista),
            ("", []),
        ]

        # 2. Contas a receber Parcelado (somar todos e mostrar total por mês)
        total_receber_parcelado = [0] * self.num_meses
        n_parcelas_vendas = int(self.setup["vendas_parcelamento"])
        for p in range(n_parcelas_vendas):
            for mes in range(self.num_meses):
                total_receber_parcelado[mes] += self.duplicatas_receber[p][mes]
        
        resultados_ordenados.append(("Contas a receber Parcelado", total_receber_parcelado))
        resultados_ordenados.append(("", []))

        # 3. Contas a receber anteriores
        resultados_ordenados.append(("Contas a receber anteriores", self.contas_receber_anteriores))
        resultados_ordenados.append(("", []))

        # 4. Pagamento de comissões à vista
        comissoes_vista = [self.comissoes_mes[mes] / 4 for mes in range(self.num_meses)]
        resultados_ordenados.append(("Pagamento de comissões à vista", comissoes_vista))
        resultados_ordenados.append(("", []))

        # 5. Comissões parceladas (somar todas e mostrar total por mês)
        total_comissoes_parceladas = [0] * self.num_meses
        n_parcelas_comissoes = 4
        for p in range(1, n_parcelas_comissoes):  # Começa de 1 para pular a parcela à vista
            for mes in range(self.num_meses):
                total_comissoes_parceladas[mes] += self.comissoes_pagar[p][mes]
        
        resultados_ordenados.append(("Comissões parceladas", total_comissoes_parceladas))
        resultados_ordenados.append(("", []))

        # 6. Comissões a pagar anteriores
        resultados_ordenados.append(("Comissões a pagar anteriores", self.comissoes_anteriores))
        resultados_ordenados.append(("", []))

        # 7. Total de Comissões a pagar
        resultados_ordenados.append(("Total de Comissões a pagar", self.total_comissoes))
        resultados_ordenados.append(("", []))

        # 8. Compras à vista
        resultados_ordenados.append(("Compras à vista", self.compras_vista))
        resultados_ordenados.append(("", []))

        # 9. Fornecedores Parcelados (somar todos e mostrar total por mês)
        total_fornecedores_parcelados = [0] * self.num_meses
        n_parcelas_compras = int(self.setup["compras_parcelamento"])
        for p in range(n_parcelas_compras):
            for mes in range(self.num_meses):
                total_fornecedores_parcelados[mes] += self.duplicatas_pagar[p][mes]
        
        resultados_ordenados.append(("Fornecedores Parcelados", total_fornecedores_parcelados))
        resultados_ordenados.append(("", []))

        # 10. Total Pagamento de Fornecedores
        resultados_ordenados.append(("Total Pagamento de Fornecedores", self.total_pagamento_compras))
        resultados_ordenados.append(("", []))

        # 11. Despesas variáveis
        resultados_ordenados.append(("Despesas variáveis", self.desp_variaveis))
        resultados_ordenados.append(("", []))

        # 12. Despesas fixas
        resultados_ordenados.append(("Despesas fixas", self.desp_fixas))
        resultados_ordenados.append(("", []))

        # 13. SALDO OPERACIONAL
        resultados_ordenados.append(("SALDO OPERACIONAL", self.saldo_operacional))
        resultados_ordenados.append(("", []))

        # 14. SALDO FINAL DE CAIXA PREVISTO
        resultados_ordenados.append(("SALDO FINAL DE CAIXA PREVISTO", self.saldo_final_caixa))

        # Formatar resultados
        resultados_formatados = {}
        for key, values in resultados_ordenados:
            if key == "":
                resultados_formatados[key] = [""] * (self.num_meses + 1)
            else:
                if values:
                    total = sum(values) if len(values) == self.num_meses else values[-1]
                    valores_formatados = [f"R$ {x:,.0f}" for x in values] + [f"R$ {total:,.0f}"]
                else:
                    valores_formatados = [""] * (self.num_meses + 1)
                resultados_formatados[key] = valores_formatados

        indicadores = {
            "Total de Vendas": f"R$ {sum(self.previsao_vendas):,.0f}",
            "Total de Recebimentos": f"R$ {sum(self.total_recebimentos):,.0f}",
            "Total de Despesas": f"R$ {sum(self.total_comissoes) + sum(self.total_pagamento_compras) + sum(self.desp_variaveis) + sum(self.desp_fixas):,.0f}",
            "Saldo Final Acumulado": f"R$ {self.saldo_final_caixa[-1]:,.0f}",
            "Margem Líquida": f"{(sum(self.saldo_operacional) / sum(self.total_recebimentos)) * 100:.1f}%" if sum(self.total_recebimentos) > 0 else "0%"
        }

        dados_graficos = {
            "meses": [f"Mês {i+1}" for i in range(self.num_meses)],
            "saldo_final_caixa": self.saldo_final_caixa,
            "receitas": self.total_recebimentos,
            "despesas": [
                a + b + c + d for a, b, c, d in zip(
                    self.total_comissoes,
                    self.total_pagamento_compras,
                    self.desp_variaveis,
                    self.desp_fixas
                )
            ]
        }

        return {
            "resultados": resultados_formatados,
            "indicadores": indicadores,
            "graficos": dados_graficos,
            "meses": meses
        }

def validate_email(email):
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None

@app.route("/")
def index():
    try:
        if "user_id" not in session:
            return redirect(url_for("login"))

        user = User.query.get(session["user_id"])
        if not user:
            session.pop("user_id", None)
            return redirect(url_for("login"))

        if not user.has_active_subscription():
            return redirect(url_for("payment"))

        return render_template("calculadora.html")

    except Exception as e:
        return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        if not email or not password:
            return render_template("login.html", error="Email e senha são obrigatórios")

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            session["user_id"] = user.id
            if user.has_active_subscription():
                return redirect(url_for("index"))
            else:
                return redirect(url_for("payment"))

        return render_template("login.html", error="Email ou senha inválidos")

    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        if not email or not password:
            return render_template("register.html", error="Email e senha são obrigatórios")

        if not validate_email(email):
            return render_template("register.html", error="Email inválido")

        if User.query.filter_by(email=email).first():
            return render_template("register.html", error="Email já cadastrado")

        try:
            password_hash = generate_password_hash(password)
            user = User(email=email, password_hash=password_hash)

            db.session.add(user)
            db.session.commit()

            session["user_id"] = user.id
            return redirect(url_for("payment"))

        except Exception as e:
            db.session.rollback()
            print(f"Erro durante o registro: {e}") # Adicionado para depuração
            return render_template("register.html", error=f"Erro ao criar conta: {str(e)}")

    return render_template("register.html")

@app.route("/payment")
def payment():
    if "user_id" not in session:
        return redirect(url_for("login"))
    user = User.query.get(session["user_id"])
    if not user:
        session.pop("user_id", None)
        return redirect(url_for("login"))
    return render_template("payment.html", user=user)

@app.route("/subscribe", methods=["POST"])
def subscribe():
    if "user_id" not in session:
        return jsonify({"success": False, "message": "Usuário não logado"}), 401
    user = User.query.get(session["user_id"])
    if not user:
        session.pop("user_id", None)
        return jsonify({"success": False, "message": "Usuário não encontrado"}), 404
    try:
        user.add_subscription_days(30) # Adiciona 30 dias de assinatura
        db.session.commit()
        return jsonify({"success": True, "message": "Assinatura ativada com sucesso!"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Erro ao ativar assinatura: {str(e)}"}), 500

@app.route("/subscription_info")
def subscription_info():
    if "user_id" not in session:
        return jsonify({"active": False, "end_date": None})
    user = User.query.get(session["user_id"])
    if not user:
        session.pop("user_id", None)
        return jsonify({"active": False, "end_date": None})
    return jsonify({"active": user.has_active_subscription(), "end_date": user.subscription_end.isoformat() if user.subscription_end else None})

@app.route("/user_info")
def user_info():
    if "user_id" not in session:
        return jsonify({"email": None})
    user = User.query.get(session["user_id"])
    if not user:
        session.pop("user_id", None)
        return jsonify({"email": None})
    return jsonify({"email": user.email})

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect(url_for("login"))

@app.route("/calcular", methods=["POST"])
def calcular_projecao():
    try:
        if "user_id" not in session:
            return jsonify({"error": "Usuário não autenticado."}), 401
        user = User.query.get(session["user_id"])
        if not user or not user.has_active_subscription():
            return jsonify({"error": "Assinatura inativa ou inválida."}), 403

        dados = request.get_json()
        planejamento = PlanejamentoCaixa()
        resultados = planejamento.calcular(dados)
        return jsonify(resultados)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# Criar tabelas do banco de dados
print("🔄 Criando tabelas do banco de dados...")
with app.app_context():
    db.create_all()
    print("✅ Tabelas criadas com sucesso!")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
