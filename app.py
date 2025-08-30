import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import json
import hashlib

# Configuração da página
st.set_page_config(page_title="Planejamento de Caixa Premium", layout="wide")

# Sistema de gerenciamento de usuários
class UserManager:
    def __init__(self):
        self.users_file = "users.json"
        self.load_users()
    
    def load_users(self):
        try:
            with open(self.users_file, 'r') as f:
                self.users = json.load(f)
        except:
            self.users = {}
    
    def save_users(self):
        with open(self.users_file, 'w') as f:
            json.dump(self.users, f)
    
    def create_user(self, email, password):
        user_id = hashlib.md5(email.encode()).hexdigest()
        
        if user_id in self.users:
            return False, "Usuário já existe"
        
        self.users[user_id] = {
            'email': email,
            'password': hashlib.md5(password.encode()).hexdigest(),
            'signup_date': datetime.now().isoformat(),
            'subscription_status': 'trial',
            'trial_end_date': (datetime.now() + timedelta(days=30)).isoformat(),
            'last_payment_date': None,
            'next_payment_date': None
        }
        self.save_users()
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
            self.save_users()
            return False, "Período de teste expirado. Por favor, assine o plano premium."
        
        if self.users[user_id]['subscription_status'] == 'expired':
            return False, "Assinatura expirada. Por favor, renove seu plano."
        
        return True, "Login bem-sucedido"
    
    def update_subscription(self, email, status):
        user_id = hashlib.md5(email.encode()).hexdigest()
        
        if user_id in self.users:
            self.users[user_id]['subscription_status'] = status
            if status == 'active':
                self.users[user_id]['last_payment_date'] = datetime.now().isoformat()
                self.users[user_id]['next_payment_date'] = (datetime.now() + timedelta(days=30)).isoformat()
            self.save_users()
            return True
        return False

# Inicializar gerenciador de usuários
user_manager = UserManager()

# Função para mostrar página de autenticação
def show_auth_page():
    st.title("💰 Planejamento de Caixa Premium")
    
    tab1, tab2 = st.tabs(["Login", "Cadastro"])
    
    with tab1:
        st.subheader("Acesse sua conta")
        email = st.text_input("E-mail", key="login_email")
        password = st.text_input("Senha", type="password", key="login_password")
        
        if st.button("Entrar", key="login_btn"):
            success, message = user_manager.verify_user(email, password)
            if success:
                st.session_state.authenticated = True
                st.session_state.user_email = email
                st.rerun()
            else:
                st.error(message)
    
    with tab2:
        st.subheader("Crie sua conta")
        new_email = st.text_input("E-mail", key="signup_email")
        new_password = st.text_input("Senha", type="password", key="signup_password")
        confirm_password = st.text_input("Confirmar Senha", type="password", key="confirm_password")
        
        if st.button("Criar Conta", key="signup_btn"):
            if new_password != confirm_password:
                st.error("As senhas não coincidem")
            else:
                success, message = user_manager.create_user(new_email, new_password)
                if success:
                    st.success(message)
                    st.info("Você pode fazer login agora com suas credenciais")
                else:
                    st.error(message)
    
    # Seção de assinatura
    st.markdown("---")
    st.subheader("📦 Planos de Assinatura")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.info("**Teste Grátis**")
        st.write("✅ 30 dias completos")
        st.write("✅ Todas as funcionalidades")
        st.write("⏰ Válido por 30 dias")
        st.write("💰 **R$ 0,00**")
    
    with col2:
        st.success("**Plano Mensal**")
        st.write("✅ Acesso completo")
        st.write("✅ Suporte prioritário")
        st.write("✅ Atualizações constantes")
        st.write("💰 **R$ 97,00/mês**")
        if st.button("Assinar Mensal", key="monthly_btn"):
            st.session_state.plan_type = "monthly"
            st.session_state.show_payment = True
    
    with col3:
        st.warning("**Plano Anual**")
        st.write("✅ Todos os benefícios")
        st.write("✅ 2 meses grátis")
        st.write("✅ Melhor custo-benefício")
        st.write("💰 **R$ 970,00/ano**")
        if st.button("Assinar Anual", key="annual_btn"):
            st.session_state.plan_type = "annual"
            st.session_state.show_payment = True
    
    # Seção de pagamento
    if st.session_state.get('show_payment', False):
        st.markdown("---")
        st.subheader("💳 Finalizar Assinatura")
        
        plan_type = st.session_state.plan_type
        plan_name = "Mensal (R$ 97,00)" if plan_type == "monthly" else "Anual (R$ 970,00)"
        
        st.write(f"Plano selecionado: **{plan_name}**")
        
        payment_method = st.radio("Forma de Pagamento:", ["PIX", "Cartão de Crédito", "Boleto Bancário"])
        
        if payment_method == "PIX":
            st.success("**Chave PIX: 123.456.789-00**")
            st.info("Após o pagamento, seu acesso será liberado em até 15 minutos")
        elif payment_method == "Cartão de Crédito":
            st.info("Pagamento recorrente mensal/anual no cartão")
        else:
            st.info("Boleto avecimento em 3 dias úteis")
        
        if st.button("Confirmar Pagamento", key="confirm_payment"):
            # Aqui você integraria com a API do gateway de pagamento
            # Por enquanto, vamos simular um pagamento bem-sucedido
            if 'user_email' in st.session_state:
                user_manager.update_subscription(st.session_state.user_email, 'active')
                st.success("Pagamento confirmado! Acesso liberado.")
                st.session_state.show_payment = False
                st.rerun()
            else:
                st.error("Faça login primeiro para finalizar a assinatura")

