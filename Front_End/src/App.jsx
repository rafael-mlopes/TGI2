import { useState, useEffect } from 'react'
import './App.css'

function App() {
  const [maquinas, setMaquinas] = useState([])
  const [carregando, setCarregando] = useState(true)
  const [erro, setErro] = useState(null)

  // Função que busca os dados na API Flask
  const buscarEstadoMaquinas = async () => {
    try {
      const resposta = await fetch('http://localhost:5000/api/estado-maquinas')
      
      if (!resposta.ok) {
        throw new Error(`Erro na comunicação com a API (Status: ${resposta.status})`)
      }

      const json = await resposta.json()

      if (json.status === 'sucesso') {
        setMaquinas(json.dados)
        setErro(null)
      } else {
        setErro(json.mensagem || 'Erro desconhecido ao processar dados.')
      }
    } catch (err) {
      console.error('Falha no fetch:', err)
      setErro('Não foi possível conectar ao servidor de telemetria (Verifique se o Docker está rodando).')
    } finally {
      setCarregando(false)
    }
  }

  // Dispara a busca ao abrir a tela e atualiza a cada 3 segundos
  useEffect(() => {
    buscarEstadoMaquinas()

    const intervalo = setInterval(() => {
      buscarEstadoMaquinas()
    }, 3000)

    // Limpa o intervalo se o componente for desmontado
    return () => clearInterval(intervalo)
  }, [])

  return (
    <div style={{ padding: '20px', fontFamily: 'sans-serif' }}>
      <h1>Dashboard de Telemetria - TGI</h1>
      <hr />

      {carregando && <p>Carregando dados do chão de fábrica...</p>}
      
      {erro && <p style={{ color: 'red' }}><strong>Aviso:</strong> {erro}</p>}

      {!carregando && !erro && maquinas.length === 0 && (
        <p>Nenhuma máquina operando ou enviando telemetria na memória RAM no momento.</p>
      )}

      {/* Lista de Cards das Máquinas */}
      <div>
        {maquinas.map((maq) => {
          // Chave única combinando os identificadores principais
          const chaveUnica = `${maq.SEQ_TAREFA}-${maq.MAQUINA}-${maq.IDJOB}`

          return (
            <div 
              key={chaveUnica} 
              style={{ border: '1px solid #000', margin: '15px 0', padding: '15px' }}
            >
              <h2>Máquina: {maq.MAQUINA}</h2>
              <p><strong>Status:</strong> {maq.MAQATIVA === 'S' ? '🟢 Operando (Ativa)' : '🔴 Parada'}</p>
              <p><strong>Ordem de Produção (Job):</strong> {maq.IDJOB}</p>
              <p><strong>Seq. Tarefa:</strong> {maq.SEQ_TAREFA}</p>
              <p><strong>Velocidade Atual:</strong> {maq.VELATUAL} ciclos/h</p>
              <p><strong>Produção Líquida (Bons):</strong> {maq.QTDLIQ} | <strong>Refugo:</strong> {maq.QTDREFUGO}</p>
              <p><strong>OEE Total:</strong> {maq.OEETOTAL}%</p>

              {/* Estrutura pronta para receber a navegação no próximo passo */}
              <a 
                href={`#detalhes?seqTarefa=${maq.SEQ_TAREFA}&maquina=${maq.MAQUINA}&job=${maq.IDJOB}`}
              >
                Ver detalhes desta máquina &rarr;
              </a>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default App