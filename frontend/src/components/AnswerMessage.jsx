import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { renderAnswer } from '../lib/formatAnswer'
import { sourceAnchorId } from '../lib/sourceAnchor'
import CitationList from './CitationList'
import RetryBadge from './RetryBadge'

// How long a jumped-to source stays highlighted: long enough to catch the eye
// once the scroll settles, short enough that it doesn't read as a persistent
// selection the reader has to dismiss.
const HIGHLIGHT_MS = 1600

// Its own component rather than inline in ChatPanel because each answer needs
// its own highlight state, and hooks can't be called inside the messages map.
export default function AnswerMessage({ message }) {
  const [highlightedNumber, setHighlightedNumber] = useState(null)
  const timerRef = useRef(null)

  const citationsByNumber = useMemo(
    () => new Map((message.citations ?? []).map((citation) => [citation.number, citation])),
    [message.citations],
  )

  const handleCitationClick = useCallback(
    (number) => {
      document
        .getElementById(sourceAnchorId(message.id, number))
        ?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })

      // Cleared and restarted rather than stacked, so clicking a second
      // marker mid-highlight doesn't cut the new highlight short.
      setHighlightedNumber(number)
      clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => setHighlightedNumber(null), HIGHLIGHT_MS)
    },
    [message.id],
  )

  useEffect(() => () => clearTimeout(timerRef.current), [])

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] rounded-2xl rounded-bl-sm border border-stone-200 bg-white px-4 py-3 shadow-sm sm:max-w-xl">
        <div className="mb-2 flex items-center gap-2">
          <RetryBadge retriesUsed={message.retries_used} />
        </div>
        <p className="whitespace-pre-wrap text-[14px] leading-relaxed text-stone-800">
          {renderAnswer(message.answer, {
            citationsByNumber,
            onCitationClick: handleCitationClick,
          })}
        </p>
        <CitationList
          citations={message.citations}
          messageId={message.id}
          highlightedNumber={highlightedNumber}
        />
      </div>
    </div>
  )
}
