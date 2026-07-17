import { useState } from 'react';
import { ApiError, admin } from '../../api';
import { formatBytes } from '../../format';

interface CleanupResult {
  expired: number;
  freed_bytes: number;
  stale_tmp: number;
}

export default function CleanupPanel() {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<CleanupResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const runCleanup = async () => {
    if (!window.confirm('Запустить очистку: удалить истёкшие файлы и освободить место?')) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const res = await admin.cleanup();
      setResult(res);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Очистка не удалась.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="admin-cleanup">
      <div className="admin-panel-head">
        <h2>Очистка</h2>
      </div>

      <div className="admin-card">
        <p className="muted">
          Удаляет истёкшие временные ссылки и файлы, применяет лимит хранилища (вытеснение самых
          старых) и чистит незавершённые временные файлы.
        </p>
        <button type="button" className="btn btn-primary" onClick={runCleanup} disabled={busy}>
          {busy ? 'Очистка…' : 'Запустить очистку'}
        </button>

        {error && <div className="alert alert-error">{error}</div>}

        {result && (
          <div className="cleanup-result">
            <div className="stat">
              <span className="stat-value">{result.expired}</span>
              <span className="stat-label">истёкших удалено</span>
            </div>
            <div className="stat">
              <span className="stat-value">{formatBytes(result.freed_bytes)}</span>
              <span className="stat-label">освобождено</span>
            </div>
            <div className="stat">
              <span className="stat-value">{result.stale_tmp}</span>
              <span className="stat-label">временных файлов</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
