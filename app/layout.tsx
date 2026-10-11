import type { Metadata, Viewport } from 'next';
import './globals.css';

const SITE = process.env.NEXT_PUBLIC_SITE_URL || 'https://aibuildoutfrontier.org';

export const metadata: Metadata = {
  metadataBase: new URL(SITE),
  title: { default: 'AI Buildout Frontier', template: '%s · AI Buildout Frontier' },
  description:
    'An open observatory of data layers on the physical side of AI: power generation, demand, transmission lines and interconnection queues. Download, cite and rebuild every layer from its source.',
};

export const viewport: Viewport = { width: 'device-width', initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="flex min-h-screen flex-col">{children}</body>
    </html>
  );
}
