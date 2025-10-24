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
from collections import OrderedDict

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
            "cmv": 0.4480,
            "percent_compras": 0.2,
            "compras_vista": 0.2,
            "compras_parcelamento": 6,
            "desp_variaveis_impostos": 0.0613,
            "desp_variaveis_parcelamento": 0.1313
        }
        self.previsao_vendas = [0] * self.num_meses
        self.contas_receber_anteriores = [0] * self.num_meses
        self.contas_pagar_anteriores = [0] * self.num_meses
        self.desp_fixas_manuais = [0] * self.num_meses
        self.desp_variaveis_manuais = [0]
        self.venda_mes0 = 0  # Vendas do mês anterior
        self.saldo_caixa_mes0 = 0  # Saldo de caixa inicial (Mês 0)

    def calcular(self, dados):
        for key in self.setup:
            if key in dados.get("setup", {}):
                self.setup[key] = float(dados["setup"][key])

        # Obter venda_mes0 e saldo_caixa_mes0 dos dados recebidos
        if "venda_mes0" in dados:
            self.venda_mes0 = float(dados["venda_mes0"])
        else:
            self.venda_mes0 = 0

        if "saldo_caixa_mes0" in dados:
            self.saldo_caixa_mes0 = float(dados["saldo_caixa_mes0"])
        else:
            self.saldo_caixa_mes0 = 0

        if "previsao_vendas" in dados:
            self.previsao_vendas = [float(x) for x in dados["previsao_vendas"]]
        if "contas_receber_anteriores" in dados:
            self.contas_receber_anteriores = [float(x) for x in dados["contas_receber_anteriores"]]
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

        # CALCULAR CONTAS A RECEBER PARCELADO REFERENTE AO MÊS 1 COM BASE NO MÊS 0
        # Para o primeiro mês, usar venda_mes0 como base
        if self.venda_mes0 > 0:
            valor_parcelado_mes0 = (self.venda_mes0 - (self.venda_mes0 * self.setup["vendas_vista"])) / n_parcelas
            for parcela_idx in range(n_parcelas):
                mes_recebimento = parcela_idx  # Mês 0, 1, 2, ... (ajustado para índice 0-based)
                if mes_recebimento < self.num_meses:
                    self.duplicatas_receber[parcela_idx][mes_recebimento] += valor_parcelado_mes0

        # Para os demais meses, usar as vendas escalonadas normalmente
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

        # 3. Planejamento de Compras - CÁLCULO CORRIGIDO
        # LINHA MÃE: Compras (CMV * % Compras sobre CMV)
        self.compras_totais = [0] * self.num_meses
        
        # CALCULAR COMPRAS REFERENTE AO MÊS 1 COM BASE NO MÊS 0
        # Para o primeiro mês, usar venda_mes0 como base
        if self.venda_mes0 > 0 and self.num_meses > 0:
            self.compras_totais[0] = self.venda_mes0 * self.setup["cmv"] * self.setup["percent_compras"]
        
        # Para os demais meses, usar as vendas do mês anterior normalmente
        for mes in range(1, self.num_meses):
            self.compras_totais[mes] = self.vendas_escalonadas[mes - 1] * self.setup["cmv"] * self.setup["percent_compras"]

        # LINHA FILHA: Fornecedores à Vista (Compras * % Compras a Vista)
        self.fornecedores_vista = [
            compra_total * self.setup["compras_vista"]
            for compra_total in self.compras_totais
        ]

        n_parcelas_compras = int(self.setup["compras_parcelamento"])
        self.duplicatas_pagar = [[0] * self.num_meses for _ in range(n_parcelas_compras)]

        # CALCULAR FORNECEDORES PARCELADOS REFERENTE AO MÊS 1 COM BASE NO MÊS 0
        # Para o primeiro mês, usar venda_mes0 como base
        if self.venda_mes0 > 0:
            compra_total_mes0 = self.venda_mes0 * self.setup["cmv"] * self.setup["percent_compras"]
            fornecedor_vista_mes0 = compra_total_mes0 * self.setup["compras_vista"]
            # Fornecedores Parcelados = (Compras totais - Fornecedores à vista) / N parcelas
            valor_parcelado_fornecedor_mes0 = (compra_total_mes0 - fornecedor_vista_mes0) / n_parcelas_compras
            for parcela_idx in range(n_parcelas_compras):
                mes_pagamento = parcela_idx  # Mês 0, 1, 2, ... (ajustado para índice 0-based)
                if mes_pagamento < self.num_meses:
                    self.duplicatas_pagar[parcela_idx][mes_pagamento] += valor_parcelado_fornecedor_mes0

        # Para os demais meses, usar as compras normalmente
        for mes in range(self.num_meses):
            # Fornecedores Parcelados = (Compras totais - Fornecedores à vista) / N parcelas
            valor_parcelado = (self.compras_totais[mes] - self.fornecedores_vista[mes]) / n_parcelas_compras
            for parcela_idx in range(n_parcelas_compras):
                mes_pagamento = mes + parcela_idx + 1
                if mes_pagamento < self.num_meses:
                    self.duplicatas_pagar[parcela_idx][mes_pagamento] += valor_parcelado

        self.total_pagamento_compras = []
        for mes in range(self.num_meses):
            total = self.fornecedores_vista[mes]
            for p in range(n_parcelas_compras):
                total += self.duplicatas_pagar[p][mes]
            total += self.contas_pagar_anteriores[mes]
            self.total_pagamento_compras.append(total)

        # 4.1 Despesas variáveis s/ Vendas
        self.desp_variaveis = [0] * self.num_meses
        
        # DESPESAS VARIÁVEIS REFERENTE AO MÊS 1 COM BASE NO MÊS 0
        # Para o primeiro mês, usar venda_mes0 como base
        if self.venda_mes0 > 0 and self.num_meses > 0:
            self.desp_variaveis[0] = self.venda_mes0 * self.setup["desp_variaveis_impostos"]
        
        # Se houver valor manual, substituir
        if self.desp_variaveis_manuais and self.desp_variaveis_manuais[0] > 0:
            self.desp_variaveis[0] = self.desp_variaveis_manuais[0]
        
        # Para os demais meses, usar as vendas do mês anterior normalmente
        for mes in range(1, self.num_meses):
            self.desp_variaveis[mes] = self.vendas_escalonadas[mes - 1] * self.setup["desp_variaveis_impostos"]

        # 4.2 NOVAS DESPESAS VARIÁVEIS S/ PARCELAMENTO DAS VENDAS
        percent_desp_var_parcelamento = self.setup["desp_variaveis_parcelamento"]
        n_parcelas_vendas = int(self.setup["vendas_parcelamento"])

        # 2.1) Despesas Variáveis à Vista (% Despesas variáveis s/ Parcelamento das Vendas * % Vendas a Vista)
        # CORREÇÃO: Considerar referência às vendas do mês atual
        self.desp_variaveis_vista = [
            venda * percent_desp_var_parcelamento * self.setup["vendas_vista"]
            for venda in self.vendas_escalonadas
        ]

        # 2.2) Despesas Variáveis Parceladas
        self.desp_variaveis_parceladas = [[0] * self.num_meses for _ in range(n_parcelas_vendas)]

        # Para o primeiro mês, usar venda_mes0 como base
        if self.venda_mes0 > 0:
            # CORREÇÃO: Usar venda_mes0 como referência para o mês anterior
            total_desp_var_mes0 = self.venda_mes0 * percent_desp_var_parcelamento
            desp_vista_mes0 = total_desp_var_mes0 * self.setup["vendas_vista"]
            valor_parcelado_desp_mes0 = (total_desp_var_mes0 - desp_vista_mes0) / n_parcelas_vendas
            for parcela_idx in range(n_parcelas_vendas):
                mes_pagamento = parcela_idx
                if mes_pagamento < self.num_meses:
                    self.desp_variaveis_parceladas[parcela_idx][mes_pagamento] += valor_parcelado_desp_mes0

        # Para os demais meses
        for mes in range(self.num_meses):
            # CORREÇÃO: Usar vendas do mês atual como referência
            total_desp_var_mes = self.vendas_escalonadas[mes] * percent_desp_var_parcelamento
            desp_vista_mes = total_desp_var_mes * self.setup["vendas_vista"]
            valor_parcelado_desp = (total_desp_var_mes - desp_vista_mes) / n_parcelas_vendas
            for parcela_idx in range(n_parcelas_vendas):
                mes_pagamento = mes + parcela_idx + 1
                if mes_pagamento < self.num_meses:
                    self.desp_variaveis_parceladas[parcela_idx][mes_pagamento] += valor_parcelado_desp

        # Total Despesas Variáveis Parceladas por mês
        self.total_desp_variaveis_parceladas = [0] * self.num_meses
        for p in range(n_parcelas_vendas):
            for mes in range(self.num_meses):
                self.total_desp_variaveis_parceladas[mes] += self.desp_variaveis_parceladas[p][mes]

        # 2.3) Total Despesas Variáveis s/ Parcelamento das Vendas
        self.total_desp_variaveis_parcelamento = [
            self.desp_variaveis_vista[i] + self.total_desp_variaveis_parceladas[i]
            for i in range(self.num_meses)
        ]

        # 5. Despesas fixas
        self.desp_fixas = self.desp_fixas_manuais

        # 6. Saldo operacional
        self.saldo_operacional = []
        for mes in range(self.num_meses):
            saldo = (self.total_recebimentos[mes] -
                     self.total_pagamento_compras[mes] -
                     self.desp_variaveis[mes] -
                     self.total_desp_variaveis_parcelamento[mes] -
                     self.desp_fixas[mes])
            self.saldo_operacional.append(saldo)

        # 7. Saldo final de caixa - COMEÇANDO COM SALDO MÊS 0
        self.saldo_final_caixa = [self.saldo_caixa_mes0 + self.saldo_operacional[0]]
        for mes in range(1, self.num_meses):
            self.saldo_final_caixa.append(self.saldo_final_caixa[-1] + self.saldo_operacional[mes])

        return self.gerar_resultados()

