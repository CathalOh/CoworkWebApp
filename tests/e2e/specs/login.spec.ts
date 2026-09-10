import { expect, test } from '@playwright/test'
import { USER, loginViaUi } from '../helpers'

test.describe('login', () => {
  test('dev login lands in the app, sign out returns to /login', async ({ page }) => {
    await loginViaUi(page, USER)
    await expect(page.getByRole('navigation', { name: 'Primary' })).toBeVisible()
    await expect(page.getByText(USER.email).or(page.getByText('user', { exact: true }))).toBeVisible()
    await page.getByRole('button', { name: 'Sign out' }).click()
    await page.waitForURL(/\/login/)
    await expect(page.getByRole('form', { name: 'Development login' })).toBeVisible()
  })

  test('protected route redirects to /login when logged out', async ({ page }) => {
    await page.goto('/projects')
    await page.waitForURL(/\/login/)
    await expect(page.getByRole('form', { name: 'Development login' })).toBeVisible()
  })
})
