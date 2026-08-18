import fdb
import time

# =====================================================================
# 1. CONFIGURAÇÕES DE CONEXÃO
# =====================================================================

# Banco de Origem (Onde estão os 70 mil registros com os JSONs)
con_origem = fdb.connect(
    host='192.168.0.28', 
    database=r'D:\BANCOS_DESENV\NAZA_DW.FDB',
    user='SYSDBA',
    password='masterkey'
)
cur_origem = con_origem.cursor()

# Banco de Destino (O banco vazio que o seu chefe liberou)
con_destino = fdb.connect(
    host='192.168.0.28', 
    database=r'D:\BANCOS_DESENV\DW_ZERADO.FDB',
    user='SYSDBA',
    password='masterkey'
)
cur_destino = con_destino.cursor()

# =====================================================================
# 2. CONFIGURAÇÃO DAS QUERIES (Substitua pelos nomes reais)
# =====================================================================

# Query para buscar os dados. É fundamental listar as colunas na mesma ordem
query_select = """
    SELECT DTHORA, TOPICO, DADOS_BASE, JA_LEU, PODEEXCLUIR 
    FROM CLP_MMQTT
"""

# Query para inserir os dados no banco novo
query_insert = """
    INSERT INTO CLP_MMQTT (DTHORA, TOPICO, DADOS_BASE, JA_LEU, PODEEXCLUIR) 
    VALUES (?, ?, ?, ?, ?)
"""

# =====================================================================
# 3. EXECUÇÃO DA MIGRAÇÃO EM LOTES (BATCHING)
# =====================================================================

print("Iniciando a extração e migração dos dados...")
start_time = time.time()

# Executa o select no banco de origem
cur_origem.execute(query_select)

TAMANHO_LOTE = 10000  # Pega de 10 em 10 mil para não sobrecarregar a RAM
linhas_migradas = 0

while True:
    # fetchmany traz apenas o número de linhas definido em TAMANHO_LOTE
    lote_dados = cur_origem.fetchmany(TAMANHO_LOTE)
    
    # Se a lista voltar vazia, significa que acabaram os dados
    if not lote_dados:
        break
    
    # Insere o lote inteiro de uma vez no banco de destino
    cur_destino.executemany(query_insert, lote_dados)
    
    # Efetiva a gravação no banco de destino
    con_destino.commit()
    
    linhas_migradas += len(lote_dados)
    print(f"Progresso: {linhas_migradas} registros transferidos com sucesso...")

# =====================================================================
# 4. ENCERRAMENTO
# =====================================================================
con_origem.close()
con_destino.close()

end_time = time.time()
print("\n--- MIGRAÇÃO CONCLUÍDA! ---")
print(f"Total transferido: {linhas_migradas} registros.")
print(f"Tempo total: {end_time - start_time:.2f} segundos.")