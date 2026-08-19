import { ArrowUp, BadgeCheck, ListFilter, Search, Sparkles, Sprout } from 'lucide-react'
import { useState } from 'react'
import { renderInlineMarkdown } from '../lib/formatAnswer'
import CitationList from './CitationList'
import RetryBadge from './RetryBadge'

const EXAMPLE_QUESTIONS = [
  'How effective is mindfulness-based stress reduction for anxiety?',
  'What coping strategies help with depression in chronic illness?',
  'Does cognitive behavioral therapy help caregivers manage stress?',
]

const PIPELINE_STEPS = [
  { label: 'Retrieve', Icon: Search },
  { label: 'Grade', Icon: ListFilter },
  { label: 'Generate', Icon: Sparkles },
  { label: 'Verify', Icon: BadgeCheck },
]

function EmptyState({ onPickExample }) {
  return (
    <div className="mx-auto max-w-lg pt-10 text-center sm:pt-16">
      <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-50">
        <Sprout className="h-7 w-7 text-brand-600" strokeWidth={1.75} />
      </div>
      <p className="font-display text-xl text-stone-800">
        Ask about coping strategies for depression, anxiety, or stress
      </p>
      <p className="mt-2 text-[13px] text-stone-500">
        Answers are grounded in PubMed research and self-checked before you see them.
      </p>

      <div className="mt-9 flex items-center justify-center">
        {PIPELINE_STEPS.map(({ label, Icon }, index) => (
          <div key={label} className="flex items-center">
            {index > 0 && <div className="h-px w-6 bg-stone-200 sm:w-10" />}
            <div className="flex flex-col items-center gap-1.5 px-1">
              <div className="flex h-9 w-9 items-center justify-center rounded-full border border-stone-200 bg-white">
                <Icon className="h-4 w-4 text-brand-600" strokeWidth={2} />
              </div>
              <span className="font-mono text-[9px] uppercase tracking-wide text-stone-400">
                {label}
              </span>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-9 flex flex-wrap justify-center gap-2">
        {EXAMPLE_QUESTIONS.map((question) => (
          <button
            key={question}
            type="button"
            onClick={() => onPickExample(question)}
            className="rounded-full border border-stone-200 bg-white px-3 py-1.5 text-[12.5px] text-stone-600 transition-colors hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700"
          >
            {question}
          </button>
        ))}
      </div>
    </div>
  )
}

export default function ChatPanel({ messages, isStreaming, onSubmit }) {
  const [input, setInput] = useState('')

  const handleSubmit = (event) => {
    event.preventDefault()
    if (!input.trim() || isStreaming) return
    onSubmit(input)
    setInput('')
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto px-4 py-5 sm:px-6">
        <div className="mx-auto max-w-3xl space-y-5">
          {messages.length === 0 && <EmptyState onPickExample={setInput} />}

          {messages.map((message) => (
            <div key={message.id} className="space-y-2">
              <div className="flex justify-end">
                <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-brand-600 px-4 py-2.5 text-[14px] leading-relaxed text-white shadow-sm sm:max-w-xl">
                  {message.question}
                </div>
              </div>

              <div className="flex justify-start">
                <div className="max-w-[85%] rounded-2xl rounded-bl-sm border border-stone-200 bg-white px-4 py-3 shadow-sm sm:max-w-xl">
                  <div className="mb-2 flex items-center gap-2">
                    <RetryBadge retriesUsed={message.retries_used} />
                  </div>
                  <p className="whitespace-pre-wrap text-[14px] leading-relaxed text-stone-800">
                    {renderInlineMarkdown(message.answer)}
                  </p>
                  <CitationList citations={message.citations} />
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <form onSubmit={handleSubmit} className="border-t border-stone-200 bg-white p-3 sm:p-4">
        <div className="mx-auto flex max-w-3xl items-center gap-2 rounded-full border border-stone-300 bg-stone-50 py-1.5 pl-4 pr-1.5 transition-colors focus-within:border-brand-400 focus-within:bg-white focus-within:ring-2 focus-within:ring-brand-100">
          <input
            type="text"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            disabled={isStreaming}
            placeholder="Ask a question..."
            className="flex-1 bg-transparent text-[14px] text-stone-800 placeholder:text-stone-400 focus:outline-none disabled:text-stone-400"
          />
          <button
            type="submit"
            disabled={isStreaming || !input.trim()}
            aria-label="Send"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-600 text-white transition-colors hover:bg-brand-700 disabled:bg-stone-300"
          >
            {isStreaming ? (
              <span className="h-2 w-2 animate-pulse-dot rounded-full bg-white" />
            ) : (
              <ArrowUp className="h-4 w-4" strokeWidth={2.5} />
            )}
          </button>
        </div>
      </form>
    </div>
  )
}
