import paho.mqtt.client as mqtt
import sys
import time
import json
import random
from datetime import datetime

BROKER = "mqtt-broker" 
PORT = 1883

# Se passar argumentos (ex: python simuladorRoland700.py 1 1), roda apenas a máquina informada.
# Se rodar sem argumentos (padrão do Docker), simula as máquinas 1, 2 e 3 simultaneamente!
if len(sys.argv) >= 3:
    LISTA_MAQUINAS = [(int(sys.argv[1]), int(sys.argv[2]))]
else:
    LISTA_MAQUINAS = [
        (1, 1), # (cSeqTarefa = 1, cMaquina = 1)
        (2, 2), # (cSeqTarefa = 2, cMaquina = 2)
        (3, 3)  # (cSeqTarefa = 3, cMaquina = 3)
    ]

def publicar_status(client, topico, nome_maq, payload_dict):
    """Transforma o dicionário em JSON e publica no MQTT."""
    mensagem = json.dumps(payload_dict, ensure_ascii=False)
    client.publish(topico, mensagem, qos=1, retain=False)
    
    os_print = payload_dict['jobPlannerData_id'] if payload_dict['jobPlannerData_id'] else "NENHUMA"
    status_print = "RODANDO" if payload_dict['jobRunning'] else "PARADA"
    
    # Formatação de log identificando qual das 3 máquinas está falando
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [{nome_maq}] OS: {os_print:<9} | Status: {status_print:<7} | Vel: {payload_dict['actualSpeed']:>5.0f} fl/h | Boas: {payload_dict['netCnt']:<5} | Refugo: {payload_dict['wasteCnt']:<3} | OEE: {payload_dict['oee']['oee']}%")

def simular_planta(client, maquinas_config):
    print("=" * 75)
    print(f"🚀 INICIANDO IHM VIRTUAL MULTI-MÁQUINAS - MANROLAND 700 EVOLUTION")
    print("=" * 75)

    # Criamos uma "memória" independente para cada impressora
    estados_maquinas = []
    for seq_tarefa, id_maq in maquinas_config:
        nome_maq = f"Manroland_700_EVO_{id_maq:02d}"
        topico = f"Tgi/BR_SP/Planta1/Rotativa/{nome_maq}/{seq_tarefa}/jobRunData"
        
        estados_maquinas.append({
            "seq_tarefa": seq_tarefa,
            "id_maq": id_maq,
            "nome_maq": nome_maq,
            "topico": topico,
            "os_atual": f"JOB-{random.randint(10000, 99999)}",
            "net_cnt": 0,
            "waste_cnt": 0,
            "setup_time": 0,
            "run_time": 0,
            "elapsed_time": 0
        })
        print(f"📠 Equipamento: {nome_maq} | 📡 Tópico: {topico}")
    
    print("=" * 75 + "\n")

    while True:
        for maq in estados_maquinas:
            cenario = random.random()
            
            job_running = False
            actual_speed = 0.0
            
            if cenario < 0.85:
                # 85% do tempo: Velocidade de cruzeiro alta
                job_running = True
                actual_speed = round(random.uniform(12000.0, 16000.0), 2)
                maq["net_cnt"] += random.randint(30, 80)
                maq["waste_cnt"] += random.randint(0, 3)
                maq["run_time"] += 3
            elif cenario < 0.95:
                # 10% do tempo: Parada para Setup
                job_running = False
                actual_speed = 0.0
                maq["setup_time"] += 3
            else:
                # 5% do tempo: Baixa velocidade (Acerto de cor/registro)
                job_running = True
                actual_speed = round(random.uniform(3000.0, 6000.0), 2)
                maq["waste_cnt"] += random.randint(10, 25)
                maq["run_time"] += 3
            
            maq["elapsed_time"] += 3
            
            total_folhas = maq["net_cnt"] + maq["waste_cnt"]
            qualidade = round((maq["net_cnt"] / total_folhas) * 100, 2) if total_folhas > 0 else 0.0
            
            payload = {
                "jobPlannerData_id": maq["os_atual"],
                "avgSpdShortTerm": 14500.0,
                "averageSpeed": 13800.0,
                "actualSpeed": actual_speed,
                "averageCycle": 0.25,
                "actualCycle": 0.22,
                "setupCounter": 1,
                "netCnt": maq["net_cnt"],
                "bruttoCnt": total_folhas,
                "wasteCnt": maq["waste_cnt"],
                "setupTime": maq["setup_time"],
                "runTime": maq["run_time"],
                "stopTime": 0,
                "goodsTime": round(maq["run_time"] - (maq["waste_cnt"] * 0.22), 2),
                "jobRunning": job_running,
                "cntButton": False,
                "elapsedTime": maq["elapsed_time"],
                "remainingTime": max(0, 3600 - maq["elapsed_time"]),
                "oee": {
                    "availability": 94.5,
                    "performance": 91.0,
                    "quality": qualidade,
                    "oee": round((94.5 * 91.0 * qualidade) / 10000, 2)
                }
            }
            
            publicar_status(client, maq["topico"], maq["nome_maq"], payload)
        
        print("-" * 75)
        time.sleep(3) # Envia o pacote das 3 máquinas a cada 3 segundos

if __name__ == "__main__":
    cliente_mqtt = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    
    print(f"Conectando ao broker industrial MQTT ({BROKER}:{PORT})...")
    cliente_mqtt.connect(BROKER, PORT)
    cliente_mqtt.loop_start()
    
    try:
        simular_planta(cliente_mqtt, LISTA_MAQUINAS)
    except KeyboardInterrupt:
        print("\nDesligando simulador da Roland 700...")
        cliente_mqtt.disconnect()