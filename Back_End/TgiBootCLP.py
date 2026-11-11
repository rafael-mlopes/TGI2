import paho.mqtt.client as mqtt
import json
import os
import sys
import time
import random
from datetime import datetime, timedelta
from LibDB import GerenciadorBanco
from LibConfig import carregarConfig, ErroConfiguracao

class TransceiverMqttPlanta:
    def __init__(self, nHostBanco: str, nNomeBanco: str, nUsuarioBanco: str, nSenhaBanco: str, nUsuarioMqtt: str, nSenhaMqtt: str, nBroker: str, nPort: int, nTopicFilter: str, nLogDetalhado: bool, nRetencaoDias: int = 30):
        self.fUsuarioMqtt: str = nUsuarioMqtt
        self.fSenhaMqtt: str = nSenhaMqtt
        self.fBroker: str = nBroker
        self.fPort: int = nPort
        self.fTopicFilter: str = str(nTopicFilter).strip()
        self.fLogDetalhado: bool = nLogDetalhado
        self.fRetencaoDias: int = nRetencaoDias
        self.fIntervaloRecargaTarefas: int = 60      # segundos entre recargas do cadastro de máquinas/tarefas
        self.fIntervaloLimpeza: int = 3600           # segundos entre limpezas de histórico
        
        self.fTempoSemaforo: int = 30
        self.fChaveInt: int = random.randint(1, 999999) 
        self.fDirProjeto: str = os.path.dirname(os.path.abspath(__file__))   
        self.fUltimaMsgTempo = None
        self.fUltimoDelete = datetime.now()  
        # Sufixo sequencial do CODSTR: garante chave única mesmo com várias mensagens no mesmo milissegundo
        self.fSeqCodstr: int = 0
        cNomeSistema = os.path.splitext(os.path.basename(__file__))[0].capitalize()      
        
        self.db = GerenciadorBanco(
            nHostBanco=nHostBanco,
            nNomeBanco=nNomeBanco,
            nUsuarioBanco=nUsuarioBanco,
            nSenhaBanco=nSenhaBanco,
            nNomeProjeto="TRANSCEIVER_MQTT_PLANTA1",
            nChaveInt=self.fChaveInt,
            nSistemaLog=cNomeSistema
        )
        
        # {SEQ_TAREFA (str): MAQUINA (int)} - recarregado periodicamente (ver atualizarTarefasAtivas)
        self.fTarefasAtivas = {}
        
        cIdUnico = f"TgiReceptor_{random.randint(10000,99999)}"
            
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
            partesTopico = cTopicoRecebido.split("/")
            
            # Ignora mensagens de comando/ocorrência (que não são pacotes jobRunData das máquinas)
            if len(partesTopico) < 7 or partesTopico[-1] != "jobRunData":
                return

            cTopicoFinal = partesTopico[-1]
            cSeqTarefa = partesTopico[5]
            
            # A máquina é resolvida pela tarefa (AG_MTAR); tarefa não liberada = telemetria ignorada
            cMaquina = self.fTarefasAtivas.get(str(cSeqTarefa))
            if cMaquina is None:
                return            
            
            cDti = datetime.now()
            self.fUltimaMsgTempo = cDti
            cCodstr = cDti.strftime("%Y%m%d%H%M%S") + cDti.strftime("%f")[:3] + f"{self.fSeqCodstr:03d}"
            self.fSeqCodstr = (self.fSeqCodstr + 1) % 1000
            cJsonRecebido = msg.payload.decode()                        
            cIdMsg = msg.mid
            cAgora = datetime.now()                        
            cDeletar = False
            
            if (cAgora - self.fUltimoDelete).total_seconds() > 300:
                cDeletar = True
                self.fUltimoDelete = cAgora
                self.db.printLog("\n Iniciando o Delete de limpeza")        
            
            self.db.insertTblRec(cCodstr, cTopicoFinal, cTopicoRecebido, cJsonRecebido, cIdMsg, cDti, cSeqTarefa, cDeletar, self.fLogDetalhado, nMaquina=cMaquina)            

        except Exception as e:
            self.db.printLog(f"** ERRO GRAVE no on_message: {e}")   

    def on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):    
        if reason_code != 0:
            cDtiQueda = datetime.now()
            cCodstrQueda = cDtiQueda.strftime("%Y%m%d%H%M%S") + cDtiQueda.strftime("%f")[:3]            
            cErroMsg = f"Conexão perdida com o Broker MQTT. Código: {reason_code}"
            self.db.printLog(f"\n {cErroMsg}. O Paho tentará reconectar sozinho...")
            self.db.registraLog(cCodstrQueda, "** ERRO REDE", cErroMsg, 9, cDtiQueda)  
            
    def atualizarTarefasAtivas(self) -> None:
        cNovoMapa = self.db.carregarTarefasAtivas()
        if cNovoMapa is None:
            return  # erro de banco: mantém o mapa anterior para não descartar telemetria
        
        if cNovoMapa != self.fTarefasAtivas:
            if cNovoMapa:
                cLista = ", ".join(f"T{seq}->M{maq}" for seq, maq in sorted(cNovoMapa.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0))
                self.db.printLog(f"Cache de Tarefas/Máquinas atualizado: {len(cNovoMapa)} liberada(s). [{cLista}]")
            else:
                self.db.printLog("AVISO: Cache atualizado, mas NENHUMA tarefa rodando em máquina ativa foi encontrada no banco!")
        
        self.fTarefasAtivas = cNovoMapa  # troca atômica da referência (lida pela thread do paho)
    
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
        self.db.printLog(f"=== INICIANDO TgiBootCLP - DATA: {datetime.now().strftime('%d/%m/%Y')} - VERSÃO MYSQL ===")
        self.db.printLog("=" * 60)
        
        self.atualizarTarefasAtivas()
        cUltimaRecarga = datetime.now()
        # Primeira limpeza no 1º ciclo (com o MQTT já recebendo), para não atrasar a inscrição no broker
        cUltimaLimpeza = datetime.now() - timedelta(seconds=self.fIntervaloLimpeza)
              
        try:    
            self.fClient.connect(self.fBroker, self.fPort)
            
            cDtiInicio = datetime.now()
            cCodstrInicio = cDtiInicio.strftime("%Y%m%d%H%M%S") + cDtiInicio.strftime("%f")[:3]
            self.db.registraLog(cCodstrInicio, "INFO", "Leitor MQTT conectado ao Broker e iniciado com sucesso.", 1, cDtiInicio)
            
            self.db.printLog("Aguardando mensagens e enviando para o MySQL...")
            self.db.printLog("\n \n Iniciando Leitor")
            
            self.fClient.loop_start()                                    
                        
            cTotalEnviadasJanela = 0    
            cErrosConsecutivos = 0  
            cPassos = 1
            
            cHoraParada = datetime.now() + timedelta(minutes=self.fTempoSemaforo)
                  
            while datetime.now() < cHoraParada:
                cAgora = datetime.now()
                
                if (cAgora - cUltimaRecarga).total_seconds() >= self.fIntervaloRecargaTarefas:
                    self.atualizarTarefasAtivas()
                    cUltimaRecarga = cAgora
                
                if (cAgora - cUltimaLimpeza).total_seconds() >= self.fIntervaloLimpeza:
                    self.db.limparHistorico(self.fRetencaoDias)
                    cUltimaLimpeza = cAgora
                
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
            self.db.printLog(f"=== TÉRMINO TgiBootCLP - DATA: {datetime.now().strftime('%d/%m/%Y')} ===")
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

try:
    cDados = carregarConfig()
    logStartup("Configuração do CLPJS lida com sucesso (config.ini + variáveis de ambiente)!")
except ErroConfiguracao as e:
    logStartup(f"** ERRO Script interrompido: {e}")
    sys.exit()
except Exception as e:
    logStartup(f"** Erro inesperado ao tentar ler a configuração: {e}")
    sys.exit()

cDadosMqttDB = cDados["dbMqtt"]
cDadosMqttParam = cDados["Mqtt"]

cTransceiver = TransceiverMqttPlanta(
    nHostBanco=cDadosMqttDB['hDB'],
    nNomeBanco=cDadosMqttDB['db'],
    nUsuarioBanco=cDadosMqttDB['uDB'],
    nSenhaBanco=cDadosMqttDB['pDB'],
    nUsuarioMqtt=cDadosMqttParam['user'],
    nSenhaMqtt=cDadosMqttParam['pass'],
    nBroker=cDadosMqttParam['broker'],
    nPort=cDadosMqttParam['port'],
    nTopicFilter=cDadosMqttParam['topic'],
    nLogDetalhado=cDados["LogDetalhado"],
    nRetencaoDias=cDados["RetencaoDias"]
)

cTransceiver.iniciarTransceiver()
