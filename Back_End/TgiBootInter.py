import os
import sys
import json
import time
import random
import uuid
from datetime import datetime, timedelta
from LibDB import GerenciadorBanco
from LibFlask import ligarServidorWeb

if getattr(sys, 'frozen', False):
    fDirAtual = os.path.dirname(sys.executable)
else:
    fDirAtual = os.path.dirname(os.path.abspath(__file__))

cNomeScript = os.path.splitext(os.path.basename(__file__))[0].capitalize()

fAliasOrigem = "[TELEMETRIA_E2E]"
fArquivoCfg = os.path.join(fDirAtual, "config.ini")
fJsonOrigemStr = ""

if os.path.exists(fArquivoCfg):
    fDentroOrigem = False
    
    try:
        with open(fArquivoCfg, "r", encoding="utf-8", errors="ignore") as f:
            for linha in f:
                linha = linha.strip()
                if not linha: continue

                if linha.startswith("[") and linha.endswith("]"):
                    fDentroOrigem = (linha == fAliasOrigem)
                    continue

                if fDentroOrigem and linha.upper().startswith("CLPJS="):
                    fJsonOrigemStr = linha.split("=", 1)[1].strip()
                    
    except Exception as e:
        print(f"** Erro inesperado ao ler o config.ini: {e}")
        sys.exit()
else:
    print("Arquivo config.ini não encontrado.")
    sys.exit()

if fJsonOrigemStr == "":
    print("Script interrompido: Faltou alguma configuração dos bancos no CFG.")
    sys.exit()
    
try:
    print("Iniciando conexões com os bancos de dados (MySQL)...")    
    
    cDadosOrigem = json.loads(fJsonOrigemStr.replace("'", '"').replace("\\", "\\\\"))
    
    cDadosClient = cDadosOrigem.get("dbClient", {})
    cDadosMqtt = cDadosOrigem.get("dbMqtt", {})
    cLogDetalhado = cDadosOrigem.get("LogDetalhado", False)
    
    if not cDadosClient or not cDadosMqtt:
        print("** Erro: Estrutura do JSON incompleta. Faltando dbClient ou dbMqtt.")
        sys.exit()
        
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

def processarOcorrencias(cUltimaVerificacao):
    cConexaoClient = None
    cCursorClient = None
    cConexaoMqtt = None
    cCursorMqtt = None    
    cNovaUltimaVerificacao = cUltimaVerificacao
    
    try:
        cConexaoClient = dbClient.obterConexao()
        cCursorClient = cConexaoClient.cursor()
        
        cSqlBusca = """
            SELECT
                M.SEQ_OCORRE, M.INICIO, M.CODTPOCOR, M.SEQ_TAREFA,
                C.EMPRESA, C.NUMPED, C.NUMITEM, C.NUMTIRAG, T.MAQUINA
            FROM AG_MOCOR M
            LEFT JOIN AG_MTARC C ON M.SEQ_TAREFA = C.SEQ_TAREFA
            LEFT JOIN AG_MTAR T ON M.SEQ_TAREFA = T.SEQ_TAREFA
            WHERE M.INICIO > %s
            ORDER BY M.INICIO ASC        
        """
        cCursorClient.execute(cSqlBusca, (cUltimaVerificacao,))
        cOcorrencias = cCursorClient.fetchall()
        
        if not cOcorrencias:
            cConexaoClient.commit()
            return cNovaUltimaVerificacao
        
        cAgora = datetime.now()
        
        cConexaoMqtt = dbMqtt.obterConexao()
        cCursorMqtt = cConexaoMqtt.cursor()        
        
        cSqlInsertEnv = "INSERT INTO CLP_MMSGENV (CODSTR, SEQ_TAREFA, MAQUINA, IDJOB, DTI, JAENVIOU, EXCLUIR, TOPICOCPL) VALUES (%s, %s, %s, %s, %s, 'N', 'N', %s)"
        cSqlInsertEnvT = "INSERT INTO CLP_MMSGENVT (CODSTR, IDMSGMQTT, MEMJS) VALUES (%s, %s, %s)"
        
        cMsgSucesso = 0
        
        for ocor in cOcorrencias:
            cSeqOcorrencia = ocor[0]
            cDataOcorrencia = ocor[1]
            cTipoOcorrencia = ocor[2] if ocor[2] else "INDEFINIDO"
            cSeqTarefa = ocor[3] if ocor[3] else 0
            cNumOs = f"{ocor[4]}{ocor[5]}{ocor[6]}{ocor[7]}"
            cNumeroOs = cNumOs if cNumOs else "SEM_OS"
            
            try:
                cMaquina = int(ocor[8]) if ocor[8] else 0
            except ValueError:
                cMaquina = 0
            
            cCodstr = cAgora.strftime("%Y%m%d%H%M%S") + str(random.randint(100000, 999999))    
            cIdMqtt = str(uuid.uuid4())
            cTopico = f"Tgi/BR_SP/Planta1/Ocorrencia/{cMaquina}"
        
            cDictPayload = {
                "id_ocorrencia": cSeqOcorrencia,
                "maquina": cMaquina,
                "job_id": cNumeroOs,
                "descricao": cTipoOcorrencia,
                "data_hora_falha": cDataOcorrencia.strftime("%Y-%m-%d %H:%M:%S"),
                "tipo_mensagem": "ocorrencia_nova"
            }
            
            cJson = json.dumps(cDictPayload)
            
            cCursorMqtt.execute(cSqlInsertEnv, (cCodstr, cSeqTarefa, cMaquina, cNumeroOs, cAgora, cTopico))
            cCursorMqtt.execute(cSqlInsertEnvT, (cCodstr, cIdMqtt, cJson))
            
            if cDataOcorrencia > cNovaUltimaVerificacao:
                cNovaUltimaVerificacao = cDataOcorrencia
                
            cMsgSucesso += 1
        
        cConexaoMqtt.commit()
    
        if cLogDetalhado:
            dbMqtt.printLog(f"> Sucesso: {cMsgSucesso} novas ocorrências repassadas para a fila de envio.")
    
    except Exception as e:
        dbMqtt.printLog(f"** Erro ao processar AG_MOCOR: {e}")
        if cConexaoMqtt: cConexaoMqtt.rollback()
        
    finally:
        if cCursorClient:
            try: cCursorClient.close()
            except: pass
        if cCursorMqtt:
            try: cCursorMqtt.close()
            except: pass            
    return cNovaUltimaVerificacao        

