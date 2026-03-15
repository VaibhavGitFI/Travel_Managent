import clsx from 'clsx'

const sizes = {
  xs:  'w-3 h-3 border-[1.5px]',
  sm:  'w-4 h-4 border-2',
  md:  'w-6 h-6 border-2',
  lg:  'w-8 h-8 border-[3px]',
  xl:  'w-12 h-12 border-4',
}

const colors = {
  white:  'border-white/25 border-t-white',
  dark:   'border-gray-200 border-t-gray-600',
  accent: 'border-accent-100 border-t-accent-600',
  sky:    'border-sky-100 border-t-sky-500',
}

export default function Spinner({ size = 'md', color = 'accent', className }) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={clsx(
        'inline-block rounded-full animate-spin',
        sizes[size],
        colors[color],
        className
      )}
    />
  )
}
