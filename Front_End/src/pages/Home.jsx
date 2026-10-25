import { useState, useEffect } from 'react'
import MaquinaCard from '../components/MaquinaCard'

function Home({ setBancoConectado }) {
  const [maquinas, setMaquinas] = useState([])
  const [carregando, setCarregando] = useState(true)
  const [erro, setErro] = useState(null)

  const buscarEstadoMaquinas = async () => {
    try {
      const resposta = await fetch('http://localhost:5000/api/estado-maquinas')
      if (!resposta.ok) {
        throw new Error(`Erro HTTP: ${resposta.status}`)
      }
      const json = await resposta.json()

      setBancoConectado(Boolean(json.bancoConectado))

      if (json.status === 'sucesso') {
        setMaquinas(json.dados)
        setErro(null)
      } else {
        setErro(json.mensagem || 'Erro ao buscar dados.')
      }
    } catch (err) {
      setBancoConectado(false)
      setErro('Não foi possível conectar à API na porta 5000. Verifique se o Docker está ativo.')
    } finally {
      setCarregando(false)
    }
  }

  useEffect(() => {
    buscarEstadoMaquinas()
    const intervalo = setInterval(buscarEstadoMaquinas, 3000)
    return () => clearInterval(intervalo)
  }, [])

  return (
    <main className="main-container">
      <div className="section-header">
        <h2>Visão Geral do Chão de Fábrica ({maquinas.length} máquinas)</h2>
        <span className="live-badge">🔄 Atualização automática (3s)</span>
      </div>

      {carregando && <p>Carregando telemetria...</p>}

      {erro && <div className="alert-box"><strong>Aviso:</strong> {erro}</div>}

      {!carregando && !erro && maquinas.length === 0 && (
        <p>Nenhuma máquina ativa na memória RAM no momento. Aguardando pacotes MQTT...</p>
      )}

      <div className="machines-grid">
        {maquinas.map((maq) => (
          <MaquinaCard 
            key={`${maq.SEQ_TAREFA}-${maq.MAQUINA}-${maq.IDJOB}`} 
            maq={maq} 
          />
        ))}
      </div>
    </main>
  )
}

export default Home