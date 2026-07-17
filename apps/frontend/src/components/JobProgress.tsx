import Spinner from './Spinner';
import {
  formatBytes,
  formatEta,
  formatPercent,
  formatSpeed,
  progressPercent,
  stageLabel,
  statusLabel,
} from '../format';
import type { JobOut, JobProgressEvent } from '../types';

interface JobProgressProps {
  job: JobOut;
  live: JobProgressEvent | null;
  onCancel?: () => void;
  cancelling?: boolean;
  connected?: boolean;
}

/**
 * Live download progress. Prefers the freshest SSE event, falling back to the
 * last known job snapshot for each field.
 */
export default function JobProgress({
  job,
  live,
  onCancel,
  cancelling,
  connected,
}: JobProgressProps) {
  const status = live?.status ?? job.status;
  const stage = live?.stage ?? job.stage;
  const pct = progressPercent(live?.progress ?? job.progress);
  const speed = live?.speed;
  const downloaded = live?.downloaded_bytes;
  const total = live?.total_bytes ?? job.approx_size_bytes;
  const eta = live?.eta;

  // Some stages (merging/converting/uploading) have no measurable byte progress.
  const indeterminate =
    pct <= 0 && (status === 'merging' || status === 'converting' || status === 'uploading');

  return (
    <div className="job-progress">
      <div className="progress-head">
        <span className="progress-status">
          <Spinner />
          <strong>{statusLabel(status)}</strong>
          {stage && <span className="progress-stage">· {stageLabel(stage)}</span>}
        </span>
        <span className="progress-pct">{formatPercent(pct)}</span>
      </div>

      <div className={`progress-bar${indeterminate ? ' is-indeterminate' : ''}`}>
        <div className="progress-fill" style={{ width: indeterminate ? '100%' : `${pct}%` }} />
      </div>

      <dl className="progress-meta">
        <div>
          <dt>Скорость</dt>
          <dd>{formatSpeed(speed)}</dd>
        </div>
        <div>
          <dt>Загружено</dt>
          <dd>
            {formatBytes(downloaded)}
            {total ? ` / ${formatBytes(total)}` : ''}
          </dd>
        </div>
        <div>
          <dt>Осталось</dt>
          <dd>{formatEta(eta) || '—'}</dd>
        </div>
      </dl>

      <div className="progress-actions">
        {!connected && <span className="hint">Переподключение к потоку прогресса…</span>}
        {onCancel && (
          <button
            type="button"
            className="btn btn-danger"
            onClick={onCancel}
            disabled={cancelling}
          >
            {cancelling ? 'Отмена…' : 'Отменить'}
          </button>
        )}
      </div>
    </div>
  );
}
