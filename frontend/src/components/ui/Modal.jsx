import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import clsx from 'clsx'

const widthClasses = {
  sm:   'max-w-md',
  md:   'max-w-lg',
  lg:   'max-w-2xl',
  xl:   'max-w-4xl',
  full: 'max-w-screen-xl mx-4',
}

export default function Modal({
  open,
  onClose,
  title,
  subtitle,
  children,
  footer,
  width = 'md',
  hideCloseButton = false,
  className,
}) {
  const overlayRef = useRef(null)

  useEffect(() => {
    if (!open) return
    const handler = (e) => { if (e.key === 'Escape') onClose?.() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, onClose])

  useEffect(() => {
    if (open) document.body.style.overflow = 'hidden'
    else document.body.style.overflow = ''
    return () => { document.body.style.overflow = '' }
  }, [open])

  if (!open) return null

  return createPortal(
    <div
      ref={overlayRef}
      className="fixed inset-0 z-[9999] flex items-center justify-center overflow-y-auto p-4 animate-fade-in"
      style={{ background: 'rgba(15,23,42,0.6)', backdropFilter: 'blur(6px)', WebkitBackdropFilter: 'blur(6px)' }}
      onClick={(e) => { if (e.target === overlayRef.current) onClose?.() }}
    >
      <div
        className={clsx(
          'relative w-full bg-white rounded-2xl shadow-2xl animate-slide-up overflow-hidden',
          widthClasses[width],
          className
        )}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? 'modal-title' : undefined}
      >
        {(title || !hideCloseButton) && (
          <div className="flex items-start justify-between px-6 py-5 border-b border-gray-100">
            <div>
              {title && (
                <h2 id="modal-title" className="text-lg font-semibold text-gray-900 font-heading">{title}</h2>
              )}
              {subtitle && <p className="text-sm text-gray-500 mt-0.5">{subtitle}</p>}
            </div>
            {!hideCloseButton && (
              <button onClick={onClose} className="ml-4 p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors shrink-0" aria-label="Close modal">
                <X size={18} />
              </button>
            )}
          </div>
        )}
        <div className="px-6 py-5">{children}</div>
        {footer && (
          <div className="flex items-center justify-end gap-3 px-6 py-4 bg-gray-50 border-t border-gray-100">{footer}</div>
        )}
      </div>
    </div>,
    document.body
  )
}
