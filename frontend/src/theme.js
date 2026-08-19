/**
 * 全局明暗主题。
 *
 * 在 <html> 上同时打 data-theme（驱动本项目的 CSS 变量）
 * 与 dark 类（驱动 Element Plus 官方暗色主题），并持久化到 localStorage。
 */
import { ref } from 'vue'

const STORAGE_KEY = 'theme'
export const theme = ref('light')

function apply(value) {
  const root = document.documentElement
  root.setAttribute('data-theme', value)
  root.classList.toggle('dark', value === 'dark')
  theme.value = value
}

export function initTheme() {
  const saved = localStorage.getItem(STORAGE_KEY)
  // 没存过则跟随系统偏好
  const prefersDark = window.matchMedia?.('(prefers-color-scheme: dark)').matches
  apply(saved || (prefersDark ? 'dark' : 'light'))
}

export function setTheme(value) {
  localStorage.setItem(STORAGE_KEY, value)
  apply(value)
}

export function toggleTheme() {
  setTheme(theme.value === 'dark' ? 'light' : 'dark')
}
