export default function Header() {
  return (
    <header className="border-b bg-white px-6 py-3 z-10 relative">
      <div className="flex items-center justify-between max-w-7xl mx-auto">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">
            The AI Buildout Frontier
          </h1>
          <p className="text-xs text-gray-500">
            Physical constraints on AI infrastructure — Virginia pilot
          </p>
        </div>
        <a
          href="https://github.com/Geofuturist/ai-buildout-frontier"
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm text-gray-600 hover:text-gray-900 transition-colors"
        >
          GitHub →
        </a>
      </div>
    </header>
  );
}
