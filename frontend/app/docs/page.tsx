export default function DocsPage() {
  return (
    <div className="flex items-center justify-center min-h-[70vh] px-8">
      <div className="max-w-xl space-y-6 text-left">
        <h1 className="text-3xl font-bold tracking-tight text-center">IsoCrates</h1>
        <p className="text-lg text-muted-foreground leading-relaxed">
          Collaborate with your colleagues and AI to keep your documentation
          flawless. Connect your GitHub repositories and let the Agent
          automatically generate wikipedia-style docs, complete with
          cross-references, diagrams, and tables.
        </p>

        <p className="text-sm text-muted-foreground">
          Select a document from the sidebar to get started.
        </p>

        <hr className="border-border" />

        <div className="text-sm text-muted-foreground space-y-1">
          <p>
            IsoCrates is open source.{' '}
            <a
              href="https://github.com/Matthieu5555/IsoCrates"
              target="_blank"
              rel="noopener noreferrer"
              className="font-medium text-primary hover:underline"
            >
              View the source code
            </a>
          </p>
          <p>
            Want to deploy it at your organization? Read the{' '}
            <a
              href="https://github.com/Matthieu5555/IsoCrates/blob/main/docs/DEPLOYING_AT_YOUR_ORGANIZATION.md"
              target="_blank"
              rel="noopener noreferrer"
              className="font-medium text-primary hover:underline"
            >
              deployment guide
            </a>
            .
          </p>
        </div>
      </div>
    </div>
  );
}
