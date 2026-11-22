import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource/cinzel/600.css'
import '@fontsource/cinzel/700.css'
import '@fontsource-variable/manrope'
import 'bootstrap/dist/js/bootstrap.bundle.min.js'
import './styles/tokens.css'
import './styles/fonts.css'
import './styles/global.css'
import './styles/components.css'
import './styles/prototype.css'
import './styles/prototypeExact.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
