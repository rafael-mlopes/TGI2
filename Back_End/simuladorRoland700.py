import paho.mqtt.client as mqtt
import os
import sys
import time
import json
import random
from datetime import datetime

BROKER = os.getenv("MQTT_BROKER", "mqtt-broker")
PORT = 1883

# =====================================================================
# DEFINIÇÃO FLEXÍVEL DE MÁQUINAS VIA LINHA DE COMANDO OU DOCKER
# - python simuladorRoland700.py          -> Roda 3 máquinas (ou QTD_MAQUINAS)
# - python simuladorRoland700.py 50       -> Roda 50 máquinas (1 até 50)
# - python simuladorRoland700.py 12 12    -> Roda apenas a máquina 12
# =====================================================================
if len(sys.argv) == 2:
    qtd = int(sys.argv[1])
    LISTA_MAQUINAS = [(i, i) for i in range(1, qtd + 1)]
elif len(sys.argv) >= 3:
    LISTA_MAQUINAS = [(int(sys.argv[1]), int(sys.argv[2]))]
else:
    qtd_padrao = int(os.getenv("QTD_MAQUINAS", 3))
    LISTA_MAQUINAS = [(i, i) for i in range(1, qtd_padrao + 1)]

ESTADOS_MAQUINAS = {}

NOMES_MODO = {
    1: "SETUP (Refugo)",
    2: "PRODUCAO (Boas)",
    3: "SUSPENSAO (Parada)"
}

def ao_conectar(client, userdata, flags, reason_code, properties):
    topico_ocorrencias = "Tgi/BR_SP/Planta1/Ocorrencia/+"
    client.subscribe(topico_ocorrencias, qos=1)
    print(f"📡 Escutando comandos de apontamento em: [{topico_ocorrencias}]")

def ao_receber_ocorrencia(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode("utf-8", errors="ignore"))
        id_maq = int(payload.get("maquina", 0))
        cod_ocor = int(payload.get("descricao", 2))

        if id_maq in ESTADOS_MAQUINAS and cod_ocor in [1, 2, 3]:
            maq = ESTADOS_MAQUINAS[id_maq]
            if cod_ocor == 1 and maq["modo_operacao"] != 1:
                maq["setup_cnt"] += 1
            
            maq["modo_operacao"] = cod_ocor
            print("=" * 80)
            print(f"🔔 [COMANDO MQTT RECEBIDO] Máquina #{id_maq} alterada para modo: {NOMES_MODO[cod_ocor]}")
            print("=" * 80)
    except Exception as e:
        print(f"** Erro ao processar comando MQTT no simulador: {e}")

def publicar_status(client, topico, nome_maq, modo_atual, payload_dict, exibir_log=True):
    mensagem = json.dumps(payload_dict, ensure_ascii=False)
    client.publish(topico, mensagem, qos=1, retain=False)
    
    if exibir_log:
        modo_str = NOMES_MODO.get(modo_atual, "PRODUCAO")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [{nome_maq}] Modo: {modo_str:<18} | Vel: {payload_dict['actualSpeed']:>6.0f} fl/h | Boas: {payload_dict['netCnt']:<5} | Refugo: {payload_dict['wasteCnt']:<4} | OEE: {payload_dict['oee']['oee']}%")

