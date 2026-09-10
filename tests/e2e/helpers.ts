import { expect, type APIRequestContext, type Locator, type Page } from '@playwright/test'

export const USER = { email: 'user@example.com', roles: ['user'] }
// dev-login REPLACES the user's roles with the submitted set, so admin logins must always carry both seeded roles.
export const ADMIN = { email: 'admin@example.com', roles: ['org_admin', 'developer'] }

/** Mint a session through POST /v1/auth/dev-login; the cookie lands in the page's browser context. */
export async function loginViaApi(page: Page, who: { email: string; roles: string[] }) {
  const res = await page.request.post('/v1/auth/dev-login', { data: { email: who.email, roles: who.roles } })
  expect(res.ok(), `dev-login failed: ${res.status()} ${await res.text()}`).toBeTruthy()
  return (await res.json()) as { id: string; csrf_token: string; teams: string[] }
}

/** Log in through the real login form (used by login.spec; everything else uses the API for speed). */
export async function loginViaUi(page: Page, who: { email: string; roles: string[] }) {
  await page.goto('/login')
  const form = page.getByRole('form', { name: 'Development login' })
  await form.getByLabel('Email').fill(who.email)
  for (const role of who.roles) {
    if (role === 'user') continue // always on and disabled
    await form.getByLabel(role, { exact: true }).check()
  }
  await form.getByRole('button', { name: 'Sign in' }).click()
  await page.waitForURL(/\/chat/)
}

export interface Api {
  get<T = any>(path: string): Promise<T>
  post<T = any>(path: string, data?: unknown): Promise<T>
  patch<T = any>(path: string, data?: unknown): Promise<T>
  del(path: string): Promise<void>
}

/** JSON API wrapper on a request context that already holds a session cookie; adds the CSRF header. */
export async function apiFor(request: APIRequestContext): Promise<Api> {
  const me = await request.get('/v1/users/me')
  expect(me.ok(), 'GET /v1/users/me should succeed after login').toBeTruthy()
  const csrf = ((await me.json()) as { csrf_token: string }).csrf_token
  const headers = { 'X-CSRF-Token': csrf }
  const check = async (r: Awaited<ReturnType<APIRequestContext['get']>>) => {
    expect(r.ok(), `${r.url()} -> ${r.status()} ${await r.text()}`).toBeTruthy()
    return r.status() === 204 ? undefined : r.json()
  }
  return {
    get: async (path) => check(await request.get(path)),
    post: async (path, data) => check(await request.post(path, { data, headers })),
    patch: async (path, data) => check(await request.patch(path, { data, headers })),
    del: async (path) => {
      await check(await request.delete(path, { headers }))
    },
  }
}

export async function createConversation(api: Api, body: { title?: string; permission_mode?: string; project_id?: string } = {}) {
  return api.post<{ id: string }>('/v1/conversations', {
    title: body.title ?? null,
    permission_mode: body.permission_mode ?? 'default',
    project_id: body.project_id ?? null,
  })
}

/** Poll a run until its status is one of `until`. */
export async function waitForRunStatus(api: Api, runId: string, until: string[], timeoutMs = 30_000) {
  const t0 = Date.now()
  let last = ''
  while (Date.now() - t0 < timeoutMs) {
    const run = await api.get<{ status: string }>(`/v1/runs/${runId}`)
    last = run.status
    if (until.includes(run.status)) return run
    await new Promise((r) => setTimeout(r, 250))
  }
  throw new Error(`run ${runId} did not reach ${until.join('|')} (last: ${last})`)
}

// ---- chat page helpers -----------------------------------------------------------------------------

export function composer(page: Page) {
  return page.getByLabel('Message', { exact: true })
}

export async function sendMessage(page: Page, text: string) {
  await composer(page).fill(text)
  await page.getByRole('button', { name: 'Send message' }).click()
}

/** Persisted assistant messages (rendered by MessageList with aria-label="assistant message"). */
export function assistantMessages(page: Page): Locator {
  return page.getByRole('article', { name: 'assistant message' })
}

/** The in-flight streaming bubble (LiveAssistant renders aria-busy="true" while streaming). */
export function liveBubble(page: Page): Locator {
  return page.locator('article[aria-busy="true"]')
}

export function costChip(page: Page): Locator {
  return page.getByTitle('Total cost of all runs in this conversation')
}

/** Wait until an assistant message containing `text` is part of the persisted history (run finished). */
export async function expectAssistantReply(page: Page, text: string, timeout = 45_000) {
  await expect(assistantMessages(page).filter({ hasText: text }).first()).toBeVisible({ timeout })
}

export function conversationIdFromUrl(page: Page): string {
  const m = page.url().match(/\/chat\/([0-9a-f-]{36})/)
  if (!m) throw new Error(`not on a conversation page: ${page.url()}`)
  return m[1]
}
