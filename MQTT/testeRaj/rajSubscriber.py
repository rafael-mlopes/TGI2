import os
import json
import threading
import paho.mqtt.client as mqtt
from flask import Flask, render_template_string, send_from_directory
from waitress import serve
from datetime import datetime

# --- CONFIGURAÇÕES MQTT ---
BROKER = "192.168.0.25"
PORT = 15896
USR = "sensor_maquinas"
PSW = "raj_maq2026"
TOPICO_ALVO = "Raj/BR_SP/log/+/+"

# --- CONFIGURAÇÕES DE ARQUIVOS ---
DIR_RECEBIDOS = "./arquivos_recebidos"
os.makedirs(DIR_RECEBIDOS, exist_ok=True)

# ==========================================
# 1. SERVIÇO WEB (FLASK + WAITRESS)
# ==========================================
app = Flask(__name__)

HTML_HOME = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Painel Multi-Empresas</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; background-color: #f4f4f9; }
        .card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; }
        a { text-decoration: none; color: #0066cc; font-size: 18px; font-weight: bold; }
        a:hover { color: #004499; text-decoration: underline; }
        .data-badge { background: #e0e0e0; color: #333; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }
    </style>
</head>
<body>
    <h1>🏢 Painel de Logs - Clientes</h1>
    <p>Selecione a empresa para visualizar os arquivos sincronizados:</p>
    {% for empresa in empresas %}
        <div class="card">
            <span>📁 <a href="/empresa/{{ empresa.nome }}">{{ empresa.nome }}</a></span>
            {% if empresa.data %}
                <span class="data-badge">Última atividade: {{ empresa.data }}</span>
            {% else %}
                <span class="data-badge">Nenhum log recebido</span>
            {% endif %}
        </div>
    {% else %}
        <div class="card">Aguardando conexão de clientes... Nenhuma pasta criada ainda.</div>
    {% endfor %}
</body>
</html>
"""

HTML_EMPRESA = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Logs - {{ empresa }}</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; background-color: #f4f4f9; }
        .card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); }
        li { margin: 10px 0; border-bottom: 1px solid #eee; padding-bottom: 10px; list-style: none; display: flex; justify-content: space-between; align-items: center; }
        a { text-decoration: none; color: #0066cc; font-weight: bold; font-size: 16px;}
        .btn-voltar { display: inline-block; margin-bottom: 20px; padding: 8px 15px; background: #333; color: white; border-radius: 5px; text-decoration: none; }
        .data-badge { background: #e0e0e0; color: #333; padding: 4px 8px; border-radius: 4px; font-size: 12px; }
    </style>
</head>
<body>
    <a href="/" class="btn-voltar">⬅ Voltar para Empresas</a>
    <h1>📂 Arquivos da Empresa: {{ empresa }}</h1>
    <div class="card">
        <ul>
            {% for arquivo in arquivos %}
                <li>
                    <span>📄 <a href="/view/{{ empresa }}/{{ arquivo.nome }}">{{ arquivo.nome }}</a></span>
                    <span class="data-badge">Última atualização: {{ arquivo.data }}</span>
                </li>
            {% else %}
                <li>Nenhum log encontrado para esta empresa.</li>
            {% endfor %}
        </ul>
    </div>
</body>
</html>
"""

HTML_VISUALIZADOR = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Visualizando - {{ arquivo }}</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; background-color: #f4f4f9; }
        .cabecalho-botoes { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
        .btn-voltar { padding: 8px 15px; background: #333; color: white; text-decoration: none; border-radius: 5px; }
        .btn-voltar:hover { background: #555; }
        
        /* Botão de Tema */
        .btn-tema { padding: 8px 15px; background: #0066cc; color: white; border: none; border-radius: 5px; cursor: pointer; font-weight: bold; font-size: 14px; }
        .btn-tema:hover { background: #004499; }
        
        /* Tema Escuro (Padrão) */
        .terminal { background: #1e1e1e; color: #00ff00; padding: 20px; border-radius: 8px; overflow-x: auto; font-family: "Courier New", Courier, monospace; line-height: 1.5; box-shadow: 0 4px 10px rgba(0,0,0,0.5); transition: all 0.3s ease; }
        
        /* Tema Claro (Adicionado via JavaScript) */
        .terminal.tema-claro { background: #ffffff; color: #333333; box-shadow: 0 4px 10px rgba(0,0,0,0.1); border: 1px solid #ccc; }
    </style>
</head>
<body>
    <div class="cabecalho-botoes">
        <a href="/empresa/{{ empresa }}" class="btn-voltar">⬅ Voltar para os Arquivos</a>
        <button id="btnToggleTema" class="btn-tema">☀️ Mudar para Tema Claro</button>
    </div>
    
    <h1>{{ arquivo }}</h1>
    <p><strong>Origem:</strong> {{ empresa }}</p>
    
    <div id="caixaTerminal" class="terminal">
<pre>{{ conteudo }}</pre>
    </div>

    <script>
        // Lógica simples em JavaScript para trocar as cores
        const btnTema = document.getElementById('btnToggleTema');
        const caixaTerminal = document.getElementById('caixaTerminal');

        btnTema.addEventListener('click', function() {
            // Liga/Desliga a classe 'tema-claro' na div do terminal
            caixaTerminal.classList.toggle('tema-claro');
            
            // Troca o texto e o ícone do botão dependendo do tema ativo
            if (caixaTerminal.classList.contains('tema-claro')) {
                btnTema.innerHTML = '🌙 Mudar para Tema Escuro';
                btnTema.style.background = '#333'; // Deixa o botão escuro
            } else {
                btnTema.innerHTML = '☀️ Mudar para Tema Claro';
                btnTema.style.background = '#0066cc'; // Volta o botão pro azul
            }
        });
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    cEmpresasDados = []
    cEmpresasLocais = [nome for nome in os.listdir(DIR_RECEBIDOS) if os.path.isdir(os.path.join(DIR_RECEBIDOS, nome))]
    
    for fNomeEmpresa in cEmpresasLocais:
        cCaminhoEmpresa = os.path.join(DIR_RECEBIDOS, fNomeEmpresa)
        cArquivos = [f for f in os.listdir(cCaminhoEmpresa) if f.endswith('.txt')]
        
        cMaxTimestamp = 0
        cDataFormatada = ""
        
        if cArquivos:
            # Pega o timestamp do arquivo mais recente dentro da pasta da empresa
            cMaxTimestamp = max([os.path.getmtime(os.path.join(cCaminhoEmpresa, f)) for f in cArquivos])
            cDataFormatada = datetime.fromtimestamp(cMaxTimestamp).strftime('%d/%m/%Y %H:%M:%S')
            
        cEmpresasDados.append({
            'nome': fNomeEmpresa,
            'timestamp': cMaxTimestamp,
            'data': cDataFormatada
        })
        
    # Ordena a lista de empresas pela data mais recente (maior timestamp)
    cEmpresasDados = sorted(cEmpresasDados, key=lambda x: x['timestamp'], reverse=True)
    
    return render_template_string(HTML_HOME, empresas=cEmpresasDados)

@app.route('/empresa/<fNomeEmpresa>')
def verEmpresa(fNomeEmpresa):
    cCaminhoEmpresa = os.path.join(DIR_RECEBIDOS, fNomeEmpresa)
    if not os.path.exists(cCaminhoEmpresa):
        return "Empresa não encontrada.", 404
    
    cArquivoLocais = []
    for fNomeArquivo in os.listdir(cCaminhoEmpresa):
        if fNomeArquivo.endswith('.txt'):
            cCaminhoCompleto = os.path.join(cCaminhoEmpresa, fNomeArquivo)
            cTimestamp = os.path.getmtime(cCaminhoCompleto)
            cDataFormatada = datetime.fromtimestamp(cTimestamp).strftime('%d/%m/%Y %H:%M:%S')
            
            cArquivoLocais.append({
                'nome': fNomeArquivo, 
                'timestamp': cTimestamp, 
                'data': cDataFormatada
            })
            
    # Ordena a lista de arquivos pela data mais recente
    cArquivoLocais = sorted(cArquivoLocais, key=lambda x: x['timestamp'], reverse=True)
    
    return render_template_string(HTML_EMPRESA, empresa=fNomeEmpresa, arquivos=cArquivoLocais)

@app.route('/view/<fNomeEmpresa>/<fNomeArquivo>')
def visualizarLog(fNomeEmpresa, fNomeArquivo):
    cCaminhoArquivo = os.path.join(DIR_RECEBIDOS, fNomeEmpresa, fNomeArquivo)
    if not os.path.exists(cCaminhoArquivo):
        return "Arquivo não encontrado.", 404
    
    with open(cCaminhoArquivo, 'r', encoding='utf-8') as f:
        cConteudoTexto = f.read()
    
    return render_template_string(HTML_VISUALIZADOR, empresa=fNomeEmpresa, arquivo=fNomeArquivo, conteudo=cConteudoTexto)    


def iniciarServidorWeb():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Painel Web iniciado! Acesse: http://localhost:5050")
    serve(app, host='0.0.0.0', port=5050)

# ==========================================
# 2. MOTOR MQTT (PAHO V2)
# ==========================================
def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Conectado ao Broker!")
        client.subscribe(TOPICO_ALVO, qos=1)
        print(f"Ouvindo o tópico dinâmico: {TOPICO_ALVO}")
    else:
        print(f"** Erro: Falha na conexão. Código: {reason_code}")

def on_message(client, userdata, msg):
    try:
        cTopicoRecebido = msg.topic
        cPartesTopico = cTopicoRecebido.split("/")
        
        cNomeArquivo = cPartesTopico[-1]
        cNomeEmpresa = cPartesTopico[-2]
        
        cPayload = json.loads(msg.payload.decode('utf-8'))
        cConteudo = cPayload.get('conteudo', '')
        
        cCaminhoEmpresa = os.path.join(DIR_RECEBIDOS, cNomeEmpresa)
        os.makedirs(cCaminhoEmpresa, exist_ok=True)
        
        cCaminhoCompleto = os.path.join(cCaminhoEmpresa, cNomeArquivo)
        
        with open(cCaminhoCompleto, 'a', encoding='utf-8') as f:
            f.write(cConteudo + '\n')
            
        print(f"{cNomeEmpresa} -> {cNomeArquivo}: {cConteudo[:30]}...")

    except Exception as e:
        print(f"** Erro crítico ao gravar arquivo: {e}")

if __name__ == "__main__":
    print("=== RECEPTOR DE ARQUIVOS (SUBSCRIBER) ===")

    cThreadWeb = threading.Thread(target=iniciarServidorWeb, daemon=True)
    cThreadWeb.start()
    
    cIdUnico = f"mqttx_SUB_TXT_RAJ"
    cClienteMqtt = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cIdUnico, clean_session=False)
    
    cClienteMqtt.username_pw_set(USR, PSW)    
    cClienteMqtt.on_connect = on_connect
    cClienteMqtt.on_message = on_message
    
    try:
        cClienteMqtt.connect(BROKER, PORT)
        cClienteMqtt.loop_forever() 
            
    except KeyboardInterrupt:
        print("\nDesligando receptor...")
        cClienteMqtt.disconnect()
        
# Futuro -- Disparar telegram/whatsSuporte do exception ocorrido