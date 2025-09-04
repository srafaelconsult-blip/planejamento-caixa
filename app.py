@app.route('/calcular', methods=['POST'])
def calcular():
    if 'user_id' not in session:
        return jsonify({'error': 'Usuário não autenticado'}), 401
    
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'error': 'Usuário não encontrado'}), 401
    
    if not user.has_active_subscription():
        return jsonify({
            'error': 'Assinatura expirada',
            'redirect_url': '/payment'
        }), 403
    
    try:
        dados = request.get_json()
        print("Dados recebidos:", dados)  # Debug
        
        planejamento = PlanejamentoCaixa()
        resultados = planejamento.calcular(dados)
        
        # Garantir que a estrutura está correta
        response_data = {
            'resultados': resultados['resultados'],
            'indicadores': resultados['indicadores'],
            'graficos': resultados['graficos'],
            'meses': resultados['meses']
        }
        
        print("Resultados enviados:", response_data)  # Debug
        return jsonify(response_data)
        
    except Exception as e:
        print("Erro no cálculo:", str(e))  # Debug
        return jsonify({'error': str(e)}), 400
