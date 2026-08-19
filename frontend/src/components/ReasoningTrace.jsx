import {
  AlertTriangle,
  BadgeCheck,
  ChevronDown,
  Circle,
  ListFilter,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
} from 'lucide-react'
import { useMemo } from 'react'

const NODE_META = {
  safety_check: { label: 'Safety check', Icon: ShieldCheck },
  retrieve: { label: 'Retrieve', Icon: Search },
  grade_documents: { label: 'Grade documents', Icon: ListFilter },
  transform_query: { label: 'Rewrite query', Icon: RefreshCw },
  generate: { label: 'Generate answer', Icon: Sparkles },
  check_groundedness: { label: 'Check groundedness', Icon: BadgeCheck },
  flag_ungrounded: { label: 'Flag caveat', Icon: AlertTriangle },
}

const TONE_STYLES = {
  complete: { dot: 'bg-brand-600', ring: 'ring-brand-100' },
  retry: { dot: 'bg-accent-500', ring: 'ring-accent-100' },
  crisis: { dot: 'bg-rose-600', ring: 'ring-rose-100' },
}

function stepTone(event, isRepeatPass) {
  if (event.node === 'safety_check' && event.detail.startsWith('crisis')) return 'crisis'
  if (event.node === 'flag_ungrounded') return 'retry'
  if (isRepeatPass || event.node === 'transform_query') return 'retry'
  return 'complete'
}

// Loop iterations (grade_documents -> transform_query -> retrieve ->
// grade_documents again) show up as repeated node names in the stream - a
// node's second-or-later occurrence is what "retry" tone actually detects.
function useRepeatFlags(events) {
  return useMemo(() => {
    const counts = {}
    return events.map((event) => {
      counts[event.node] = (counts[event.node] || 0) + 1
      return counts[event.node] > 1
    })
  }, [events])
}

export default function ReasoningTrace({ events, isOpen, onToggle, isStreaming }) {
  const repeatFlags = useRepeatFlags(events)

  return (
    <div className="overflow-hidden rounded-xl border border-stone-200">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between bg-stone-50 px-3 py-2.5 text-left"
      >
        <span className="flex items-center gap-2">
          <span className="font-mono text-[11px] font-medium uppercase tracking-wide text-stone-500">
            Reasoning trace
          </span>
          {isStreaming && (
            <span className="flex items-center gap-1 font-mono text-[10px] uppercase tracking-wide text-brand-600">
              <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-brand-500" />
              Live
            </span>
          )}
        </span>
        <ChevronDown
          className={`h-4 w-4 text-stone-400 transition-transform duration-200 ${
            isOpen ? 'rotate-180' : ''
          }`}
        />
      </button>

      {isOpen && (
        <div className="max-h-80 overflow-y-auto px-3 py-3 md:max-h-[28rem]">
          {events.length === 0 && (
            <p className="py-2 text-[13px] text-stone-400">Waiting for the first step...</p>
          )}

          <ol className="relative space-y-4">
            {events.map((event, index) => {
              const tone = stepTone(event, repeatFlags[index])
              const styles = TONE_STYLES[tone]
              const meta = NODE_META[event.node] ?? { label: event.node, Icon: Circle }
              const Icon = meta.Icon
              const isLast = index === events.length - 1

              return (
                <li key={index} className="relative flex animate-fade-slide-in gap-3">
                  {!isLast && (
                    <span className="absolute left-[13px] top-7 h-[calc(100%+4px)] w-px bg-stone-200" />
                  )}
                  <span
                    className={`relative z-10 flex h-7 w-7 shrink-0 items-center justify-center rounded-full ring-4 ${styles.dot} ${styles.ring}`}
                  >
                    <Icon className="h-3.5 w-3.5 text-white" strokeWidth={2.25} />
                  </span>
                  <div className="min-w-0 pt-0.5">
                    <div className="flex items-center gap-1.5">
                      <p className="text-[13px] font-medium text-stone-800">{meta.label}</p>
                      {tone === 'retry' && (
                        <span className="rounded-full bg-accent-50 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wide text-accent-700">
                          Retry
                        </span>
                      )}
                    </div>
                    <p className="text-[12px] leading-snug text-stone-500">{event.detail}</p>
                  </div>
                </li>
              )
            })}

            {isStreaming && (
              <li className="flex animate-fade-slide-in items-center gap-3">
                <span className="relative z-10 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-stone-100 ring-4 ring-stone-50">
                  <span className="h-2 w-2 animate-pulse-dot rounded-full bg-stone-400" />
                </span>
                <p className="text-[12px] italic text-stone-400">Working...</p>
              </li>
            )}
          </ol>
        </div>
      )}
    </div>
  )
}
