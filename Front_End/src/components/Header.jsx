import { Link } from 'react-router-dom'

function Header({ temaEscuro, alternarTema, bancoConectado }) {
  return (
    <header className="header">
      <Link to="/" className="header-brand">
        <div>
          <h1>🏭 Dashboard de Telemetria - TGI</h1>
          <span className="header-subtitle">Monitoramento e Apontamento Industrial End-to-End</span>
        </div>
      </Link>

      <div className="header-actions">
        <span className={`db-badge ${bancoConectado ? 'db-online' : 'db-offline'}`}>
          {bancoConectado 
            ? '🟢 Banco Conectado (Apontamento Ativo)' 
            : '🟡 Banco Offline (Modo Visualização)'}
        </span>

        <button onClick={alternarTema} className="theme-btn">
          {temaEscuro ? '☀️ Modo Claro' : '🌙 Modo Escuro'}
        </button>
      </div>
    </header>
  )
}

export default Header