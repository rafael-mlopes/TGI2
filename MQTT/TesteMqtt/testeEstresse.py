import subprocess
import time

cQtdInstancias = 1
cNomeDoScript = "publisher.py"

print(f"Iniciando {cQtdInstancias} instâncias de {cNomeDoScript}...")

processos = []

for i in range(1, cQtdInstancias + 1):
    cSeqTarefa = i
    cMaquina = i
    
    cComando = f'start cmd /k "python {cNomeDoScript} {cSeqTarefa} {cMaquina}"'
    
    p = subprocess.Popen(cComando, shell=True)
    processos.append(p)
    
    time.sleep(0.5)
    
print("Todas as intâncias foram iniciadas com sucesso!")