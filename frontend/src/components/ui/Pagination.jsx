import { ChevronLeft, ChevronRight } from 'lucide-react'
import { cn } from '../../lib/cn'

export default function Pagination({ page, totalPages, total, onPageChange, className }) {
  if (totalPages <= 1) return null

  return (
    <div className={cn('flex items-center justify-between gap-3 px-4 py-3', className)}>
      <span className="text-xs text-gray-400">
        {total} total
      </span>

      <div className="flex items-center gap-1.5">
        <button
          type="button"
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          className="flex h-8 w-8 items-center justify-center rounded-lg border border-gray-200 bg-white text-gray-500 transition-colors hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
          aria-label="Previous page"
        >
          <ChevronLeft size={15} />
        </button>

        <span className="min-w-[4rem] text-center text-xs font-medium text-gray-600">
          {page} / {totalPages}
        </span>

        <button
          type="button"
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages}
          className="flex h-8 w-8 items-center justify-center rounded-lg border border-gray-200 bg-white text-gray-500 transition-colors hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
          aria-label="Next page"
        >
          <ChevronRight size={15} />
        </button>
      </div>
    </div>
  )
}
