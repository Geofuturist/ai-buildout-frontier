import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'The AI Buildout Frontier',
  description:
    'Physical constraints on AI infrastructure buildout — compute, energy, geopolitics. Virginia pilot.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="h-screen flex flex-col overflow-hidden bg-gray-50">
        {children}
      </body>
    </html>
  );
}
