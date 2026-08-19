import { ExternalLink } from 'lucide-react'

export default function CitationList({ citations }) {
  if (!citations || citations.length === 0) return null

  // Retrieval can surface more than one chunk from the same abstract, which
  // would otherwise list the same paper twice - collapse to one link per PMID.
  const seen = new Set()
  const uniqueCitations = citations.filter((citation) => {
    if (seen.has(citation.pmid)) return false
    seen.add(citation.pmid)
    return true
  })

  return (
    <div className="mt-3 border-t border-stone-100 pt-3">
      <p className="mb-1.5 font-mono text-[10px] uppercase tracking-wide text-stone-400">
        Sources
      </p>
      <ul className="space-y-1.5">
        {uniqueCitations.map((citation) => (
          <li key={citation.pmid}>
            <a
              href={`https://pubmed.ncbi.nlm.nih.gov/${citation.pmid}/`}
              target="_blank"
              rel="noreferrer"
              className="group flex items-start gap-2 rounded-lg border border-stone-200 bg-stone-50/60 px-3 py-2 transition-colors hover:border-brand-300 hover:bg-brand-50"
            >
              <ExternalLink
                className="mt-0.5 h-3.5 w-3.5 shrink-0 text-stone-400 group-hover:text-brand-600"
                strokeWidth={2}
              />
              <span className="min-w-0">
                <span className="block text-[13px] leading-snug text-stone-700 group-hover:text-brand-800">
                  {citation.title}
                </span>
                <span className="mt-0.5 block font-mono text-[10px] text-stone-400">
                  {citation.journal} · {citation.year} · PMID {citation.pmid}
                </span>
              </span>
            </a>
          </li>
        ))}
      </ul>
    </div>
  )
}
