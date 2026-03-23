import { cn } from '../../lib/cn'

export function Skeleton({ className, ...props }) {
  return <div className={cn('skeleton', className)} {...props} />
}

export function SkeletonText({ lines = 3, className }) {
  return (
    <div className={cn('space-y-2', className)}>
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className={cn('skeleton h-3.5', i === lines - 1 ? 'w-3/4' : 'w-full')}
        />
      ))}
    </div>
  )
}

export function SkeletonCard({ className }) {
  return (
    <div className={cn('rounded-xl border border-gray-100 bg-white p-5 space-y-3', className)}>
      <div className="flex items-center gap-2.5">
        <div className="skeleton h-9 w-9 rounded-xl" />
        <div className="space-y-1.5 flex-1">
          <div className="skeleton h-4 w-32" />
          <div className="skeleton h-3 w-20" />
        </div>
      </div>
      <div className="skeleton h-3.5 w-full" />
      <div className="skeleton h-3.5 w-2/3" />
    </div>
  )
}

export function SkeletonRow({ className }) {
  return (
    <div className={cn('flex items-center gap-3 px-5 py-3.5', className)}>
      <div className="skeleton h-9 w-9 rounded-xl shrink-0" />
      <div className="flex-1 space-y-1.5">
        <div className="skeleton h-4 w-48" />
        <div className="skeleton h-3 w-32" />
      </div>
      <div className="skeleton h-6 w-20 rounded-full shrink-0" />
    </div>
  )
}

export function SkeletonTable({ rows = 5, cols = 5, className }) {
  return (
    <div className={cn('overflow-hidden', className)}>
      <div className="bg-gray-50 px-6 py-3 flex gap-6">
        {Array.from({ length: cols }).map((_, i) => (
          <div key={i} className="skeleton h-3.5 w-20 flex-1" />
        ))}
      </div>
      <div className="divide-y divide-gray-50">
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="px-6 py-4 flex gap-6">
            {Array.from({ length: cols }).map((_, j) => (
              <div key={j} className="skeleton h-4 flex-1" style={{ maxWidth: j === 0 ? '12rem' : undefined }} />
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}
