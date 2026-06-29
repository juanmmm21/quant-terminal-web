export function LoadingPanel({ label = "Cargando datos del terminal…" }: { label?: string }) {
  return (
    <div className="loading-panel" role="status" aria-busy="true">
      <div className="loading-spinner" aria-hidden="true" />
      <p>{label}</p>
    </div>
  );
}
