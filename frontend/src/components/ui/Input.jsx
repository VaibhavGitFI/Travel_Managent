import clsx from 'clsx'

export default function Input({
  label,
  id,
  error,
  hint,
  leftIcon,
  rightIcon,
  className,
  inputClassName,
  required,
  size = 'md',
  ...props
}) {
  const inputId = id || label?.toLowerCase().replace(/\s+/g, '-')

  const sizeClasses = {
    sm: 'h-8 text-sm px-3',
    md: 'h-10 text-sm px-3',
    lg: 'h-11 text-base px-4',
  }

  return (
    <div className={clsx('flex flex-col gap-1.5', className)}>
      {label && (
        <label
          htmlFor={inputId}
          className="text-sm font-medium text-gray-700 select-none"
        >
          {label}
          {required && <span className="text-red-500 ml-0.5">*</span>}
        </label>
      )}

      <div className="relative flex items-center">
        {leftIcon && (
          <span className="absolute left-3 text-gray-400 pointer-events-none z-10">
            {leftIcon}
          </span>
        )}

        <input
          id={inputId}
          className={clsx(
            'w-full rounded-lg border bg-white transition-all duration-150',
            'placeholder:text-gray-400 text-gray-900',
            'focus:outline-none focus:ring-2 focus:ring-accent-500/20 focus:border-accent-500',
            'disabled:bg-gray-50 disabled:text-gray-400 disabled:cursor-not-allowed',
            error
              ? 'border-red-400 focus:border-red-400 focus:ring-red-400/20'
              : 'border-gray-200 hover:border-gray-300',
            sizeClasses[size],
            leftIcon && 'pl-9',
            rightIcon && 'pr-9',
            inputClassName
          )}
          {...props}
        />

        {rightIcon && (
          <span className="absolute right-3 text-gray-400 pointer-events-none z-10">
            {rightIcon}
          </span>
        )}
      </div>

      {error && (
        <p className="text-xs text-red-500 flex items-center gap-1">
          <svg className="w-3 h-3 shrink-0" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
          </svg>
          {error}
        </p>
      )}

      {hint && !error && (
        <p className="text-xs text-gray-500">{hint}</p>
      )}
    </div>
  )
}
