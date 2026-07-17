// TypeScript contracts mirroring the FastAPI backend (apps/backend/app/schemas.py).
// Keep field names identical to the JSON returned by the API.

export type JobStatus =
  | 'pending'
  | 'analyzing'
  | 'analyzed'
  | 'queued'
  | 'downloading'
  | 'merging'
  | 'converting'
  | 'uploading'
  | 'done'
  | 'failed'
  | 'cancelled';

export type ContentType =
  | 'video'
  | 'short'
  | 'audio'
  | 'photo'
  | 'photo_carousel'
  | 'mixed'
  | 'playlist'
  | 'live'
  | 'unknown';

/** Known format labels emitted by the backend. */
export type FormatLabel =
  | 'auto'
  | '1080p'
  | '720p'
  | '480p'
  | 'min'
  | 'original'
  | 'audio'
  | string;

export interface Format {
  id: number | null;
  label: FormatLabel;
  ext: string | null;
  vcodec: string | null;
  acodec: string | null;
  width: number | null;
  height: number | null;
  fps: number | null;
  approx_size_bytes: number | null;
  size_is_estimate: boolean;
  audio_only: boolean;
}

export interface MediaItem {
  position: number;
  kind: string;
  filename: string | null;
  width: number | null;
  height: number | null;
}

export interface JobOut {
  id: string;
  status: JobStatus;
  stage: string | null;
  progress: number;
  source: string | null;
  content_type: ContentType;
  original_url: string;
  normalized_url: string;
  title: string | null;
  author: string | null;
  duration_sec: number | null;
  thumbnail_url: string | null;
  item_count: number;
  approx_size_bytes: number | null;
  actual_size_bytes: number | null;
  error_code: string | null;
  error_message: string | null;
  delivery_method: string | null;
  download_url: string | null;
  telegram_file_id: string | null;
  formats: Format[];
  items: MediaItem[];
  created_at: string | null;
  finished_at: string | null;
}

/** SSE payload from GET /api/jobs/{id}/events. */
export interface JobProgressEvent {
  job_id: string;
  status: JobStatus;
  stage?: string | null;
  progress?: number;
  speed?: number | null;
  downloaded_bytes?: number | null;
  total_bytes?: number | null;
  eta?: number | null;
  download_url?: string | null;
  error?: string | null;
}

export interface Me {
  id: number;
  display_name: string | null;
  is_admin: boolean;
}

export interface TelegramAuthPayload {
  id: number;
  first_name?: string;
  last_name?: string;
  username?: string;
  photo_url?: string;
  auth_date: number;
  hash: string;
}

export interface TelegramLoginResult {
  ok: boolean;
  user_id: number;
  is_admin: boolean;
}

// ---------------- Admin contracts ----------------

export interface AdminDashboard {
  jobs: { active: number; queued: number; failed: number; done: number };
  users: number;
  storage: {
    used_bytes: number;
    cap_bytes: number;
    disk_total: number | null;
    disk_free: number | null;
  };
}

export interface AdminJob {
  id: string;
  user_id: number;
  source: string | null;
  status: JobStatus;
  content_type: ContentType;
  progress: number;
  stage: string | null;
  actual_size_bytes: number | null;
  error_code: string | null;
  created_at: string | null;
  url: string;
}

export interface AdminUser {
  id: number;
  display_name: string | null;
  is_admin: boolean;
  is_blocked: boolean;
  quota_daily_jobs: number | null;
  created_at: string | null;
}

export interface ProxyDisplayMeta {
  protocol?: string;
  host?: string;
  port?: number;
  has_auth?: boolean;
}

export interface ProxyProfile {
  id: number;
  name: string;
  kind: string;
  enabled: boolean;
  is_primary: boolean;
  is_backup: boolean;
  priority: number;
  bound_sources: string | null;
  display_meta: ProxyDisplayMeta | null;
  last_status: string;
  last_latency_ms: number | null;
  last_checked_at: string | null;
  error_count: number;
  last_error_category: string | null;
}

export interface ProxyCheckResult {
  status: string;
  latency_ms: number | null;
  error_category: string | null;
  checked_at: string | null;
}

export interface CookieProfile {
  id: number;
  source: string;
  name: string;
  enabled: boolean;
  health_status: string;
  last_checked_at: string | null;
  has_data: boolean;
}

export interface ToolVersions {
  yt_dlp: string;
  gallery_dl: string;
  ffmpeg: string;
  ffprobe: string;
}

export interface AdminSettings {
  limits: Record<string, number>;
  telegram: {
    bot_username: string;
    mode: string;
    local_bot_api: boolean;
    token_fingerprint: string;
  };
  network: { outbound_required: boolean };
  storage_provider: string;
}

export interface AuditLogEntry {
  created_at: string | null;
  actor: string;
  action: string;
  target: string | null;
  detail: Record<string, unknown> | null;
}
