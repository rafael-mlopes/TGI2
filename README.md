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
Este repositório contém a aplicação de telemetria para chão de fábrica. O sistema coleta dados simulados de uma impressora industrial via protocolo MQTT, processa as regras de negócio através de um middleware em Python, persiste os dados em um banco MySQL (InnoDB), expõe as métricas de OEE (Overall Equipment Effectiveness) e velocidade em tempo real através de uma API REST (Flask) e as apresenta em um dashboard React com terminal de apontamento.

## ⚙️ Arquitetura (Contêineres Docker)
1. **mysql-db:** Banco de dados relacional.
2. **mqtt-broker:** Eclipse Mosquitto gerenciando as filas MQTT (com autenticação por usuário/senha).
3. **tgi-simulador:** Script Python simulando a produção da *Manroland 700 EVO*.
4. **tgi-clp (Transceiver):** Escuta o Mosquitto (`Tgi/#`), grava os JSONs brutos no banco e despacha os comandos de apontamento para as máquinas.
5. **tgi-inter (Interpretador):** Lê a fila do banco, persiste o OEE, enfileira os apontamentos do ERP e hospeda a API Web.
6. **tgi-front:** Dashboard React servido pelo Nginx em http://localhost:8080.

> ℹ️ Nos comandos `docker compose` use o **nome do serviço** (com hífen: `tgi-clp`, `tgi-inter`, `tgi-simulador`...). Os nomes com sublinhado (`tgi_clp`, `tgi_inter`...) são os nomes dos *containers*, usados em comandos `docker` (sem `compose`).

---

## 🚀 Como rodar o projeto localmente

### 1. Pré-requisitos
* **Docker Desktop** instalado e rodando.
* **VS Code** com extensão para acesso a banco de dados (ex: *MySQL* ou *Database Client*).
* Arquivo `Back_End/config.ini` com a seção `[TELEMETRIA_E2E]` (já versionado, **sem senhas**).

### 2. Credenciais (arquivo `.env`)
As senhas **não ficam mais no `config.ini`** — elas chegam aos serviços por variáveis de ambiente.
Para uso local o Compose já traz valores padrão de desenvolvimento, então este passo é opcional. Para definir as suas próprias senhas:

    cd Back_End
    cp .env.example .env      # edite os valores; o .env não é versionado

| Variável | Uso |
|---|---|
| `MYSQL_ROOT_PASSWORD` / `TGI_DB_PASSWORD` | Senhas do MySQL (valem apenas na **primeira** criação do volume `mysql_data`) |
| `TGI_MQTT_USER` / `TGI_MQTT_PASSWORD` | Usuário/senha exigidos pelo Mosquitto de todos os clientes |
| `TGI_RETENCAO_DIAS` | Dias de retenção do histórico técnico nas tabelas `CLP_*` (padrão 30; `0` desativa) |
| `VITE_API_URL` | URL da API usada pelo front-end (padrão `http://localhost:5000`) |

Para rodar os scripts Python **fora do Docker**, exporte as mesmas variáveis (ex.: `TGI_DB_HOST=127.0.0.1`, `TGI_DB_PASSWORD=...`, `TGI_MQTT_BROKER=127.0.0.1`, `TGI_MQTT_USER=...`, `TGI_MQTT_PASSWORD=...`).

### 3. Subindo a Infraestrutura
Abra o terminal na pasta `Back_End` e execute:

    docker compose up --build -d


### 4. ⚠️ PASSO CRÍTICO: Liberação no Banco de Dados
O sistema possui travas de segurança rigorosas. Ele **ignora** qualquer telemetria cuja tarefa não esteja "Rodando" (`AG_MTAR.ESTADO = 'R'`) em uma máquina cadastrada e ativa (`CLP_CEQP.ATIVO = 'S'`). A máquina de cada pacote é obtida pela tarefa (`AG_MTAR.MAQUINA`).

Conecte-se ao banco `tgi_database` (Host: `localhost`, Porta: `3306`, User: `tgi_user`, Pass: `tgi_password` ou o valor de `TGI_DB_PASSWORD`) e execute o script SQL abaixo (ele libera as 3 máquinas que o simulador gera por padrão — `QTD_MAQUINAS=3`):

    -- 1. Destrava possíveis semáforos zumbis de execuções anteriores
    UPDATE CLP_MSEMAF SET DTFIM = NOW() WHERE DTFIM IS NULL;

    -- 2. Cadastra as impressoras Roland (Máquinas 1 a 3) como ATIVAS no chão de fábrica
    INSERT INTO CLP_CEQP (MAQUINA, NOME, TOPLEITURA, TOPENVIO, ATIVO) VALUES
        (1, 'Manroland 700 EVO 01', 'Tgi/BR_SP/Planta1/Rotativa/', '', 'S'),
        (2, 'Manroland 700 EVO 02', 'Tgi/BR_SP/Planta1/Rotativa/', '', 'S'),
        (3, 'Manroland 700 EVO 03', 'Tgi/BR_SP/Planta1/Rotativa/', '', 'S');

    -- 3. Cria as Ordens de Produção (Tarefas 1 a 3) no ERP, cada uma em sua máquina, como "Rodando"
    INSERT INTO AG_MTAR (SEQ_TAREFA, CODTPTAR, MAQUINA, ESTADO, INIPROG) VALUES
        (1, 1, 1, 'R', NOW()),
        (2, 1, 2, 'R', NOW()),
        (3, 1, 3, 'R', NOW());

