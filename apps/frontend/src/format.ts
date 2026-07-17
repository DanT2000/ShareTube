// Presentation helpers: human-readable RU labels, sizes, durations, statuses.

import type { ContentType, Format, JobStatus } from './types';

const FORMAT_LABELS: Record<string, string> = {
  auto: 'Авто',
  '1080p': '1080p',
  '720p': '720p',
  '480p': '480p',
  min: 'Мин. размер',
  original: 'Оригинал',
  audio: '🎵 Только аудио',
};

/** Human RU label for a format, wrapping special ones in guillemets. */
export function formatLabel(f: Format): string {
  const known = FORMAT_LABELS[f.label];
  if (known) {
    if (f.label === 'min') return '«Мин. размер»';
    if (f.label === 'original') return '«Оригинал»';
    return known;
  }
  if (f.audio_only) return '🎵 Только аудио';
  if (f.height) return `${f.height}p`;
  return f.label;
}

const STATUS_LABELS: Record<JobStatus, string> = {
  pending: 'Ожидание',
  analyzing: 'Анализ',
  analyzed: 'Готово к загрузке',
  queued: 'В очереди',
  downloading: 'Загрузка',
  merging: 'Сборка',
  converting: 'Конвертация',
  uploading: 'Отправка',
  done: 'Готово',
  failed: 'Ошибка',
  cancelled: 'Отменено',
};

export function statusLabel(status: JobStatus): string {
  return STATUS_LABELS[status] ?? status;
}

const STAGE_LABELS: Record<string, string> = {
  analysis: 'Анализ ссылки',
  waiting: 'Ожидание в очереди',
  downloading: 'Загрузка',
  merging: 'Склейка дорожек',
  converting: 'Перекодирование',
  uploading: 'Доставка',
  cancelled: 'Отменено',
};

export function stageLabel(stage: string | null | undefined): string {
  if (!stage) return '';
  return STAGE_LABELS[stage] ?? stage;
}

const CONTENT_TYPE_LABELS: Record<ContentType, string> = {
  video: 'Видео',
  short: 'Shorts / Reels',
  audio: 'Аудио',
  photo: 'Фото',
  photo_carousel: 'Фотокарусель',
  mixed: 'Смешанное',
  playlist: 'Плейлист',
  live: 'Трансляция',
  unknown: 'Неизвестно',
};

export function contentTypeLabel(ct: ContentType): string {
  return CONTENT_TYPE_LABELS[ct] ?? ct;
}

const SOURCE_LABELS: Record<string, string> = {
  youtube: 'YouTube',
  vk: 'VK',
  instagram: 'Instagram',
  tiktok: 'TikTok',
  vimeo: 'Vimeo',
  twitch: 'Twitch',
  twitter: 'X / Twitter',
  direct: 'Прямая ссылка',
  generic: 'Другое',
};

export function sourceLabel(source: string | null | undefined): string {
  if (!source) return '—';
  return SOURCE_LABELS[source] ?? source;
}

const KB = 1024;
const MB = KB * 1024;
const GB = MB * 1024;

/** Bytes -> "1.5 ГБ" / "740 МБ" / "12 КБ". */
export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return '—';
  if (bytes < KB) return `${bytes} Б`;
  if (bytes < MB) return `${(bytes / KB).toFixed(0)} КБ`;
  if (bytes < GB) return `${(bytes / MB).toFixed(bytes < 10 * MB ? 1 : 0)} МБ`;
  return `${(bytes / GB).toFixed(2)} ГБ`;
}

/** Approximate size with a leading "~" (used for pre-download estimates). */
export function formatApproxSize(f: Pick<Format, 'approx_size_bytes' | 'size_is_estimate'>): string {
  if (f.approx_size_bytes === null || f.approx_size_bytes === undefined) return '';
  const size = formatBytes(f.approx_size_bytes);
  return f.size_is_estimate ? `~${size}` : size;
}

/** Bytes/second -> "3.2 МБ/с". */
export function formatSpeed(bytesPerSec: number | null | undefined): string {
  if (!bytesPerSec) return '—';
  return `${formatBytes(bytesPerSec)}/с`;
}

/** Seconds -> "1:02:03" / "4:07". */
export function formatDuration(totalSec: number | null | undefined): string {
  if (totalSec === null || totalSec === undefined) return '';
  const sec = Math.max(0, Math.round(totalSec));
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  const pad = (n: number) => n.toString().padStart(2, '0');
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}

/** Seconds remaining -> "осталось ~2 мин". */
export function formatEta(sec: number | null | undefined): string {
  if (sec === null || sec === undefined || !isFinite(sec) || sec < 0) return '';
  if (sec < 60) return `осталось ~${Math.round(sec)} с`;
  const min = Math.floor(sec / 60);
  const rem = Math.round(sec % 60);
  return `осталось ~${min} мин ${rem ? `${rem} с` : ''}`.trim();
}

/** ISO timestamp -> localized RU date/time. */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '—';
  return d.toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function formatPercent(progress: number | null | undefined): string {
  if (progress === null || progress === undefined) return '0%';
  const pct = progress <= 1 ? progress * 100 : progress;
  return `${Math.min(100, Math.max(0, Math.round(pct)))}%`;
}

/** Normalize progress (backend may send 0..1 or 0..100) to a 0..100 number. */
export function progressPercent(progress: number | null | undefined): number {
  if (!progress) return 0;
  const pct = progress <= 1 ? progress * 100 : progress;
  return Math.min(100, Math.max(0, pct));
}
