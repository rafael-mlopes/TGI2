import threading
from flask import Flask, jsonify, request
from waitress import serve
    
app = Flask(__name__)    

fDbDestino = None
fCacheMemoria = None

app.json.sort_keys = False

@app.route('/api/estado-maquinas', methods=['GET'])
def estado_maquinas():
    try:
        # Extrai apenas os valores (os dados das máquinas) do dicionário
        cListaMaquinas = list(fCacheMemoria.values())
        cTotal = len(cListaMaquinas)
        
        fDbDestino.printLog(f"Consultando Estado Geral -> Retornando {cTotal} máquinas da MEMÓRIA RAM!")
        
        return jsonify({
            "origem": "cache",
            "status": "sucesso",
            "totalMaquinas": cTotal,
            "dados": cListaMaquinas
        }), 200
        
    except Exception as e:
        fDbDestino.printLog(f"** Erro na API (Estado Geral): {e}")
        return jsonify({"status": "erro", "mensagem": "Erro interno ao buscar estado das máquinas."}), 500
        
@app.route('/api/consultaJob', methods=['GET'])
def consultarJob():
    cSeqTarefa = request.args.get('seqTarefa')
    cMaquina = request.args.get('maquina')
    cJob = request.args.get('job', 0)
    
    if not cSeqTarefa or not cMaquina:
        return jsonify({"status": "erro", "mensagem": "Parâmetros obrigatórios ausentes. Informe '?seqTarefa=X&maquina=Y&job=Z' na URL." }), 400
    
    cTmpJOB = f"{cSeqTarefa}|{cMaquina}|{cJob}"
    
    if cTmpJOB in fCacheMemoria:
        fDbDestino.printLog(f"Consultando {cTmpJOB} -> Retornando da MEMÓRIA RAM!")
        return jsonify({
                    "origem": "cache",
                    "status": "sucesso",
                    "dados": fCacheMemoria[cTmpJOB]
                }), 200        
    cConexao = None
    cCursor = None
    try:
        fDbDestino.printLog(f"Consultando {cTmpJOB} -> Buscando no Banco de Dados...")
        cConexao = fDbDestino.obterConexao()
        cCursor = cConexao.cursor()
        
        cSql = "SELECT * FROM CLP_MACOMP WHERE SEQ_TAREFA = ? AND MAQUINA = ? AND IDJOB = ?"
        cCursor.execute(cSql, (cSeqTarefa, cMaquina, cJob))        
        cResultado = cCursor.fetchone()
        
        if cResultado:
            cColunas = [desc[0] for desc in cCursor.description]
            cLinha = dict(zip(cColunas, cResultado))
            return jsonify({"origem": "banco", "status": "sucesso", "dados": cLinha}),200
        else:
            return jsonify({"status": "erro", "mensagem": "Máquina/Job não encontrados no sistema."}), 404
        
    except Exception as e:
        fDbDestino.printLog(f"** Erro na API: {e}")
        return jsonify ({"status": "erro", "mensagem": "Erro interno ."}),500
    finally:
        if cCursor:
            try: cCursor.close()    
            except: pass
        
        if fDbDestino:
            fDbDestino.fecharConexao()

def rodarWaitress():
    serve(app, host='0.0.0.0', port=5000)
    
def ligarServidorWeb(nBancoInstancia, nDicionarioMemoria):
    global fDbDestino, fCacheMemoria
    
    fDbDestino = nBancoInstancia
    fCacheMemoria = nDicionarioMemoria
    fDbDestino.printLog("Iniciando API com waitress na porta 5000...")
    
    cThreadWeb = threading.Thread(target=rodarWaitress, daemon=True)
    cThreadWeb.start()            