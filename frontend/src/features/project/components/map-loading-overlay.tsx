// Shown over the map while the basemap style/tiles are still loading, so
// the first paint is an on-brand wave rather than a blank/white flash.
function WaveTile({ className }: { className: string }) {
  return (
    <svg viewBox="0 0 400 100" preserveAspectRatio="none" className={className}>
      <path
        d="M0,50 C25,20 75,80 100,50 C125,20 175,80 200,50 C225,20 275,80 300,50 C325,20 375,80 400,50 L400,100 L0,100 Z"
        fill="currentColor"
      />
    </svg>
  );
}

function WaveBand({ className, durationSeconds }: { className: string; durationSeconds: number }) {
  return (
    <div
      className="absolute inset-0 flex w-[200%]"
      style={{ animation: `wave-scroll ${durationSeconds}s linear infinite` }}
    >
      <WaveTile className={`h-full w-1/2 shrink-0 ${className}`} />
      <WaveTile className={`h-full w-1/2 shrink-0 ${className}`} />
    </div>
  );
}

export function MapLoadingOverlay() {
  return (
    <div className="bg-surface-900 relative h-full w-full overflow-hidden">
      <div className="absolute inset-x-0 bottom-0 h-1/2">
        <div className="absolute inset-x-0 bottom-0 h-full">
          <WaveBand className="text-secondary-500/35" durationSeconds={11} />
        </div>
        <div className="absolute inset-x-0 bottom-0 h-3/4">
          <WaveBand className="text-accent-400/55" durationSeconds={7} />
        </div>
      </div>
    </div>
  );
}
