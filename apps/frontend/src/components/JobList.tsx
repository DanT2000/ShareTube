import { Link } from 'react-router-dom';
import StatusBadge from './StatusBadge';
import {
  contentTypeLabel,
  formatDateTime,
  formatDuration,
  progressPercent,
  sourceLabel,
} from '../format';
import { ACTIVE_STATUSES } from '../api';
import type { JobOut } from '../types';

interface JobListProps {
  jobs: JobOut[];
  emptyText?: string;
  onOpen?: (job: JobOut) => void;
}

function JobRow({ job, onOpen }: { job: JobOut; onOpen?: (job: JobOut) => void }) {
  const active = ACTIVE_STATUSES.has(job.status);
  const pct = progressPercent(job.progress);
  const clickable = Boolean(onOpen);

  const inner = (
    <>
      <div className="job-thumb">
        {job.thumbnail_url ? (
          <img src={job.thumbnail_url} alt="" loading="lazy" referrerPolicy="no-referrer" />
        ) : (
          <span className="job-thumb-ph" aria-hidden>
            ▶
          </span>
        )}
      </div>
      <div className="job-body">
        <div className="job-title-row">
          <span className="job-title">{job.title || job.normalized_url}</span>
          <StatusBadge status={job.status} />
        </div>
        <div className="job-sub">
          <span className="chip chip-sm">{sourceLabel(job.source)}</span>
          <span className="chip chip-sm chip-muted">{contentTypeLabel(job.content_type)}</span>
          {job.duration_sec ? (
            <span className="job-meta-item">{formatDuration(job.duration_sec)}</span>
          ) : null}
          <span className="job-meta-item">{formatDateTime(job.created_at)}</span>
        </div>
        {active && (
          <div className="progress-bar progress-bar-sm">
            <div className="progress-fill" style={{ width: `${pct}%` }} />
          </div>
        )}
      </div>
    </>
  );

  return (
    <li className="job-row">
      {clickable ? (
        <button type="button" className="job-row-main" onClick={() => onOpen?.(job)}>
          {inner}
        </button>
      ) : (
        <div className="job-row-main">{inner}</div>
      )}
      {job.status === 'done' && job.download_url && (
        <a className="btn btn-sm btn-secondary job-dl" href={job.download_url} download>
          Скачать
        </a>
      )}
    </li>
  );
}

export default function JobList({ jobs, emptyText, onOpen }: JobListProps) {
  if (jobs.length === 0) {
    return (
      <div className="empty-state">
        <p>{emptyText || 'Пока нет заданий.'}</p>
        <Link to="/" className="btn btn-secondary">
          Добавить ссылку
        </Link>
      </div>
    );
  }
  return (
    <ul className="job-list">
      {jobs.map((job) => (
        <JobRow key={job.id} job={job} onOpen={onOpen} />
      ))}
    </ul>
  );
}
