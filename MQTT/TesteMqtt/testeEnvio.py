import os
import sys
import fdb
import json
import time 
import random
from datetime import datetime

def carregarConf():
    cDirAtual = os.path.dirname(os.path.abspath(__file__))
    cArquivoCfg = os.path.join(cDirAtual, "GRP.cfg")
    cAliasAlvo = "[MENDES_ZERADO]"
    cJsonOrigemStr = ""
    
    if not os.path.exists(cArquivoCfg):
        print("** ERRO: Arquivo GRP.cfg não encontrado.")
        sys.exit()
    
    fDentroAlias = False
    with open(cArquivoCfg, "r", encoding="utf-8", errors="ignore") as f:
        for linha in f:
            linha = linha.strip()
            if not linha: continue
            
            if linha.startswith("[") and linha.endswith("]"):
                fDentroAlias = (linha == cAliasAlvo)
                continue
            if fDentroAlias and linha.upper().startswith("CLPJS="):
                cJsonOrigemStr = linha.split("=", 1)[1].strip()
                break
    if not cJsonOrigemStr:
        print("** ERRO: Configuração do banco não encontrada no CFG.")
        sys.exit()
        
    cDadosOrigem = json.loads(cJsonOrigemStr.replace("'", '"').replace("\\", "\\\\"))
    return cDadosOrigem.get("dbClp", {})

def injetarMensagem(nQtdMensagens, nIntervaloSegundos):
    print(f"--- Iniciando Injetor de Ordens (Teste de Estresse) ---")
    cDbConfig = carregarConf()
    cConexao = None
    
    try: 
        cConexao = fdb.connect(host=cDbConfig['hDB'], database=cDbConfig['db'], user=cDbConfig['uDB'], password=cDbConfig['pDB'], charset='WIN1252')
        cCursor = cConexao.cursor()
        print("Conectado ao Firebird com sucesso! Preparando injeção...\n")
        
        cSqlPai = """
            INSERT INTO CLP_MMSGENV
            (CODSTR, DTI, JAENVIOU, EXCLUIR, DTPROGENV, TOPICOCPL, USUDB)
            VALUES (?, ?, 'N', 'N', NULL, ?, 'SYSDBA')
        """
        cSqlFilho = "INSERT INTO CLP_MMSGENVT (CODSTR, MEMJS) VALUES (?, ?)"
        
        for i in range(1, nQtdMensagens + 1):
            cAgora = datetime.now()
            cCodstr = cAgora.strftime("%Y%m%d%H%M%S") + cAgora.strftime("%f")[:3]
            
            cSeqMaquina = random.randint(1, 10)
            cTopico = f"Raj/BR_SP/Planta1/Rotativa/Impressora_Offset_01/{cSeqMaquina}/command"
            
            cComandoJson = {
                "comandoID": f"CMD-{random.randint(1000, 9999)}",
                "tipoAcao": random.choice(["AJUSTAR_VELOCIDADE", "PAUSAR_PRODUCAO", "NOVO_JOB", "RESETAR_ALARMES"]),
                "valorParemtro": random.randint(50, 200),
                "timeStamp": cAgora.isoformat()
            }
            cJsonString = json.dumps(cComandoJson)
            
            cCursor.execute(cSqlPai, (cCodstr, cAgora, cTopico))
            cCursor.execute(cSqlFilho, (cCodstr, cJsonString))
            cConexao.commit()
            
            print(f"[{i}/{nQtdMensagens}] Ordem despachada para a fila: {cTopico}")
            time.sleep(nIntervaloSegundos)
    except Exception as e:
        print(f"** Erro ao injetar mensagens: {e}")
        if cConexao: cConexao.rollback()
    finally:
        if cConexao:
            cCursor.close()
            cConexao.close()
            print("\nInjeção finalizada. Conexão encerrada.")
            
if __name__ == "__main__":
    injetarMensagem(nQtdMensagens=50, nIntervaloSegundos=0.5)