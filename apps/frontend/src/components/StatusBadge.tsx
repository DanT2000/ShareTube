import { statusLabel } from '../format';
import type { JobStatus } from '../types';

// Groups a status into a color family used by CSS (data-tone).
function tone(status: JobStatus): 'done' | 'failed' | 'active' | 'idle' {
  if (status === 'done') return 'done';
  if (status === 'failed' || status === 'cancelled') return 'failed';
  if (status === 'analyzed' || status === 'pending') return 'idle';
  return 'active';
}

export default function StatusBadge({ status }: { status: JobStatus }) {
  const t = tone(status);
  const spinning = t === 'active';
  return (
    <span className="status-badge" data-tone={t}>
      {spinning && <span className="status-dot" aria-hidden />}
      {statusLabel(status)}
    </span>
  );
}
