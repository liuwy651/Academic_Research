import { Moon, Sun, Monitor } from 'lucide-react'
import { useThemeStore, type ThemeMode } from '../store/themeStore'

export function ThemeToggle() {
  const mode = useThemeStore((state) => state.mode)
  const setMode = useThemeStore((state) => state.setMode)

  const cycleTheme = () => {
    const modes: ThemeMode[] = ['light', 'dark', 'system']
    const currentIndex = modes.indexOf(mode)
    const nextIndex = (currentIndex + 1) % modes.length
    setMode(modes[nextIndex])
  }

  return (
    <button
      onClick={cycleTheme}
      className="p-2 rounded-lg transition-colors"
      title={`Theme: ${mode}`}
      aria-label="Toggle theme"
      style={{
        color: 'var(--text-secondary)',
        backgroundColor: 'transparent',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.backgroundColor = 'var(--hover-bg)'
        e.currentTarget.style.color = 'var(--text-primary)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.backgroundColor = 'transparent'
        e.currentTarget.style.color = 'var(--text-secondary)'
      }}
    >
      {mode === 'light' && <Sun size={20} />}
      {mode === 'dark' && <Moon size={20} />}
      {mode === 'system' && <Monitor size={20} />}
    </button>
  )
}
