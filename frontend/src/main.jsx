import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import App from './App.jsx'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
      <Toaster
        position="top-right"
        gutter={8}
        toastOptions={{
          duration: 4000,
          style: {
            background: '#fff',
            color: '#0a1628',
            border: '1px solid #e5e7eb',
            borderRadius: '10px',
            fontSize: '14px',
            fontFamily: 'Inter, sans-serif',
            boxShadow: '0 4px 6px -1px rgba(0,0,0,.08)',
          },
          success: {
            iconTheme: { primary: '#059669', secondary: '#fff' },
          },
          error: {
            iconTheme: { primary: '#dc2626', secondary: '#fff' },
          },
        }}
      />
    </BrowserRouter>
  </React.StrictMode>,
)
