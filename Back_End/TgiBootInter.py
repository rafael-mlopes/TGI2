import os
import sys
import json
import time
import random
import uuid
import mysql.connector
from datetime import datetime, timedelta
from LibDB import GerenciadorBanco
from LibFlask import ligarServidorWeb
from LibConfig import carregarConfig, ErroConfiguracao

if getattr(sys, 'frozen', False):
    fDirAtual = os.path.dirname(sys.executable)
else:
    fDirAtual = os.path.dirname(os.path.abspath(__file__))

cNomeScript = os.path.splitext(os.path.basename(__file__))[0].capitalize()

try:
    print("Iniciando conexões com os bancos de dados (MySQL)...")    
    
    cDadosOrigem = carregarConfig()
    
    cDadosClient = cDadosOrigem["dbClient"]
    cDadosMqtt = cDadosOrigem["dbMqtt"]
    cLogDetalhado = cDadosOrigem["LogDetalhado"]
        
    fChaveInt1: int = random.randint(1, 999999) 
    dbClient = GerenciadorBanco(
        nHostBanco=cDadosClient['hDB'], 
        nNomeBanco=cDadosClient['db'], 
        nUsuarioBanco=cDadosClient['uDB'], 
        nSenhaBanco=cDadosClient['pDB'], 
        nNomeProjeto="INTERPRETADOR_ORIG", 
        nChaveInt=fChaveInt1,
        nSistemaLog=cNomeScript
    )
    
    fChaveInt2: int = random.randint(1, 999999) 
    dbMqtt = GerenciadorBanco(
        nHostBanco=cDadosMqtt['hDB'], 
        nNomeBanco=cDadosMqtt['db'], 
        nUsuarioBanco=cDadosMqtt['uDB'], 
        nSenhaBanco=cDadosMqtt['pDB'], 
        nNomeProjeto="INTERPRETADOR_DEST", 
        nChaveInt=fChaveInt2,
        nSistemaLog=cNomeScript
    )
    
    print("Conexões instanciadas com sucesso!")

except ErroConfiguracao as e:
    print(f"** Script interrompido: {e}")
    sys.exit()
except Exception as e:
    print(f"** Erro ao instanciar os bancos: {e}")
    sys.exit()   
    
cCacheMaquinasMemoria = {}       
cColunasAcomp = [
    "SEQ_TAREFA", "MAQUINA", "IDJOB", "VELMEDCURTA", "VELMEDGLOBAL", "VELATUAL", 
    "CICLOMED", "CICLOATUAL", "QTDSETUP", "QTDLIQ", "QTDBRUTA", "QTDREFUGO", 
    "TMPEXEC", "TMPPREP", "TMPBONS", "TMPPARADO", "TMPTOTAL", "TMPREST", 
    "MAQATIVA", "BTNCONTAGEM", "OEEDISP", "OEEDESEMP", "OEEQUALID", "OEETOTAL"
]

# Ocorrências já enfileiradas: {(SEQ_TAREFA, SEQ_OCORRE): INICIO}.
# É reconstruído no startup a partir da própria fila de envio (CLP_MMSGENV/ENVT), para que um
# reinício do serviço não reenvie nem perca apontamentos. Entradas antigas são podadas a cada ciclo.
cOcorrenciasJaProcessadas = {}

# A busca na AG_MOCOR recua esta margem em relação ao último INICIO visto. Cobre o arredondamento
# de segundos do DATETIME e INSERTs confirmados alguns instantes depois do horário gravado em INICIO.
# Duplicidades são barradas por cOcorrenciasJaProcessadas.
MARGEM_BUSCA_OCORRENCIAS = timedelta(seconds=60)

# No startup, ocorrências com INICIO dentro desta janela e ainda não enfileiradas são enviadas.
JANELA_STARTUP_OCORRENCIAS = timedelta(minutes=10)

