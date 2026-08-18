import paho.mqtt.client as mqtt
import json
import os
import sys
import time
import random
from datetime import datetime, timedelta
from LibDB import GerenciadorBanco

class TransceiverMqttPlanta:
    def __init__(self, nHostBanco: str, nCaminhoBanco: str, nUsuarioBanco: str, nSenhaBanco: str, nUsuarioMqtt: str, nSenhaMqtt: str, nBroker: str, nPort: int, nTopicFilter: str, nLogDetalhado: bool):
        self.fUsuarioMqtt: str = nUsuarioMqtt
        self.fSenhaMqtt: str = nSenhaMqtt        
        self.fBroker: str = nBroker
        self.fPort: int = nPort
        self.fTopicFilter: str = str(nTopicFilter).strip()
        self.fLogDetalhado: bool = nLogDetalhado
        
        self.fTempoSemaforo: int = 30
        self.fChaveInt: int = random.randint(1, 999999) 
        self.fDirProjeto: str = os.path.dirname(os.path.abspath(__file__))   
        self.fUltimaMsgTempo = None
        self.fUltimoDelete = datetime.now()  
        cNomeSistema = os.path.splitext(os.path.basename(__file__))[0].capitalize()      
        
        self.db = GerenciadorBanco(
            nHostBanco,
            nCaminhoBanco,
            nUsuarioBanco,
            nSenhaBanco,
            "TRANSCEIVER_MQTT_PLANTA1",
            self.fChaveInt,
            cNomeSistema
            )
        
        self.fMaquinasAtivas = set()
        
        cIdUnico = f"RajReceptor_{random.randint(10000,99999)}"
            
        self.fClient = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cIdUnico, protocol=mqtt.MQTTv311)                        
        self.fClient.username_pw_set(self.fUsuarioMqtt, self.fSenhaMqtt)
        
        self.fClient.on_message = self.on_message
        self.fClient.on_disconnect = self.on_disconnect
        self.fClient.on_connect = self.on_connect
        
    def on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            self.db.printLog("Conexão MQTT estabelecida (ou restabelecida) com o Broker!")            
            
            self.fClient.subscribe(self.fTopicFilter, qos=0)
            self.db.printLog(f"Inscrito com sucesso no tópico: [{self.fTopicFilter}]")
        else:
            self.db.printLog(f"Falha na conexão MQTT. Código de retorno: {reason_code}")            
                
    def on_message(self, client, userdata, msg):
        try:
            cTopicoRecebido = msg.topic
            cTopicoFinal = cTopicoRecebido.split("/")[-1]
            
            #-----------Simulando SEQTAREFA E MAQUINA
            cSeqTarefa = cTopicoRecebido.split("/")[5]
            
            if str(cSeqTarefa) not in self.fMaquinasAtivas:
                return            
            
            cDti = datetime.now()
            self.fUltimaMsgTempo = cDti
            cCodstr = cDti.strftime("%Y%m%d%H%M%S") + cDti.strftime("%f")[:3]
            cJsonRecebido = msg.payload.decode()                        
            cIdMsg = msg.mid
            cAgora = datetime.now()                        
            cDeletar = False
            if (cAgora - self.fUltimoDelete).total_seconds() > 300:
                cDeletar = True
                self.fUltimoDelete = cAgora
                self.db.printLog("\n Iniciando o Delete")        
            self.db.insertTblRec(cCodstr, cTopicoFinal, cTopicoRecebido, cJsonRecebido, cIdMsg, cDti, cSeqTarefa, cDeletar, self.fLogDetalhado)            

        except Exception as e:
            self.db.printLog(f"** ERRO GRAVE no on_message: {e}")   

    def on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):    
        if reason_code != 0:
            cDtiQueda = datetime.now()
            cCodstrQueda = cDtiQueda.strftime("%Y%m%d%H%M%S") + cDtiQueda.strftime("%f")[:3]            
            cErroMsg = f"Conexão perdida com o Broker MQTT. Código: {reason_code}"
            self.db.printLog(f"\n {cErroMsg}. O Paho tentará reconectar sozinho...")
            self.db.registraLog(cCodstrQueda, "** ERRO REDE", cErroMsg, 9, cDtiQueda)  
            
    def processarMensagensPendentes(self) -> int:
        cQtdEnviada = 0 
        cRetornoBusca = self.db.buscarMensagensPendentes()
        
        if cRetornoBusca is None:
            return -1
        
        cMensagens = cRetornoBusca
        
        for msg in cMensagens:
            cCodstr = msg[0]
            cTopicoCompleto = msg[1]
            cJsonPayload = msg[2]
            
            if not cTopicoCompleto or cTopicoCompleto == "None" or "+" in cTopicoCompleto or "#" in cTopicoCompleto:
                self.db.printLog(f"** LIXO NO BANCO: Tópico de envio inválido '{cTopicoCompleto}'. Bloqueando e isolando...")
                self.db.marcarMensagemComoEnviada(cCodstr, "ERRO_TOPICO")
                continue
            
            try:
                msgInfo = self.fClient.publish(cTopicoCompleto, cJsonPayload, qos=1)
                cIdMsgMqtt = str(msgInfo.mid)
                
                if not self.db.marcarMensagemComoEnviada(cCodstr, cIdMsgMqtt):
                    return -1
                
                cQtdEnviada += 1
                
                self.db.registraLog(cCodstr, "ENVIO OK", f"Ordem despachada para o tópico: {cTopicoCompleto}", 1, datetime.now())                
            except Exception as e:
                self.db.printLog(f"Falha ao enviar a mensagem {cCodstr} pelo MQTT: {e}")
                self.db.registraLog(cCodstr, " ** ERRO ENVIO", f"Falha isolada ao publicar no MQTT: {e}", 9, datetime.now())                
        return cQtdEnviada

    def iniciarTransceiver(self) -> None:
        if not self.db.verificaSemaforo(self.fTempoSemaforo, self.fDirProjeto):
            sys.exit()        
            
        self.db.printLog("=" * 60)
        self.db.printLog(f"=== INICIANDO RajBootCLP - DATA: {datetime.now().strftime('%d/%m/%Y')} - VERSÃO 2026 1a ===")
        self.db.printLog("=" * 60)
        
        self.fMaquinasAtivas = self.db.verificaMaquinasAtivas()
              
        try:    
            self.fClient.connect(self.fBroker, self.fPort)
            
            cDtiInicio = datetime.now()
            cCodstrInicio = cDtiInicio.strftime("%Y%m%d%H%M%S") + cDtiInicio.strftime("%f")[:3]
            self.db.registraLog(cCodstrInicio, "INFO", "Leitor MQTT conectado ao Broker e iniciado com sucesso.", 1, cDtiInicio)
            
            self.db.printLog("Aguardando mensagens e enviando para o Firebird (via FDB)...")
            self.db.printLog("\n \n iniciando Leitor")
            
            self.fClient.loop_start()                                    
                        
            cTotalEnviadasJanela = 0    
            cErrosConsecutivos = 0  
            cPassos = 1
            
            cHoraParada = datetime.now() + timedelta(minutes=self.fTempoSemaforo)
                  
            while datetime.now() < cHoraParada:
                cAgora = datetime.now()
                
                if not self.fClient.is_connected():
                    self.db.printLog("Aviso: Conexão MQTT perdida! O paho está tentando reconectar...")
                    cErrosConsecutivos += 1
                    if cErrosConsecutivos >= 3:
                        self.db.printLog("** ERRO CRÍTICO: Falha de rede MQTT persistente. Abortando serviço!")
                        break
                    time.sleep(5)
                    continue
                
                cEnviadasAgora = self.processarMensagensPendentes()
                
                if cEnviadasAgora == -1:
                    cErrosConsecutivos += 1
                    self.db.printLog(f"Instabilidade de rede/banco detectada ({cErrosConsecutivos}/3)...")
                    
                    if cErrosConsecutivos >= 3:
                        self.db.printLog("** ERRO Queda de rede crítica. Encerrando o script de forma segura para evitar Zombie Sockets!")
                        break
                    time.sleep(5)
                    continue
                
                cErrosConsecutivos = 0
                cTotalEnviadasJanela += cEnviadasAgora
                
                if cEnviadasAgora > 0:
                    cTextOut = f"Despachou {cEnviadasAgora} ordens (Total: {cTotalEnviadasJanela})"
                else:
                    cTextOut = "Fila vazia"                                    
                
                if self.fUltimaMsgTempo is not None:
                    cUltimaStr = self.fUltimaMsgTempo.strftime("%H:%M:%S")                    
                    cDiffSegundos = (cAgora - self.fUltimaMsgTempo).total_seconds()
                    
                    if cDiffSegundos < 60:
                        cOcioso = f"{int(cDiffSegundos)}s"
                    else:
                        cOcioso = f"{int(cDiffSegundos // 60)}m {int(cDiffSegundos % 60)}s"                       
                    cTextIn = f"Última: {cUltimaStr} (Ociosa há {cOcioso})" 
                else:
                    cTextIn = f"Aguardando 1° msg da máquina..."
                if self.fLogDetalhado:
                    self.db.printLog(f"Ciclo {cPassos:03d} | IN: [{cTextIn}] | OUT: [{cTextOut}]") 
                cPassos += 1   
                time.sleep(5)    
                
            if cErrosConsecutivos < 3:                    
                self.db.printLog("Tempo esgotado! Encerrando rotina para liberar o semáforo.")    
                cDtFim = datetime.now()
                cCodstrFim = cDtFim.strftime("%Y%m%d%H%M%S") + cDtFim.strftime("%f")[:3]
                self.db.registraLog(cCodstrFim, "INFO", f"Janela de {self.fTempoSemaforo} min concluída. Liberando semáforo.", 1, cDtFim)       
        
        except KeyboardInterrupt:
            self.db.printLog("\n[!] Comando Ctrl+C detectado. Iniciando desligamento seguro...")
                             
        except Exception as e:
            self.db.printLog(f"** ERRO Falha fatal ao conectar no Broker MQTT: {e}")
            fDtiErro = datetime.now()
            fCodstrErro = fDtiErro.strftime("%Y%m%d%H%M%S") + fDtiErro.strftime("%f")[:3]
            self.db.registraLog(fCodstrErro, "** ERRO MQTT", f"Falha na conexão inicial: {str(e)}", 9, fDtiErro)
        finally:
            self.fClient.loop_stop()
            self.fClient.disconnect()
            self.db.liberarSemaforo() 
            self.db.fecharConexao()   
            self.db.printLog("Serviço finalizado com sucesso.")
            
            self.db.printLog("=" * 60)
            self.db.printLog(f"=== TÉRMINO RajBootCLP - DATA: {datetime.now().strftime('%d/%m/%Y')} ===")
            self.db.printLog("=" * 60)
                        
            sys.exit()              
            
