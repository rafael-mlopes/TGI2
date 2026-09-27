import threading
from flask import Flask, jsonify, request
from waitress import serve
from flasgger import Swagger
from flask_cors import CORS

app = Flask(__name__)

CORS(app)    

fSwagger = Swagger(app, template={
    "info": {
        "title": "API de Telemetria Industrial TGI",
        "description": "Documentação interativa para consulta de status das máquinas no chão de fábrica.",
        "version": "1.0.0"
    }
})

fDbMqtt = None
fCacheMemoria = None

app.json.sort_keys = False

@app.route('/api/estado-maquinas', methods=['GET'])
def estado_maquinas():
    """
    Consulta o estado geral de todas as máquinas
    Retorna uma lista em tempo real com todas as máquinas que estão enviando telemetria e operando no momento.
    ---
    responses:
      200:
        description: Sucesso. Retorna a lista de máquinas lidas diretamente da Memória RAM.
      500:
        description: Erro interno no servidor.
    """
    try:       
        cListaMaquinas = list(fCacheMemoria.values())
        cTotal = len(cListaMaquinas)
        
        fDbMqtt.printLog(f"Consultando Estado Geral -> Retornando {cTotal} máquinas da MEMÓRIA RAM!")
        
        return jsonify({
            "origem": "cache",
            "status": "sucesso",
            "totalMaquinas": cTotal,
            "dados": cListaMaquinas
        }), 200
        
    except Exception as e:
        fDbMqtt.printLog(f"** Erro na API (Estado Geral): {e}")
        return jsonify({"status": "erro", "mensagem": "Erro interno ao buscar estado das máquinas."}), 500
        
@app.route('/api/consultaJob', methods=['GET'])
def consultarJob():
    """
    Consulta os dados detalhados de um Job específico
    Busca as informações de ciclo, OEE e tempos de um Job amarrado a uma máquina.
    ---
    parameters:
      - name: seqTarefa
        in: query
        type: string
        required: true
        description: A sequência da tarefa da máquina (ex 5)
      - name: maquina
        in: query
        type: string
        required: true
        description: O nome ou ID da máquina (ex Impressora_Offset_01)
      - name: job
        in: query
        type: string
        required: true
        description: O ID do Job Planner que está sendo executado
    responses:
      200:
        description: Sucesso. Retorna os dados completos do Job solicitado.
      400:
        description: Faltam parâmetros obrigatórios na URL.
      404:
        description: Máquina ou Job não encontrados.
      500:
        description: Erro interno ao buscar no banco de dados.
    """    
    cSeqTarefa = request.args.get('seqTarefa')
    cMaquina = request.args.get('maquina')
    cJob = request.args.get('job', 0)
    
    if not cSeqTarefa or not cMaquina:
        return jsonify({"status": "erro", "mensagem": "Parâmetros obrigatórios ausentes. Informe '?seqTarefa=X&maquina=Y&job=Z' na URL." }), 400
    
    cTmpJOB = f"{cSeqTarefa}|{cMaquina}|{cJob}"
    
    if cTmpJOB in fCacheMemoria:
        fDbMqtt.printLog(f"Consultando {cTmpJOB} -> Retornando da MEMÓRIA RAM!")
        return jsonify({
            "origem": "cache",
            "status": "sucesso",
            "dados": fCacheMemoria[cTmpJOB]
        }), 200        
    
    cConexao = None
    cCursor = None
    try:
        fDbMqtt.printLog(f"Consultando {cTmpJOB} -> Buscando no Banco de Dados...")
        cConexao = fDbMqtt.obterConexao()
        cCursor = cConexao.cursor()
        
        cSql = "SELECT * FROM CLP_MACOMP WHERE SEQ_TAREFA = %s AND MAQUINA = %s AND IDJOB = %s"
        cCursor.execute(cSql, (cSeqTarefa, cMaquina, cJob))        
        cResultado = cCursor.fetchone()
        
        if cResultado:
            cColunas = [desc[0] for desc in cCursor.description]
            cLinha = dict(zip(cColunas, cResultado))
            return jsonify({"origem": "banco", "status": "sucesso", "dados": cLinha}), 200
        else:
            return jsonify({"status": "erro", "mensagem": "Máquina/Job não encontrados no sistema."}), 404
        
    except Exception as e:
        fDbMqtt.printLog(f"** Erro na API: {e}")
        return jsonify ({"status": "erro", "mensagem": "Erro interno."}), 500
    finally:
        if cCursor:
            try: cCursor.close()    
            except: pass
        
        if fDbMqtt:
            fDbMqtt.fecharConexao()

def rodarWaitress():
    serve(app, host='0.0.0.0', port=5000, threads=6)
    
def ligarServidorWeb(nBancoInstancia, nDicionarioMemoria):
    global fDbMqtt, fCacheMemoria
    
    fDbMqtt = nBancoInstancia
    fCacheMemoria = nDicionarioMemoria
    fDbMqtt.printLog("Iniciando API com waitress na porta 5000...")
    
    cThreadWeb = threading.Thread(target=rodarWaitress, daemon=True)
    cThreadWeb.start()