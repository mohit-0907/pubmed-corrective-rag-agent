import { CheckCircle2, RotateCw } from 'lucide-react'

export default function RetryBadge({ retriesUsed }) {
  const hasRetries = retriesUsed > 0
  const label = hasRetries
    ? `${retriesUsed} ${retriesUsed === 1 ? 'retry' : 'retries'}`
    : 'Direct answer'
  const Icon = hasRetries ? RotateCw : CheckCircle2

  return (
    <span
      className={
        'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-mono text-[10px] font-medium uppercase tracking-wide ' +
        (hasRetries
          ? 'border-accent-200 bg-accent-50 text-accent-700'
          : 'border-brand-200 bg-brand-50 text-brand-700')
      }
    >
      <Icon className="h-3 w-3" strokeWidth={2.5} />
      {label}
    </span>
  )
}
