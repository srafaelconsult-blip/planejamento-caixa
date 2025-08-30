import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import json
import hashlib

# Configuração da página
st.set_page_config(page_title="Planejamento de Caixa Premium", layout="wide")

# Sistema simplificado de usuários (apenas para demo)
users = {}

def show_auth_page():
    st.title("💰 Planejamento de Caixa Premium")
    
    tab1, tab2 = st.tabs(["Login", "Cadastro"])
    
    with tab1:
        st.subheader("Acesse sua conta")
        email = st.text_input("E-mail", key="login_email")
        password = st.text_input("Senha", type="password", key="login_password")
        
        if st.button("Entrar", key="login_btn"):
            if email in users and users[email]['password'] == password:
                st.session_state.authenticated = True
                st.session_state.user_email = email
                st.rerun()
            else:
                st.error("Credenciais inválidas")
    
    with tab2:
        st.subheader("Crie sua conta")
        new_email = st.text_input("E-mail", key="signup_email")
        new_password = st.text_input("Senha", type="password", key="signup_password")
        confirm_password = st.text_input("Confirmar Senha", type="password", key="confirm_password")
        
        if st.button("Criar Conta", key="signup_btn"):
            if new_password != confirm_password:
                st.error("As senhas não coincidem")
            elif new_email in users:
                st.error("Usuário já existe")
            else:
                users[new_email] = {
                    'password': new_password,
                    'signup_date': datetime.now(),
                    'subscription_status': 'trial'
                }
                st.success("Conta criada com sucesso! Faça login.")
    
    # Seção de assinatura
    st.markdown("---")
    st.subheader("📦 Planos de Assinatura")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.info("**Teste Grátis**")
        st.write("✅ 30 dias completos")
        st.write("✅ Todas as funcionalidades")
        st.write("💰 **R$ 0,00**")
    
    with col2:
        st.success("**Plano Premium**")
        st.write("✅ Acesso completo")
        st.write("✅ Suporte prioritário")
        st.write("💰 **R$ 97,00/mês**")
        if st.button("Assinar Agora", key="signup_btn"):
            st.info("Sistema de pagamento em desenvolvimento")

# Classe principal simplificada
class PlanejamentoCaixaStreamlit:
    def __init__(self):
        self.setup = {
            'vendas_vista': 0.3,
            'vendas_parcelamento': 5,
            'cmv': 0.425,
            'compras_vista': 0.2,
            'compras_parcelamento': 6,
            'comissoes': 0.0761,
        }
        self.previsao_vendas = [1200, 1100, 1200, 1100, 700]
        
    def criar_interface(self):
        st.title("📊 Planejamento de Caixa - Versão Demo")
        
        # Configurações básicas
        st.header("Configurações")
        col1, col2 = st.columns(2)
        
        with col1:
            self.setup['vendas_vista'] = st.slider("Vendas à Vista (%)", 0, 100, 30) / 100
            self.setup['cmv'] = st.slider("CMV (%)", 0, 100, 42) / 100
        
        with col2:
            self.setup['vendas_parcelamento'] = st.slider("Parcelamento Vendas (meses)", 1, 12, 5)
            self.setup['comissoes'] = st.slider("Comissões (%)", 0, 100, 7) / 100
        
        st.header("Previsão de Vendas")
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
        
        if st.button("Calcular", type="primary"):
            self.mostrar_resultados()
    
    def mostrar_resultados(self):
        st.success("Cálculo realizado!")
        
        # Cálculos simplificados
        total_vendas = sum(self.previsao_vendas)
        vendas_vista = total_vendas * self.setup['vendas_vista']
        custos = total_vendas * self.setup['cmv']
        comissoes = total_vendas * self.setup['comissoes']
        saldo = vendas_vista - custos - comissoes
        
        # Resultados
        st.subheader("Resultados")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Vendas", f"R$ {total_vendas:,.2f}")
        with col2:
            st.metric("Vendas à Vista", f"R$ {vendas_vista:,.2f}")
        with col3:
            st.metric("Custos", f"R$ {custos:,.2f}")
        with col4:
            st.metric("Saldo", f"R$ {saldo:,.2f}")
        
        # Gráfico simples
        st.subheader("Projeção de Vendas")
        fig, ax = plt.subplots()
        ax.plot(range(1, 6), self.previsao_vendas, marker='o')
        ax.set_xlabel('Meses')
        ax.set_ylabel('Vendas (R$)')
        ax.grid(True, alpha=0.3)
        st.pyplot(fig)

# Aplicação principal
def main():
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    
    if not st.session_state.authenticated:
        show_auth_page()
    else:
        st.sidebar.success(f"Logado como: {st.session_state.user_email}")
        if st.sidebar.button("Sair"):
            st.session_state.authenticated = False
            st.rerun()
        
        app = PlanejamentoCaixaStreamlit()
        app.criar_interface()

if __name__ == "__main__":
    main()
