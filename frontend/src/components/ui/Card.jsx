import clsx from 'clsx'

const paddingVariants = {
  none:  '',
  sm:    'p-4',
  md:    'p-5',
  lg:    'p-6',
  xl:    'p-8',
}

const headerPaddingVariants = {
  none: 'px-5 pt-5 pb-4',
  sm: 'px-4 pt-4 pb-3',
  md: 'px-5 pt-5 pb-4',
  lg: 'px-6 pt-6 pb-4',
  xl: 'px-8 pt-8 pb-5',
}

export default function Card({
  children,
  title,
  subtitle,
  className,
  padding = 'md',
  hover = false,
  headerRight,
  noBorder = false,
  ...props
}) {
  const contentPadding = paddingVariants[padding] ?? paddingVariants.md
  const headerPadding = headerPaddingVariants[padding] ?? headerPaddingVariants.md

  return (
    <div
      className={clsx(
        'bg-white rounded-xl shadow-card',
        !noBorder && 'border border-gray-100',
        hover && 'card-hover cursor-pointer',
        className
      )}
      {...props}
    >
      {(title || headerRight) && (
        <div
          className={clsx(
            'flex items-center justify-between border-b border-gray-50',
            headerPadding
          )}
        >
          <div>
            {title && (
              <h3 className="text-base font-semibold text-gray-900 font-heading">
                {title}
              </h3>
            )}
            {subtitle && (
              <p className="text-sm text-gray-500 mt-0.5">{subtitle}</p>
            )}
          </div>
          {headerRight && <div className="shrink-0">{headerRight}</div>}
        </div>
      )}

      <div className={contentPadding}>{children}</div>
    </div>
  )
}

// Simpler version without header
export function CardBody({ children, className, padding = 'md' }) {
  return (
    <div className={clsx('bg-white rounded-xl shadow-card border border-gray-100', paddingVariants[padding] ?? paddingVariants.md, className)}>
      {children}
    </div>
  )
}
