import { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Header from './components/Header'
import Home from './pages/Home'
import DetalhesMaquina from './pages/DetalhesMaquina'
import './App.css'

function App() {
  const [temaEscuro, setTemaEscuro] = useState(() => {
    return localStorage.getItem('tgi_tema') === 'dark'
  })
  const [bancoConectado, setBancoConectado] = useState(false)

  useEffect(() => {
    const atributoTema = temaEscuro ? 'dark' : 'light'
    document.documentElement.setAttribute('data-theme', atributoTema)
    localStorage.setItem('tgi_tema', atributoTema)
  }, [temaEscuro])

  const alternarTema = () => {
    setTemaEscuro((anterior) => !anterior)
  }

  return (
    <BrowserRouter>
      <Header 
        temaEscuro={temaEscuro} 
        alternarTema={alternarTema} 
        bancoConectado={bancoConectado} 
      />
      <Routes>
        <Route path="/" element={<Home setBancoConectado={setBancoConectado} />} />
        <Route 
          path="/maquina/:seqTarefa/:maquina/:job" 
          element={<DetalhesMaquina bancoConectado={bancoConectado} setBancoConectado={setBancoConectado} />} 
        />
      </Routes>
    </BrowserRouter>
  )
}

export default App