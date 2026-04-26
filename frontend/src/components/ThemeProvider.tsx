import { useEffect } from 'react'
import { useThemeStore } from '../store/themeStore'

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const mode = useThemeStore((state) => state.mode)
  const getEffectiveTheme = useThemeStore((state) => state.getEffectiveTheme)

  useEffect(() => {
    const updateTheme = () => {
      const effectiveTheme = getEffectiveTheme()
      const html = document.documentElement

      if (effectiveTheme === 'dark') {
        html.classList.add('dark')
        html.style.colorScheme = 'dark'
      } else {
        html.classList.remove('dark')
        html.style.colorScheme = 'light'
      }
    }

    updateTheme()

    // Listen for system theme changes
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    const handleChange = () => {
      if (mode === 'system') {
        updateTheme()
      }
    }

    mediaQuery.addEventListener('change', handleChange)
    return () => mediaQuery.removeEventListener('change', handleChange)
  }, [mode, getEffectiveTheme])

  return <>{children}</>
}
