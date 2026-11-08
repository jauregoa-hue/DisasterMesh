import {test, expect} from '@playwright/test';
import {execFileSync} from 'node:child_process';

const python = process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python';
const api = 'http://127.0.0.1:8001';

test('live receiver event, duplicate, map tile fallback and responder workflow', async ({page, request}) => {
  const username = `browser_${Date.now()}`, password = 'BrowserTestPassword123!';
  expect((await request.post(api + '/auth/register', {data: {username, password}})).status()).toBe(201);
  execFileSync(python, ['scripts/set_role.py', username, 'responder']);
  await page.route('https://tile.openstreetmap.org/**', route => route.abort());
  await page.goto('/');
  await page.getByLabel('Username', {exact: true}).fill(username);
  await page.getByLabel('Password', {exact: true}).fill(password);
  await page.getByRole('button', {name: 'Log in', exact: true}).click();
  await expect(page.getByText('Live — checks every 2 seconds')).toBeVisible();
  await expect(page.getByText('No reports yet.')).toBeVisible();
  // Runs the actual Python position/text callbacks and durable HTTP sender, no COM port.
  execFileSync(python, ['scripts/simulate_gateway.py', '--packet-id', '4000000001']);
  const incident = page.getByTestId('incident').filter({hasText: 'Packet 4000000001'});
  await expect(incident).toBeVisible({timeout: 10000});
  await expect(incident).toContainText('39.138099, -84.489011');
  await expect(page.getByText(/Map tiles unavailable or offline/)).toBeVisible();
  await expect(page.locator('.leaflet-interactive')).toHaveCount(1);
  execFileSync(python, ['scripts/simulate_gateway.py', '--packet-id', '4000000001']);
  await expect(page.getByTestId('incident')).toHaveCount(1);
  const status = incident.getByRole('combobox');
  await status.selectOption('in_progress');
  await expect(status).toHaveValue('in_progress');
  await status.selectOption('resolved');
  await expect(status).toHaveValue('resolved');
  await incident.getByRole('button', {name: 'Summarize'}).click();
  await expect(incident.locator('.summary')).toContainText('(rules)');
  execFileSync(python, ['scripts/simulate_gateway.py', '--gps', 'stale', '--packet-id', '4000000002']);
  const stale = page.getByTestId('incident').filter({hasText: 'Packet 4000000002'});
  await expect(stale).toContainText('GPS fix is stale', {timeout: 10000});
  await expect(page.locator('.leaflet-interactive')).toHaveCount(1);
  await page.getByRole('button', {name: 'Log out'}).click();
  await expect(page.getByRole('heading', {name: 'Log in or register'})).toBeVisible();
  await expect(page.getByTestId('incident')).toHaveCount(0);
});

test('citizen report form and access to own reports only', async ({page, request}) => {
  const username = `citizen_${Date.now()}`, password = 'BrowserTestPassword123!';
  await request.post(api + '/auth/register', {data: {username, password}});
  await page.goto('/');
  await page.getByLabel('Username', {exact: true}).fill(username);
  await page.getByLabel('Password', {exact: true}).fill(password);
  await page.getByRole('button', {name: 'Log in', exact: true}).click();
  await expect(page.getByText('No reports yet.')).toBeVisible();
  await page.getByLabel('Incident title', {exact: true}).fill('Synthetic citizen report');
  await page.getByLabel('Description', {exact: true}).fill('Road blocked by debris (synthetic)');
  await page.getByRole('button', {name: 'Submit report'}).click();
  await expect(page.getByTestId('incident')).toHaveCount(1);
  await expect(page.getByTestId('incident')).toContainText('Synthetic citizen report');
  await expect(page.getByRole('combobox')).toHaveCount(0);
  await expect(page.getByText('No valid GPS locations to map. Reports remain available below.')).toBeVisible();
});
