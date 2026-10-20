import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { AshStatus } from '../types'

// The orchestrator writes .ash/status.json in the project after every step;
// this mod only reads it, so it works for any session opened in that project.
const PANE = 'ash-console'
const STATUS_FILE = '.ash/status.json'
const status = atom({ plugin: 'ash-console', key: 'status' } as const, null)

function line(s: AshStatus): string {
  const c = s.counts
  const now = s.current ? ` ${s.current.id}` : ''
  return `ASH ${s.state}${now} · ${c.done ?? 0} done · ${c.pending ?? 0} queued · ${c.failed ?? 0} failed · harness ${s.harness.commit || '-'}`
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({ name: 'ash', description: 'Open the ASH console pane' })

    const refresh = async () => {
      let parsed: AshStatus | null = null
      try {
        parsed = JSON.parse(await $.fs.read(STATUS_FILE)) as AshStatus
      } catch {
        parsed = null
      }
      await update($, status, () => parsed)
      $.ui.status(parsed ? line(parsed) : undefined)
    }
    await refresh()
    $.clock.every(5000, refresh)

    return next(e)
  })

  on('command.run', { command: 'ash' }, async $ => {
    await $.ui.open({ id: PANE, title: 'ASH console' })

    return { text: 'ASH console opened.' }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    const s = await read($, status)
    if (!s) {
      return (
        <Box flexDirection="column">
          <Text dimColor>No .ash/status.json here. Run `ash run` in this project.</Text>
        </Box>
      )
    }

    return (
      <Box flexDirection="column">
        <Text bold>{line(s)}</Text>
        {s.current && <Text>Working: {s.current.kind} {s.current.id} {s.current.title}</Text>}
        {s.note !== '' && <Text color="yellow">{s.note}</Text>}
        <Text bold>Recent runs</Text>
        {s.recent.length === 0 && <Text dimColor>none yet</Text>}
        {s.recent.map(r => (
          <Text dimColor={r.outcome === 'done'}>
            {r.outcome.padEnd(7)} {r.task} ${r.cost_usd.toFixed(2)} {r.turns}t {r.title}
          </Text>
        ))}
        <Text bold>Self-improvement ({s.harness.lessons} lessons in memory)</Text>
        {s.harness.improvements.length === 0 && <Text dimColor>no cycles yet</Text>}
        {s.harness.improvements.map(i => (
          <Text color={i.accepted ? 'green' : undefined} dimColor={!i.accepted}>
            {i.accepted ? 'kept    ' : 'rejected'} {i.hypothesis ?? ''} ({i.reason ?? ''})
          </Text>
        ))}
      </Box>
    )
  })
}