# Classe principal do Planejamento de Caixa adaptada para Streamlit
class PlanejamentoCaixaStreamlit:
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
        
        self.calcular_tudo()
    
    def criar_interface(self):
        st.title("📊 Planejamento de Caixa")
        
        tab1, tab2 = st.tabs(["Configurações", "Dados Manuais"])
        
        with tab1:
            st.header("Configurações (SETUP - células vermelhas)")
            
            # Sliders para configurações
            col1, col2 = st.columns(2)
            
            with col1:
                self.setup['vendas_vista'] = st.slider("Vendas Vista (%)", 0, 100, 30) / 100
                self.setup['plus_vendas'] = st.slider("Plus Vendas (%)", 0, 100, 0) / 100
                self.setup['cmv'] = st.slider("CMV (%)", 0, 100, 42) / 100
                self.setup['compras_vista'] = st.slider("Compras Vista (%)", 0, 100, 20) / 100
            
            with col2:
                self.setup['vendas_parcelamento'] = st.slider("Vendas Parcelamento (meses)", 1, 12, 5)
                self.setup['compras_parcelamento'] = st.slider("Compras Parcelamento (meses)", 1, 12, 6)
                self.setup['comissoes'] = st.slider("Comissões (%)", 0, 100, 7) / 100
                self.setup['desp_variaveis_impostos'] = st.slider("Desp. Variáveis/Impostos (%)", 0, 100, 8) / 100
            
            self.setup['percent_compras'] = st.slider("Percentual de Compras (%)", 0, 100, 20) / 100
            
            st.header("Previsão de Vendas (células verdes)")
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                self.previsao_vendas[0] = st.number_input("Mês 1", value=1200, step=100)
            with col2:
                self.previsao_vendas[1] = st.number_input("Mês 2", value=1100, step=100)
            with col3:
                self.previsao_vendas[2] = st.number_input("Mês 3", value=1200, step=100)
            with col4:
                self.previsao_vendas[3] = st.number_input("Mês 4", value=1100, step=100)
            with col5:
                self.previsao_vendas[4] = st.number_input("Mês 5", value=700, step=100)
        
        with tab2:
            st.header("Dados Manuais")
            
            st.subheader("Contas a Receber de Vendas Anteriores")
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                self.contas_receber_anteriores[0] = st.number_input("Mês 1 Rec.", value=0.0, step=100.0)
            with col2:
                self.contas_receber_anteriores[1] = st.number_input("Mês 2 Rec.", value=0.0, step=100.0)
            with col3:
                self.contas_receber_anteriores[2] = st.number_input("Mês 3 Rec.", value=0.0, step=100.0)
            with col4:
                self.contas_receber_anteriores[3] = st.number_input("Mês 4 Rec.", value=0.0, step=100.0)
            with col5:
                self.contas_receber_anteriores[4] = st.number_input("Mês 5 Rec.", value=0.0, step=100.0)
            
            st.subheader("Comissões Referente a Vendas Anteriores")
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                self.comissoes_anteriores[0] = st.number_input("Mês 1 Com.", value=0.0, step=100.0)
            with col2:
                self.comissoes_anteriores[1] = st.number_input("Mês 2 Com.", value=0.0, step=100.0)
            with col3:
                self.comissoes_anteriores[2] = st.number_input("Mês 3 Com.", value=0.0, step=100.0)
            with col4:
                self.comissoes_anteriores[3] = st.number_input("Mês 4 Com.", value=0.0, step=100.0)
            with col5:
                self.comissoes_anteriores[4] = st.number_input("Mês 5 Com.", value=0.0, step=100.0)
            
            st.subheader("Contas a Pagar de Compras Anteriores")
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                self.contas_pagar_anteriores[0] = st.number_input("Mês 1 Pag.", value=0.0, step=100.0)
            with col2:
                self.contas_pagar_anteriores[1] = st.number_input("Mês 2 Pag.", value=0.0, step=100.0)
            with col3:
                self.contas_pagar_anteriores[2] = st.number_input("Mês 3 Pag.", value=0.0, step=100.0)
            with col4:
                self.contas_pagar_anteriores[3] = st.number_input("Mês 4 Pag.", value=0.0, step=100.0)
            with col5:
                self.contas_pagar_anteriores[4] = st.number_input("Mês 5 Pag.", value=0.0, step=100.0)
            
            st.subheader("Despesas Fixas (por mês)")
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                self.desp_fixas_manuais[0] = st.number_input("Mês 1 Desp.", value=438.0, step=10.0)
            with col2:
                self.desp_fixas_manuais[1] = st.number_input("Mês 2 Desp.", value=438.0, step=10.0)
            with col3:
                self.desp_fixas_manuais[2] = st.number_input("Mês 3 Desp.", value=438.0, step=10.0)
            with col4:
                self.desp_fixas_manuais[3] = st.number_input("Mês 4 Desp.", value=438.0, step=10.0)
            with col5:
                self.desp_fixas_manuais[4] = st.number_input("Mês 5 Desp.", value=438.0, step=10.0)
        
        if st.button("Calcular", type="primary"):
            self.calcular_tudo()
            self.mostrar_resultados()
    
    def calcular_tudo(self):
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
        self.duplicatas_receber = [[0] * 5 for _ in range(n_parcelas)]
        
        for mes in range(5):
            valor_parcelado = (self.vendas_escalonadas[mes] - self.vendas_vista[mes]) / n_parcelas
            
            for parcela_idx in range(n_parcelas):
                mes_recebimento = mes + parcela_idx
                if mes_recebimento < 5:
                    self.duplicatas_receber[parcela_idx][mes_recebimento] += valor_parcelado
        
        # Total recebimentos
        self.total_recebimentos = []
        for mes in range(5):
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
        for mes in range(5):
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
        
        # Duplicatas a pagar
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
        
        # 5. Despesas variáveis
        self.desp_variaveis = [
            venda * self.setup['desp_variaveis_impostos'] 
            for venda in self.vendas_escalonadas
        ]
        
        # 6. Despesas fixas
        self.desp_fixas = self.desp_fixas_manuais
        
        # 7. Saldo operacional
        self.saldo_operacional = []
        for mes in range(5):
            saldo = (self.total_recebimentos[mes] - 
                    self.total_comissoes[mes] - 
                    self.total_pagamento_compras[mes] - 
                    self.desp_variaveis[mes] - 
                    self.desp_fixas[mes])
            self.saldo_operacional.append(saldo)
        
        # 8. Saldo final de caixa
        self.saldo_final_caixa = [self.saldo_operacional[0]]
        for mes in range(1, 5):
            self.saldo_final_caixa.append(self.saldo_final_caixa[-1] + self.saldo_operacional[mes])
    
    def mostrar_resultados(self):
        st.success("Cálculo realizado com sucesso!")
        
        # Criar DataFrame com resultados
        meses = ['Mês 1', 'Mês 2', 'Mês 3', 'Mês 4', 'Mês 5', 'TOTAL']
        
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
            for mes in range(5):
                parcelas.append(self.duplicatas_receber[p][mes])
            dados[f'Parc. {p+1}º Mês Rec.'] = parcelas + [sum(parcelas)]
        
        # Adicionar parcelas de pagamento
        n_parcelas_compras = int(self.setup['compras_parcelamento'])
        for p in range(n_parcelas_compras):
            parcelas = []
            for mes in range(5):
                parcelas.append(self.duplicatas_pagar[p][mes])
            dados[f'Parc. {p+1}º Mês Pag.'] = parcelas + [sum(parcelas)]
        
        # Criar DataFrame
        df = pd.DataFrame(dados, index=meses)
        
        # Formatar valores monetários
        for col in df.columns:
            df[col] = df[col].apply(lambda x: f"R$ {x:,.2f}" if isinstance(x, (int, float)) else x)
        
        st.subheader("Resultados do Planejamento de Caixa")
        st.dataframe(df.T, use_container_width=True)
        
        # Gráficos
        st.subheader("Visualizações Gráficas")
        
        col1, col2 = st.columns(2)
        
        with col1:
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.plot(range(1, 6), self.saldo_final_caixa, marker='o', linewidth=2, markersize=8, color='blue')
            ax.set_xlabel('Meses')
            ax.set_ylabel('Saldo (R$)')
            ax.set_title('Evolução do Saldo de Caixa')
            ax.grid(True, alpha=0.3)
            ax.axhline(y=0, color='r', linestyle='--', alpha=0.7)
            st.pyplot(fig)
        
        with col2:
            fig, ax = plt.subplots(figsize=(10, 6))
            width = 0.35
            x = np.arange(5)
            ax.bar(x - width/2, self.total_recebimentos, width, label='Receitas', alpha=0.7)
            ax.bar(x + width/2, [a+b+c+d for a,b,c,d in zip(self.total_comissoes, self.total_pagamento_compras, 
                                                           self.desp_variaveis, self.desp_fixas)], 
                    width, label='Despesas', alpha=0.7)
            ax.set_xlabel('Meses')
            ax.set_ylabel('Valor (R$)')
            ax.set_title('Receitas vs Despesas por Mês')
            ax.set_xticks(x)
            ax.set_xticklabels(['Mês 1', 'Mês 2', 'Mês 3', 'Mês 4', 'Mês 5'])
            ax.legend()
            ax.grid(True, alpha=0.3)
            st.pyplot(fig)
        
        # Indicadores financeiros
        st.subheader("Indicadores Financeiros")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total de Vendas", f"R$ {sum(self.previsao_vendas):,.2f}")
        with col2:
            st.metric("Total de Recebimentos", f"R$ {sum(self.total_recebimentos):,.2f}")
        with col3:
            st.metric("Total de Despesas", f"R$ {sum(self.total_comissoes) + sum(self.total_pagamento_compras) + sum(self.desp_variaveis) + sum(self.desp_fixas):,.2f}")
        with col4:
            st.metric("Saldo Final", f"R$ {self.saldo_final_caixa[-1]:,.2f}")
        
        margem = (sum(self.saldo_operacional) / sum(self.total_recebimentos)) * 100 if sum(self.total_recebimentos) > 0 else 0
        st.metric("Margem Líquida", f"{margem:.1f}%")

