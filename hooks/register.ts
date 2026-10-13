import type { Register } from 'claude-code'

const ACTIONS = ['on', 'off', 'stop', 'status'] as const

export const register: Register = (on, options) => {
  // speak.py hands these to the daemon, where they override ~/.config/claude-speaks/config.json.
  const env = { CLAUDE_SPEAKS_OPTIONS: JSON.stringify(options) }

  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'speaks',
      description: 'Spoken replies: on, off, stop (cut off current speech) or status',
      argumentHint: ACTIONS.join('|'),
      immediate: true,
    })
    // Install pocket-tts on first use and preload the model now, not while a reply waits.
    $.process
      .run(['python3', `${$.plugin.root}/speak.py`, '--warm'], { timeoutMs: 600_000 })
      .catch(() => {})
    return next(e)
  })

  // Speak the main loop's final answer. speak.py hands it to the background daemon (waiting for it
  // to start if needed); nothing here waits on it.
  on('turn.complete', async ($, e, next) => {
    const result = await next(e)
    if (e.loop === undefined && e.reason === 'answer' && e.answer.trim()) {
      $.process
        .run(['python3', `${$.plugin.root}/speak.py`, '--stdin-text'], { stdin: e.answer, env, timeoutMs: 60_000 })
        .catch(() => {})
    }
    return result
  })

  on('command.run', { command: 'speaks' }, async ($, e) => {
    const action = e.args.trim() || 'status'
    if (!(ACTIONS as readonly string[]).includes(action)) {
      return { text: `usage: /speaks ${ACTIONS.join('|')}` }
    }
    const ran = await $.process.run([`${$.plugin.root}/bin/claude-speaks`, action])
    return { text: (ran.stdout || ran.stderr).trim() || `claude-speaks: ${action}` }
  })
}
