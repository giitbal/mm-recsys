import test from 'node:test'
import assert from 'node:assert/strict'
import {recordEvent} from '../src/lib/live.ts'

test('an ambiguous network failure retries the same event ID, payload and attribution', async () => {
  const memory = new Map([['mm-user', 'u1'], ['mm-session', 's1']])
  globalThis.sessionStorage = {getItem: key => memory.get(key) ?? null, setItem: (key, value) => memory.set(key, value), removeItem: key => memory.delete(key)}
  const calls = []
  const previous = globalThis.fetch
  globalThis.fetch = async (url, options) => {
    calls.push({url, ...options})
    if (calls.length === 1) throw new Error('response lost after server commit')
    return Response.json({applied: false})
  }
  try {
    await assert.rejects(recordEvent('P1', 'purchase', {requestId: 'r1', userId: 'u1'}))
    await recordEvent('P1', 'purchase', {requestId: 'r2', userId: 'u1'})
    assert.equal(calls[0].body, calls[1].body)
    assert.equal(calls[1].headers['X-Recommendation-Request-ID'], 'r1')
    assert.equal([...memory.keys()].filter(key => key.startsWith('mm-pending:')).length, 0)
  } finally {globalThis.fetch = previous}
})

test('an exposure belonging to another shopper is not attached to their purchase', async () => {
  const memory = new Map([['mm-user', 'u2'], ['mm-session', 's2']])
  globalThis.sessionStorage = {getItem: key => memory.get(key) ?? null, setItem: (key, value) => memory.set(key, value), removeItem: key => memory.delete(key)}
  const previous = globalThis.fetch
  globalThis.fetch = async (url, options) => {
    assert.equal(options.headers['X-Recommendation-Request-ID'], undefined)
    assert.equal(JSON.parse(options.body).user_id, 'u2')
    return Response.json({applied: true})
  }
  try {await recordEvent('P1', 'purchase', {requestId: 'r1', userId: 'u1'})}
  finally {globalThis.fetch = previous}
})