def carregarOcorrenciasJaEnviadas():
    """Reconstrói cOcorrenciasJaProcessadas a partir das ocorrências que já estão na fila de envio."""
    cCursor = None
    try:
        cConexao = dbMqtt.obterConexao()
        cConexao.commit()
        cCursor = cConexao.cursor()
        cLimite = datetime.now() - timedelta(days=1)
        cCursor.execute("""
            SELECT E.SEQ_TAREFA, T.MEMJS
            FROM CLP_MMSGENV E
            JOIN CLP_MMSGENVT T ON T.CODSTR = E.CODSTR
            WHERE E.TOPICOCPL LIKE 'Tgi/%%/Ocorrencia/%%' AND E.DTI >= %s
        """, (cLimite,))
        cQtd = 0
        for cSeqTarefa, cMemjs in cCursor.fetchall():
            try:
                cPayload = json.loads(cMemjs or "{}")
                cChave = (int(cSeqTarefa), int(cPayload["id_ocorrencia"]))
                cInicio = datetime.strptime(cPayload["data_hora_falha"], "%Y-%m-%d %H:%M:%S")
                cOcorrenciasJaProcessadas[cChave] = cInicio
                cQtd += 1
            except Exception:
                continue
        dbMqtt.printLog(f"Controle de ocorrências restaurado: {cQtd} ocorrência(s) já enfileirada(s) nas últimas 24h.")
    except Exception as e:
        dbMqtt.printLog(f"** Aviso: não foi possível restaurar o controle de ocorrências: {e}")
    finally:
        if cCursor:
            try: cCursor.close()
            except: pass

def podarOcorrenciasProcessadas(nUltimaVerificacao):
    cLimite = nUltimaVerificacao - MARGEM_BUSCA_OCORRENCIAS - timedelta(minutes=1)
    for cChave in [k for k, v in cOcorrenciasJaProcessadas.items() if v < cLimite]:
        del cOcorrenciasJaProcessadas[cChave]

def processarOcorrencias(cUltimaVerificacao):
    cConexaoClient = None
    cCursorClient = None
    cConexaoMqtt = None
    cCursorMqtt = None    
    cNovaUltimaVerificacao = cUltimaVerificacao.replace(microsecond=0)
    
    try:
        cConexaoClient = dbClient.obterConexao()
        # Importante no MySQL InnoDB: atualiza o snapshot da transação para enxergar os INSERTs da API Flask
        cConexaoClient.commit()
        cCursorClient = cConexaoClient.cursor()
        
        cSqlBusca = """
            SELECT
                M.SEQ_OCORRE, M.INICIO, M.CODTPOCOR, M.SEQ_TAREFA,
                C.EMPRESA, C.NUMPED, C.NUMITEM, C.NUMTIRAG, T.MAQUINA
            FROM AG_MOCOR M
            LEFT JOIN AG_MTARC C ON M.SEQ_TAREFA = C.SEQ_TAREFA
            LEFT JOIN AG_MTAR T ON M.SEQ_TAREFA = T.SEQ_TAREFA
            WHERE M.INICIO >= %s
            ORDER BY M.INICIO ASC, M.SEQ_OCORRE ASC        
        """
        cCursorClient.execute(cSqlBusca, (cNovaUltimaVerificacao - MARGEM_BUSCA_OCORRENCIAS,))
        cOcorrencias = cCursorClient.fetchall()
        
        # Filtra apenas as ocorrências (SEQ_TAREFA, SEQ_OCORRE) que ainda não foram enviadas
        cNovasOcorrencias = [
            ocor for ocor in cOcorrencias 
            if (int(ocor[3] or 0), int(ocor[0])) not in cOcorrenciasJaProcessadas
        ]

        if not cNovasOcorrencias:
            podarOcorrenciasProcessadas(cNovaUltimaVerificacao)
            return cNovaUltimaVerificacao
        
        cAgora = datetime.now()
        
        cConexaoMqtt = dbMqtt.obterConexao()
        cCursorMqtt = cConexaoMqtt.cursor()        
        
        cSqlInsertEnv = "INSERT INTO CLP_MMSGENV (CODSTR, SEQ_TAREFA, MAQUINA, IDJOB, DTI, JAENVIOU, EXCLUIR, TOPICOCPL) VALUES (%s, %s, %s, %s, %s, 'N', 'N', %s)"
        cSqlInsertEnvT = "INSERT INTO CLP_MMSGENVT (CODSTR, IDMSGMQTT, MEMJS) VALUES (%s, %s, %s)"
        
        cMsgSucesso = 0
        cProcessadasLote = {}
        cMaiorData = cNovaUltimaVerificacao
        
        for ocor in cNovasOcorrencias:
            cSeqOcorrencia = ocor[0]
            cDataOcorrencia = ocor[1]
            cTipoOcorrencia = ocor[2] if ocor[2] else 2
            cSeqTarefa = ocor[3] if ocor[3] else 0
            cNumOs = f"{ocor[4] or ''}{ocor[5] or ''}{ocor[6] or ''}{ocor[7] or ''}"
            cNumeroOs = cNumOs if cNumOs else f"JOB-{10000 + int(cSeqTarefa)}"
            
            # Se T.MAQUINA vier vazio no JOIN, usa o próprio SEQ_TAREFA como ID da máquina
            try:
                cMaquina = int(ocor[8]) if ocor[8] else int(cSeqTarefa)
            except ValueError:
                cMaquina = int(cSeqTarefa)
            
            cCodstr = cAgora.strftime("%Y%m%d%H%M%S") + str(random.randint(100000, 999999))    
            cIdMqtt = str(uuid.uuid4())
            cTopico = f"Tgi/BR_SP/Planta1/Ocorrencia/{cMaquina}"
        
            cDictPayload = {
                "id_ocorrencia": cSeqOcorrencia,
                "maquina": cMaquina,
                "job_id": cNumeroOs,
                "descricao": int(cTipoOcorrencia),
                "data_hora_falha": cDataOcorrencia.strftime("%Y-%m-%d %H:%M:%S"),
                "tipo_mensagem": "ocorrencia_nova"
            }
            
            cJson = json.dumps(cDictPayload)
            
            cCursorMqtt.execute(cSqlInsertEnv, (cCodstr, cSeqTarefa, cMaquina, cNumeroOs, cAgora, cTopico))
            cCursorMqtt.execute(cSqlInsertEnvT, (cCodstr, cIdMqtt, cJson))
            
            cProcessadasLote[(int(cSeqTarefa), int(cSeqOcorrencia))] = cDataOcorrencia
            if cDataOcorrencia > cMaiorData:
                cMaiorData = cDataOcorrencia
                
            cMsgSucesso += 1
        
        cConexaoMqtt.commit()
        # Só marca como processado / avança o rastreador depois do COMMIT (se falhar, tenta de novo no próximo ciclo)
        cOcorrenciasJaProcessadas.update(cProcessadasLote)
        cNovaUltimaVerificacao = cMaiorData
        podarOcorrenciasProcessadas(cNovaUltimaVerificacao)
        dbMqtt.printLog(f"> Sucesso: {cMsgSucesso} nova(s) ocorrência(s) enviada(s) para a fila CLP_MMSGENV!")
    
    except Exception as e:
        dbMqtt.printLog(f"** Erro ao processar AG_MOCOR: {e}")
        if cConexaoMqtt:
            try: cConexaoMqtt.rollback()
            except: pass
        dbClient.fecharConexao()
        dbMqtt.fecharConexao()
        
    finally:
        if cCursorClient:
            try: cCursorClient.close()
            except: pass
        if cCursorMqtt:
            try: cCursorMqtt.close()
            except: pass            
    return cNovaUltimaVerificacao
    
