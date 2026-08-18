import os
import sys
import json
import time
import random
from datetime import datetime, timedelta
from LibDB import GerenciadorBanco
from LibFlask import ligarServidorWeb

fDirAtual = os.path.dirname(os.path.abspath(__file__))

cNomeScript = os.path.splitext(os.path.basename(__file__))[0].capitalize()

fAliasOrigem = "[MENDES_ZERADO]"

fArquivoCfg = os.path.join(fDirAtual, "GRP.cfg")

if os.path.exists(fArquivoCfg):
    fDentroOrigem = False
    fDentroDestino = False
    
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
        print(f"** Erro inesperado ao ler o GRP.cfg: {e}")
        sys.exit()
else:
    print("Arquivo GRP.cfg não encontrado.")
    sys.exit()

if fJsonOrigemStr == "":
    print("Script interrompido: Faltou alguma configuração dos bancos no CFG.")
    sys.exit()
    
def logStartup(nMensagem):
    print(nMensagem)
    try:
        import os
        from datetime import datetime
        cDirAtual = os.path.dirname(os.path.abspath(__file__))
        cPastaLogs = os.path.join(cDirAtual, "logs", "Startup")
        if not os.path.exists(cPastaLogs):
            os.makedirs(cPastaLogs)
            
        cNomeArquivo = f"Log_Startup_{datetime.now().strftime('%d%m%Y')}.txt"
        with open(os.path.join(cPastaLogs, cNomeArquivo), "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().strftime('%H:%M:%S')} - {nMensagem}\n")
    except:
        pass
    
logStartup("=" * 60)
logStartup(f"=== INÍCIO INTERPRETADOR - DATA: {datetime.now().strftime('%d/%m/%Y')} - VERSÃO 2026 1a ===")
logStartup("=" * 60)        
    
try:
    print("Iniciando conexões com os bancos de dados...")    
    
    cDadosOrigem = json.loads(fJsonOrigemStr.replace("'", '"').replace("\\", "\\\\"))
    
    cDadosClp = cDadosOrigem.get("dbClp", {})
    
    if "dbAcomp" in cDadosOrigem and cDadosOrigem["dbAcomp"]:
        cDadosAcomp = cDadosOrigem["dbAcomp"]
    else:
        cDadosAcomp = cDadosClp
        logStartup("AVISO: Chave 'dbAcomp' ausente no CFG. Utilizando o banco principal (dbClp) para acompanhamento.")
                
    if not cDadosClp or not cDadosAcomp:
        print("** Erro: Estrutura do JSON incompleta. Faltando dbClp ou dbAcomp.")
        sys.exit()
        
    fChaveInt: int = random.randint(1, 999999) 
    dbOrigem = GerenciadorBanco(
        nHostBanco=cDadosClp['hDB'], 
        nCaminhoBanco=cDadosClp['db'], 
        nUsuarioBanco=cDadosClp['uDB'], 
        nSenhaBanco=cDadosClp['pDB'], 
        nNomeProjeto="INTERPRETADOR_ORIG", 
        nChaveInt=fChaveInt,
        nSistemaLog=cNomeScript
    )
    
    fChaveInt: int = random.randint(1, 999999) 
    dbDestino = GerenciadorBanco(
        nHostBanco=cDadosAcomp['hDB'], 
        nCaminhoBanco=cDadosAcomp['db'], 
        nUsuarioBanco=cDadosAcomp['uDB'], 
        nSenhaBanco=cDadosAcomp['pDB'], 
        nNomeProjeto="INTERPRETADOR_DEST", 
        nChaveInt=fChaveInt,
        nSistemaLog=cNomeScript
    )
    
    print("Conexões instanciadas com sucesso!")

except Exception as e:
    print(f"** Erro ao instanciar os bancos: {e}")
    sys.exit()   
    
