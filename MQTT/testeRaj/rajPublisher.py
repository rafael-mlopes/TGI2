import glob

import paho.mqtt.client as mqtt   #pip install paho-mqtt
import sys
import time
import json
import random
from datetime import datetime

cSeqTarefa = 1
cMaquina = 1

if len(sys.argv) >= 3:
    cSeqTarefa = int(sys.argv[1])
    cMaquina = int(sys.argv[2])

BROKER = "192.168.0.25"
BROKER = "rajportal.no-ip.org"
PORT = 15896
USR = "sensor_maquinas"
PSW = "raj_maq2026"

def publicar_status(client, topico, payload_dict):
    """Transforma o dicionário em JSON e publica no MQTT."""
    mensagem = json.dumps(payload_dict, ensure_ascii=False)
    client.publish(topico, mensagem, qos=1, retain=False)
    
    # os_print = payload_dict['jobPlannerData_id'] if payload_dict['jobPlannerData_id'] else "NENHUMA"
    # status_print = "RODANDO" if payload_dict['jobRunning'] else "PARADA"
    # print(f"[{datetime.now().strftime('%H:%M:%S')}] OS: {os_print:<10} | Status: {status_print:<8} | Boas: {payload_dict['netCnt']:<6} | Refugo: {payload_dict['wasteCnt']}")


def simular_impressora(client, topico, maquina):
    
    print(f"\n🚀 Iniciando simulação do CLP na impressora gráfica: {maquina}")
    print(f"📡 Tópico Alvo: {topico}\n")

    
    while True:
        payload = {
                "jobPlannerData_id": 1,
                "avgSpdShortTerm": 10500.5,
                "averageSpeed": 9800.0,
                "actualSpeed": 123,
                "averageCycle": 0.5,
                "actualCycle": 0.45,
                "setupCounter": 1,
                "remainingTime": 3600,
                "oee": {
                    "availability": 92.5,
                    "performance": 88.0,
                    "oee": 80.5
                }
        }
        time.sleep(3)
        publicar_status(client, topico, payload)
       
    # while True:

        # { "PlugApp_20260424.txt": 123, "PLUGSCP_202604.txt": 12 }
        # carrega todos os arquivos no mesmo diretorio
        # verifica se a Data de Modificação = HOJE, se for
        # Carrega no seu "arqConfiguracao" a ultima linha lida do arquivo de mesmo ou se nao existir o nome dele no seu arqConfiguracao -- definir a ult linha lida == cUltimaLinhaLida
        # roda a leitura do arquivo
        # cUltimaLinhaLida = 
        # with open('file.txt', 'r') as arquivo:
        #     for i, linha in enumerate(arquivo):
        #         if i >= cUltimaLinhaLida:
        #             print(linha.strip())
        #             sender to mqtt
        
        #             payload = {
        #                 "ln": 16265,
        #                 "conteudo": ""
        #             }
        #             sleep( 1.5 )


        # cTmpData = "_YYYYMM.txt"
        
        # for arquivo in glob.glob(os.path.join(vDirMsgsPendentes, "*.txt")):
            # lstTemp = arquivo.split("\\")
            #nomeArquivoDestino = lstTemp[len(lstTemp) - 1]
            #nomeArquivoOriginal = nomeArquivoDestino         
            
            # timestamp = os.path.getmtime(arquivo) # Obter o tempo de modificação em segundos           
            # data_modificacao = datetime.datetime.fromtimestamp(timestamp) # Converter timestamp para formato legível (datetime)

        
        
        # publicar_status(client, topico, payload)
        
        # time.sleep(3)

if __name__ == "__main__":

    print("=== SIMULADOR DE DO RAFAEL ===")
    
    cSubTopico = "SRVRAJ"
    cTopicoRaiz = f"Raj/BR_SP/logsPlug/{cSubTopico}"

    cliente_mqtt = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    cliente_mqtt.username_pw_set(USR, PSW)    
    print(f"\nConectando ao broker {BROKER} na porta segura {PORT}...")
    cliente_mqtt.connect(BROKER, PORT)
    print("Conectado")
    
    cliente_mqtt.loop_start()

    
    try:
        simular_impressora(cliente_mqtt, cTopicoRaiz, cSubTopico)
            
    except KeyboardInterrupt:
        print("\nDesligando simulador...")
        cliente_mqtt.disconnect()