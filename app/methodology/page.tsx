import type { Metadata } from 'next';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeSlug from 'rehype-slug';
import SiteHeader from '@/components/SiteHeader';
import SiteFooter from '@/components/SiteFooter';
import { getMethodology } from '@/lib/data';

export const metadata: Metadata = {
  title: 'Methodology',
  description: 'How the layers are built, what they show and what they do not show.',
};

export default function MethodologyPage() {
  const md = getMethodology();
  return (
    <>
      <SiteHeader />
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-8">
        <article className="prose-abf">
          <Markdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeSlug]}
            components={{
              table: ({ children }) => (
                <div className="table-wrap">
                  <table>{children}</table>
                </div>
              ),
            }}
          >
            {md}
          </Markdown>
        </article>
      </main>
      <SiteFooter />
    </>
  );
}
