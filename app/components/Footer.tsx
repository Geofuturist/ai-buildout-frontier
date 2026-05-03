// app/components/Footer.tsx
// New component — add to app/layout.tsx inside <body> after {children}

export default function Footer() {
  return (
    <footer className="border-t border-slate-200 mt-auto">
      <div className="mx-auto max-w-[768px] px-6 py-6 md:px-12">
        <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
          <span className="text-sm text-slate-500">
            The AI Buildout Frontier
          </span>
          <div className="flex items-center gap-4">
            <a
              href="https://github.com/Geofuturist/ai-buildout-frontier"
              className="text-sm text-slate-500 hover:text-slate-800 underline underline-offset-2"
              target="_blank"
              rel="noopener noreferrer"
            >
              GitHub
            </a>
            <span className="text-sm text-slate-400">
              Data and code: CC BY 4.0
            </span>
          </div>
        </div>
      </div>
    </footer>
  );
}
