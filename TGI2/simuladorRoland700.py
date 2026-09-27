import paho.mqtt.client as mqtt
import sys
import time
import json
import random
from datetime import datetime

# Parâmetros padrão (podem ser sobrescritos via terminal pelo testeEstresse)
cSeqTarefa = 1
cMaquina = 1

if len(sys.argv) >= 3:
    cSeqTarefa = int(sys.argv[1])
    cMaquina = int(sys.argv[2])

# Aponta para o Docker que está rodando na sua própria máquina

BROKER = "mqtt-broker" 
PORT = 1883

def publicar_status(client, topico, payload_dict):
    """Transforma o dicionário em JSON e publica no MQTT."""
    mensagem = json.dumps(payload_dict, ensure_ascii=False)
    client.publish(topico, mensagem, qos=1, retain=False)
    
    os_print = payload_dict['jobPlannerData_id'] if payload_dict['jobPlannerData_id'] else "NENHUMA"
    status_print = "RODANDO" if payload_dict['jobRunning'] else "PARADA"
    
    # Formatação de log com cara de painel industrial
    print(f"[{datetime.now().strftime('%H:%M:%S')}] OS: {os_print:<8} | Status: {status_print:<7} | Vel: {payload_dict['actualSpeed']:>5.0f} fl/h | Boas: {payload_dict['netCnt']:<5} | Refugo: {payload_dict['wasteCnt']:<3} | OEE: {payload_dict['oee']['oee']}%")

def simular_impressora(client, topico, maquina):
    print("=" * 65)
    print(f"🚀 INICIANDO IHM VIRTUAL - MANROLAND ROLAND 700 EVOLUTION")
    print(f"📠 Equipamento: {maquina}")
    print(f"📡 Tópico Alvo: {topico}")
    print("=" * 65 + "\n")

    os_atual = f"JOB-{random.randint(10000, 99999)}"
    net_cnt = 0
    waste_cnt = 0
    setup_time = 0
    run_time = 0
    elapsed_time = 0
    
    while True:
        # Lógica de oscilação de produção da Roland
        cenario = random.random()
        
        job_running = False
        job_id = os_atual
        actual_speed = 0.0
        
        if cenario < 0.85:
            # 85% do tempo: Máquina rodando em velocidade de cruzeiro alta (Offset)
            job_running = True
            actual_speed = round(random.uniform(12000.0, 16000.0), 2)
            net_cnt += random.randint(30, 80)
            waste_cnt += random.randint(0, 3)
            run_time += 3
        elif cenario < 0.95:
            # 10% do tempo: Parada para Setup (Ajuste de chapa/tinteiro)
            job_running = False
            actual_speed = 0.0
            setup_time += 3
        else:
            # 5% do tempo: Rodando em baixa velocidade (Acerto de registro/cor)
            job_running = True
            actual_speed = round(random.uniform(3000.0, 6000.0), 2)
            waste_cnt += random.randint(10, 25)
            run_time += 3
        
        elapsed_time += 3
        
        # Proteção contra divisão por zero no cálculo de Qualidade
        total_folhas = net_cnt + waste_cnt
        qualidade = round((net_cnt / total_folhas) * 100, 2) if total_folhas > 0 else 0.0
        
        payload = {
            "jobPlannerData_id": job_id,
            "avgSpdShortTerm": 14500.0,
            "averageSpeed": 13800.0,
            "actualSpeed": actual_speed,
            "averageCycle": 0.25, # Segundos por folha
            "actualCycle": 0.22,
            "setupCounter": 1,
            "netCnt": net_cnt,
            "bruttoCnt": total_folhas,
            "wasteCnt": waste_cnt,
            "setupTime": setup_time,
            "runTime": run_time,
            "stopTime": 0,
            "goodsTime": run_time - (waste_cnt * 0.22),
            "jobRunning": job_running,
            "cntButton": False,
            "elapsedTime": elapsed_time,
            "remainingTime": max(0, 3600 - elapsed_time),
            "oee": {
                "availability": 94.5,
                "performance": 91.0,
                "quality": qualidade,
                "oee": round((94.5 * 91.0 * qualidade) / 10000, 2) # Cálculo real de OEE
            }
        }
        
        publicar_status(client, topico, payload)
        time.sleep(3) # A Roland envia telemetria a cada 3 segundos

if __name__ == "__main__":
    maquina_escolhida = f"Manroland_700_EVO_{cMaquina:02d}"
    TOPICO = f"Tgi/BR_SP/Planta1/Rotativa/{maquina_escolhida}/{cSeqTarefa}/jobRunData"    

    cliente_mqtt = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    
    print(f"Conectando ao broker industrial MQTT ({BROKER}:{PORT})...")
    cliente_mqtt.connect(BROKER, PORT)
    cliente_mqtt.loop_start()
    
    try:
        simular_impressora(cliente_mqtt, TOPICO, maquina_escolhida)
            
    except KeyboardInterrupt:
        print("\nDesligando simulador da Roland 700...")
        cliente_mqtt.disconnect()