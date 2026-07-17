import Spinner from '../Spinner';
import { admin } from '../../api';
import { usePolling } from '../../hooks';
import type { ToolVersions } from '../../types';

const TOOLS: { key: keyof ToolVersions; label: string }[] = [
  { key: 'yt_dlp', label: 'yt-dlp' },
  { key: 'gallery_dl', label: 'gallery-dl' },
  { key: 'ffmpeg', label: 'ffmpeg' },
  { key: 'ffprobe', label: 'ffprobe' },
];

export default function VersionsPanel() {
  const { data, loading, error, refetch } = usePolling<ToolVersions>(() => admin.versions(), 0);

  return (
    <div className="admin-versions">
      <div className="admin-panel-head">
        <h2>Версии инструментов</h2>
        <button className="btn btn-ghost btn-sm" onClick={refetch} type="button">
          Обновить
        </button>
      </div>

      {error && <div className="alert alert-error">Не удалось получить версии.</div>}

      {loading && !data ? (
        <Spinner label="Загрузка…" />
      ) : (
        <div className="versions-grid">
          {TOOLS.map((t) => {
            const value = data?.[t.key] ?? '—';
            const unavailable = value === 'unavailable' || value === '—';
            return (
              <div className="version-card" key={t.key} data-tone={unavailable ? 'failed' : 'done'}>
                <span className="version-tool">{t.label}</span>
                <code className="version-value">{value}</code>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
