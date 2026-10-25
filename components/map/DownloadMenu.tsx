'use client';

import { useId, useState } from 'react';
import { ChevronDown, ChevronUp, Download } from 'lucide-react';

/** A closed "Download" button: the file options open under it on a click (they are not all shown at once). */
export default function DownloadMenu({ label = 'Download', children }: { label?: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <div className="mt-4">
      <button type="button" className="btn w-full justify-between" aria-expanded={open} aria-controls={id} onClick={() => setOpen((v) => !v)}>
        <span className="flex items-center"><Download size={16} aria-hidden className="mr-1.5" />{label}</span>
        {open ? <ChevronUp size={16} aria-hidden /> : <ChevronDown size={16} aria-hidden />}
      </button>
      <div id={id} hidden={!open} className="mt-1">{children}</div>
    </div>
  );
}
