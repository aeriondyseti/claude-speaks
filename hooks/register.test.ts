import { describe, expect, test } from 'claude-code/testing'

const ran = () => ({ value: { exitCode: 0, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } })
const turn = { answer: 'Edit `~/.config/x.json`.', durationMs: 5, isAborted: false, turnId: 't1' }

describe('turn.complete', () => {
  test('speaks the main loop answer', async ($, on) => {
    const calls: { argv: readonly string[]; stdin?: string; env?: Record<string, string> }[] = []
    on('process.run', ($, e) => (calls.push({ argv: e.argv, stdin: e.init?.stdin, env: e.init?.env }), ran()))
    on('turn.complete', () => ({ text: '' }))
    await $.turn.complete({ ...turn, reason: 'answer' })
    expect(calls.length).toBe(1)
    expect(calls[0].argv.slice(-2)).toEqual([expect.stringContaining('speak.py'), '--stdin-text'])
    expect(calls[0].stdin).toBe(turn.answer)
    const options = JSON.parse(calls[0].env?.CLAUDE_SPEAKS_OPTIONS ?? '{}')
    expect(options.http_text_profile).toBe('kokoro')
    expect(options.replacements).toContain('Ti => tee eye')
  })

  test('hands the configured server and key to speak.py', { options: { http_url: 'http://127.0.0.1:8880/v1/audio/speech', http_api_key: 'sk-test' } }, async ($, on) => {
    let env: Record<string, string> | undefined
    on('process.run', ($, e) => ((env = e.init?.env), ran()))
    on('turn.complete', () => ({ text: '' }))
    await $.turn.complete({ ...turn, reason: 'answer' })
    const options = JSON.parse(env?.CLAUDE_SPEAKS_OPTIONS ?? '{}')
    expect(options.http_url).toBe('http://127.0.0.1:8880/v1/audio/speech')
    expect(options.http_api_key).toBe('sk-test')
  })

  test('stays quiet for subagents and interrupted turns', async ($, on) => {
    let count = 0
    on('process.run', () => (count++, ran()))
    on('turn.complete', () => ({ text: '' }))
    await $.turn.complete({ ...turn, reason: 'answer', loop: 'agent-1' })
    await $.turn.complete({ ...turn, reason: 'aborted', isAborted: true })
    expect(count).toBe(0)
  })
})

test('/speaks rejects unknown actions', async ($, on) => {
  on('process.run', () => ran())
  const out = await $.command.run({ command: 'speaks', args: 'louder', origin: 'user' })
  expect(out.text).toContain('usage')
})
