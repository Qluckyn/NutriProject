const DEFAULT_API_BASE = 'http://localhost:8000'

const rawApiBase = import.meta.env.VITE_API_BASE || DEFAULT_API_BASE

export const API_BASE = rawApiBase.replace(/\/+$/, '')

const SESSION_KEY = 'nutri_session_id'
const ASSESSMENT_KEY = 'nutri_assessment_id'
const newId = () => crypto.randomUUID().replace(/-/g, '')

function storedId(key) {
  let value = localStorage.getItem(key)
  if (!/^[0-9a-f]{32}$/.test(value || '')) {
    value = newId()
    localStorage.setItem(key, value)
  }
  return value
}

export const getSessionId = () => storedId(SESSION_KEY)
export const getAssessmentId = () => storedId(ASSESSMENT_KEY)
export function startNewAssessment() {
  const value = newId()
  localStorage.setItem(ASSESSMENT_KEY, value)
  return value
}

export function apiUrl(path) {
  const url = new URL(path, window.location.origin)
  url.searchParams.set('session_id', getSessionId())
  url.searchParams.set('assessment_id', getAssessmentId())
  return url.toString()
}

const nativeFetch = window.fetch.bind(window)
window.fetch = (input, init) => {
  const address = typeof input === 'string' ? input : input.url
  return nativeFetch(apiUrl(address), init)
}
