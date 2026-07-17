import { useMemo, useState } from 'react';
import JobProgress from './JobProgress';
import {
  contentTypeLabel,
  formatApproxSize,
  formatBytes,
  formatDuration,
  formatLabel,
  sourceLabel,
} from '../format';
import { openExternal } from '../telegram';
import type { Format, JobOut, JobProgressEvent } from '../types';

export interface StartOptions {
  format_id?: number;
  format_label?: string;
  deliver_to_telegram?: boolean;
}

interface MediaCardProps {
  job: JobOut;
  live: JobProgressEvent | null;
  onStart: (opts: StartOptions) => void;
  onCancel: () => void;
  onRetry: () => void;
  starting?: boolean;
  cancelling?: boolean;
  connected?: boolean;
  isMiniApp: boolean;
}

const ACTIVE = new Set(['queued', 'downloading', 'merging', 'converting', 'uploading', 'analyzing']);

function FormatButton({
  format,
  selected,
  onSelect,
}: {
  format: Format;
  selected: boolean;
  onSelect: () => void;
}) {
  const size = formatApproxSize(format);
  return (
    <button
      type="button"
      className={`format-btn${selected ? ' is-selected' : ''}`}
      onClick={onSelect}
      aria-pressed={selected}
    >
      <span className="format-label">{formatLabel(format)}</span>
      <span className="format-meta">
        {format.ext && <span className="format-ext">{format.ext.toUpperCase()}</span>}
        {size && <span className="format-size">{size}</span>}
      </span>
    </button>
  );
}

export default function MediaCard({
  job,
  live,
  onStart,
  onCancel,
  onRetry,
  starting,
  cancelling,
  connected,
  isMiniApp,
}: MediaCardProps) {
  const formats = job.formats;
  // Default selection: prefer "auto", else the first (highest-res) format.
  const defaultFormat = useMemo(() => {
    const auto = formats.find((f) => f.label === 'auto');
    return auto ?? formats[0] ?? null;
  }, [formats]);

  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [deliverTg, setDeliverTg] = useState(isMiniApp);
  const [copied, setCopied] = useState(false);

  const keyOf = (f: Format) => (f.id !== null ? `id:${f.id}` : `label:${f.label}`);
  const selected =
    formats.find((f) => keyOf(f) === selectedKey) ?? defaultFormat ?? null;

  const hasEstimate = formats.some((f) => f.size_is_estimate && f.approx_size_bytes);
  const isActive = ACTIVE.has(job.status);
  const isDone = job.status === 'done';
  const isFailed = job.status === 'failed';
  const isCancelled = job.status === 'cancelled';
  const canPickFormat = (job.status === 'analyzed' || isFailed) && formats.length > 0;

  const items = job.items;
  const showGallery = items.length > 1;

  const handleStart = () => {
    if (!selected) {
      onStart({ deliver_to_telegram: deliverTg });
      return;
    }
    const opts: StartOptions = { deliver_to_telegram: deliverTg };
    if (selected.id !== null) opts.format_id = selected.id;
    else opts.format_label = selected.label;
    onStart(opts);
  };

  const copyLink = async () => {
    if (!job.download_url) return;
    try {
      await navigator.clipboard.writeText(job.download_url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <article className="media-card">
      <div className="media-head">
        <div className="media-thumb">
          {job.thumbnail_url ? (
            <img src={job.thumbnail_url} alt="" loading="lazy" referrerPolicy="no-referrer" />
          ) : (
            <div className="media-thumb-placeholder" aria-hidden>
              ▶
            </div>
          )}
          {job.duration_sec ? (
            <span className="media-duration">{formatDuration(job.duration_sec)}</span>
          ) : null}
        </div>

        <div className="media-info">
          <h3 className="media-title">{job.title || job.normalized_url}</h3>
          {job.author && <p className="media-author">{job.author}</p>}
          <div className="media-badges">
            <span className="chip">{sourceLabel(job.source)}</span>
            <span className="chip chip-muted">{contentTypeLabel(job.content_type)}</span>
            {job.item_count > 1 && (
              <span className="chip chip-muted">{job.item_count} элем.</span>
            )}
            {job.approx_size_bytes ? (
              <span className="chip chip-muted">~{formatBytes(job.approx_size_bytes)}</span>
            ) : null}
          </div>
        </div>
      </div>

      {showGallery && (
        <details className="media-items">
          <summary>Элементы галереи ({items.length})</summary>
          <ul>
            {items.map((it) => (
              <li key={it.position}>
                <span className="item-kind">{it.kind}</span>
                <span className="item-name">
                  {it.filename || `Элемент ${it.position + 1}`}
                </span>
                {it.width && it.height ? (
                  <span className="item-dim">
                    {it.width}×{it.height}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        </details>
      )}

      {/* ------- footer varies by status ------- */}

      {canPickFormat && (
        <div className="media-formats">
          <div className="section-label">Качество и формат</div>
          <div className="format-grid">
            {formats.map((f) => (
              <FormatButton
                key={keyOf(f)}
                format={f}
                selected={selected ? keyOf(selected) === keyOf(f) : false}
                onSelect={() => setSelectedKey(keyOf(f))}
              />
            ))}
          </div>
          {hasEstimate && <p className="hint">Размер приблизительный.</p>}

          {isMiniApp && (
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={deliverTg}
                onChange={(e) => setDeliverTg(e.target.checked)}
              />
              <span>Отправить файл в Telegram</span>
            </label>
          )}

          <button
            type="button"
            className="btn btn-primary btn-block"
            onClick={handleStart}
            disabled={starting}
          >
            {starting ? 'Запуск…' : 'Скачать'}
          </button>
        </div>
      )}

      {isActive && (
        <JobProgress
          job={job}
          live={live}
          onCancel={onCancel}
          cancelling={cancelling}
          connected={connected}
        />
      )}

      {isDone && (
        <div className="media-done">
          <div className="done-banner">Файл готов</div>
          {job.actual_size_bytes ? (
            <p className="hint">Размер файла: {formatBytes(job.actual_size_bytes)}</p>
          ) : null}
          <div className="done-actions">
            {job.download_url && (
              <a
                className="btn btn-primary"
                href={job.download_url}
                onClick={(e) => {
                  if (isMiniApp && job.download_url) {
                    e.preventDefault();
                    openExternal(job.download_url);
                  }
                }}
                download
              >
                Скачать
              </a>
            )}
            {isMiniApp && (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => onStart({ deliver_to_telegram: true })}
                title="Повторно доставить файл в чат Telegram"
              >
                Отправить в Telegram
              </button>
            )}
            {job.download_url && (
              <button type="button" className="btn btn-ghost" onClick={copyLink}>
                {copied ? 'Скопировано ✓' : 'Скопировать ссылку'}
              </button>
            )}
          </div>
          {job.telegram_file_id && (
            <p className="hint hint-ok">Файл доставлен в Telegram.</p>
          )}
        </div>
      )}

      {isFailed && (
        <div className="media-error">
          <p className="error-text">
            {job.error_message || 'Не удалось обработать ссылку.'}
            {job.error_code ? <span className="error-code"> ({job.error_code})</span> : null}
          </p>
          <button type="button" className="btn btn-secondary" onClick={onRetry}>
            Повторить
          </button>
        </div>
      )}

      {isCancelled && (
        <div className="media-error">
          <p className="hint">Задание отменено.</p>
          <button type="button" className="btn btn-secondary" onClick={onRetry}>
            Повторить
          </button>
        </div>
      )}
    </article>
  );
}