def escolherCorpoJson(nLinhas, nIdJob):
    """
    Normalmente há 1 corpo por CODSTR. Registros gravados por versões anteriores podem ter CODSTR
    repetido (duas mensagens no mesmo milissegundo); nesse caso usa o corpo cujo job confere com o da fila.
    """
    if not nLinhas:
        return None
    if len(nLinhas) == 1:
        return nLinhas[0]
    for cLinha in nLinhas:
        try:
            if str(json.loads(cLinha[1]).get("jobPlannerData_id", "")) == str(nIdJob or ""):
                return cLinha
        except Exception:
            continue
    return nLinhas[0]

def processarMensagem():
    cConexaoMqtt = None
    cCursorMqtt = None
    try:        
        cConexaoMqtt = dbMqtt.obterConexao()
        cCursorMqtt = cConexaoMqtt.cursor()        
        
        cSqlBuscaIds = """
            SELECT CODSTR, JALEU, EXCLUIR, DTI, SEQ_TAREFA, MAQUINA, IDJOB 
            FROM CLP_MMSGREC 
            WHERE JALEU = 'N' 
                AND EXCLUIR = 'N' 
                AND NOT EXISTS (SELECT 1 FROM CLP_MMSGRECL WHERE CLP_MMSGREC.CODSTR=CLP_MMSGRECL.CODSTR) 
            ORDER BY DTI
            LIMIT 1000
        """
        
        cCursorMqtt.execute(cSqlBuscaIds) 
        cRegistrosIds = cCursorMqtt.fetchall()
        
        if len(cRegistrosIds) == 0:
            dbMqtt.printLog("Nenhuma mensagem nova na fila de telemetria.")        
            cConexaoMqtt.commit()
            return
            
        if cLogDetalhado:
            dbMqtt.printLog(f"\n Encontrada(s) {len(cRegistrosIds)} mensagem(ns) pendente(s). Lendo JSONS...")        
        
        cSqlBuscaJson = "SELECT IDMSGMQTT, MEMJS FROM CLP_MMSGRECT WHERE CODSTR = %s "        
        
        cSqlInsertAcompH = """
            INSERT INTO CLP_MACOMPH 
              (CODSTR, IDMSGMQTT, SEQ_TAREFA, MAQUINA, IDJOB, VELMEDCURTA, VELMEDGLOBAL, VELATUAL, CICLOMED, CICLOATUAL, QTDSETUP, QTDLIQ, QTDBRUTA, QTDREFUGO,
               TMPEXEC, TMPPREP, TMPBONS, TMPPARADO, TMPTOTAL, TMPREST, MAQATIVA, BTNCONTAGEM, OEEDISP, OEEDESEMP, OEEQUALID, OEETOTAL)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """ 
        
        cSqlInsertAcomp = """
            INSERT INTO CLP_MACOMP (
                SEQ_TAREFA, MAQUINA, IDJOB, VELMEDCURTA, VELMEDGLOBAL, VELATUAL, 
                CICLOMED, CICLOATUAL, QTDSETUP, QTDLIQ, QTDBRUTA, QTDREFUGO, 
                TMPEXEC, TMPPREP, TMPBONS, TMPPARADO, TMPTOTAL, TMPREST, 
                MAQATIVA, BTNCONTAGEM, OEEDISP, OEEDESEMP, OEEQUALID, OEETOTAL
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            ) ON DUPLICATE KEY UPDATE 
                MAQUINA=VALUES(MAQUINA), IDJOB=VALUES(IDJOB), VELMEDCURTA=VALUES(VELMEDCURTA), 
                VELMEDGLOBAL=VALUES(VELMEDGLOBAL), VELATUAL=VALUES(VELATUAL), 
                CICLOMED=VALUES(CICLOMED), CICLOATUAL=VALUES(CICLOATUAL), 
                QTDSETUP=VALUES(QTDSETUP), QTDLIQ=VALUES(QTDLIQ), QTDBRUTA=VALUES(QTDBRUTA), QTDREFUGO=VALUES(QTDREFUGO), 
                TMPEXEC=VALUES(TMPEXEC), TMPPREP=VALUES(TMPPREP), TMPBONS=VALUES(TMPBONS), TMPPARADO=VALUES(TMPPARADO), 
                TMPTOTAL=VALUES(TMPTOTAL), TMPREST=VALUES(TMPREST), MAQATIVA=VALUES(MAQATIVA), BTNCONTAGEM=VALUES(BTNCONTAGEM), 
                OEEDISP=VALUES(OEEDISP), OEEDESEMP=VALUES(OEEDESEMP), OEEQUALID=VALUES(OEEQUALID), OEETOTAL=VALUES(OEETOTAL)
        """
                
        cSqlInsertLeitura = "INSERT INTO CLP_MMSGRECL (CODSTR, SEQ_TAREFA, MAQUINA, DTLEITURA) VALUES (%s, 0, 0, %s)"
        cSqlQuarentena = "UPDATE CLP_MMSGREC SET EXCLUIR = 'S' WHERE CODSTR = %s"
                    
        cMsgSucesso = 0
        cMsgErro = 0
        cAgora = datetime.now()
        
        cUltimoRegistro = {}
        cAtualizacoesCache = {}
        
        for reg in cRegistrosIds:
            cCodstr = reg[0]
            cSeqTarefa = reg[4]
            cMaquina = reg[5]
            
            cCursorMqtt.execute(cSqlBuscaJson, (cCodstr,))
            cLinhasJson = cCursorMqtt.fetchall()  # fetchall: nunca deixa resultado pendente no cursor
            cResultadoJson = escolherCorpoJson(cLinhasJson, reg[6])
            
            if not cResultadoJson:
                cMsgErro += 1
                dbMqtt.printLog(f"[Quarentena] Mensagem {cCodstr} sem corpo JSON! Isolando...")
                cCursorMqtt.execute(cSqlQuarentena, (cCodstr,))
                continue
            
            cIdMsgMqtt = cResultadoJson[0]
            cJson = cResultadoJson[1]
            
            # Cada mensagem roda isolada num SAVEPOINT: se ela falhar, desfaz-se SOMENTE ela,
            # preservando as mensagens boas já processadas neste mesmo lote.
            cCursorMqtt.execute("SAVEPOINT SP_MSG")
            try:
                cDados = json.loads(cJson)
                if not isinstance(cDados, dict):
                    raise ValueError(f"payload não é um objeto JSON ({type(cDados).__name__})")
                
                cIdJob = cDados.get("jobPlannerData_id", "")
                cTmpJOB = f"{cSeqTarefa}|{cMaquina}|{cIdJob}"                
        
                cTrabalhoAtivo = 'S' if cDados.get("jobRunning") else 'N'
                cBotaoContagem = 'S' if cDados.get("cntButton") else 'N'
                cBlocoOee = cDados.get("oee") or {}
                if not isinstance(cBlocoOee, dict):
                    raise ValueError("bloco 'oee' não é um objeto JSON")
                
                cValoresInsert = (
                    cCodstr,
                    cIdMsgMqtt,
                    cSeqTarefa,
                    cMaquina,
                    cDados.get("jobPlannerData_id", ""),
                    cDados.get("avgSpdShortTerm", 0.0),
                    cDados.get("averageSpeed", 0.0),
                    cDados.get("actualSpeed", 0.0),
                    cDados.get("averageCycle", 0.0),
                    cDados.get("actualCycle", 0.0),
                    cDados.get("setupCounter", 0.0),
                    cDados.get("netCnt", 0.0),
                    cDados.get("bruttoCnt", 0.0),
                    cDados.get("wasteCnt", 0.0),
                    cDados.get("setupTime", 0.0),
                    cDados.get("runTime", 0.0),
                    cDados.get("stopTime", 0.0),
                    cDados.get("goodsTime", 0.0),
                    cDados.get("elapsedTime", 0.0),
                    cDados.get("remainingTime", 0.0),
                    cTrabalhoAtivo,
                    cBotaoContagem,                        
                    cBlocoOee.get("availability", 0.0),
                    cBlocoOee.get("performance", 0.0),
                    cBlocoOee.get("quality", 0.0),
                    cBlocoOee.get("oee", 0.0),                        
                )
                                    
                cValoresInsertAcomp = cValoresInsert[2:]                    
                
                cCursorMqtt.execute(cSqlInsertAcompH, cValoresInsert)                  
                cCursorMqtt.execute(cSqlInsertLeitura, (cCodstr, cAgora,))
                cCursorMqtt.execute("RELEASE SAVEPOINT SP_MSG")
                
                # Só depois de gravada com sucesso a mensagem passa a valer para o estado atual / cache
                cUltimoRegistro[cTmpJOB] = cValoresInsertAcomp
                cAtualizacoesCache[cTmpJOB] = dict(zip(cColunasAcomp, cValoresInsertAcomp))
                
                cMsgSucesso += 1                                           
            except (mysql.connector.errors.OperationalError, mysql.connector.errors.InterfaceError):
                # Falha de conexão não é culpa da mensagem: aborta o ciclo SEM quarentena (será reprocessada)
                raise
            except Exception as erroLote:
                cMsgErro += 1
                dbMqtt.printLog(f"** Erro ao processar Lote {cCodstr}: {erroLote}")    
                cCursorMqtt.execute("ROLLBACK TO SAVEPOINT SP_MSG")
                cCursorMqtt.execute(cSqlQuarentena, (cCodstr,))
                dbMqtt.printLog(f"[Quarentena] Mensagem {cCodstr} corrompida foi blindada e excluída da fila.")
        
        for valoresTupla in cUltimoRegistro.values():
            cCursorMqtt.execute(cSqlInsertAcomp, valoresTupla)
        
        # Um único COMMIT grava histórico, marcas de leitura, quarentenas e o estado atual de forma atômica
        cConexaoMqtt.commit()
        cCacheMaquinasMemoria.update(cAtualizacoesCache)
                                                                            
        if cMsgSucesso > 0 or cMsgErro > 0:
            if cLogDetalhado:
                dbMqtt.printLog(f"Ciclo concluído: {cMsgSucesso} lote(s) processado(s) com sucesso | {cMsgErro} erro(s).")                    
                                                                                                                                                                                                                                                
    except Exception as e:
        dbMqtt.printLog(f"** Erro geral ao processar a telemetria: {e}")
        if cConexaoMqtt:
            try: cConexaoMqtt.rollback()
            except: pass
        dbMqtt.fecharConexao()
        
    finally:
        if cCursorMqtt:
            try: cCursorMqtt.close()
            except: pass

