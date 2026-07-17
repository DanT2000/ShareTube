// Reference view of supported sources. There is no dedicated backend endpoint,
// so this mirrors apps/backend/app/extractors/sources.py and annotates each
// source with its extractor and operational notes.

interface SourceInfo {
  key: string;
  label: string;
  extractor: string;
  types: string;
  note?: string;
}

const SOURCES: SourceInfo[] = [
  { key: 'youtube', label: 'YouTube', extractor: 'yt-dlp', types: 'Видео · Shorts · Плейлисты' },
  { key: 'vk', label: 'VK / VK Видео', extractor: 'yt-dlp', types: 'Видео · Стены' },
  {
    key: 'instagram',
    label: 'Instagram',
    extractor: 'gallery-dl / yt-dlp',
    types: 'Reels · Посты · Карусели',
    note: 'Может требовать cookie-профиль; часть диапазонов ДЦ блокируется — нужен подходящий выход.',
  },
  { key: 'tiktok', label: 'TikTok', extractor: 'yt-dlp', types: 'Видео' },
  { key: 'vimeo', label: 'Vimeo', extractor: 'yt-dlp', types: 'Видео' },
  { key: 'twitch', label: 'Twitch', extractor: 'yt-dlp', types: 'Клипы · VOD' },
  { key: 'twitter', label: 'X / Twitter', extractor: 'yt-dlp', types: 'Видео · Медиа' },
  {
    key: 'direct',
    label: 'Прямые ссылки',
    extractor: 'direct file',
    types: 'mp4 · mp3 · jpg · …',
    note: 'Скачивание файла по прямому URL с поддержкой типовых расширений.',
  },
  { key: 'generic', label: 'Другие сайты', extractor: 'yt-dlp (generic)', types: 'Best-effort' },
];

export default function SourcesPanel() {
  return (
    <div className="admin-sources">
      <div className="admin-panel-head">
        <h2>Источники</h2>
      </div>
      <p className="muted">
        Поддерживаемые площадки и используемые извлекатели. Загрузки для всех источников идут через
        активные исходящие профили.
      </p>
      <div className="sources-grid">
        {SOURCES.map((s) => (
          <div className="source-card" key={s.key}>
            <div className="source-head">
              <span className="source-name">{s.label}</span>
              <span className="chip chip-sm">{s.extractor}</span>
            </div>
            <div className="source-types">{s.types}</div>
            {s.note && <p className="hint">{s.note}</p>}
          </div>
        ))}
      </div>
    </div>
  );
}