cCacheMaquinasMemoria = {}       
cColunasAcomp = ["SEQ_TAREFA", "MAQUINA", "IDJOB", "VELMEDCURTA", "VELMEDGLOBAL", "VELATUAL", 
                 "CICLOMED", "CICLOATUAL", "QTDSETUP", "QTDLIQ", "QTDBRUTA", "QTDREFUGO", 
                 "TMPEXEC", "TMPPREP", "TMPBONS", "TMPPARADO", "TMPTOTAL", "TMPREST", 
                 "MAQATIVA", "BTNCONTAGEM", "OEEDISP", "OEEDESEMP", "OEEQUALID", "OEETOTAL"]

def processarMensagem():
    cConexaoOrigem = None
    cConexaoDestino = None
    cCursorOrigem = None
    cCursorDestino = None
    try:
        cConexaoOrigem = dbOrigem.obterConexao()       
        cCursorOrigem = cConexaoOrigem.cursor()
        
        cConexaoDestino = dbDestino.obterConexao()       
        cCursorDestino = cConexaoDestino.cursor()        
        
        cSqlBuscaIds = """
            SELECT FIRST 1000 CODSTR, JALEU, EXCLUIR, DTI, SEQ_TAREFA, MAQUINA 
            FROM CLP_MMSGREC 
            WHERE JALEU = 'N' 
                AND EXCLUIR = 'N' 
                AND NOT EXISTS (SELECT 1 FROM CLP_MMSGRECL WHERE CLP_MMSGREC.CODSTR=CLP_MMSGRECL.CODSTR) 
            ORDER BY DTI
        """
        
        cCursorOrigem.execute(cSqlBuscaIds) 
        cRegistrosIds = cCursorOrigem.fetchall()
        
        if len(cRegistrosIds) == 0:
            dbOrigem.printLog("Nenhuma mensagem nova na fila de telemetria.")        
            return
        dbOrigem.printLog(f"\n Encontrada {len(cRegistrosIds)} mensagens pendentes. Lendo JSONS...")        
        
        cSqlBuscaJson = "SELECT IDMSGMQTT, MEMJS FROM CLP_MMSGRECT WHERE CODSTR = ? "        
        
        cSqlInsertAcompH = """
            INSERT INTO CLP_MACOMPH 
              (CODSTR, IDMSGMQTT, SEQ_TAREFA, MAQUINA, IDJOB, VELMEDCURTA, VELMEDGLOBAL, VELATUAL, CICLOMED, CICLOATUAL, QTDSETUP, QTDLIQ, QTDBRUTA, QTDREFUGO,
               TMPEXEC, TMPPREP, TMPBONS, TMPPARADO, TMPTOTAL, TMPREST, MAQATIVA, BTNCONTAGEM, OEEDISP, OEEDESEMP, OEEQUALID, OEETOTAL)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """ 
        
        cSqlInsertAcomp = """
            UPDATE OR INSERT INTO CLP_MACOMP (
                SEQ_TAREFA, MAQUINA, IDJOB, VELMEDCURTA, VELMEDGLOBAL, VELATUAL, 
                CICLOMED, CICLOATUAL, QTDSETUP, QTDLIQ, QTDBRUTA, QTDREFUGO, 
                TMPEXEC, TMPPREP, TMPBONS, TMPPARADO, TMPTOTAL, TMPREST, 
                MAQATIVA, BTNCONTAGEM, OEEDISP, OEEDESEMP, OEEQUALID, OEETOTAL
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            ) MATCHING (SEQ_TAREFA, MAQUINA)
        """
                
        cSqlInsertLeitura = "INSERT INTO CLP_MMSGRECL (CODSTR, SEQ_TAREFA, MAQUINA, DTLEITURA) VALUES (?, 0, 0, ?)"
                    
        cMsgSucesso = 0
        cMsgErro = 0
        cAgora = datetime.now()
        
        cUltimoRegistro = {}
        
        for reg in cRegistrosIds:
            cCodstr = reg[0]
            cSeqTarefa = reg[4]
            cMaquina = reg[5]
            
            cCursorOrigem.execute(cSqlBuscaJson, (cCodstr,))
            cResultadoJson = cCursorOrigem.fetchone()
            
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
                    
                    cCursorDestino.execute(cSqlInsertAcompH, cValoresInsert)                  
                    cCursorOrigem.execute(cSqlInsertLeitura, (cCodstr,cAgora,))                                                                                                    
                    
                    cMsgSucesso += 1                                           
                except Exception as erroLote:
                    cMsgErro += 1
                    dbOrigem.printLog(f"** Erro ao processar Lote {cCodstr}: {erroLote}")    
                    if cConexaoDestino: cConexaoDestino.rollback()
                    
                    if cConexaoOrigem:
                        cConexaoOrigem.rollback()  
                        try:
                            cCursorOrigem.execute("UPDATE CLP_MMSGREC SET EXCLUIR = 'S' WHERE CODSTR = ?", (cCodstr,))
                            cConexaoOrigem.commit()
                            dbOrigem.printLog(f"[Quarentena] Mensagem {cCodstr} corrompida foi blindade e excluida da fila.")
                        except:
                            cConexaoOrigem.rollback()      
            else:
                dbOrigem.printLog(f"[Quarentena] Mensagem {cCodstr} sem corpo JSON! Isolando...")
                try:
                    cCursorOrigem.execute("UPDATE CLP_MMSGREC SET EXCLUIR = 'S' WHERE CODSTR = ?", (cCodstr,))
                    cConexaoOrigem.commit()
                except:
                    if cConexaoOrigem: cConexaoOrigem.rollback()
        
        if cUltimoRegistro:
            try:
                for valoresTupla in cUltimoRegistro.values():
                    cCursorDestino.execute(cSqlInsertAcomp, valoresTupla)
                    
                cConexaoDestino.commit()
                cConexaoOrigem.commit()            
            except Exception as e:
                dbOrigem.printLog(f"** Erro ao salvar estado atual: {e}")
                if cConexaoDestino: cConexaoDestino.rollback()
                if cConexaoOrigem: cConexaoOrigem.rollback()                
                                            
        if cMsgSucesso > 0 or cMsgErro > 0:
            dbOrigem.printLog(f"Ciclo concluído: {cMsgSucesso} lote(s) processado(s) com sucesso | {cMsgErro} erro(s).")                    
                                                                                                                      
    except Exception as e:
        dbOrigem.printLog(f"** Erro geral ao processar a telemetria: {e}")
        
    finally:
        if cCursorOrigem:
            try: cCursorOrigem.close()
            except: pass
        if cCursorDestino:
            try: cCursorDestino.close()
            except: pass                                    

