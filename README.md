# 🏭 TGI 2 - Telemetria Industrial End-to-End

**Universidade Cruzeiro do Sul - Ciência da Computação (7º Semestre - 2026)**  
**Projeto:** Modernização de Arquitetura de Telemetria Industrial (Migração Firebird para MySQL/Docker)  
**Orientador:** Prof. Alexandre Miccheleti Lucena  
**Equipe:** 
* Rafael Mendes Martins Lopes (RGM: 34271503)
* Pietro Danton Silveira (RGM: 33512515)
* Vinicius Tadeu Silva dos Santos (RGM: 34360883)

---

## 📌 Sobre o Projeto
Este repositório contém o back-end da aplicação de telemetria para chão de fábrica. O sistema coleta dados simulados de uma impressora industrial via protocolo MQTT, processa as regras de negócio através de um middleware em Python, persiste os dados em um banco MySQL (InnoDB) e expõe as métricas de OEE (Overall Equipment Effectiveness) e velocidade em tempo real através de uma API REST (Flask).

## ⚙️ Arquitetura (Contêineres Docker)
1. **mysql-db:** Banco de dados relacional.
2. **mqtt-broker:** Eclipse Mosquitto gerenciando as filas MQTT.
3. **tgi-simulador:** Script Python simulando a produção da *Manroland 700 EVO*.
4. **tgi-clp (Transceiver):** Escuta o Mosquitto (`Tgi/#`) e grava os JSONs brutos no banco.
5. **tgi-inter (Interpretador):** Lê a fila do banco, calcula o OEE, atualiza o status do ERP e hospeda a API Web.

---

## 🚀 Como rodar o projeto localmente

### 1. Pré-requisitos
* **Docker Desktop** instalado e rodando.
* **VS Code** com extensão para acesso a banco de dados (ex: *MySQL* ou *Database Client*).
* Arquivo `config.ini` devidamente configurado na raiz do projeto (contendo a chave `[TELEMETRIA_E2E]` e as credenciais do banco/broker).

### 2. Subindo a Infraestrutura
Abra o terminal na pasta raiz do projeto e execute:

    docker compose up --build -d


### 3. ⚠️ PASSO CRÍTICO: Liberação no Banco de Dados
O sistema possui travas de segurança rigorosas. Ele **ignora** qualquer telemetria de máquinas que não estejam cadastradas e com uma Ordem de Produção (Job) "Rodando".

Conecte-se ao banco `tgi_database` (Host: `localhost`, Porta: `3306`, User: `tgi_user`, Pass: `tgi_password`) e execute o script SQL abaixo:

    -- 1. Destrava possíveis semáforos zumbis de execuções anteriores
    UPDATE CLP_MSEMAF SET DTFIM = NOW() WHERE DTFIM IS NULL;

    -- 2. Cadastra a Impressora Roland (Máquina 1) como ATIVA no chão de fábrica
    INSERT INTO CLP_CEQP (MAQUINA, NOME, TOPLEITURA, TOPENVIO, ATIVO)
    VALUES (1, 'Manroland 700 EVO', 'Tgi/BR_SP/Planta1/Rotativa/', '', 'S');

    -- 3. Cria a Ordem de Produção (Tarefa 1) no ERP associada à Máquina 1
    INSERT INTO AG_MTAR (SEQ_TAREFA, CODTPTAR, MAQUINA, ESTADO, INIPROG) 
    VALUES (1, 1, 1, 'R', NOW());

    -- 4. Inicializa o estado de produção da máquina
    INSERT INTO CLP_MACOMP (SEQ_TAREFA, MAQUINA, IDJOB, MAQATIVA) 
    VALUES (1, 1, 'JOB-SIMULACAO', 'S');

Após rodar este script, reinicie os interpretadores para que leiam as máquinas ativas:

    docker compose restart tgi_clp tgi_inter


### 4. Monitoramento (Logs)
Para verificar a fábrica virtual funcionando, acompanhe os terminais:

    # Acompanhar a impressora gerando dados a cada 3 segundos:
    docker compose logs -f tgi_simulador

    # Acompanhar o transceiver gravando no banco:
    docker compose logs -f tgi_clp

    # Acompanhar o interpretador processando e atualizando a API:
    docker compose logs -f tgi_inter


### 5. Consumindo a API REST
A API Flask expõe os dados cacheados em memória RAM para consumo imediato do Front-end (React).

* 📄 **Documentação Swagger (Interativa):** http://localhost:5000/apidocs/
* 📊 **Dashboard (Todas as Máquinas):** http://localhost:5000/api/estado-maquinas
* 🔍 **Detalhes do Job (OEE/Ciclos):** http://localhost:5000/api/consultaJob?seqTarefa=1&maquina=1

---

## 🛑 Comandos Úteis
* **Desligar sem perder dados:** `docker compose stop`
* **Ligar novamente:** `docker compose start`
* **Destruir tudo (Reset completo do Banco de Dados):** `docker compose down -v`