import { describe, expect, test } from 'claude-code/testing'

const ran = () => ({ value: { exitCode: 0, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } })
const turn = { answer: 'Edit `~/.config/x.json`.', durationMs: 5, isAborted: false, turnId: 't1' }

describe('turn.complete', () => {
  test('speaks the main loop answer', async ($, on) => {
    const calls: { argv: readonly string[]; stdin?: string }[] = []
    on('process.run', ($, e) => (calls.push({ argv: e.argv, stdin: e.init?.stdin }), ran()))
    on('turn.complete', () => ({ text: '' }))
    await $.turn.complete({ ...turn, reason: 'answer' })
    expect(calls.length).toBe(1)
    expect(calls[0].argv.slice(-2)).toEqual([expect.stringContaining('speak.py'), '--stdin-text'])
    expect(calls[0].stdin).toBe(turn.answer)
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