Não é necessário criar registros na `CLP_MACOMP`: o interpretador cria/atualiza o estado de cada tarefa automaticamente.

O transceiver relê o cadastro de máquinas/tarefas **a cada 60 segundos**, então a liberação passa a valer sozinha. Para aplicar imediatamente, reinicie os serviços (atenção: nomes dos **serviços**, com hífen):

    docker compose restart tgi-clp tgi-inter

> Ao alterar `QTD_MAQUINAS` no `docker-compose.yml`, cadastre as máquinas/tarefas correspondentes (o simulador publica a tarefa *N* para a máquina *N*).


### 5. Monitoramento (Logs)
Para verificar a fábrica virtual funcionando, acompanhe os terminais:

    # Acompanhar a impressora gerando dados a cada 3 segundos:
    docker compose logs -f tgi-simulador

    # Acompanhar o transceiver gravando no banco:
    docker compose logs -f tgi-clp

    # Acompanhar o interpretador processando e atualizando a API:
    docker compose logs -f tgi-inter


### 6. Consumindo a API REST
A API Flask expõe os dados cacheados em memória RAM para consumo imediato do Front-end (React). O cache é pré-carregado do banco quando o serviço inicia.

* 🖥️ **Dashboard Web:** http://localhost:8080 (ou `npm run dev` dentro de `Front_End`)
* 📄 **Documentação Swagger (Interativa):** http://localhost:5000/apidocs/
* 📊 **Estado (Todas as Máquinas):** http://localhost:5000/api/estado-maquinas
* 🔍 **Detalhes do Job (OEE/Ciclos):** http://localhost:5000/api/consultaJob?seqTarefa=1&maquina=1&job=JOB-10001
  * O parâmetro `job` é opcional: sem ele a API retorna o job atual da tarefa/máquina (ex.: `?seqTarefa=1&maquina=1`).
* ✍️ **Apontamento:** `POST http://localhost:5000/api/apontamento` com `{"seqTarefa": 1, "maquina": 1, "codTpOcor": 1}` (1=Setup, 2=Produção, 3=Suspensão)

---

## 🧹 Manutenção automática
* **Fila de recepção:** mensagens já processadas são removidas a cada 5 minutos (`CLP_MMSGREC`, `CLP_MMSGRECT`, `CLP_MMSGRECL`).
* **Histórico técnico:** a cada hora o transceiver remove registros mais antigos que `TGI_RETENCAO_DIAS` de `CLP_MACOMPH`, `CLP_MMSGENV/ENVT` (já enviadas), mensagens em quarentena, `CLP_MLOG` e semáforos encerrados. Tabelas do ERP (`AG_*`) nunca são apagadas.
  * Em um banco criado **antes** desta versão, crie uma vez o índice que acelera essa limpeza: `CREATE INDEX CLP_MACOMPH_CODSTR ON CLP_MACOMPH (CODSTR);` (bancos novos já o recebem pelo `init.sql`).
* **Quarentena:** um pacote inválido (JSON quebrado, tipos errados) é marcado com `EXCLUIR = 'S'` e isolado, sem interromper o processamento das demais mensagens.

## 🔐 Segurança
* O broker MQTT **não aceita conexões anônimas**: todos os clientes usam `TGI_MQTT_USER` / `TGI_MQTT_PASSWORD`.
* A porta do MySQL é publicada apenas em `127.0.0.1` (acessível somente a partir da própria máquina).
* Os arquivos `GRP.cfg` dos scripts legados (pastas `MQTT/` e `MQTTDocker/`) não são versionados; use `GRP.cfg.example` como modelo. Credenciais desses scripts vêm de variáveis de ambiente `RAJ_*`.

---

## 🛑 Comandos Úteis
* **Desligar sem perder dados:** `docker compose stop`
* **Ligar novamente:** `docker compose start`
* **Destruir tudo (Reset completo do Banco de Dados):** `docker compose down -v`
