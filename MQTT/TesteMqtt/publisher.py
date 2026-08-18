import paho.mqtt.client as mqtt
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
PORT = 15896

def publicar_status(client, topico, payload_dict):
    """Transforma o dicionário em JSON e publica no MQTT."""
    mensagem = json.dumps(payload_dict, ensure_ascii=False)
    client.publish(topico, mensagem, qos=1, retain=False)
    
    os_print = payload_dict['jobPlannerData_id'] if payload_dict['jobPlannerData_id'] else "NENHUMA"
    status_print = "RODANDO" if payload_dict['jobRunning'] else "PARADA"
    print(f"[{datetime.now().strftime('%H:%M:%S')}] OS: {os_print:<10} | Status: {status_print:<8} | Boas: {payload_dict['netCnt']:<6} | Refugo: {payload_dict['wasteCnt']}")

def simular_impressora(client, topico, maquina):
    print(f"\n🚀 Iniciando simulação do CLP na impressora gráfica: {maquina}")
    print(f"📡 Tópico Alvo: {topico}\n")

    os_atual = str(random.randint(1000000, 9999999))
    net_cnt = 0
    waste_cnt = 0
    setup_time = 0
    run_time = 0
    elapsed_time = 0
    
    while True:
        cenario = random.random()
        
        job_running = False
        job_id = os_atual
        actual_speed = 0.0
        
        if cenario < 0.80:
            job_running = True
            actual_speed = round(random.uniform(8000.0, 12000.0), 2)
            net_cnt += random.randint(10, 50)
            waste_cnt += random.randint(0, 2)
            run_time += 3
        elif cenario < 0.95:
            job_running = False
            actual_speed = 0.0
            setup_time += 3
        else:
            job_running = True
            actual_speed = round(random.uniform(3000.0, 5000.0), 2)
            waste_cnt += random.randint(5, 15)
            run_time += 3
        
        elapsed_time += 3
        
        payload = {
            "jobPlannerData_id": job_id,
            "avgSpdShortTerm": 10500.5,
            "averageSpeed": 9800.0,
            "actualSpeed": actual_speed,
            "averageCycle": 0.5,
            "actualCycle": 0.45,
            "setupCounter": 1,
            "netCnt": net_cnt,
            "bruttoCnt": net_cnt + waste_cnt,
            "wasteCnt": waste_cnt,
            "setupTime": setup_time,
            "runTime": run_time,
            "stopTime": 0,
            "goodsTime": run_time - 10,
            "jobRunning": job_running,
            "cntButton": False,
            "elapsedTime": elapsed_time,
            "remainingTime": 3600,
            "oee": {
                "availability": 92.5,
                "performance": 88.0,
                "quality": round((net_cnt / (net_cnt + waste_cnt)) * 100, 2) if (net_cnt + waste_cnt) > 0 else 0.0,
                "oee": 80.5
            }
        }
        
        publicar_status(client, topico, payload)
        
        time.sleep(3)

if __name__ == "__main__":
    print("=== SIMULADOR DE CHÃO DE FÁBRICA (Gráfica) ===")
    
    maquina_escolhida = f"Impressora_Offset_{cMaquina:02d}"
    
    TOPICO = f"Raj/BR_SP/Planta1/Rotativa/{maquina_escolhida}/{cSeqTarefa}/jobRunData"    

    cliente_mqtt = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    
    cliente_mqtt.username_pw_set("sensor_maquinas", "raj_maq2026")    
    
    print(f"\nConectando ao broker {BROKER} na porta segura {PORT}...")
    cliente_mqtt.connect(BROKER, PORT)
    
    cliente_mqtt.loop_start()
    
    try:
        simular_impressora(cliente_mqtt, TOPICO, maquina_escolhida)
            
    except KeyboardInterrupt:
        print("\nDesligando simulador...")
        cliente_mqtt.disconnect()