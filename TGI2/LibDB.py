import os
import json
import time
import threading
from datetime import datetime
import mysql.connector
from mysql.connector import Error

class GerenciadorBanco:
    def __init__(self, nHostBanco: str, nNomeBanco: str, nUsuarioBanco: str, nSenhaBanco: str, nNomeProjeto: str, nChaveInt: int, nSistemaLog: str):
        self.fHostBanco: str = nHostBanco
        self.fNomeBanco: str = nNomeBanco 
        self.fUsuarioBanco: str = nUsuarioBanco
        self.fSenhaBanco: str = nSenhaBanco
        self.fNomeProjeto: str = nNomeProjeto
        self.fChaveInt: int = nChaveInt
        
        self.fSistemaLog = nSistemaLog
        self.fDirProjeto: str = os.path.dirname(os.path.abspath(__file__))       
                
        self.fMochilaThread = threading.local()        
        
    def printLog(self, nMensagem: str) -> None:        
        cHoje = datetime.now()        
        cHorario = cHoje.strftime("%H:%M:%S.%f")[:-3]
        cMensagemFormatada = f"[{cHorario}] {nMensagem}"
        print(cMensagemFormatada)       
    
        try:
            cNomeArquivo = f"Log{self.fSistemaLog}{cHoje.strftime('%Y%m%d')}.txt"
            cPastaLogs = os.path.join(self.fDirProjeto, "logs", self.fSistemaLog)
            if not os.path.exists(cPastaLogs):
                os.makedirs(cPastaLogs)
                
            cCaminhoCompleto = os.path.join(cPastaLogs, cNomeArquivo)
            with open(cCaminhoCompleto, "a", encoding="utf-8") as f:
                f.write(cMensagemFormatada + "\n")
        
        except Exception as e:
            print(f"[{cHoje.strftime('%H:%M:%S')}] ** Erro interno ao tentar salvar no TXT: {e}")        
        
    def obterConexao(self):
        if not hasattr(self.fMochilaThread, 'fConDB') or self.fMochilaThread.fConDB is None:
            self.fMochilaThread.fConDB = mysql.connector.connect(
                host=self.fHostBanco, 
                database=self.fNomeBanco, 
                user=self.fUsuarioBanco, 
                password=self.fSenhaBanco, 
                charset='utf8mb4'
            )
            self.fMochilaThread.fUsosDB = 0
        else:
            try:
                self.fMochilaThread.fConDB.ping(reconnect=True, attempts=1, delay=0)
            except Error:
                self.fMochilaThread.fConDB = mysql.connector.connect(
                    host=self.fHostBanco, 
                    database=self.fNomeBanco, 
                    user=self.fUsuarioBanco, 
                    password=self.fSenhaBanco, 
                    charset='utf8mb4'
                )

        self.fMochilaThread.fUsosDB += 1
        
        if self.fMochilaThread.fUsosDB > 1000:
            self.printLog("\nReciclando conexão com o MySQL (1000 usos atingidos)...")
            
            try:
                self.fMochilaThread.fConDB.close()
            except Exception:
                pass
            
            self.fMochilaThread.fConDB = mysql.connector.connect(
                host=self.fHostBanco, 
                database=self.fNomeBanco, 
                user=self.fUsuarioBanco, 
                password=self.fSenhaBanco, 
                charset='utf8mb4'
            )
            self.fMochilaThread.fUsosDB = 1
            
        return self.fMochilaThread.fConDB
    
    def fecharConexao(self):
        if hasattr(self.fMochilaThread, 'fConDB') and self.fMochilaThread.fConDB is not None:
            try:
                self.fMochilaThread.fConDB.close()
            except Exception:
                pass
        self.fMochilaThread.fConDB = None
        self.fMochilaThread.fUsosDB = 0
    
    def verificaSemaforo(self, nTempoSemaforo: int, nDirProjeto: str) -> bool:
        try:
            cConexao = self.obterConexao()            
            cCursor = cConexao.cursor()
            
            cNomeProjLim = self.fNomeProjeto[:50]
            cDirProjLim = nDirProjeto[:200]
            
            cPossoExecutar = False
            
            cSqlBusca = "SELECT QUEMINI, DTINI FROM CLP_MSEMAF WHERE QUEMINI = %s AND DTINI IS NOT NULL AND DTFIM IS NULL ORDER BY DTINI DESC"
            cCursor.execute(cSqlBusca, (cNomeProjLim,))
            cRegistros = cCursor.fetchall()
            
            if len(cRegistros) == 0:
                cPossoExecutar = True
            else:
                cZumbiMorto = False
                for reg in cRegistros:
                    cDtIni = reg[1]    
                    cMinutosPassados = (datetime.now() - cDtIni).total_seconds() / 60
                    
                    if cMinutosPassados > nTempoSemaforo:
                        self.printLog(f"Zumbi detectado ({cMinutosPassados:.1f} min). Enterrando processo antigo...")
                        
                        cDtLog = datetime.now()
                        cCodstrLog = cDtLog.strftime("%Y%m%d%H%M%S") + cDtLog.strftime("%f")[:3]
                        self.registraLog(cCodstrLog, "AVISO SEMAFORO", f"Zumbi detectado e removido. Estava travado há {cMinutosPassados:.1f} min.", 3, cDtLog)
                        
                        cDtFim = datetime.now()
                        cSqlMataZumbi = "UPDATE CLP_MSEMAF SET DTFIM = %s WHERE QUEMINI = %s AND DTINI = %s"
                        cCursor.execute(cSqlMataZumbi, (cDtFim, cNomeProjLim, cDtIni))
                        cZumbiMorto = True
                    else:
                        self.printLog(f"Outro leitor/Envio vivo detectado (rodando há {cMinutosPassados:.1f} min). Abortando.")    
                        return False
                
                if cZumbiMorto:
                    cConexao.commit()
                    cPossoExecutar = True
            
            if cPossoExecutar:
                cDtIni = datetime.now()
                cSqlInsere = "INSERT INTO CLP_MSEMAF (QUEMINI, DTINI, DTFIM, TMPSEMAF, DIRINIC, INTRDM) VALUES (%s, %s, NULL, 30, %s, %s)"            
                cCursor.execute(cSqlInsere, (cNomeProjLim, cDtIni, cDirProjLim, self.fChaveInt))
                cConexao.commit()
                
                time.sleep(0.1)
                
                fSqlDesempate = "SELECT INTRDM FROM CLP_MSEMAF WHERE QUEMINI = %s AND DTINI IS NOT NULL AND DTFIM IS NULL ORDER BY DTINI ASC"
                cCursor.execute(fSqlDesempate, (cNomeProjLim,))
                fFila = cCursor.fetchall()
                
                if len(fFila) > 0:
                    fPrimeiroIntrdm = fFila[0][0]
                    if fPrimeiroIntrdm != self.fChaveInt:
                        self.printLog("Perdi a corrida de concorrência. Encerrando processo...")
                        cDtFim = datetime.now()
                        cSqlSuicidio = "UPDATE CLP_MSEMAF SET DTFIM = %s WHERE QUEMINI = %s AND INTRDM = %s"
                        cCursor.execute(cSqlSuicidio, (cDtFim, cNomeProjLim, self.fChaveInt))
                        cConexao.commit()
                        cCursor.close()
                        return False
                    else:
                        self.printLog("Semáforo travado com sucesso!")
                        cCursor.close()
                        return True
            cCursor.close()
            return False 
        except Exception as e:
            self.printLog(f"** Erro no controle do Semáforo: {e}")
            self.fecharConexao()
            return False
 
    def liberarSemaforo(self) -> None:
        try:
            self.fecharConexao()
            cConexao = self.obterConexao()
            cCursor = cConexao.cursor()            
            cDtFim = datetime.now()
            cSqlLiberar = "UPDATE CLP_MSEMAF SET DTFIM = %s WHERE QUEMINI = %s AND INTRDM = %s"
            cCursor.execute(cSqlLiberar, (cDtFim, self.fNomeProjeto[:50], self.fChaveInt))
            cConexao.commit()
            self.printLog("Semáforo liberado com sucesso.")
            cCursor.close()
        except Exception:    
            pass   
        
    def registraLog(self, nCodStr: str, nTplogStr: str, nObsLog: str, nTpLog: int, nDti: datetime ) -> None:    
        cConexaoLog = None
        try:
            cConexaoLog = self.obterConexao()
            cCursorLog = cConexaoLog.cursor() 
            
            cSqlLog = "INSERT INTO CLP_MLOG (CODSTR, DTI, USUDB, TPLOG, TPLOGSTR, TABELA, PROCESSO, DESCRICAO, OBSLOG) VALUES (%s, %s, %s, %s, %s, '', '', '', %s)"
            cCursorLog.execute(cSqlLog, (nCodStr, nDti, self.fUsuarioBanco, nTpLog, nTplogStr, nObsLog))
            cConexaoLog.commit()
            cCursorLog.close()
        
        except Exception as erro_fatal:
            self.printLog(f"** ERRO FATAL AO GRAVAR LOG: {erro_fatal}")
            if cConexaoLog:
                try:
                    cConexaoLog.rollback()
                except Exception:
                    pass    
            self.fecharConexao()
    
    def insertTblRec(self, nCodstr: str, nTopicoFinal: str, nTopicoMsg: str, nJsonRecebido: str, nIdMsg: int, nDti: datetime, nSeqTarefa: int, nDeletar: bool = False, nLogDetalhado: bool = False) -> None:
        cConexao = None        
        try:
            cConexao = self.obterConexao()
            cCursor = cConexao.cursor()
            cIdJob = ""
            
            try:
                cDadosJson = json.loads(nJsonRecebido)
                cIdJob = str(cDadosJson.get("jobPlannerData_id", ""))
            except Exception:
                pass
            
            cSqlControle = "INSERT INTO CLP_MMSGREC (CODSTR, DTI, JALEU, DTLEITURA, EXCLUIR, TOPICOFNL, TOPICOCPL, USUDB, SEQ_TAREFA, MAQUINA, IDJOB) VALUES (%s, %s, 'N', NULL, 'N', %s, %s, %s, %s, %s, %s)"
            cCursor.execute(cSqlControle, (nCodstr, nDti, nTopicoFinal, nTopicoMsg, self.fUsuarioBanco, nSeqTarefa, nSeqTarefa, cIdJob))
            
            cSqlDados = "INSERT INTO CLP_MMSGRECT (CODSTR, IDMSGMQTT, MEMJS) VALUES (%s, %s, %s)"
            cCursor.execute(cSqlDados, (nCodstr, nIdMsg, nJsonRecebido))                    
            cConexao.commit()
            
            if nLogDetalhado:
                self.printLog(f"Sucesso: Tópico '{nTopicoMsg}' inserido.")
            
            if nDeletar:
                cSqlDeletePai = "DELETE FROM CLP_MMSGREC WHERE CODSTR IN (SELECT CODSTR FROM CLP_MMSGRECL)"
                cSqlDeleteFilho = "DELETE FROM CLP_MMSGRECT WHERE CODSTR IN (SELECT CODSTR FROM CLP_MMSGRECL)"
                
                cCursor.execute(cSqlDeleteFilho)
                cCursor.execute(cSqlDeletePai)
                cConexao.commit()
                self.printLog("Delete concluído com sucesso.")
                
            cCursor.close()
                                                                                                            
        except Exception as e:
            self.printLog(f"** Erro ao conectar ou inserir no MySQL: {e}")
            if cConexao:
                try:
                    cConexao.rollback()
                except Exception:
                    pass
            self.fecharConexao()
            self.registraLog(nCodstr, "** ERRO SQL", str(e), 9, nDti)        
            
    def buscarMensagensPendentes(self) -> list:
        cConexao = None
        cListaMensagens = []
        try:
            cConexao = self.obterConexao()
            cCursor = cConexao.cursor()
            cAgora = datetime.now()
            
            cSqlBuscaMestre = """
                SELECT CODSTR, TOPICOCPL 
                FROM CLP_MMSGENV 
                WHERE JAENVIOU = 'N' 
                  AND EXCLUIR = 'N'
                  AND (DTPROGENV IS NULL OR DTPROGENV <= %s)
                ORDER BY DTI ASC
            """
            cCursor.execute(cSqlBuscaMestre, (cAgora,))
            cRegistrosMestre = cCursor.fetchall()
            
            if len(cRegistrosMestre) > 0:
                cSqlBuscaDetalhe = "SELECT MEMJS FROM CLP_MMSGENVT WHERE CODSTR = %s"
                
                for reg in cRegistrosMestre:
                    cCodstr = reg[0]
                    cTopicoCompleto = reg[1]
                    
                    cCursor.execute(cSqlBuscaDetalhe, (cCodstr,))
                    cResultadoMemo = cCursor.fetchone()
                    
                    cJsonPayload = cResultadoMemo[0] if cResultadoMemo else ""
                    cListaMensagens.append((cCodstr, cTopicoCompleto, cJsonPayload))
            
            cCursor.close()
            return cListaMensagens
            
        except Exception as e:
            self.printLog(f"** Erro SQL ao buscar pendentes: {e}")
            cDtLog = datetime.now()
            cCodstrLog = cDtLog.strftime("%Y%m%d%H%M%S") + cDtLog.strftime("%f")[:3]
            self.registraLog(cCodstrLog, "** ERRO SQL ENVIO", f"Falha no SELECT de busca de mensagens pendentes: {e}", 9, cDtLog)
            self.fecharConexao()
            return None
        
    def verificaMaquinasAtivas(self) -> set:
        cConexao = None
        cMaquinasAtivas = set()
        
        try:
            cConexao = self.obterConexao()
            cCursor = cConexao.cursor()
            
            cSql = "SELECT MAQUINA FROM CLP_CEQP WHERE ATIVO = 'S'"
            cCursor.execute(cSql)
            cRegistros = cCursor.fetchall()
            
            for reg in cRegistros:
                cMaquinasAtivas.add(str(reg[0]))
                
            cCursor.close()
            
            if len(cMaquinasAtivas) > 0:
                cListaFormatada = ", ".join(sorted(cMaquinasAtivas))
                self.printLog(f"Cache de Máquinas atualizado: {len(cMaquinasAtivas)} carregadas na memória. [IDs: {cListaFormatada}]")
            else:
                self.printLog("AVISO: Cache atualizado, mas NENHUMA máquina ativa foi encontrada no banco!")    
            return cMaquinasAtivas
        
        except Exception as e:
            self.printLog(f"** Erro SQL ao carregar máquinas ativas: {e}")
            self.fecharConexao()
            return set()
        
    def marcarMensagemComoEnviada(self, cCodStr: str, cIdMsgMqtt: str) -> bool:
        cConexao = None
        try:
            cConexao = self.obterConexao()
            cCursor = cConexao.cursor()
            cDtEnvio = datetime.now()
            
            cCursor.execute("UPDATE CLP_MMSGENV SET JAENVIOU = 'S', DTENVIO = %s WHERE CODSTR = %s", (cDtEnvio, cCodStr))
            cCursor.execute("UPDATE CLP_MMSGENVT SET IDMSGMQTT = %s WHERE CODSTR = %s", (cIdMsgMqtt, cCodStr))
            
            cConexao.commit()
            cCursor.close()
            return True
        except Exception as e:
            self.printLog(f"** Erro SQL ao atualizar status de envio: {e}")
            if cConexao:
                try:
                    cConexao.rollback()
                except Exception:
                    pass   
            self.registraLog(cCodStr, "** ERRO SQL ENVIO", f"MQTT enviou, mas falhou UPDATE no banco: {e}", 9, datetime.now())        
            self.fecharConexao()
            return False