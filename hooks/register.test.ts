import { describe, expect, test } from 'claude-code/testing'

const ran = () => ({ value: { exitCode: 0, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } })
const turn = { answer: 'Edit `~/.config/x.json`.', durationMs: 5, isAborted: false, turnId: 't1' }

type Spawned = { argv: readonly string[]; input?: string; env?: Record<string, string> }
// A stand-in for speak.py: records the call and writes `lines` to stdout.
const fakeSpeak = (calls: Spawned[], lines = '') =>
  async function* (_$: unknown, e: Spawned) {
    calls.push({ argv: e.argv, input: e.input, env: e.env })
    if (lines) yield { stream: 'stdout' as const, text: lines }
    return { value: { code: 0, signal: null } }
  }

describe('turn.complete', () => {
  test('speaks the main loop answer', async ($, on) => {
    const calls: Spawned[] = []
    on('process.spawn', fakeSpeak(calls))
    on('turn.complete', () => ({ text: '' }))
    await $.turn.complete({ ...turn, reason: 'answer' })
    expect(calls.length).toBe(1)
    expect(calls[0].argv.slice(0, 2)).toEqual(['uv', 'run'])
    expect(calls[0].argv.slice(-2)).toEqual([expect.stringContaining('speak.py'), '--stdin-text'])
    expect(calls[0].input).toBe(turn.answer)
    const options = JSON.parse(calls[0].env?.CLAUDE_SPEAKS_OPTIONS ?? '{}')
    expect(options.spell_abbreviations).toBe(false)
    expect(options.replacements).toContain('Ti => tee eye')
  })

  test('hands the configured server and key to speak.py', { options: { http_url: 'http://127.0.0.1:8880/v1/audio/speech', http_api_key: '${TTS_KEY}' } }, async ($, on) => {
    const calls: Spawned[] = []
    on('process.spawn', fakeSpeak(calls))
    on('turn.complete', () => ({ text: '' }))
    await $.turn.complete({ ...turn, reason: 'answer' })
    const options = JSON.parse(calls[0].env?.CLAUDE_SPEAKS_OPTIONS ?? '{}')
    expect(options.http_url).toBe('http://127.0.0.1:8880/v1/audio/speech')
    expect(options.http_api_key).toBe('${TTS_KEY}')
  })

  test('toasts while Pocket TTS loads', async ($, on) => {
    const toasts: string[] = []
    on('ui.toast', ($, e) => (toasts.push(e.text), { value: undefined }))
    on('process.spawn', fakeSpeak([], 'loading-pocket\npocket-ready\n'))
    on('turn.complete', () => ({ text: '' }))
    await $.turn.complete({ ...turn, reason: 'answer' })
    await new Promise(r => setTimeout(r, 50))
    expect(toasts).toEqual(['Loading Pocket TTS. Please wait…', 'Pocket TTS ready'])
  })

  test('stays quiet for subagents and interrupted turns', async ($, on) => {
    const calls: Spawned[] = []
    on('process.spawn', fakeSpeak(calls))
    on('turn.complete', () => ({ text: '' }))
    await $.turn.complete({ ...turn, reason: 'answer', loop: 'agent-1' })
    await $.turn.complete({ ...turn, reason: 'aborted', isAborted: true })
    expect(calls.length).toBe(0)
  })
})

test('/speaks rejects unknown actions', async ($, on) => {
  on('process.run', () => ran())
  const out = await $.command.run({ command: 'speaks', args: 'louder', origin: 'user' })
  expect(out.text).toContain('usage')
})
