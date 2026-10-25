import { Link } from 'react-router-dom'

function MaquinaCard({ maq }) {
  const ativa = maq.MAQATIVA === 'S'
  const urlDetalhes = `/maquina/${maq.SEQ_TAREFA}/${maq.MAQUINA}/${maq.IDJOB}`

  return (
    <Link to={urlDetalhes} className="machine-card">
      <div className="card-top">
        <span className="card-title">Máquina #{maq.MAQUINA}</span>
        <span className={`status-badge ${ativa ? 'status-ok' : 'status-stop'}`}>
          {ativa ? '● Operando' : '● Parada'}
        </span>
      </div>

      <div className="card-metrics">
        <div className="metric-row">
          <span className="metric-label">Ordem (Job):</span>
          <span className="metric-value">{maq.IDJOB}</span>
        </div>
        <div className="metric-row">
          <span className="metric-label">Seq. Tarefa:</span>
          <span className="metric-value">{maq.SEQ_TAREFA}</span>
        </div>
        <div className="metric-row">
          <span className="metric-label">Velocidade Atual:</span>
          <span className="metric-value">{Number(maq.VELATUAL).toLocaleString('pt-BR')} fl/h</span>
        </div>
        <div className="metric-row">
          <span className="metric-label">Prod. Líquida (Boas):</span>
          <span className="metric-value">{maq.QTDLIQ}</span>
        </div>
        <div className="metric-row">
          <span className="metric-label">Refugo:</span>
          <span className="metric-value">{maq.QTDREFUGO}</span>
        </div>
      </div>

      <div className="oee-box">
        <div className="metric-row">
          <span className="metric-label">OEE Total:</span>
          <span className="metric-value">{maq.OEETOTAL}%</span>
        </div>
        <div className="oee-bar-bg">
          <div 
            className="oee-bar-fill" 
            style={{ width: `${Math.min(100, Number(maq.OEETOTAL) || 0)}%` }}
          />
        </div>
      </div>

      <div className="card-footer">
        Ver telemetria detalhada &rarr;
      </div>
    </Link>
  )
}

export default MaquinaCard