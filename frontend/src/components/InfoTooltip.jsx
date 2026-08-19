import { Info, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

const ABOUT_TEXT =
  'This assistant answers questions about coping strategies for depression, anxiety, and stress by retrieving and reasoning over PubMed research abstracts. It grades its own retrieval for relevance, checks generated answers for groundedness, and automatically retries when either check fails - a "corrective RAG" pattern. Not a clinical tool.'

export default function InfoTooltip() {
  const [isOpen, setIsOpen] = useState(false)
  const containerRef = useRef(null)

  useEffect(() => {
    if (!isOpen) return undefined

    const handleClickOutside = (event) => {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [isOpen])

  return (
    <div ref={containerRef} className="relative shrink-0">
      <button
        type="button"
        aria-label="About this app"
        onClick={() => setIsOpen((open) => !open)}
        className="flex h-8 w-8 items-center justify-center rounded-full text-stone-400 transition-colors hover:bg-stone-100 hover:text-brand-600"
      >
        {isOpen ? (
          <X className="h-4 w-4" strokeWidth={2} />
        ) : (
          <Info className="h-4 w-4" strokeWidth={2} />
        )}
      </button>

      {isOpen && (
        <div className="animate-fade-slide-in absolute right-0 top-10 z-30 w-72 rounded-xl border border-stone-200 bg-white p-3.5 shadow-lg">
          <p className="font-display text-[13px] font-semibold text-stone-800">
            About this assistant
          </p>
          <p className="mt-1.5 text-[13px] leading-relaxed text-stone-600">{ABOUT_TEXT}</p>
        </div>
      )}
    </div>
  )
}
