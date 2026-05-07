// app/components/BottomSheet.tsx
// Mobile-only slide-up panel. Rendered inside AppShell when sheetOpen=true.
// Tap outside or press ✕ to close.

'use client';

import type { ReactNode } from 'react';

interface BottomSheetProps {
  onClose: () => void;
  children: ReactNode;
}

export default function BottomSheet({ onClose, children }: BottomSheetProps) {
  return (
    <>
      {/* Backdrop */}
      <div
        className="lg:hidden fixed inset-0 bg-black/40 z-40"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Sheet */}
      <div className="lg:hidden fixed bottom-0 left-0 right-0 bg-white rounded-t-2xl z-50 max-h-[80vh] flex flex-col shadow-xl">
        {/* Handle + header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 flex-shrink-0">
          {/* Drag handle visual */}
          <div className="w-10 h-1 bg-gray-200 rounded-full absolute left-1/2 -translate-x-1/2 top-2" />
          <h2 className="text-sm font-semibold text-gray-900 mt-1">Layers</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-700 text-lg leading-none p-1 -mr-1"
            aria-label="Close layer panel"
          >
            ✕
          </button>
        </div>

        {/* Scrollable content */}
        <div className="overflow-y-auto flex-1">
          {children}
        </div>
      </div>
    </>
  );
}