def logStartup(nMensagem):
    print(nMensagem)
    try:
        cDirAtual = os.path.dirname(os.path.abspath(__file__))
        cPastaLogs = os.path.join(cDirAtual, "logs", "Startup")
        if not os.path.exists(cPastaLogs):
            os.makedirs(cPastaLogs)
            
        cNomeArquivo = f"Log_Startup_{datetime.now().strftime('%d%m%Y')}.txt"
        with open(os.path.join(cPastaLogs, cNomeArquivo), "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().strftime('%H:%M:%S')} - {nMensagem}\n")
    except:
        pass            

fAlias = "MENDES_ZERADO"
fStringJsonClp = ""

if getattr(sys, 'frozen', False):
    fDiretorioAtual = os.path.dirname(sys.executable)    
else:
    fDiretorioAtual = os.path.dirname(os.path.abspath(__file__))

fArquivoCfg = os.path.join(fDiretorioAtual, "GRP.cfg")

if (fAlias != "") and (os.path.exists(fArquivoCfg)):
    fAliasAlvo = f"[{fAlias}]"
    fDentroAlias = False
    
    try:
        with open(fArquivoCfg, "r", encoding="utf-8", errors="ignore") as f:
            for linha in f:
                linha = linha.strip()
                
                if not linha:
                    continue
                
                if linha.startswith("[") and linha.endswith("]"):
                    if linha == fAliasAlvo:
                        fDentroAlias = True
                    else:
                        fDentroAlias = False
                    continue
                
                if fDentroAlias and linha.upper().startswith("CLPJS="):
                    fStringJsonClp = linha.split("=", 1)[1].strip()
                    logStartup("Configuração do CLPJS lida com sucesso direto do arquivo!")
                    break
                    
    except Exception as e:
        logStartup(f"** Erro inesperado ao tentar ler o arquivo GRP.cfg: {e}")