def carregarCacheInicial():
    """
    Pré-carrega o cache em RAM com o último estado gravado (CLP_MACOMP) das tarefas liberadas,
    para que a API não fique vazia após um reinício do serviço.
    Linhas sem telemetria real (ex.: registro inicial criado manualmente) são ignoradas.
    """
    cMapa = dbMqtt.carregarTarefasAtivas()
    if not cMapa:
        dbMqtt.printLog("Cache inicial: nenhuma tarefa liberada encontrada (ou banco indisponível).")
        return
    
    cCursor = None
    try:
        cConexao = dbMqtt.obterConexao()
        cCursor = cConexao.cursor()
        cCursor.execute(f"SELECT {', '.join(cColunasAcomp)} FROM CLP_MACOMP WHERE OEETOTAL IS NOT NULL")
        cQtd = 0
        for cLinha in cCursor.fetchall():
            cRegistro = dict(zip(cColunasAcomp, cLinha))
            if cMapa.get(str(cRegistro["SEQ_TAREFA"])) != cRegistro["MAQUINA"]:
                continue
            cTmpJOB = f"{cRegistro['SEQ_TAREFA']}|{cRegistro['MAQUINA']}|{cRegistro['IDJOB']}"
            cCacheMaquinasMemoria.setdefault(cTmpJOB, cRegistro)
            cQtd += 1
        cConexao.commit()
        dbMqtt.printLog(f"Cache inicial carregado da CLP_MACOMP: {cQtd} máquina(s)/job(s).")
    except Exception as e:
        dbMqtt.printLog(f"** Aviso: não foi possível pré-carregar o cache: {e}")
        dbMqtt.fecharConexao()
    finally:
        if cCursor:
            try: cCursor.close()
            except: pass

