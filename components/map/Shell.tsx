'use client';

import { X } from 'lucide-react';

/** The floating details card (bottom sheet on a phone, right-hand card on a desktop). */
export default function Shell({ title, subtitle, onClose, children }: { title: string; subtitle?: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <aside
      className="absolute inset-x-0 bottom-0 z-20 flex max-h-[68%] flex-col rounded-t-xl border border-line bg-surface shadow-lg md:inset-x-auto md:bottom-auto md:right-3 md:top-14 md:max-h-[calc(100%-4.5rem)] md:w-[24rem] md:rounded-xl"
      aria-label="Details"
    >
      <div className="flex items-start justify-between gap-2 px-4 pt-3">
        <div className="min-w-0">
          <h2 className="text-base font-semibold leading-tight">{title}</h2>
          {subtitle && <p className="mt-0.5 break-all text-xs text-muted">{subtitle}</p>}
        </div>
        <button type="button" className="-mr-2 -mt-1 flex h-11 w-11 shrink-0 items-center justify-center" aria-label="Close" onClick={onClose}>
          <X size={20} aria-hidden />
        </button>
      </div>
      <div className="overflow-y-auto px-4 pb-4 text-sm">{children}</div>
    </aside>
  );
}
