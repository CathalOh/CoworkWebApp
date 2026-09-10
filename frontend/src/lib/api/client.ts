import type { Problem } from './types'

export const API_BASE: string = (import.meta.env.VITE_API_BASE ?? '').replace(/\/$/, '')

export class ApiError extends Error {
  status: number
  problem: Problem
  constructor(problem: Problem) {
    super(problem.detail || problem.title)
    this.name = 'ApiError'
    this.status = problem.status
    this.problem = problem
  }
}

type Listener = (err: ApiError) => void
const unauthorizedListeners = new Set<Listener>()
/** Register a handler for 401s (the auth store redirects to /login). */
export function onUnauthorized(fn: Listener): () => void {
  unauthorizedListeners.add(fn)
  return () => unauthorizedListeners.delete(fn)
}

let csrfToken: string | null = null
export function setCsrfToken(token: string | null | undefined) {
  csrfToken = token ?? null
}
export function getCsrfToken() {
  return csrfToken
}

const MUTATING = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

export interface RequestOptions {
  method?: string
  body?: unknown
  /** FormData bodies are sent as-is (multipart). */
  form?: FormData
  query?: Record<string, string | number | boolean | null | undefined>
  signal?: AbortSignal
  headers?: Record<string, string>
}

export function buildUrl(path: string, query?: RequestOptions['query']): string {
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`
  if (!query) return url
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null || v === '') continue
    params.set(k, String(v))
  }
  const qs = params.toString()
  return qs ? `${url}${url.includes('?') ? '&' : '?'}${qs}` : url
}

async function toProblem(res: Response): Promise<Problem> {
  const ct = res.headers.get('content-type') || ''
  try {
    if (ct.includes('json')) {
      const j = (await res.json()) as Partial<Problem> & { detail?: unknown }
      const detail = typeof j.detail === 'string' ? j.detail : j.detail ? JSON.stringify(j.detail) : undefined
      return { type: j.type || 'about:blank', title: j.title || res.statusText || `HTTP ${res.status}`, status: j.status || res.status, detail, request_id: j.request_id ?? null }
    }
    const text = await res.text()
    return { title: res.statusText || `HTTP ${res.status}`, status: res.status, detail: text.slice(0, 500) || undefined }
  } catch {
    return { title: res.statusText || `HTTP ${res.status}`, status: res.status }
  }
}

/** fetch() wrapper: same-origin cookies, CSRF header on mutations, problem+json errors, 401 broadcast. */
export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const method = (opts.method || 'GET').toUpperCase()
  const headers: Record<string, string> = { Accept: 'application/json, application/problem+json', ...(opts.headers || {}) }
  let body: BodyInit | undefined
  if (opts.form) {
    body = opts.form
  } else if (opts.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(opts.body)
  }
  if (MUTATING.has(method) && csrfToken) headers['X-CSRF-Token'] = csrfToken

  let res: Response
  try {
    res = await fetch(buildUrl(path, opts.query), { method, headers, body, credentials: 'include', signal: opts.signal })
  } catch (e) {
    if ((e as Error).name === 'AbortError') throw e
    throw new ApiError({ title: 'Network error', status: 0, detail: 'Could not reach the server.' })
  }
  if (res.status === 401) {
    const err = new ApiError(await toProblem(res))
    unauthorizedListeners.forEach((fn) => fn(err))
    throw err
  }
  if (!res.ok) throw new ApiError(await toProblem(res))
  if (res.status === 204 || res.headers.get('content-length') === '0') return undefined as T
  const ct = res.headers.get('content-type') || ''
  if (ct.includes('json')) return (await res.json()) as T
  return (await res.text()) as unknown as T
}

export const api = {
  get: <T>(path: string, query?: RequestOptions['query'], signal?: AbortSignal) => request<T>(path, { query, signal }),
  post: <T>(path: string, body?: unknown, query?: RequestOptions['query']) => request<T>(path, { method: 'POST', body, query }),
  put: <T>(path: string, body?: unknown) => request<T>(path, { method: 'PUT', body }),
  patch: <T>(path: string, body?: unknown) => request<T>(path, { method: 'PATCH', body }),
  delete: <T = void>(path: string) => request<T>(path, { method: 'DELETE' }),
  upload: <T>(path: string, form: FormData) => request<T>(path, { method: 'POST', form }),
}

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return e.problem.detail || e.problem.title
  if (e instanceof Error) return e.message
  return String(e)
}
