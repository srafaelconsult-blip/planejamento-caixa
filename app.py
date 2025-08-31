from flask import Flask, render_template, request, jsonify
import pandas as pd
import numpy as np
import json
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-123')

class PlanejamentoCaixa:
    def __init__(self):
        # Valores iniciais dos SETUPS (células em vermelho)
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
        
        # Previsão de vendas inicial (células em verde)
        self.previsao_vendas = [1200, 1100, 1200, 1100, 700]
        
        # Valores manuais para os campos adicionais
        self.contas_receber_anteriores = [0, 0, 0, 0, 0]
        self.comissoes_anteriores = [0, 0, 0, 0, 0]
        self.contas_pagar_anteriores = [0, 0, 0, 0, 0]
        self.desp_fixas_manuais = [438, 438, 438, 438, 438]

    def calcular_tudo(self, dados_usuario):
        try:
            # Atualizar valores com dados do usuário
            for key in self.setup:
                if key in dados_usuario:
                    self.setup[key] = float(dados_usuario[key])
            
            if 'previsao_vendas' in dados_usuario:
                self.previsao_vendas = [float(x) for x in dados_usuario['previsao_vendas']]
            
            # Cálculos
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
            
            self.comissoes_mes = [venda * self.setup['comissoes'] for venda in self.vendas_escalonadas]
            self.total_comissoes = [self.comissoes_mes[i] + self.comissoes_anteriores[i] for i in range(5)]
            
            self.compras_planejadas = [venda * self.setup['cmv'] * self.setup['percent_compras'] for venda in self.vendas_escalonadas]
            self.compras_vista = [compra * self.setup['compras_vista'] for compra in self.compras_planejadas]
            
            n_parcelas_compras = int(self.setup['compras_parcelamento'])
            self.duplicatas_pagar = [[0] * 5 for _ in range(n_parcelas_compras)]
            for mes in range(5):
                valor_parcelado = (self.compras_planejadas[mes] - self.compras_vista[mes]) / n_parcelas_compras
                for parcela_idx in range(n_parcelas_compras):
                    mes_pagamento = mes + parcela_idx
                    if mes_pagamento < 5:
                        self.duplicatas_pagar[parcela_idx][mes_pagamento] += valor_parcelado
            
            self.total_pagamento_compras = []
            for mes in range(5):
                total = self.compras_vista[mes]
                for p in range(n_parcelas_compras):
                    total += self.duplicatas_pagar[p][mes]
                total += self.contas_pagar_anteriores[mes]
                self.total_pagamento_compras.append(total)
            
            self.desp_variaveis = [venda * self.setup['desp_variaveis_impostos'] for venda in self.vendas_escalonadas]
            self.desp_fixas = self.desp_fixas_manuais
            
            self.saldo_operacional = []
            for mes in range(5):
                saldo = (self.total_recebimentos[mes] - 
                        self.total_comissoes[mes] - 
                        self.total_pagamento_compras[mes] - 
                        self.desp_variaveis[mes] - 
                        self.desp_fixas[mes])
                self.saldo_operacional.append(saldo)
            
            self.saldo_final_caixa = [self.saldo_operacional[0]]
            for mes in range(1, 5):
                self.saldo_final_caixa.append(self.saldo_final_caixa[-1] + self.saldo_operacional[mes])
            
            return self.gerar_resultados()
            
        except Exception as e:
            raise Exception(f"Erro no cálculo: {str(e)}")

    def gerar_resultados(self):
        return {
            'vendas_escalonadas': self.vendas_escalonadas,
            'vendas_vista': self.vendas_vista,
            'total_recebimentos': self.total_recebimentos,
            'comissoes_mes': self.comissoes_mes,
            'total_comissoes': self.total_comissoes,
            'compras_planejadas': self.compras_planejadas,
            'compras_vista': self.compras_vista,
            'total_pagamento_compras': self.total_pagamento_compras,
            'desp_variaveis': self.desp_variaveis,
            'desp_fixas': self.desp_fixas,
            'saldo_operacional': self.saldo_operacional,
            'saldo_final_caixa': self.saldo_final_caixa,
            'duplicatas_receber': self.duplicatas_receber,
            'duplicatas_pagar': self.duplicatas_pagar
        }

# Rotas Flask
@app.route('/')
def index():
    return render_template('calculadora.html')

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
    return jsonify({
        'status': 'healthy', 
        'timestamp': datetime.now().isoformat(),
        'python_version': '3.11.x'
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)
