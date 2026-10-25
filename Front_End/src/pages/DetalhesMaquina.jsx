import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'

function DetalhesMaquina({ bancoConectado, setBancoConectado }) {
  const { seqTarefa, maquina, job } = useParams()
  const [dados, setDados] = useState(null)
  const [origem, setOrigem] = useState('')
  const [carregando, setCarregando] = useState(true)
  const [erro, setErro] = useState(null)
  const [enviandoApontamento, setEnviandoApontamento] = useState(false)
  const [mensagemFeedback, setMensagemFeedback] = useState('')

  const buscarDetalhesJob = async () => {
    try {
      const url = `http://localhost:5000/api/consultaJob?seqTarefa=${seqTarefa}&maquina=${maquina}&job=${job}`
      const resposta = await fetch(url)
      const json = await resposta.json()

      if (json.bancoConectado !== undefined) {
        setBancoConectado(Boolean(json.bancoConectado))
      }

      if (resposta.ok && json.status === 'sucesso') {
        setDados(json.dados)
        setOrigem(json.origem)
        setErro(null)
      } else {
        setErro(json.mensagem || 'Máquina não encontrada.')
      }
    } catch (err) {
      setBancoConectado(false)
      setErro('Falha de comunicação com a API.')
    } finally {
      setCarregando(false)
    }
  }

  useEffect(() => {
    buscarDetalhesJob()
    const intervalo = setInterval(buscarDetalhesJob, 3000)
    return () => clearInterval(intervalo)
  }, [seqTarefa, maquina, job])

  const enviarApontamento = async (codTpOcor) => {
    setEnviandoApontamento(true)
    setMensagemFeedback('Gravando ocorrência na AG_MOCOR e enviando via MQTT...')
    try {
      const resposta = await fetch('http://localhost:5000/api/apontamento', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          seqTarefa: Number(seqTarefa),
          maquina: Number(maquina),
          codTpOcor: Number(codTpOcor)
        })
      })
      const json = await resposta.json()
      setBancoConectado(Boolean(json.bancoConectado))

      if (resposta.ok && json.status === 'sucesso') {
        setMensagemFeedback(`✅ ${json.mensagem} (Aguarde ~5s para o CLP publicar no MQTT)`)
        buscarDetalhesJob()
      } else {
        setMensagemFeedback(`⚠️ ${json.mensagem}`)
      }
    } catch (err) {
      setBancoConectado(false)
      setMensagemFeedback('❌ Sem conexão com o banco de dados. Operando apenas como visualizador.')
    } finally {
      setEnviandoApontamento(false)
    }
  }

  if (carregando) {
    return <main className="main-container"><p>Carregando detalhes da Máquina #{maquina}...</p></main>
  }

  if (erro || !dados) {
    return (
      <main className="main-container">
        <Link to="/" className="back-btn">&larr; Voltar para o Painel Geral</Link>
        <div className="alert-box"><strong>Erro:</strong> {erro}</div>
      </main>
    )
  }

  const ativa = dados.MAQATIVA === 'S'
  const modoAtual = dados.APONTAMENTO_ATUAL || 2

  return (
    <main className="main-container">
      <Link to="/" className="back-btn">&larr; Voltar para o Painel Geral</Link>

      <div className="details-header-card">
        <div>
          <h2>Impressora Manroland 700 EVO — Máquina #{dados.MAQUINA}</h2>
          <p className="header-subtitle">
            Ordem de Produção: <strong>{dados.IDJOB}</strong> | Seq. Tarefa: <strong>{dados.SEQ_TAREFA}</strong> | Leitura via: <strong>{origem.toUpperCase()}</strong>
          </p>
        </div>
        <span className={`status-badge ${ativa ? 'status-ok' : 'status-stop'}`}>
          {ativa ? '● Operando (Ativa)' : '● Máquina Parada'}
        </span>
      </div>

      {/* Painel de Apontamento de Produção (AG_MOCOR -> MQTT -> Simulador) */}
      <div className="apontamento-panel">
        <div className="apontamento-header">
          <h3> Terminal de Apontamento de Ocorrências </h3>
          {!bancoConectado && (
            <span className="status-badge status-stop">
              ⚠️ Banco Offline: Modo Somente Visualização
            </span>
          )}
        </div>

        <div className="apontamento-buttons">
          <button
            className={`apont-btn ${modoAtual === 1 ? 'ativo-setup' : ''}`}
            disabled={!bancoConectado || enviandoApontamento}
            onClick={() => enviarApontamento(1)}
          >
            1. Apontar SETUP
          </button>

          <button
            className={`apont-btn ${modoAtual === 2 ? 'ativo-producao' : ''}`}
            disabled={!bancoConectado || enviandoApontamento}
            onClick={() => enviarApontamento(2)}
          >
            2. Apontar PRODUÇÃO
          </button>

          <button
            className={`apont-btn ${modoAtual === 3 ? 'ativo-suspensao' : ''}`}
            disabled={!bancoConectado || enviandoApontamento}
            onClick={() => enviarApontamento(3)}
          >
            3. Apontar SUSPENSÃO
          </button>
        </div>

        {mensagemFeedback && <p className="feedback-msg">{mensagemFeedback}</p>}
      </div>

      <div className="details-grid">
        <div className="details-panel">
          <h3>📊 Eficiência Global do Equipamento (OEE)</h3>
          <div className="kpi-grid">
            <div className="kpi-item">
              <span>OEE Total</span>
              <strong>{dados.OEETOTAL}%</strong>
            </div>
            <div className="kpi-item">
              <span>Disponibilidade</span>
              <strong>{dados.OEEDISP}%</strong>
            </div>
            <div className="kpi-item">
              <span>Performance (Desempenho)</span>
              <strong>{dados.OEEDESEMP}%</strong>
            </div>
            <div className="kpi-item">
              <span>Qualidade</span>
              <strong>{dados.OEEQUALID}%</strong>
            </div>
          </div>
        </div>

        <div className="details-panel">
          <h3>📦 Contadores de Produção</h3>
          <div className="kpi-grid">
            <div className="kpi-item">
              <span>Quantidade Líquida (Boas)</span>
              <strong>{dados.QTDLIQ} fls</strong>
            </div>
            <div className="kpi-item">
              <span>Quantidade Bruta Total</span>
              <strong>{dados.QTDBRUTA} fls</strong>
            </div>
            <div className="kpi-item">
              <span>Refugo (Perdas)</span>
              <strong>{dados.QTDREFUGO} fls</strong>
            </div>
            <div className="kpi-item">
              <span>Acionamentos de Setup</span>
              <strong>{dados.QTDSETUP}</strong>
            </div>
          </div>
        </div>

        <div className="details-panel">
          <h3>⚡ Velocidades e Ciclos</h3>
          <div className="kpi-grid">
            <div className="kpi-item">
              <span>Velocidade Atual</span>
              <strong>{Number(dados.VELATUAL).toLocaleString('pt-BR')} fl/h</strong>
            </div>
            <div className="kpi-item">
              <span>Velocidade Média (Curto Prazo)</span>
              <strong>{Number(dados.VELMEDCURTA).toLocaleString('pt-BR')} fl/h</strong>
            </div>
            <div className="kpi-item">
              <span>Velocidade Média Global</span>
              <strong>{Number(dados.VELMEDGLOBAL).toLocaleString('pt-BR')} fl/h</strong>
            </div>
            <div className="kpi-item">
              <span>Ciclo Atual / Ciclo Médio</span>
              <strong>{dados.CICLOATUAL}s / {dados.CICLOMED}s</strong>
            </div>
          </div>
        </div>

        <div className="details-panel">
          <h3>⏱️ Tempos de Operação (Segundos)</h3>
          <div className="kpi-grid">
            <div className="kpi-item">
              <span>Tempo Total Decorrido</span>
              <strong>{dados.TMPTOTAL} s</strong>
            </div>
            <div className="kpi-item">
              <span>Tempo Restante Estimado</span>
              <strong>{dados.TMPREST} s</strong>
            </div>
            <div className="kpi-item">
              <span>Tempo de Produção Boa</span>
              <strong>{dados.TMPBONS} s</strong>
            </div>
            <div className="kpi-item">
              <span>Execução / Prep. / Parado</span>
              <strong>{dados.TMPEXEC}s / {dados.TMPPREP}s / {dados.TMPPARADO}s</strong>
            </div>
          </div>
        </div>
      </div>
    </main>
  )
}

export default DetalhesMaquina