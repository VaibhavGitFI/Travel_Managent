import { cn } from '../../lib/cn'
import { TrendingUp, TrendingDown, Minus } from 'lucide-react'

export default function StatCard({
  icon,
  value,
  label,
  trend,
  trendLabel,
  className,
  accentColor = 'blue',
  loading = false,
}) {
  const accentMap = {
    blue:   { bg: 'bg-accent-50',   icon: 'text-accent-600',  border: 'border-accent-100' },
    sky:    { bg: 'bg-sky-50',      icon: 'text-sky-600',     border: 'border-sky-100' },
    green:  { bg: 'bg-success-50',  icon: 'text-success-600', border: 'border-success-100' },
    orange: { bg: 'bg-warning-50',  icon: 'text-warning-600', border: 'border-warning-100' },
    red:    { bg: 'bg-red-50',      icon: 'text-red-600',     border: 'border-red-100' },
    purple: { bg: 'bg-purple-50',   icon: 'text-purple-600',  border: 'border-purple-100' },
    corporate: { bg: 'bg-surface-sunken', icon: 'text-brand-dark', border: 'border-surface-border' },
  }

  const accent = accentMap[accentColor] || accentMap.blue

  const isPositive = typeof trend === 'number' ? trend > 0 : trend === 'up'
  const isNegative = typeof trend === 'number' ? trend < 0 : trend === 'down'
  const isNeutral  = !isPositive && !isNegative

  const trendValue = typeof trend === 'number'
    ? `${Math.abs(trend)}%`
    : null

  return (
    <div
      className={cn(
        'bg-white rounded-xl border border-gray-100 shadow-card p-5 card-hover',
        className
      )}
    >
      {loading ? (
        <div className="space-y-3">
          <div className="skeleton h-10 w-10 rounded-lg" />
          <div className="skeleton h-7 w-24" />
          <div className="skeleton h-4 w-32" />
        </div>
      ) : (
        <>
          {/* Icon */}
          {icon && (
            <div
              className={cn(
                'inline-flex items-center justify-center w-11 h-11 rounded-xl mb-4',
                accent.bg,
                'border',
                accent.border
              )}
            >
              <span className={cn('w-5 h-5', accent.icon)}>{icon}</span>
            </div>
          )}

          {/* Value */}
          <div className="text-2xl font-bold text-gray-900 font-heading animate-count mb-1">
            {value}
          </div>

          {/* Label */}
          <div className="text-sm text-gray-500 font-medium">{label}</div>

          {/* Trend */}
          {(trend !== undefined && trend !== null) && (
            <div
              className={cn(
                'flex items-center gap-1 mt-3 text-xs font-medium',
                isPositive && 'text-success-600',
                isNegative && 'text-red-600',
                isNeutral  && 'text-gray-500',
              )}
            >
              {isPositive && <TrendingUp size={13} />}
              {isNegative && <TrendingDown size={13} />}
              {isNeutral  && <Minus size={13} />}
              {trendValue && <span>{trendValue}</span>}
              {trendLabel && <span className="text-gray-400 font-normal">{trendLabel}</span>}
            </div>
          )}
        </>
      )}
    </div>
  )
}
