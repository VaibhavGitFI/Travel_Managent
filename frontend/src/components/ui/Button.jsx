import clsx from 'clsx'
import Spinner from './Spinner'

const variantClasses = {
  primary:
    'bg-accent-600 hover:bg-accent-700 active:bg-accent-800 text-white shadow-sm border border-accent-700/30',
  secondary:
    'bg-white hover:bg-gray-50 active:bg-gray-100 text-gray-700 border border-gray-200 shadow-sm',
  danger:
    'bg-red-600 hover:bg-red-700 active:bg-red-800 text-white shadow-sm border border-red-700/30',
  ghost:
    'bg-transparent hover:bg-gray-100 active:bg-gray-200 text-gray-700 border border-transparent',
  'ghost-white':
    'bg-transparent hover:bg-white/10 active:bg-white/20 text-white border border-transparent',
  outline:
    'bg-transparent hover:bg-accent-50 active:bg-accent-100 text-accent-600 border border-accent-300',
  success:
    'bg-success-600 hover:bg-success-700 active:bg-success-700 text-white shadow-sm border border-success-700/30',
}

const sizeClasses = {
  xs:  'px-2.5 py-1 text-xs gap-1.5 rounded-md',
  sm:  'px-3 py-1.5 text-sm gap-1.5 rounded-lg',
  md:  'px-4 py-2 text-sm gap-2 rounded-lg',
  lg:  'px-5 py-2.5 text-base gap-2 rounded-xl',
  xl:  'px-6 py-3 text-base gap-2.5 rounded-xl',
}

export default function Button({
  children,
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled = false,
  className,
  leftIcon,
  rightIcon,
  fullWidth = false,
  type = 'button',
  ...props
}) {
  const isDisabled = disabled || loading

  return (
    <button
      type={type}
      disabled={isDisabled}
      className={clsx(
        'inline-flex items-center justify-center font-medium transition-all duration-150 cursor-pointer select-none',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500 focus-visible:ring-offset-2',
        'disabled:opacity-50 disabled:cursor-not-allowed disabled:pointer-events-none',
        variantClasses[variant],
        sizeClasses[size],
        fullWidth && 'w-full',
        className
      )}
      {...props}
    >
      {loading ? (
        <Spinner
          size={size === 'xs' || size === 'sm' ? 'xs' : 'sm'}
          color={variant === 'secondary' || variant === 'ghost' || variant === 'outline' ? 'dark' : 'white'}
        />
      ) : (
        leftIcon && <span className="shrink-0">{leftIcon}</span>
      )}
      {children}
      {!loading && rightIcon && <span className="shrink-0">{rightIcon}</span>}
    </button>
  )
}
