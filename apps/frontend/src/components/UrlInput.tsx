import { useState, type FormEvent } from 'react';
import Spinner from './Spinner';

interface UrlInputProps {
  onSubmit: (url: string) => void;
  loading: boolean;
  disabled?: boolean;
}

function looksLikeUrl(value: string): boolean {
  const v = value.trim();
  if (v.length < 4) return false;
  return /^(https?:\/\/|www\.)/i.test(v) || /\.[a-z]{2,}\//i.test(v) || /\.[a-z]{2,}$/i.test(v);
}

export default function UrlInput({ onSubmit, loading, disabled }: UrlInputProps) {
  const [value, setValue] = useState('');
  const [pasteError, setPasteError] = useState<string | null>(null);

  const handlePaste = async () => {
    setPasteError(null);
    try {
      const text = await navigator.clipboard.readText();
      if (text) setValue(text.trim());
      else setPasteError('Буфер обмена пуст.');
    } catch {
      setPasteError('Не удалось прочитать буфер обмена. Вставьте ссылку вручную.');
    }
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const url = value.trim();
    if (!url || loading || disabled) return;
    onSubmit(url);
  };

  const canSubmit = looksLikeUrl(value) && !loading && !disabled;

  return (
    <form className="url-input" onSubmit={handleSubmit}>
      <div className="url-input-row">
        <input
          type="url"
          inputMode="url"
          className="url-field"
          placeholder="Вставьте ссылку: YouTube, VK, TikTok, Instagram…"
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            setPasteError(null);
          }}
          autoComplete="off"
          autoCapitalize="off"
          spellCheck={false}
          aria-label="Ссылка на медиа"
          disabled={loading || disabled}
        />
        <button
          type="button"
          className="btn btn-ghost url-paste"
          onClick={handlePaste}
          disabled={loading || disabled}
          title="Вставить из буфера обмена"
        >
          Вставить
        </button>
      </div>
      <button type="submit" className="btn btn-primary btn-block" disabled={!canSubmit}>
        {loading ? <Spinner label="Анализируем…" /> : 'Получить медиа'}
      </button>
      {pasteError && <p className="hint hint-warn">{pasteError}</p>}
    </form>
  );
}
