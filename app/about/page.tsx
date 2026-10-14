import fs from 'node:fs';
import path from 'node:path';
import type { Metadata } from 'next';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import SiteHeader from '@/components/SiteHeader';
import SiteFooter from '@/components/SiteFooter';

export const metadata: Metadata = {
  title: 'About',
  description: 'Who runs AI Buildout Frontier and why.',
};

export default function AboutPage() {
  // content/about.md is read at build time
  const md = fs.readFileSync(path.join(process.cwd(), 'content', 'about.md'), 'utf8');
  return (
    <>
      <SiteHeader />
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-8">
        <article className="prose-abf">
          <Markdown remarkPlugins={[remarkGfm]}>{md}</Markdown>
        </article>
      </main>
      <SiteFooter />
    </>
  );
}
