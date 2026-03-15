import clsx from 'clsx'

const variants = {
  blue:   'bg-accent-50 text-accent-700 border border-accent-100',
  sky:    'bg-sky-50 text-sky-700 border border-sky-100',
  green:  'bg-success-50 text-success-700 border border-success-100',
  orange: 'bg-warning-50 text-warning-700 border border-warning-100',
  red:    'bg-red-50 text-red-700 border border-red-100',
  gray:   'bg-gray-100 text-gray-600 border border-gray-200',
  navy:   'bg-navy-900 text-white border border-navy-800',
  purple: 'bg-purple-50 text-purple-700 border border-purple-100',
}

const sizes = {
  xs: 'px-1.5 py-0.5 text-xs gap-1',
  sm: 'px-2 py-0.5 text-xs gap-1',
  md: 'px-2.5 py-1 text-xs gap-1.5',
  lg: 'px-3 py-1 text-sm gap-1.5',
}

// Maps common status strings to color variants
const statusMap = {
  approved:   'green',
  active:     'green',
  completed:  'green',
  pending:    'orange',
  'in-progress': 'orange',
  review:     'blue',
  rejected:   'red',
  cancelled:  'gray',
  draft:      'gray',
  planning:   'sky',
  submitted:  'blue',
}

export default function Badge({
  children,
  variant,
  status,
  size = 'sm',
  dot = false,
  className,
}) {
  const resolvedVariant = variant || statusMap[status?.toLowerCase()] || 'gray'

  return (
    <span
      className={clsx(
        'inline-flex items-center font-medium rounded-full whitespace-nowrap',
        variants[resolvedVariant],
        sizes[size],
        className
      )}
    >
      {dot && (
        <span
          className={clsx(
            'w-1.5 h-1.5 rounded-full shrink-0',
            resolvedVariant === 'green'  && 'bg-success-500',
            resolvedVariant === 'orange' && 'bg-warning-500',
            resolvedVariant === 'red'    && 'bg-red-500',
            resolvedVariant === 'blue'   && 'bg-accent-500',
            resolvedVariant === 'sky'    && 'bg-sky-500',
            resolvedVariant === 'gray'   && 'bg-gray-400',
            resolvedVariant === 'navy'   && 'bg-white',
            resolvedVariant === 'purple' && 'bg-purple-500',
          )}
        />
      )}
      {children}
    </span>
  )
}
