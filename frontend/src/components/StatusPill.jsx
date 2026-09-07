export default function StatusPill({ jobStatus, needsReview, approved }) {
  let label
  let className = 'pill'

  if (jobStatus === 'queued' || jobStatus === 'processing') {
    label = 'Processing'
    className += ' pill-processing'
  } else if (jobStatus === 'failed') {
    label = 'Failed'
    className += ' pill-failed'
  } else if (approved) {
    label = 'Approved'
    className += ' pill-approved'
  } else if (needsReview) {
    label = 'Needs review'
    className += ' pill-review'
  } else {
    label = 'Ready for review'
    className += ' pill-ready'
  }

  return <span className={className}>{label}</span>
}