def simular_planta(client, maquinas_config):
    total_maq = len(maquinas_config)
    print("=" * 80)
    print(f"🚀 INICIANDO SIMULADOR MANROLAND 700 EVO | TOTAL: {total_maq} MÁQUINA(S)")
    print("=" * 80)

    for seq_tarefa, id_maq in maquinas_config:
        nome_maq = f"Manroland_700_EVO_{id_maq:02d}"
        topico = f"Tgi/BR_SP/Planta1/Rotativa/{nome_maq}/{seq_tarefa}/jobRunData"
        
        ESTADOS_MAQUINAS[id_maq] = {
            "seq_tarefa": seq_tarefa,
            "id_maq": id_maq,
            "nome_maq": nome_maq,
            "topico": topico,
            "os_atual": f"JOB-{10000 + id_maq}",
            "modo_operacao": 2, # Inicia em Produção
            "setup_cnt": 1,
            "net_cnt": 0,
            "waste_cnt": 0,
            "setup_time": 0,
            "run_time": 0,
            "stop_time": 0,
            "elapsed_time": 0
        }
    
    print(f"✅ {total_maq} máquinas inicializadas na memória e prontas para disparo!\n")

    ciclo = 0
    while True:
        ciclo += 1
        inicio_ciclo = time.time()
        
        # Se houver mais de 10 máquinas, resume o log no terminal para não travar a tela
        log_detalhado = (total_maq <= 10)

        for id_maq, maq in ESTADOS_MAQUINAS.items():
            modo = maq["modo_operacao"]
            
            if modo == 1:
                job_running = True
                actual_speed = round(random.uniform(3000.0, 5000.0), 2)
                maq["waste_cnt"] += random.randint(10, 22)
                maq["setup_time"] += 3
                actual_cycle = 0.85
            elif modo == 2:
                job_running = True
                actual_speed = round(random.uniform(13000.0, 16000.0), 2)
                maq["net_cnt"] += random.randint(45, 75)
                maq["run_time"] += 3
                actual_cycle = 0.22
            else:
                job_running = False
                actual_speed = 0.0
                maq["stop_time"] += 3
                actual_cycle = 0.0
            
            maq["elapsed_time"] += 3
            
            total_folhas = maq["net_cnt"] + maq["waste_cnt"]
            qualidade = round((maq["net_cnt"] / total_folhas) * 100, 2) if total_folhas > 0 else 100.0
            
            tempo_produtivo = maq["run_time"] + maq["setup_time"]
            disponibilidade = round((tempo_produtivo / maq["elapsed_time"]) * 100, 2) if maq["elapsed_time"] > 0 else 100.0
            performance = 92.5 if modo == 2 else (35.0 if modo == 1 else 0.0)
            oee_total = round((disponibilidade * performance * qualidade) / 10000, 2)
            
            payload = {
                "jobPlannerData_id": maq["os_atual"],
                "avgSpdShortTerm": 14500.0,
                "averageSpeed": 13800.0,
                "actualSpeed": actual_speed,
                "averageCycle": 0.25,
                "actualCycle": actual_cycle,
                "setupCounter": maq["setup_cnt"],
                "netCnt": maq["net_cnt"],
                "bruttoCnt": total_folhas,
                "wasteCnt": maq["waste_cnt"],
                "setupTime": maq["setup_time"],
                "runTime": maq["run_time"],
                "stopTime": maq["stop_time"],
                "goodsTime": round(maq["run_time"] * 0.95, 2),
                "jobRunning": job_running,
                "cntButton": modo == 2,
                "elapsedTime": maq["elapsed_time"],
                "remainingTime": max(0, 3600 - maq["elapsed_time"]),
                "oee": {
                    "availability": disponibilidade,
                    "performance": performance,
                    "quality": qualidade,
                    "oee": oee_total
                }
            }
            
            publicar_status(client, maq["topico"], maq["nome_maq"], modo, payload, exibir_log=log_detalhado)
        
        if not log_detalhado:
            duracao = round((time.time() - inicio_ciclo) * 1000, 1)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 📦 Lote #{ciclo:04d}: {total_maq} pacotes MQTT disparados em {duracao}ms")
        else:
            print("-" * 80)

        time.sleep(3)

if __name__ == "__main__":
    cliente_mqtt = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    cliente_mqtt.on_connect = ao_conectar
    cliente_mqtt.on_message = ao_receber_ocorrencia
    
    print(f"Conectando ao broker industrial MQTT ({BROKER}:{PORT})...")
    cliente_mqtt.connect(BROKER, PORT)
    cliente_mqtt.loop_start()
    
    try:
        simular_planta(cliente_mqtt, LISTA_MAQUINAS)
    except KeyboardInterrupt:
        print("\nDesligando simulador da Roland 700...")
        cliente_mqtt.disconnect()