else:
    logStartup("** ERRO Arquivo GRP.cfg não encontrado ou Alias vazio *")

if fStringJsonClp != "":
    try:
        cStringCorrigida = fStringJsonClp.replace("'", '"').replace("\\", "\\\\")      
        cDados = json.loads(cStringCorrigida)        
        cDadosMqttDB = cDados.get("dbMqtt", {})
        cDadosMqttParam = cDados.get("Mqtt", {})
        cLogDetalhado = cDados.get("LogDetalhado", False)
                
        cTransceiver = TransceiverMqttPlanta(
            nHostBanco=cDadosMqttDB['hDB'],
            nCaminhoBanco=cDadosMqttDB['db'],
            nUsuarioBanco=cDadosMqttDB['uDB'],
            nSenhaBanco=cDadosMqttDB['pDB'],
            nUsuarioMqtt=cDadosMqttParam['user'],
            nSenhaMqtt=cDadosMqttParam['pass'],
            nBroker=cDadosMqttParam['broker'],
            nPort=cDadosMqttParam['port'],
            nTopicFilter=cDadosMqttParam['topic'],
            nLogDetalhado=cLogDetalhado
            )
        
        cTransceiver.iniciarTransceiver()
        
    except json.JSONDecodeError as e:
        logStartup(f"** Erro ao decodificar o JSON do arquivo CFG: {e}")
        sys.exit()
else:
    logStartup("** ERRO Script interrompido: Configurações do CFG não foram carregadas corretamente.")
    sys.exit()              