def gerar_resultados(self):
    meses = [f"Mês {i+1}" for i in range(self.num_meses)] + ["TOTAL"]

        # Calcular totais agrupados CORRETAMENTE
        n_parcelas_vendas = int(self.setup["vendas_parcelamento"])
        n_parcelas_compras = int(self.setup["compras_parcelamento"])

        # 1. CONTAS A RECEBER PARCELADO - Somar TODAS as parcelas (da 1ª à última)
        total_receber_parcelado = [0] * self.num_meses
        for p in range(n_parcelas_vendas):
            for mes in range(self.num_meses):
                total_receber_parcelado[mes] += self.duplicatas_receber[p][mes]
        
        # 2. FORNECEDORES PARCELADOS - Somar TODAS as parcelas (da 1ª à última)
        total_fornecedores_parcelados = [0] * self.num_meses
        for p in range(n_parcelas_compras):
            for mes in range(self.num_meses):
                total_fornecedores_parcelados[mes] += self.duplicatas_pagar[p][mes]

        # Calcular totais
        total_contas_receber = [
            self.vendas_vista[i] + total_receber_parcelado[i] + self.contas_receber_anteriores[i] 
            for i in range(self.num_meses)
        ]

        # Criar resultados na ordem EXATA solicitada usando OrderedDict
        resultados_ordenados = OrderedDict()
        
        # 1: PREVISÃO DE VENDAS
        resultados_ordenados["PREVISÃO DE VENDAS"] = [""] * (self.num_meses + 1)
        
        # 2: Recebimento de vendas à vista
        resultados_ordenados["Recebimento de vendas à vista"] = self.vendas_vista
        
        # 3: Contas a receber Parcelado (total) - TODAS as parcelas
        resultados_ordenados["Contas a receber Parcelado"] = total_receber_parcelado
        
        # 4: Contas a receber anteriores
        resultados_ordenados["Contas a receber anteriores"] = self.contas_receber_anteriores
        
        # 5: Total de Contas a Receber (negrito)
        resultados_ordenados["Total de Contas a Receber"] = total_contas_receber
        
        # 6: Despesas Variáveis à Vista
        resultados_ordenados["Despesas Variáveis s/ a receber à Vista"] = self.desp_variaveis_vista
        
        # 7: Despesas Variáveis Parceladas
        resultados_ordenados["Despesas Variáveis a receber Parcelados"] = self.total_desp_variaveis_parceladas
        
        # 8: Despesas variáveis s/ Parcelamento das Vendas
        resultados_ordenados["Total Despesas variáveis s/ Parcelamento das Vendas"] = self.total_desp_variaveis_parcelamento
        
        resultados_ordenados[""] = [""] * (self.num_meses + 1)
        
        # 9: LINHA MÃE: COMPRAS (CMV * % Compras sobre CMV)
        resultados_ordenados["Planejamento de Compras"] = self.compras_totais
        
        # 10: LINHA FILHA: FORNECEDORES À VISTA (Compras * % Compras a Vista)
        resultados_ordenados["Fornecedores à vista"] = self.fornecedores_vista
        
        # 11: Fornecedores Parcelados (total) - TODAS as parcelas
        resultados_ordenados["Fornecedores Parcelados"] = total_fornecedores_parcelados
        
        # 12: Fornecedores Anteriores
        resultados_ordenados["Contas a Pagar Anteriores"] = self.contas_pagar_anteriores
        
        # 13: Total Pagamento de Fornecedores (negrito)
        resultados_ordenados["Total Pagamento de Fornecedores e Contas a Pagar"] = self.total_pagamento_compras
        
        resultados_ordenados[""] = [""] * (self.num_meses + 1)
        
        # 14: Despesas variáveis s/ Vendas (negrito)
        resultados_ordenados["Despesas variáveis s/ Vendas"] = self.desp_variaveis
        
        # 15: Despesas fixas (negrito)
        resultados_ordenados["Despesas fixas"] = self.desp_fixas
        
        resultados_ordenados[""] = [""] * (self.num_meses + 1)
        
        # 16: SALDO OPERACIONAL (negrito)
        resultados_ordenados["SALDO OPERACIONAL"] = self.saldo_operacional

        # 17: SALDO FINAL DE CAIXA PREVISTO (negrito)
        resultados_ordenados["SALDO FINAL DE CAIXA PREVISTO"] = self.saldo_final_caixa

        # Formatar resultados
        resultados_formatados = OrderedDict()
        for key, values in resultados_ordenados.items():
            if key == "":
                resultados_formatados[key] = [""] * (self.num_meses + 1) + ["TOTAL"]
            else:
                if values and key != "PREVISÃO DE VENDAS":
                    total = sum(values) if len(values) == self.num_meses else values[-1]
                    valores_formatados = [f"R$ {x:,.0f}" for x in values] + [f"R$ {total:,.0f}"]
                else:
                    valores_formatados = [""] * (self.num_meses + 1)
                resultados_formatados[key] = valores_formatados

        indicadores = {
            "Total de Vendas": f"R$ {sum(self.previsao_vendas):,.0f}",
            "Total de Recebimentos": f"R$ {sum(self.total_recebimentos):,.0f}",
            "Total de Despesas": f"R$ {sum(self.total_pagamento_compras) + sum(self.desp_variaveis) + sum(self.desp_fixas) + sum(self.total_desp_variaveis_parcelamento):,.0f}",
            "Saldo Final Acumulado": f"R$ {self.saldo_final_caixa[-1]:,.0f}",
            "Margem de Fluxo de Caixa (Geração de Caixa / Vendas)": f"{(sum(self.saldo_operacional) / sum(self.previsao_vendas)) * 100:.1f}%" if sum(self.previsao_vendas) > 0 else "0%"
        }

        dados_graficos = {
            "meses": [f"Mês {i+1}" for i in range(self.num_meses)],
            "saldo_final_caixa": self.saldo_final_caixa,
            "receitas": self.total_recebimentos,
            "despesas": [
                a + b + c + d for a, b, c, d in zip(
                    self.total_pagamento_compras,
                    self.desp_variaveis,
                    self.total_desp_variaveis_parcelamento,
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








