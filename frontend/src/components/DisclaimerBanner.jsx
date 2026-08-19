import { ShieldCheck } from 'lucide-react'

const DEFAULT_TEXT =
  'This tool summarizes published research literature for informational purposes only and is not a substitute for care from a qualified healthcare provider.'

// Shown once, always visible above the conversation - not attached to any
// single message - per the "persistent, not per-message" requirement.
// Deliberately quiet: a thin neutral strip with an icon, not a saturated
// full-width alert bar competing with the header above it.
export default function DisclaimerBanner({ text }) {
  return (
    <div className="flex items-center gap-1.5 border-b border-stone-200 bg-stone-50 px-4 py-1.5 sm:px-6">
      <ShieldCheck className="h-3.5 w-3.5 shrink-0 text-stone-400" strokeWidth={2} />
      <p className="text-[12px] leading-snug text-stone-500">
        <span className="font-medium text-stone-600">Not medical advice</span> —{' '}
        {text || DEFAULT_TEXT}
      </p>
    </div>
  )
}
