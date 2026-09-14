// Two things in the answer text need turning into real elements.
//
// The generation LLM sometimes emphasizes a study/paper name with markdown
// bold (**like this**) even though the system prompt never asks for markdown.
// Rendered as plain text, that shows up as literal asterisks.
//
// Citation markers ([1], [2][3]) become buttons that jump to the matching
// entry in the source list. The markers and the list share one numbering by
// construction (see agent/citations.py), so a marker resolves to a source
// without the frontend having to guess.

// One pass over both, so a marker inside a bold span can't be split in half.
const SEGMENT_PATTERN = /(\*\*[^*]+\*\*|\[\d+\])/g
const MARKER_PATTERN = /^\[(\d+)\]$/

export function renderAnswer(text, { citationsByNumber, onCitationClick } = {}) {
  return text.split(SEGMENT_PATTERN).map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return (
        <strong key={index} className="font-semibold text-stone-900">
          {part.slice(2, -2)}
        </strong>
      )
    }

    const marker = MARKER_PATTERN.exec(part)
    const citation = marker && citationsByNumber?.get(Number(marker[1]))

    // A number with no matching source - the model inventing one, or citing
    // a document that was dropped before the answer was assembled - stays
    // plain text. Better a visible [9] than a button that goes nowhere.
    if (!citation) return part

    return (
      <button
        key={index}
        type="button"
        onClick={() => onCitationClick?.(citation.number)}
        title={citation.title}
        aria-label={`Jump to source ${citation.number}: ${citation.title}`}
        className="mx-0.5 inline-flex h-4 min-w-4 translate-y-px items-center justify-center rounded border border-brand-200 bg-brand-50 px-1 align-baseline font-mono text-[10px] font-medium leading-none text-brand-700 transition-colors hover:border-brand-400 hover:bg-brand-100 hover:text-brand-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-300"
      >
        {citation.number}
      </button>
    )
  })
}
