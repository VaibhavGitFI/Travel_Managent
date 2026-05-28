import { useState } from 'react'
import OtisVoiceWidget from './OtisVoiceWidget'
import useStore from '../../store/useStore'

// ─────────────────────────────────────────────────────────────────────────────
// OtisLauncher — click-to-open JARVIS launcher
// ─────────────────────────────────────────────────────────────────────────────
export default function OtisLauncher() {
  const { auth, theme } = useStore()
  const isDark = theme === 'dark'
  const [isOpen, setIsOpen] = useState(false)
  const [hovered, setHovered] = useState(false)

  if (!auth.isLoggedIn) return null

  return (
    <>
      <style>{`
        @keyframes jarvis-fade-in {
          from { opacity: 0; transform: translateY(-50%) translateX(6px); }
          to   { opacity: 1; transform: translateY(-50%) translateX(0); }
        }
        @keyframes jarvis-launcher-glow {
          0%,100% { box-shadow: ${isDark
            ? '0 4px 20px rgba(76,201,240,0.3), 0 2px 8px rgba(0,0,0,0.4)'
            : '0 4px 16px rgba(26,86,219,0.35), 0 2px 6px rgba(0,0,0,0.12)'}; }
          50%     { box-shadow: ${isDark
            ? '0 4px 30px rgba(76,201,240,0.5), 0 2px 8px rgba(0,0,0,0.4)'
            : '0 4px 24px rgba(14,165,233,0.6), 0 2px 6px rgba(0,0,0,0.12)'}; }
        }
      `}</style>

      {!isOpen && (
        <div style={{
          position: 'fixed',
          bottom: '28px',
          right: '28px',
          zIndex: 9998,
          width: '56px',
          height: '56px',
        }}>
          <button
            onClick={() => setIsOpen(true)}
            onMouseEnter={() => setHovered(true)}
            onMouseLeave={() => setHovered(false)}
            aria-label="Open Jarvis Voice Assistant"
            title="Open Jarvis"
            style={{
              width: '56px',
              height: '56px',
              borderRadius: '50%',
              border: isDark ? '2px solid rgba(255,255,255,0.15)' : '2px solid rgba(255,255,255,0.5)',
              cursor: 'pointer',
              position: 'relative',
              overflow: 'hidden',
              background: 'linear-gradient(135deg, #1a56db 0%, #0ea5e9 50%, #4CC9F0 100%)',
              animation: 'jarvis-launcher-glow 3s ease-in-out infinite',
              transform: hovered ? 'scale(1.06)' : 'scale(1)',
              transition: 'transform 0.15s ease',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <div style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: '100%',
              background: 'radial-gradient(circle at 30% 30%, rgba(255,255,255,0.3) 0%, transparent 60%)',
              filter: 'blur(4px)',
              pointerEvents: 'none',
            }} />

            <span style={{
              fontSize: '9px',
              fontWeight: 800,
              letterSpacing: '0.18em',
              textTransform: 'uppercase',
              color: 'rgba(255,255,255,0.95)',
              fontFamily: "'Inter', system-ui, sans-serif",
              position: 'relative',
              zIndex: 1,
            }}>
              JARVIS
            </span>
          </button>

          {hovered && (
            <div style={{
              position: 'absolute',
              right: '64px',
              top: '50%',
              transform: 'translateY(-50%)',
              whiteSpace: 'nowrap',
              pointerEvents: 'none',
              padding: '6px 12px',
              borderRadius: '10px',
              fontSize: '12px',
              fontWeight: 500,
              fontFamily: "'Inter', system-ui, sans-serif",
              background: isDark ? '#0d2244' : '#ffffff',
              border: `1px solid ${isDark ? '#1e3a72' : '#e2e8f0'}`,
              color: isDark ? '#f0f1ed' : '#0f172a',
              boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
              animation: 'jarvis-fade-in 0.15s ease',
            }}>
              Click to open Jarvis
            </div>
          )}
        </div>
      )}

      {isOpen && (
        <OtisVoiceWidget
          autoStart
          entryMode="manual"
          onClose={() => setIsOpen(false)}
        />
      )}
    </>
  )
}
