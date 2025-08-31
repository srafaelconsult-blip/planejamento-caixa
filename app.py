import pandas as pd
import numpy as np
from flask import Flask, render_template, request, jsonify, session
import json
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-123')

class PlanejamentoCaixa:
    def __init__(self):
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
        
        self.previsao_vendas = [1200, 1100, 1200, 1100, 700]
        self.contas_receber_anteriores = [0, 0, 0, 0, 0]
        self.comissoes_anteriores = [0, 0, 0, 0, 0]
        self.contas_pagar_anteriores = [0, 0, 0, 0, 0]
        self.desp_fixas_manuais = [438, 438, 438, 438, 438]

    def calcular_tudo(self, dados_usuario):
        # Atualizar valores com dados do usuário
        for key in self.setup:
            if key in dados_usuario:
                self.setup[key] = float(dados_usuario[key])
        
        self.previsao_vendas = [float(x) for x in dados_usuario.get('previsao_vendas', self.previsao_vendas)]
        
        # Cálculos (mesma lógica anterior)
        plus = self.setup['plus_vendas']
        self.vendas_escalonadas = [
            venda * (1 + plus) if plus > 0 else venda
            for venda in self.previsao_vendas
        ]
        
        n_parcelas = int(self.setup['vendas_parcelamento'])
        self.vendas_vista = [venda * self.setup['vendas_vista'] for venda in self.vendas_escalonadas]
        
        self.duplicatas_receber = [[0] * 5 for _ in range(n_parcelas)]
        for mes in range(5):
            valor_parcelado = (self.vendas_escalonadas[mes] - self.vendas_vista[mes]) / n_parcelas
            for parcela_idx in range(n_parcelas):
                mes_recebimento = mes + parcela_idx
                if mes_recebimento < 5:
                    self.duplicatas_receber[parcela_idx][mes_recebimento] += valor_parcelado
        
        self.total_recebimentos = []
        for mes in range(5):
            total = self.vendas_vista[mes]
            for p in range(n_parcelas):
                total += self.duplicatas_receber[p][mes]
            total += self.contas_receber_anteriores[mes]
            self.total_recebimentos.append(total)
        
        # ... (restante dos cálculos)
        
        return self.gerar_resultados()

    def gerar_resultados(self):
        return {
            'vendas_escalonadas': self.vendas_escalonadas,
            'vendas_vista': self.vendas_vista,
            'total_recebimentos': self.total_recebimentos,
            'saldo_final_caixa': [sum(self.total_recebimentos[:i+1]) for i in range(5)]
        }

# Rotas Flask
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/calcular', methods=['POST'])
def calcular():
    try:
        dados = request.get_json()
        planejamento = PlanejamentoCaixa()
        resultados = planejamento.calcular_tudo(dados)
        return jsonify({'success': True, 'data': resultados})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('DEBUG', 'False').lower() == 'true')

