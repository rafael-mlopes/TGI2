import threading
from datetime import datetime
from flask import Flask, jsonify, request
from waitress import serve
from flasgger import Swagger
from flask_cors import CORS

app = Flask(__name__)

CORS(app)    

fSwagger = Swagger(app, template={
    "info": {
        "title": "API de Telemetria Industrial TGI",
        "description": "Documentação interativa para consulta de status e apontamento de máquinas no chão de fábrica.",
        "version": "1.1.0"
    }
})

fDbMqtt = None
fCacheMemoria = None
# Guarda em memória o último apontamento de cada máquina (1=Setup, 2=Produção, 3=Suspensão)
fApontamentoAtual = {}

app.json.sort_keys = False

def verificarBancoAtivo():
    """Testa rapidamente se o banco MySQL está acessível para apontamentos."""
    if not fDbMqtt:
        return False
    cCursor = None
    try:
        cConexao = fDbMqtt.obterConexao()
        if not cConexao:
            return False
        cCursor = cConexao.cursor()
        cCursor.execute("SELECT 1")
        cCursor.fetchone()
        return True
    except Exception:
        return False
    finally:
        if cCursor:
            try: cCursor.close()
            except: pass

@app.route('/api/estado-maquinas', methods=['GET'])
def estado_maquinas():
    """
    Consulta o estado geral de todas as máquinas e o status de conexão com o Banco
    ---
    responses:
      200:
        description: Sucesso. Retorna a lista de máquinas da Memória RAM e o status do banco.
    """
    try:       
        cBancoOk = verificarBancoAtivo()
        cListaMaquinas = []

        for chave, dadosMaq in fCacheMemoria.items():
            copiaMaq = dict(dadosMaq)
            idMaq = int(copiaMaq.get("MAQUINA", 0))
            copiaMaq["APONTAMENTO_ATUAL"] = fApontamentoAtual.get(idMaq, 2)
            cListaMaquinas.append(copiaMaq)

        cTotal = len(cListaMaquinas)
        
        return jsonify({
            "origem": "cache",
            "status": "sucesso",
            "bancoConectado": cBancoOk,
            "totalMaquinas": cTotal,
            "dados": cListaMaquinas
        }), 200
        
    except Exception as e:
        fDbMqtt.printLog(f"** Erro na API (Estado Geral): {e}")
        return jsonify({
            "status": "erro",
            "bancoConectado": False,
            "mensagem": "Erro interno ao buscar estado das máquinas."
        }), 500
        
@app.route('/api/consultaJob', methods=['GET'])
def consultarJob():
    """
    Consulta os dados detalhados de um Job específico
    ---
    parameters:
      - name: seqTarefa
        in: query
        type: string
        required: true
      - name: maquina
        in: query
        type: string
        required: true
      - name: job
        in: query
        type: string
        required: true
    """    
    cSeqTarefa = request.args.get('seqTarefa')
    cMaquina = request.args.get('maquina')
    cJob = request.args.get('job', 0)
    
    if not cSeqTarefa or not cMaquina:
        return jsonify({"status": "erro", "mensagem": "Parâmetros obrigatórios ausentes."}), 400
    
    cBancoOk = verificarBancoAtivo()
    cTmpJOB = f"{cSeqTarefa}|{cMaquina}|{cJob}"
    
    if cTmpJOB in fCacheMemoria:
        dadosMaq = dict(fCacheMemoria[cTmpJOB])
        dadosMaq["APONTAMENTO_ATUAL"] = fApontamentoAtual.get(int(cMaquina), 2)
        return jsonify({
            "origem": "cache",
            "status": "sucesso",
            "bancoConectado": cBancoOk,
            "dados": dadosMaq
        }), 200        
    
    cConexao = None
    cCursor = None
    try:
        cConexao = fDbMqtt.obterConexao()
        cCursor = cConexao.cursor()
        
        cSql = "SELECT * FROM CLP_MACOMP WHERE SEQ_TAREFA = %s AND MAQUINA = %s AND IDJOB = %s"
        cCursor.execute(cSql, (cSeqTarefa, cMaquina, cJob))        
        cResultado = cCursor.fetchone()
        
        if cResultado:
            cColunas = [desc[0] for desc in cCursor.description]
            cLinha = dict(zip(cColunas, cResultado))
            cLinha["APONTAMENTO_ATUAL"] = fApontamentoAtual.get(int(cMaquina), 2)
            return jsonify({
                "origem": "banco",
                "status": "sucesso",
                "bancoConectado": True,
                "dados": cLinha
            }), 200
        else:
            return jsonify({"status": "erro", "bancoConectado": cBancoOk, "mensagem": "Máquina/Job não encontrados."}), 404
        
    except Exception as e:
        fDbMqtt.printLog(f"** Erro na API: {e}")
        return jsonify({"status": "erro", "bancoConectado": False, "mensagem": "Banco de dados indisponível."}), 500
    finally:
        if cCursor:
            try: cCursor.close()    
            except: pass

