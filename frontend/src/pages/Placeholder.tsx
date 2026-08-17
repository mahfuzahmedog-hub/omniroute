// Honest placeholder for command-center areas whose backing subsystem is not yet built.
// It states the phase the area depends on rather than showing fake data.

export default function Placeholder({ title, phase }: { title: string; phase: number }) {
  return (
    <div>
      <h1 className="text-2xl font-semibold text-white">{title}</h1>
      <div className="mt-6 rounded-lg border border-dashed border-forge-border bg-forge-panel p-8">
        <div className="text-sm uppercase tracking-wide text-forge-accent">
          Planned — Phase {phase}
        </div>
        <p className="mt-2 max-w-prose text-gray-400">
          This command-center area is part of the Forge roadmap but its backing subsystem
          has not been implemented yet. It is shown here so the navigation reflects the
          full target product, without presenting placeholder functionality as complete.
        </p>
      </div>
    </div>
  );
}
