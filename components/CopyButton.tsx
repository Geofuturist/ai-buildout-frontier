'use client';

import { useState } from 'react';
import { Check, Copy } from 'lucide-react';

/** Copies a text to the clipboard; shows "Copied" for two seconds. */
export default function CopyButton({ text, label, className = 'btn' }: { text: string; label: string; className?: string }) {
  const [done, setDone] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand('copy'); } catch { /* nothing else to try */ }
      document.body.removeChild(ta);
    }
    setDone(true);
    window.setTimeout(() => setDone(false), 2000);
  }

  return (
    <button type="button" className={className} onClick={copy} aria-live="polite">
      {done ? <Check size={16} aria-hidden /> : <Copy size={16} aria-hidden />}
      {done ? 'Copied' : label}
    </button>
  );
}
