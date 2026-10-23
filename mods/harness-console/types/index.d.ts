export type AshRun = {
  task: string
  title: string
  outcome: string
  cost_usd: number
  turns: number
}

export type AshImprovement = {
  ts: number
  accepted: boolean
  hypothesis: string | null
  reason: string | null
}

export type AshStatus = {
  updated: number
  state: string
  note: string
  current: { id: string; title: string; kind: string } | null
  counts: Record<string, number>
  harness: { commit: string; lessons: number; improvements: AshImprovement[] }
  recent: AshRun[]
}

declare module 'claude-code' {
  interface PluginState {
    'ash-console': { status: AshStatus | null }
  }
}
