import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import App from './App.jsx'
import useStore from './store/useStore'
import './index.css'

function ThemedToaster() {
  const theme = useStore((s) => s.theme)
  const isDark = theme === 'dark'

  return (
    <Toaster
      position="top-right"
      gutter={10}
      containerStyle={{ top: 68 }}
      toastOptions={{
        duration: 4000,
        style: {
          background: isDark ? '#0d2244' : '#ffffff',
          color: isDark ? '#f0f1ed' : '#0f172a',
          border: isDark ? '1px solid #1e3a72' : '1px solid #e2e8f0',
          borderRadius: '14px',
          fontSize: '13.5px',
          fontFamily: "'Inter', system-ui, sans-serif",
          padding: '12px 16px',
          boxShadow: isDark
            ? '0 10px 25px -5px rgba(0,0,0,.4), 0 4px 10px -6px rgba(0,0,0,.3)'
            : '0 10px 25px -5px rgba(0,0,0,.1), 0 4px 10px -6px rgba(0,0,0,.06)',
          maxWidth: '420px',
          lineHeight: '1.4',
        },
        success: {
          iconTheme: {
            primary: '#10b981',
            secondary: isDark ? '#0d2244' : '#ffffff',
          },
          style: {
            borderLeft: '4px solid #10b981',
          },
        },
        error: {
          iconTheme: {
            primary: '#ef4444',
            secondary: isDark ? '#0d2244' : '#ffffff',
          },
          style: {
            borderLeft: '4px solid #ef4444',
          },
        },
      }}
    />
  )
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
      <ThemedToaster />
    </BrowserRouter>
  </React.StrictMode>,
)
