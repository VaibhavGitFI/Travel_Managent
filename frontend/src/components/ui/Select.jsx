import clsx from 'clsx'
import { ChevronDown } from 'lucide-react'

export default function Select({
  label,
  id,
  error,
  hint,
  options = [],
  placeholder,
  className,
  selectClassName,
  required,
  size = 'md',
  ...props
}) {
  const selectId = id || label?.toLowerCase().replace(/\s+/g, '-')

  const sizeClasses = {
    sm: 'h-8 text-sm pl-3 pr-8',
    md: 'h-10 text-sm pl-3 pr-8',
    lg: 'h-11 text-base pl-4 pr-10',
  }

  return (
    <div className={clsx('flex flex-col gap-1.5', className)}>
      {label && (
        <label
          htmlFor={selectId}
          className="text-sm font-medium text-gray-700 select-none"
        >
          {label}
          {required && <span className="text-red-500 ml-0.5">*</span>}
        </label>
      )}

      <div className="relative">
        <select
          id={selectId}
          className={clsx(
            'w-full rounded-lg border bg-white appearance-none transition-all duration-150',
            'text-gray-900',
            'focus:outline-none focus:ring-2 focus:ring-accent-500/20 focus:border-accent-500',
            'disabled:bg-gray-50 disabled:text-gray-400 disabled:cursor-not-allowed',
            error
              ? 'border-red-400 focus:border-red-400 focus:ring-red-400/20'
              : 'border-gray-200 hover:border-gray-300',
            sizeClasses[size],
            selectClassName
          )}
          {...props}
        >
          {placeholder && (
            <option value="" disabled>
              {placeholder}
            </option>
          )}
          {options.map((opt) => {
            if (typeof opt === 'string') {
              return <option key={opt} value={opt}>{opt}</option>
            }
            return (
              <option key={opt.value} value={opt.value} disabled={opt.disabled}>
                {opt.label}
              </option>
            )
          })}
        </select>

        <ChevronDown
          size={16}
          className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none"
        />
      </div>

      {error && (
        <p className="text-xs text-red-500">{error}</p>
      )}
      {hint && !error && (
        <p className="text-xs text-gray-500">{hint}</p>
      )}
    </div>
  )
}
