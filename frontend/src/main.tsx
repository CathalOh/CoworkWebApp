import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { registerBuiltinSlots } from './slots'
import './styles/global.css'

registerBuiltinSlots()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
