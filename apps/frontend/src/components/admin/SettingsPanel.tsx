import Spinner from '../Spinner';
import { admin } from '../../api';
import { usePolling } from '../../hooks';
import type { AdminSettings } from '../../types';

const LIMIT_LABELS: Record<string, string> = {
  CLOUD_BOT_SAFE_LIMIT_MB: 'Лимит облачного бота, МБ',
  LOCAL_BOT_SAFE_LIMIT_MB: 'Лимит локального бота, МБ',
  MAX_DOWNLOAD_SIZE_MB: 'Макс. размер загрузки, МБ',
  DOWNLOAD_LINK_TTL_HOURS: 'TTL ссылки, ч',
  MAX_STORAGE_GB: 'Хранилище, ГБ',
  MAX_ACTIVE_JOBS_PER_USER: 'Активных заданий на пользователя',
  MAX_GLOBAL_DOWNLOADS: 'Одновременных загрузок',
  MAX_GLOBAL_TRANSCODES: 'Одновременных перекодировок',
  MAX_PLAYLIST_ITEMS: 'Макс. элементов плейлиста',
};

export default function SettingsPanel() {
  const { data, loading, error, refetch } = usePolling<AdminSettings>(() => admin.settings(), 0);

  return (
    <div className="admin-settings">
      <div className="admin-panel-head">
        <h2>Настройки</h2>
        <button className="btn btn-ghost btn-sm" onClick={refetch} type="button">
          Обновить
        </button>
      </div>

      <p className="muted">Отображаются только несекретные значения времени выполнения.</p>

      {error && <div className="alert alert-error">Не удалось загрузить настройки.</div>}

      {loading && !data ? (
        <Spinner label="Загрузка…" />
      ) : data ? (
        <div className="settings-groups">
          <div className="admin-card">
            <h3>Лимиты</h3>
            <dl className="kv-list">
              {Object.entries(data.limits).map(([k, v]) => (
                <div key={k}>
                  <dt>{LIMIT_LABELS[k] ?? k}</dt>
                  <dd>{v}</dd>
                </div>
              ))}
            </dl>
          </div>

          <div className="admin-card">
            <h3>Telegram</h3>
            <dl className="kv-list">
              <div>
                <dt>Бот</dt>
                <dd>@{data.telegram.bot_username}</dd>
              </div>
              <div>
                <dt>Режим</dt>
                <dd>{data.telegram.mode}</dd>
              </div>
              <div>
                <dt>Local Bot API</dt>
                <dd>{data.telegram.local_bot_api ? 'включён' : 'выключен'}</dd>
              </div>
              <div>
                <dt>Отпечаток токена</dt>
                <dd>
                  <code>{data.telegram.token_fingerprint}</code>
                </dd>
              </div>
            </dl>
          </div>

          <div className="admin-card">
            <h3>Сеть и хранилище</h3>
            <dl className="kv-list">
              <div>
                <dt>Только через прокси</dt>
                <dd>{data.network.outbound_required ? 'да' : 'нет'}</dd>
              </div>
              <div>
                <dt>Провайдер хранилища</dt>
                <dd>{data.storage_provider}</dd>
              </div>
            </dl>
          </div>
        </div>
      ) : null}
    </div>
  );
}
