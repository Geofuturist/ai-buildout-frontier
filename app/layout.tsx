import type { Metadata } from 'next';
import './globals.css';
import Footer from '@/app/components/Footer';

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
      <body className="min-h-screen flex flex-col bg-gray-50">
        {children}
        <Footer />
      </body>
    </html>
  );
}
