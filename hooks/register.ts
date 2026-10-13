import type { EngineInterface, ProcessSpawnChunk, Register } from 'claude-code'

const ACTIONS = ['on', 'off', 'stop', 'status'] as const

// speak.py runs under uv (the one requirement); it needs nothing beyond the standard library.
const speakPy = (root: string, ...args: string[]) => ['uv', 'run', '--no-project', '--quiet', `${root}/speak.py`, ...args]

const STATUS: Record<string, { text: string; timeoutMs: number }> = {
  'installing-pocket': { text: 'Installing Pocket TTS (first run, ~1 GB). Please wait…', timeoutMs: 60_000 },
  'loading-pocket': { text: 'Loading Pocket TTS. Please wait…', timeoutMs: 20_000 },
  'pocket-ready': { text: 'Pocket TTS ready', timeoutMs: 2_000 },
}

async function relay($: EngineInterface, stream: AsyncIterable<ProcessSpawnChunk>) {
  for await (const chunk of stream) {
    if (chunk.stream !== 'stdout') continue
    for (const line of chunk.text.split('\n')) {
      const status = STATUS[line.trim()]
      if (status) $.ui.toast(status.text, { timeoutMs: status.timeoutMs })
    }
  }
}

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
    // Start the daemon now (uv installs its dependencies on first use), not while a reply waits.
    $.process
      .run(speakPy($.plugin.root, '--warm'), { timeoutMs: 30_000 })
      .catch(() => {})
    return next(e)
  })

  // Speak the main loop's final answer. speak.py hands it to the background daemon and relays
  // its status lines; this reads them in the background, so the turn never waits on speech.
  on('turn.complete', async ($, e, next) => {
    const result = await next(e)
    if (e.loop === undefined && e.reason === 'answer' && e.answer.trim()) {
      relay($, $.process.spawn({ argv: speakPy($.plugin.root, '--stdin-text'), input: e.answer, env })).catch(() => {})
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
