import {defineConfig} from '@playwright/test';
import {mkdirSync} from 'node:fs';
import {resolve} from 'node:path';

mkdirSync('tmp', {recursive: true});
const run = process.env.DM_BROWSER_TEST_RUN || `browser-${process.pid}-${Date.now()}`;
process.env.DM_BROWSER_TEST_RUN = run;
Object.assign(process.env, {
  DATABASE_URL: process.env.BROWSER_DATABASE_URL || `sqlite:///${resolve('tmp', run + '.db').replaceAll('\\', '/')}`,
  JWT_SECRET: 'browser-test-only-jwt-key-at-least-32-characters',
  GATEWAY_API_KEY: 'browser-test-only-gateway-key-at-least-32-characters',
  GATEWAY_API_URL: 'http://127.0.0.1:8001',
  GATEWAY_OUTBOX: resolve('tmp', run + '-outbox.db'),
  MESHTASTIC_ALLOWED_NODES: '!0436bda8', GPS_MAX_AGE_SECONDS: '300', AI_MODE: 'rules',
  API_PROXY_TARGET: 'http://127.0.0.1:8001',
});
const python = process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python';
export default defineConfig({
  testDir: './tests/browser', workers: 1,
  use: {baseURL: 'http://127.0.0.1:5174', channel: 'chrome', headless: true},
  webServer: [
    {command: `"${resolve(python)}" -m uvicorn main:app --host 127.0.0.1 --port 8001`, url: 'http://127.0.0.1:8001/health', timeout: 30000},
    {command: 'npm run dev -- --port 5174', url: 'http://127.0.0.1:5174', timeout: 30000},
  ],
});
