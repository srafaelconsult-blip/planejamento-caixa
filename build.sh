#!/bin/bash
echo "Verificando versão do Python..."
python --version

echo "Instalando dependências..."
pip install --upgrade pip
pip install -r requirements.txt

echo "Build concluído!"
