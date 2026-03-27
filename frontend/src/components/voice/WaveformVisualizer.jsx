import { useEffect, useRef } from 'react'
import { cn } from '../../lib/cn'

/**
 * Waveform Visualizer Component
 *
 * Animated waveform bars that respond to audio input.
 * Used in OTIS voice widget to show listening/speaking state.
 *
 * Props:
 * - active: boolean - Whether visualization is active
 * - level: number - Audio level (0-100)
 * - barCount: number - Number of bars to display (default: 5)
 * - color: string - Bar color (default: blue-500)
 */

export default function WaveformVisualizer({
  active = false,
  level = 50,
  barCount = 5,
  color = 'blue',
}) {
  const barsRef = useRef([])
  const animationRef = useRef(null)

  useEffect(() => {
    if (!active) {
      // Reset bars to idle state
      barsRef.current.forEach((bar) => {
        if (bar) bar.style.height = '20%'
      })
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current)
      }
      return
    }

    // Animate bars
    const animate = () => {
      barsRef.current.forEach((bar, index) => {
        if (!bar) return

        // Each bar has a slightly different frequency and phase
        const frequency = 0.1 + index * 0.02
        const phase = index * 0.5
        const time = Date.now() * 0.001

        // Calculate height with sine wave + randomness
        const baseHeight = Math.sin(time * frequency + phase) * 0.3 + 0.5
        const noise = Math.random() * 0.2
        const audioInfluence = level / 100

        const height = Math.max(
          20,
          Math.min(100, (baseHeight + noise) * 100 * (0.5 + audioInfluence * 0.5))
        )

        bar.style.height = `${height}%`
      })

      animationRef.current = requestAnimationFrame(animate)
    }

    animate()

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current)
      }
    }
  }, [active, level])

  return (
    <div className="flex items-center justify-center gap-1 h-16 py-2">
      {Array.from({ length: barCount }).map((_, index) => (
        <div
          key={index}
          ref={(el) => (barsRef.current[index] = el)}
          className={cn(
            'w-2 rounded-full transition-all duration-100',
            `bg-${color}-500`,
            active ? 'opacity-100' : 'opacity-30'
          )}
          style={{
            height: '20%',
            minHeight: '8px',
          }}
        />
      ))}
    </div>
  )
}