def iniciarServico():
    cTempoSemaforo = 30
    cDirProjeto = fDirAtual
    
    if not dbDestino.verificaSemaforo(cTempoSemaforo, cDirProjeto):
        dbOrigem.printLog("Semáforo bloqueado por outra instância. Encerrando...")            
        sys.exit()
        
    try:
        dbOrigem.printLog(f"Semáforo garantido! Iniciando Interpretador pot {cTempoSemaforo} minutos...")
        
        cHoraParada = datetime.now() + timedelta(minutes=cTempoSemaforo)
        
        while datetime.now() < cHoraParada:
            processarMensagem()
            time.sleep(5)
            
        dbOrigem.printLog("Tempo de ciclo finalizado. Preparando para reiniciar rotina.")
        
    except KeyboardInterrupt:
        dbOrigem.printLog("\nServiço finalizado pelo usuário")
    
    except Exception as e:
        dbOrigem.printLog(f"** Erro inesperado no motor do Interpretador: {e}")
        
    finally:
        dbOrigem.printLog("Liberando semáforo e fechando conexões...")
        dbDestino.liberarSemaforo()
        dbOrigem.fecharConexao()
        dbDestino.fecharConexao()
        sys.exit()
        
if __name__ == "__main__":
    ligarServidorWeb(dbDestino, cCacheMaquinasMemoria)
    
    iniciarServico()