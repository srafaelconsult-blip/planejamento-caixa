def gerar_resultados(self):
    meses = [f'Mês {i+1}' for i in range(self.num_meses)] + ['TOTAL']
    
    # Criar lista ordenada exatamente como solicitado
    resultados_ordenados = [
        ('Previsão das Vendas', self.previsao_vendas),
        ('', []),  # Linha em branco
        ('Escalonamento das Vendas com Plus', self.vendas_escalonadas),
        ('', []),  # Linha em branco
        ('Recebimento de vendas à vista', self.vendas_vista),
        ('', []),  # Linha em branco
    ]
    
    # Adicionar Contas a receber Parcelado
    n_parcelas = int(self.setup['vendas_parcelamento'])
    for p in range(n_parcelas):
        parcelas = []
        for mes in range(self.num_meses):
            parcelas.append(self.duplicatas_receber[p][mes])
        resultados_ordenados.append((f'{p+1}º mês duplicatas a receber', parcelas))
    
    resultados_ordenados.append(('', []))  # Linha em branco
    resultados_ordenados.append(('Contas a receber anteriores', self.contas_receber_anteriores))
    resultados_ordenados.append(('', []))  # Linha em branco
    
    # Comissões à vista
    comissoes_vista = [venda * self.setup['comissoes'] * 0.3 for venda in self.vendas_escalonadas]
    resultados_ordenados.append(('Pagamento de comissões à vista', comissoes_vista))
    resultados_ordenados.append(('', []))  # Linha em branco
    
    # Comissões parceladas
    n_parcelas_comissoes = 4
    for p in range(n_parcelas_comissoes):
        parcelas = []
        for mes in range(self.num_meses):
            parcelas.append(self.comissoes_pagar[p][mes])
        resultados_ordenados.append((f'{p+1}º mês comissões a pagar', parcelas))
    
    resultados_ordenados.append(('', []))  # Linha em branco
    resultados_ordenados.append(('Comissões a pagar anteriores', self.comissoes_anteriores))
    resultados_ordenados.append(('', []))  # Linha em branco
    resultados_ordenados.append(('Total de Comissões a pagar', self.total_comissoes))
    resultados_ordenados.append(('', []))  # Linha em branco
    
    resultados_ordenados.append(('Compras à vista', self.compras_vista))
    resultados_ordenados.append(('', []))  # Linha em branco
    
    # Fornecedores Parcelados
    n_parcelas_compras = int(self.setup['compras_parcelamento'])
    for p in range(n_parcelas_compras):
        parcelas = []
        for mes in range(self.num_meses):
            parcelas.append(self.duplicatas_pagar[p][mes])
        resultados_ordenados.append((f'{p+1}º mês fornecedores a pagar', parcelas))
    
    resultados_ordenados.append(('', []))  # Linha em branco
    resultados_ordenados.append(('Total Pagamento de Fornecedores', self.total_pagamento_compras))
    resultados_ordenados.append(('', []))  # Linha em branco
    
    resultados_ordenados.append(('Despesas variáveis', self.desp_variaveis))
    resultados_ordenados.append(('Despesas fixas', self.desp_fixas))
    resultados_ordenados.append(('', []))  # Linha em branco
    
    resultados_ordenados.append(('SALDO OPERACIONAL', self.saldo_operacional))
    resultados_ordenados.append(('SALDO FINAL DE CAIXA PREVISTO', self.saldo_final_caixa))
    
    # Formatando os resultados
    resultados_formatados = {}
    for key, values in resultados_ordenados:
        if key == '':
            # Linha em branco
            resultados_formatados[key] = [''] * (self.num_meses + 1)
        else:
            # Dados com valores
            if values:
                if key in ['SALDO FINAL DE CAIXA PREVISTO']:
                    # Para saldo final, mostrar apenas o último valor no total
                    total = values[-1] if values else 0
                else:
                    total = sum(values) if len(values) == self.num_meses else values[-1] if values else 0
                valores_formatados = [f"R$ {x:,.0f}" for x in values] + [f"R$ {total:,.0f}"]
            else:
                valores_formatados = [''] * (self.num_meses + 1)
            resultados_formatados[key] = valores_formatados
    
    indicadores = {
        'Total de Vendas': f"R$ {sum(self.previsao_vendas):,.0f}",
        'Total de Recebimentos': f"R$ {sum(self.total_recebimentos):,.0f}",
        'Total de Despesas': f"R$ {sum(self.total_comissoes) + sum(self.total_pagamento_compras) + sum(self.desp_variaveis) + sum(self.desp_fixas):,.0f}",
        'Saldo Final Acumulado': f"R$ {self.saldo_final_caixa[-1]:,.0f}",
        'Margem Líquida': f"{(sum(self.saldo_operacional) / sum(self.total_recebimentos)) * 100:.1f}%" if sum(self.total_recebimentos) > 0 else "0%"
    }
    
    dados_graficos = {
        'meses': [f'Mês {i+1}' for i in range(self.num_meses)],
        'saldo_final_caixa': self.saldo_final_caixa,
        'receitas': self.total_recebimentos,
        'despesas': [
            a + b + c + d for a, b, c, d in zip(
                self.total_comissoes, 
                self.total_pagamento_compras, 
                self.desp_variaveis, 
                self.desp_fixas
            )
        ]
    }
    
    return {
        'resultados': resultados_formatados,
        'indicadores': indicadores,
        'graficos': dados_graficos,
        'meses': meses
    }