@app.route('/api/apontamento', methods=['POST'])
def registrar_apontamento():
    """
    Registra um novo apontamento de produção (Setup, Produção ou Suspensão) na tabela AG_MOCOR
    ---
    """
    dados = request.get_json(silent=True) or {}
    cSeqTarefa = dados.get("seqTarefa")
    cMaquina = dados.get("maquina")
    cCodTpOcor = dados.get("codTpOcor") # 1 = Setup, 2 = Produção, 3 = Suspensão

    if not cSeqTarefa or not cMaquina or cCodTpOcor not in [1, 2, 3]:
        return jsonify({
            "status": "erro",
            "mensagem": "Informe seqTarefa, maquina e codTpOcor válido (1=Setup, 2=Produção, 3=Suspensão)."
        }), 400

    cConexao = None
    cCursor = None
    try:
        cConexao = fDbMqtt.obterConexao()
        if not cConexao:
            raise Exception("Sem conexão com o MySQL.")
        cCursor = cConexao.cursor()
        cAgora = datetime.now()

        # 1. Garante que a tarefa e máquina existam na AG_MTAR (usada no JOIN do TgiBootInter)
        cSqlGaranteTar = """
            INSERT INTO AG_MTAR (SEQ_TAREFA, CODTPTAR, MAQUINA, ESTADO, INIPROG)
            VALUES (%s, 1, %s, 'R', %s)
            ON DUPLICATE KEY UPDATE MAQUINA = VALUES(MAQUINA), ESTADO = 'R'
        """
        cCursor.execute(cSqlGaranteTar, (cSeqTarefa, cMaquina, cAgora))

        # 2. Fecha o apontamento anterior em aberto desta tarefa
        cSqlFechaAnterior = """
            UPDATE AG_MOCOR 
            SET FIM = %s, DTA = %s 
            WHERE SEQ_TAREFA = %s AND FIM IS NULL
        """
        cCursor.execute(cSqlFechaAnterior, (cAgora, cAgora, cSeqTarefa))

        # 3. Calcula o próximo SEQ_OCORRE para esta SEQ_TAREFA
        cCursor.execute("SELECT COALESCE(MAX(SEQ_OCORRE), 0) + 1 FROM AG_MOCOR WHERE SEQ_TAREFA = %s", (cSeqTarefa,))
        cProxSeqOcorre = cCursor.fetchone()[0]

        # 4. Insere a nova ocorrência na AG_MOCOR para o TgiBootInter capturar e publicar no MQTT
        cSqlInsertOcor = """
            INSERT INTO AG_MOCOR (SEQ_TAREFA, SEQ_OCORRE, INICIO, CODTPTAR, CODTPOCOR, CODORIGEM, DTI)
            VALUES (%s, %s, %s, 1, %s, 'M', %s)
        """
        cCursor.execute(cSqlInsertOcor, (cSeqTarefa, cProxSeqOcorre, cAgora, cCodTpOcor, cAgora))
        cConexao.commit()

        fApontamentoAtual[int(cMaquina)] = int(cCodTpOcor)
        
        nomes_modo = {1: "SETUP", 2: "PRODUÇÃO", 3: "SUSPENSÃO"}
        fDbMqtt.printLog(f"[APONTAMENTO WEB] Máquina {cMaquina} (Tarefa {cSeqTarefa}) -> {nomes_modo[int(cCodTpOcor)]} gravado na AG_MOCOR!")

        return jsonify({
            "status": "sucesso",
            "bancoConectado": True,
            "seqOcorre": cProxSeqOcorre,
            "apontamentoAtual": int(cCodTpOcor),
            "mensagem": f"Apontamento de {nomes_modo[int(cCodTpOcor)]} registrado na AG_MOCOR com sucesso!"
        }), 201

    except Exception as e:
        if cConexao:
            try: cConexao.rollback()
            except: pass
        fDbMqtt.printLog(f"** Erro ao gravar apontamento na AG_MOCOR: {e}")
        return jsonify({
            "status": "erro",
            "bancoConectado": False,
            "mensagem": "Banco de dados offline. O painel está operando apenas em modo de visualização."
        }), 503
    finally:
        if cCursor:
            try: cCursor.close()
            except: pass

def rodarWaitress():
    serve(app, host='0.0.0.0', port=5000, threads=6)
    
def ligarServidorWeb(nBancoInstancia, nDicionarioMemoria):
    global fDbMqtt, fCacheMemoria
    
    fDbMqtt = nBancoInstancia
    fCacheMemoria = nDicionarioMemoria
    fDbMqtt.printLog("Iniciando API com waitress na porta 5000...")
    
    cThreadWeb = threading.Thread(target=rodarWaitress, daemon=True)
    cThreadWeb.start()