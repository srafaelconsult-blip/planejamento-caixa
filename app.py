import pandas as pd
import numpy as np
from flask import Flask, render_template, request, jsonify
import json

app = Flask(__name__)

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
        
        self.total_comissoes = []
        for mes in range(self.num_meses):
            total = self.comissoes_mes[mes] + self.comissoes_anteriores[mes]
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
        
        dados = {
            'Previsão Vendas': self.previsao_vendas + [sum(self.previsao_vendas)],
            'Vendas c/ Plus': self.vendas_escalonadas + [sum(self.vendas_escalonadas)],
            'Vendas à Vista': self.vendas_vista + [sum(self.vendas_vista)],
            'Contas Rec. Ant.': self.contas_receber_anteriores + [sum(self.contas_receber_anteriores)],
            'Total Recebimentos': self.total_recebimentos + [sum(self.total_recebimentos)],
            'Comissões Mês': self.comissoes_mes + [sum(self.comissoes_mes)],
            'Comissões Ant.': self.comissoes_anteriores + [sum(self.comissoes_anteriores)],
            'Total Comissões': self.total_comissoes + [sum(self.total_comissoes)],
            'Compras Planejadas': self.compras_planejadas + [sum(self.compras_planejadas)],
            'Compras à Vista': self.compras_vista + [sum(self.compras_vista)],
            'Contas Pagar Ant.': self.contas_pagar_anteriores + [sum(self.contas_pagar_anteriores)],
            'Total Pag. Compras': self.total_pagamento_compras + [sum(self.total_pagamento_compras)],
            'Desp. Variáveis': self.desp_variaveis + [sum(self.desp_variaveis)],
            'Desp. Fixas': self.desp_fixas + [sum(self.desp_fixas)],
            'Saldo Operacional': self.saldo_operacional + [sum(self.saldo_operacional)],
            'Saldo Final Caixa': self.saldo_final_caixa + [self.saldo_final_caixa[-1]]
        }
        
        # Adicionar parcelas de recebimento
        n_parcelas = int(self.setup['vendas_parcelamento'])
        for p in range(n_parcelas):
            parcelas = []
            for mes in range(self.num_meses):
                parcelas.append(self.duplicatas_receber[p][mes])
            dados[f'Parc. {p+1}º Mês Rec.'] = parcelas + [sum(parcelas)]
        
        # Adicionar parcelas de pagamento
        n_parcelas_compras = int(self.setup['compras_parcelamento'])
        for p in range(n_parcelas_compras):
            parcelas = []
            for mes in range(self.num_meses):
                parcelas.append(self.duplicatas_pagar[p][mes])
            dados[f'Parc. {p+1}º Mês Pag.'] = parcelas + [sum(parcelas)]
        
        # Formatar números para exibição
        resultados_formatados = {}
        for key, values in dados.items():
            resultados_formatados[key] = [f"{x:,.0f}" if isinstance(x, (int, float)) else x for x in values]
        
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

@app.route('/')
def index():
    return render_template('calculadora.html')

@app.route('/calcular', methods=['POST'])
def calcular():
    try:
        dados = request.get_json()
        planejamento = PlanejamentoCaixa()
        resultados = planejamento.calcular(dados)
        return jsonify(resultados)
    except Exception as e:
        return jsonify({'error': str(e)}), 400

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