def iniciarServico():
    cTempoSemaforo = 30
    cDirProjeto = fDirAtual
    
    dbMqtt.printLog("=" * 60)
    dbMqtt.printLog(f"=== INICIANDO TgiBootInter - DATA: {datetime.now().strftime('%d/%m/%Y')} - VERSÃO MYSQL ===")
    dbMqtt.printLog("=" * 60)
    
    if not dbMqtt.verificaSemaforo(cTempoSemaforo, cDirProjeto):
        dbMqtt.printLog("Semáforo bloqueado por outra instância. Encerrando...")            
        sys.exit()
        
    try:
        dbMqtt.printLog(f"Semáforo garantido por {cTempoSemaforo} minutos...")
        
        cHoraParada = datetime.now() + timedelta(minutes=cTempoSemaforo)
        carregarOcorrenciasJaEnviadas()
        cDataRastreadorOcorrencia = datetime.now() - JANELA_STARTUP_OCORRENCIAS
        
        while datetime.now() < cHoraParada:
            processarMensagem()
            cDataRastreadorOcorrencia = processarOcorrencias(cDataRastreadorOcorrencia)
            time.sleep(5)
            
        dbMqtt.printLog("Tempo de ciclo finalizado. Preparando para reiniciar rotina.")
        
    except KeyboardInterrupt:
        dbMqtt.printLog("\nServiço finalizado pelo usuário")
    
    except Exception as e:
        dbMqtt.printLog(f"** Erro inesperado no motor do Interpretador: {e}")
        
    finally:
        dbMqtt.printLog("Liberando semáforo e fechando conexões...")
        dbMqtt.liberarSemaforo()
        dbClient.fecharConexao()
        dbMqtt.fecharConexao()
        
        dbMqtt.printLog("=" * 60)
        dbMqtt.printLog(f"=== TÉRMINO TgiBootInter - DATA: {datetime.now().strftime('%d/%m/%Y')} ===")
        dbMqtt.printLog("=" * 60)        
        sys.exit()
        
if __name__ == "__main__":
    carregarCacheInicial()
    ligarServidorWeb(dbMqtt, cCacheMaquinasMemoria)    
    iniciarServico()