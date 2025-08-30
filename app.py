import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# Configuração básica
st.set_page_config(page_title="Planejamento de Caixa", layout="wide")
st.title("💰 Planejamento de Caixa")

# Entradas básicas
st.header("Configurações Básicas")
vendas = st.number_input("Previsão de Vendas Mensais (R$)", value=10000, step=1000)
margem = st.slider("Margem de Contribuição (%)", 0, 100, 30)
custos = st.number_input("Custos Fixos Mensais (R$)", value=3000, step=100)

# Cálculo simples
lucro = (vendas * margem / 100) - custos

# Resultados
st.header("Resultados")
st.metric("Lucro Mensal Estimado", f"R$ {lucro:,.2f}")

# Gráfico simples
if st.button("Gerar Projeção"):
    meses = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai']
    projecao = [vendas * (1 + i * 0.1) for i in range(5)]
    
    fig, ax = plt.subplots()
    ax.bar(meses, projecao)
    ax.set_ylabel('Vendas (R$)')
    st.pyplot(fig)

