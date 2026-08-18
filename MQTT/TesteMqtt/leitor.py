import paho.mqtt.client as mqtt
import time
from datetime import datetime

BROKER = "192.168.0.4"
PORT = 1883
TOPIC = "Raj/PCP/#"

CLIENT_ID = "Leitor_Log_Sistema_RAJ_01" 

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        sessao_recuperada = flags.session_present
        print(f"Conectado! (Sessão recuperada: {sessao_recuperada})")
        client.subscribe(TOPIC, qos=1) 
    else:
        print(f"Erro: {rc}")

def on_message(client, userdata, msg):
    payload_str = msg.payload.decode('utf-8')
    hora_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    texto_log = f"[{hora_atual}] Tópico: {msg.topic} | Msg: {payload_str}"
    
    print("REUPERADO/RECEBIDO: " + texto_log)
    print(str(msg.qos))
    print(str(msg.retain))
    print(str(msg.mid))
    
    with open("historico_mensagens.txt", "a", encoding='utf-8') as arquivo:
        arquivo.write(texto_log + "\n")

client = mqtt.Client(
    client_id=CLIENT_ID, 
    callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    clean_session=True
)

client.on_connect = on_connect
client.on_message = on_message

print(f"Iniciando leitor persistente ({CLIENT_ID})...")
client.connect(BROKER, PORT)

try:
    client.loop_forever()
except KeyboardInterrupt:
    print("Desconectado.")