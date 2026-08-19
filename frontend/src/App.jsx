import { GripVertical, Sprout } from 'lucide-react'
import { useMemo } from 'react'
import { Group, Panel, Separator } from 'react-resizable-panels'
import ChatPanel from './components/ChatPanel'
import DisclaimerBanner from './components/DisclaimerBanner'
import InfoTooltip from './components/InfoTooltip'
import ReasoningTrace from './components/ReasoningTrace'
import { useChat } from './hooks/useChat'
import { useMediaQuery } from './hooks/useMediaQuery'

function TracePanel({ activeTrace, isTraceOpen, setIsTraceOpen, isStreaming, error }) {
  return (
    <div className="h-full overflow-y-auto p-3 md:p-4">
      <ReasoningTrace
        events={activeTrace}
        isOpen={isTraceOpen}
        onToggle={() => setIsTraceOpen((open) => !open)}
        isStreaming={isStreaming}
      />
      {error && (
        <p className="mt-3 rounded-lg bg-rose-50 px-3 py-2 text-[13px] text-rose-700">{error}</p>
      )}
    </div>
  )
}

function App() {
  const {
    messages,
    activeTrace,
    isTraceOpen,
    setIsTraceOpen,
    isStreaming,
    error,
    submitQuestion,
  } = useChat()
  const isDesktop = useMediaQuery('(min-width: 768px)')

  const latestDisclaimer = useMemo(
    () => messages[messages.length - 1]?.disclaimer,
    [messages],
  )

  const tracePanelProps = { activeTrace, isTraceOpen, setIsTraceOpen, isStreaming, error }

  return (
    <div className="flex h-screen flex-col bg-stone-50 font-sans text-stone-800">
      <header className="flex items-center justify-between gap-2.5 border-b border-stone-200 bg-white px-4 py-3 sm:px-6">
        <div className="flex min-w-0 items-center gap-2.5">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-600">
            <Sprout className="h-4 w-4 text-white" strokeWidth={2.25} />
          </div>
          <div className="min-w-0 leading-tight">
            <h1 className="truncate font-display text-lg font-semibold text-stone-900">
              Coping Research Assistant
            </h1>
            <p className="font-mono text-[10px] uppercase tracking-wide text-stone-400">
              Evidence from PubMed · Corrective RAG
            </p>
          </div>
        </div>
        <InfoTooltip />
      </header>

      <DisclaimerBanner text={latestDisclaimer} />

      {isDesktop ? (
        <Group orientation="horizontal" className="flex-1 overflow-hidden">
          <Panel defaultSize="72" minSize="45">
            <ChatPanel messages={messages} isStreaming={isStreaming} onSubmit={submitQuestion} />
          </Panel>
          <Separator className="group relative w-1.5 cursor-col-resize bg-stone-200 transition-colors hover:bg-brand-300 active:bg-brand-400">
            <span className="absolute left-1/2 top-1/2 flex h-9 w-4 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-stone-400 opacity-0 transition-opacity group-hover:opacity-100">
              <GripVertical className="h-3 w-3 text-white" strokeWidth={2.5} />
            </span>
          </Separator>
          <Panel defaultSize="28" minSize="20" maxSize="45">
            <div className="h-full border-l border-stone-200 bg-white">
              <TracePanel {...tracePanelProps} />
            </div>
          </Panel>
        </Group>
      ) : (
        <div className="flex flex-1 flex-col overflow-hidden">
          <div className="max-h-72 shrink-0 overflow-y-auto border-b border-stone-200 bg-white">
            <TracePanel {...tracePanelProps} />
          </div>
          <div className="min-w-0 flex-1">
            <ChatPanel messages={messages} isStreaming={isStreaming} onSubmit={submitQuestion} />
          </div>
        </div>
      )}
    </div>
  )
}

export default App
