export default function Spinner({ label }: { label?: string }) {
  return (
    <span className="spinner-wrap" role="status" aria-live="polite">
      <span className="spinner" aria-hidden />
      {label && <span className="spinner-label">{label}</span>}
    </span>
  );
}