def processarMensagem():
    cConexaoMqtt = None
    cCursorMqtt = None
    try:        
        cConexaoMqtt = dbMqtt.obterConexao()
        cCursorMqtt = cConexaoMqtt.cursor()        
        
        cSqlBuscaIds = """
            SELECT CODSTR, JALEU, EXCLUIR, DTI, SEQ_TAREFA, MAQUINA 
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
                    
        cMsgSucesso = 0
        cMsgErro = 0
        cAgora = datetime.now()
        
        cUltimoRegistro = {}
        
        for reg in cRegistrosIds:
            cCodstr = reg[0]
            cSeqTarefa = reg[4]
            cMaquina = reg[5]
            
            cCursorMqtt.execute(cSqlBuscaJson, (cCodstr,))
            cResultadoJson = cCursorMqtt.fetchone()
            
            if cResultadoJson:
                cIdMsgMqtt = cResultadoJson[0]
                cJson = cResultadoJson[1]
                
                try:
                    cDados = json.loads(cJson)
                    
                    cIdJob = cDados.get("jobPlannerData_id", "")
                    cTmpJOB = f"{cSeqTarefa}|{cMaquina}|{cIdJob}"                
            
                    cTrabalhoAtivo = 'S' if cDados.get("jobRunning") else 'N'
                    cBotaoContagem = 'S' if cDados.get("cntButton") else 'N'
                    cBlocoOee = cDados.get("oee", {})
                    
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
                    
                    cDadosComNomes = dict(zip(cColunasAcomp, cValoresInsertAcomp))
                    cCacheMaquinasMemoria[cTmpJOB] = cDadosComNomes
                    
                    cUltimoRegistro[cTmpJOB] = cValoresInsertAcomp
                    
                    cCursorMqtt.execute(cSqlInsertAcompH, cValoresInsert)                  
                    cCursorMqtt.execute(cSqlInsertLeitura, (cCodstr, cAgora,))                                                                                                                                                                                                                          
                    
                    cMsgSucesso += 1                                           
                except Exception as erroLote:
                    cMsgErro += 1
                    dbMqtt.printLog(f"** Erro ao processar Lote {cCodstr}: {erroLote}")    
                    if cCursorMqtt: cCursorMqtt.rollback()
                    
                    try:
                        cCursorMqtt.execute("UPDATE CLP_MMSGREC SET EXCLUIR = 'S' WHERE CODSTR = %s", (cCodstr,))
                        cConexaoMqtt.commit()
                        dbMqtt.printLog(f"[Quarentena] Mensagem {cCodstr} corrompida foi blindada e excluída da fila.")
                    except:
                        cConexaoMqtt.rollback()      
            else:
                dbMqtt.printLog(f"[Quarentena] Mensagem {cCodstr} sem corpo JSON! Isolando...")
                try:
                    cCursorMqtt.execute("UPDATE CLP_MMSGREC SET EXCLUIR = 'S' WHERE CODSTR = %s", (cCodstr,))
                    cConexaoMqtt.commit()
                except:
                    if cConexaoMqtt: cConexaoMqtt.rollback()
        
        if cUltimoRegistro:
            try:
                for valoresTupla in cUltimoRegistro.values():
                    cCursorMqtt.execute(cSqlInsertAcomp, valoresTupla)
                    
                cConexaoMqtt.commit()                          
            except Exception as e:
                dbMqtt.printLog(f"** Erro ao salvar estado atual: {e}")
                if cConexaoMqtt: cConexaoMqtt.rollback()                                                              
                                                                            
        if cMsgSucesso > 0 or cMsgErro > 0:
            if cLogDetalhado:
                dbMqtt.printLog(f"Ciclo concluído: {cMsgSucesso} lote(s) processado(s) com sucesso | {cMsgErro} erro(s).")                    
                                                                                                                                                                                                                                                
    except Exception as e:
        dbMqtt.printLog(f"** Erro geral ao processar a telemetria: {e}")
        
    finally:
        if cCursorMqtt:
            try: cCursorMqtt.close()
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
        cDataRastreadorOcorrencia = datetime.now() - timedelta(minutes=1)
        
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
    ligarServidorWeb(dbMqtt, cCacheMaquinasMemoria)    
    iniciarServico()