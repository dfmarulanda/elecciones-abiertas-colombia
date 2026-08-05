export default function AnalysisLoading() {
  return (
    <main
      id="main-content"
      tabIndex={-1}
      className="mx-auto max-w-[1440px] animate-pulse px-[clamp(1rem,5.55vw,5rem)] py-8 sm:py-12"
      aria-busy="true"
      aria-label="Loading analysis"
      role="status"
    >
      <div className="h-12 border border-ink bg-line" />
      <div className="mt-8 h-40 border border-ink bg-line" />
      <div className="mt-4 h-72 border border-ink bg-line" />
      <p className="sr-only">Loading analysis</p>
    </main>
  );
}
