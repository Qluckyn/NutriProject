const DEFAULT_API_BASE = 'http://localhost:8000'

const rawApiBase = import.meta.env.VITE_API_BASE || DEFAULT_API_BASE

export const API_BASE = rawApiBase.replace(/\/+$/, '')