# Aplicação principal
def main():
    # Inicializar estado da sessão
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    if 'show_payment' not in st.session_state:
        st.session_state.show_payment = False
    
    # Verificar autenticação
    if not st.session_state.authenticated:
        show_auth_page()
    else:
        # Barra lateral com informações do usuário
        with st.sidebar:
            st.title(f"Olá, {st.session_state.user_email}")
            
            # Verificar status da assinatura
            user_id = hashlib.md5(st.session_state.user_email.encode()).hexdigest()
            user_data = user_manager.users.get(user_id, {})
            
            if user_data.get('subscription_status') == 'trial':
                trial_end = datetime.fromisoformat(user_data['trial_end_date'])
                days_left = (trial_end - datetime.now()).days
                st.info(f"📅 Período de teste: {days_left} dias restantes")
                
                if st.button("Assinar Agora"):
                    st.session_state.show_payment = True
                    st.rerun()
            
            elif user_data.get('subscription_status') == 'active':
                next_payment = datetime.fromisoformat(user_data['next_payment_date'])
                st.success(f"✅ Assinatura ativa até {next_payment.strftime('%d/%m/%Y')}")
            
            elif user_data.get('subscription_status') == 'expired':
                st.error("❌ Assinatura expirada")
                if st.button("Renovar Assinatura"):
                    st.session_state.show_payment = True
                    st.rerun()
            
            if st.button("Sair"):
                st.session_state.authenticated = False
                st.session_state.user_email = None
                st.rerun()
        
        # Mostrar página de pagamento se necessário
        if st.session_state.show_payment:
            show_auth_page()
        else:
            # Mostrar aplicação principal
            app = PlanejamentoCaixaStreamlit()
            app.criar_interface()

if __name__ == "__main__":
    main()