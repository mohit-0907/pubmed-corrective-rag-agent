import { ExternalLink } from 'lucide-react'
import { sourceAnchorId } from '../lib/sourceAnchor'

// Sources arrive already numbered and de-duplicated by the backend (see
// agent/citations.py), so the [1]-style markers in the answer text line up
// with this list by construction rather than by the frontend guessing.
export default function CitationList({ citations, messageId, highlightedNumber }) {
  if (!citations || citations.length === 0) return null

  return (
    <div className="mt-3 border-t border-stone-100 pt-3">
      <p className="mb-1.5 font-mono text-[10px] uppercase tracking-wide text-stone-400">
        Sources
      </p>
      <ul className="space-y-1.5">
        {citations.map((citation) => {
          const isHighlighted = citation.number === highlightedNumber

          return (
            <li key={citation.pmid} id={sourceAnchorId(messageId, citation.number)}>
              <a
                href={citation.url}
                target="_blank"
                rel="noreferrer"
                className={`group flex items-start gap-2 rounded-lg border px-3 py-2 transition-colors ${
                  isHighlighted
                    ? 'border-brand-400 bg-brand-50 ring-2 ring-brand-200'
                    : 'border-stone-200 bg-stone-50/60 hover:border-brand-300 hover:bg-brand-50'
                }`}
              >
                <span
                  className={`mt-px flex h-4 w-4 shrink-0 items-center justify-center rounded font-mono text-[10px] font-medium ${
                    isHighlighted
                      ? 'bg-brand-200 text-brand-800'
                      : 'bg-stone-200 text-stone-600 group-hover:bg-brand-200 group-hover:text-brand-800'
                  }`}
                >
                  {citation.number}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[13px] leading-snug text-stone-700 group-hover:text-brand-800">
                    {citation.title}
                  </span>
                  <span className="mt-0.5 block font-mono text-[10px] text-stone-400">
                    {citation.journal} · {citation.year} · PMID {citation.pmid}
                  </span>
                </span>
                <ExternalLink
                  className="mt-0.5 h-3.5 w-3.5 shrink-0 text-stone-400 group-hover:text-brand-600"
                  strokeWidth={2}
                />
              </a>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
