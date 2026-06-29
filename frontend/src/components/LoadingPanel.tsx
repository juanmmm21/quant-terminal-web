export function LoadingPanel() {
  return (
    <div className="loading-panel" role="status" aria-busy="true">
      <div className="loading-spinner" aria-hidden="true" />
    </div>
  );
}
