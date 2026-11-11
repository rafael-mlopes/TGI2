"""
Leitura centralizada da configuração dos serviços TGI.

A configuração não-secreta continua vindo do config.ini (seção [TELEMETRIA_E2E],
linha CLPJS={...}). Credenciais e endereços podem (e devem, fora do ambiente de
desenvolvimento) ser informados por variáveis de ambiente, que têm prioridade
sobre o arquivo. Assim nenhuma senha precisa ficar versionada no repositório.

Variáveis suportadas:
    TGI_DB_HOST, TGI_DB_NAME, TGI_DB_USER, TGI_DB_PASSWORD
        -> aplicadas aos dois bancos (dbClient e dbMqtt)
    TGI_DBCLIENT_HOST/_NAME/_USER/_PASSWORD, TGI_DBMQTT_HOST/_NAME/_USER/_PASSWORD
        -> sobrescrevem apenas um dos bancos (têm prioridade sobre TGI_DB_*)
    TGI_MQTT_BROKER, TGI_MQTT_PORT, TGI_MQTT_USER, TGI_MQTT_PASSWORD
    TGI_RETENCAO_DIAS
"""
import os
import sys
import json

ALIAS_PADRAO = "TELEMETRIA_E2E"
RETENCAO_PADRAO_DIAS = 30

_MAPA_BANCO = {"hDB": "HOST", "db": "NAME", "uDB": "USER", "pDB": "PASSWORD"}
_MAPA_MQTT = {"broker": "BROKER", "port": "PORT", "user": "USER", "pass": "PASSWORD"}


class ErroConfiguracao(Exception):
    pass


def diretorioBase() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _lerJsonDoIni(nArquivoCfg: str, nAlias: str) -> str:
    if not os.path.exists(nArquivoCfg):
        raise ErroConfiguracao(f"Arquivo config.ini não encontrado em: {nArquivoCfg}")

    cAliasAlvo = f"[{nAlias}]"
    cDentroAlias = False
    cJsonStr = ""

    with open(nArquivoCfg, "r", encoding="utf-8", errors="ignore") as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            if linha.startswith("[") and linha.endswith("]"):
                cDentroAlias = (linha == cAliasAlvo)
                continue
            if cDentroAlias and linha.upper().startswith("CLPJS="):
                cJsonStr = linha.split("=", 1)[1].strip()
                break

    if cJsonStr == "":
        raise ErroConfiguracao(f"Linha CLPJS= não encontrada na seção {cAliasAlvo} do config.ini")
    return cJsonStr


def _env(nNome: str):
    cValor = os.getenv(nNome)
    return cValor if cValor not in (None, "") else None


def _aplicarEnvBanco(nDados: dict, nChaveBanco: str, nPrefixoEspecifico: str) -> None:
    cBanco = nDados.setdefault(nChaveBanco, {})
    for cCampo, cSufixo in _MAPA_BANCO.items():
        cValor = _env(f"{nPrefixoEspecifico}_{cSufixo}") or _env(f"TGI_DB_{cSufixo}")
        if cValor is not None:
            cBanco[cCampo] = cValor


def carregarConfig(nAlias: str = ALIAS_PADRAO, nDiretorio: str = None) -> dict:
    """Lê o config.ini e aplica as variáveis de ambiente. Lança ErroConfiguracao em caso de falha."""
    cArquivoCfg = os.path.join(nDiretorio or diretorioBase(), "config.ini")
    cJsonStr = _lerJsonDoIni(cArquivoCfg, nAlias)

    try:
        cDados = json.loads(cJsonStr.replace("'", '"').replace("\\", "\\\\"))
    except json.JSONDecodeError as e:
        raise ErroConfiguracao(f"JSON inválido na linha CLPJS do config.ini: {e}")

    _aplicarEnvBanco(cDados, "dbClient", "TGI_DBCLIENT")
    _aplicarEnvBanco(cDados, "dbMqtt", "TGI_DBMQTT")

    cMqtt = cDados.setdefault("Mqtt", {})
    for cCampo, cSufixo in _MAPA_MQTT.items():
        cValor = _env(f"TGI_MQTT_{cSufixo}")
        if cValor is not None:
            cMqtt[cCampo] = cValor
    try:
        cMqtt["port"] = int(cMqtt.get("port", 1883))
    except (TypeError, ValueError):
        raise ErroConfiguracao(f"Porta MQTT inválida: {cMqtt.get('port')}")
    cMqtt.setdefault("user", "")
    cMqtt.setdefault("pass", "")
    cMqtt.setdefault("topic", "Tgi/#")

    cRetencao = _env("TGI_RETENCAO_DIAS")
    if cRetencao is None:
        cRetencao = cDados.get("RetencaoDias", RETENCAO_PADRAO_DIAS)
    try:
        cDados["RetencaoDias"] = int(cRetencao)
    except (TypeError, ValueError):
        cDados["RetencaoDias"] = RETENCAO_PADRAO_DIAS

    cDados.setdefault("LogDetalhado", False)

    for cChaveBanco in ("dbClient", "dbMqtt"):
        cFaltando = [c for c in _MAPA_BANCO if not cDados[cChaveBanco].get(c)]
        if cFaltando:
            raise ErroConfiguracao(
                f"Configuração do banco '{cChaveBanco}' incompleta (faltando: {', '.join(cFaltando)}). "
                f"Informe no config.ini ou via variáveis de ambiente TGI_DB_*."
            )
    if not cMqtt.get("broker"):
        raise ErroConfiguracao("Broker MQTT não configurado (config.ini ou TGI_MQTT_BROKER).")

    return cDados


def carregarCredenciaisMqtt(nAlias: str = ALIAS_PADRAO, nDiretorio: str = None) -> tuple:
    """
    Versão leve usada pelo simulador (que não acessa banco): retorna (usuario, senha) do MQTT,
    lidos do config.ini (se existir) e sobrescritos por TGI_MQTT_USER / TGI_MQTT_PASSWORD.
    Nunca lança exceção: na falta de configuração devolve ("", "").
    """
    cUsuario, cSenha = "", ""
    try:
        cJsonStr = _lerJsonDoIni(os.path.join(nDiretorio or diretorioBase(), "config.ini"), nAlias)
        cMqtt = json.loads(cJsonStr.replace("'", '"').replace("\\", "\\\\")).get("Mqtt", {})
        cUsuario, cSenha = cMqtt.get("user", "") or "", cMqtt.get("pass", "") or ""
    except Exception:
        pass
    cUsuario = _env("TGI_MQTT_USER") or cUsuario
    cSenha = _env("TGI_MQTT_PASSWORD") or cSenha
    return cUsuario, cSenha
