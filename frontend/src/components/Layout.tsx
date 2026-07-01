import type { ReactNode } from 'react';

interface LayoutProps {
  children: ReactNode;
}

/**
 * App shell: Header / content / Footer stacked vertically (TEMPLATE_NOTES.md).
 * Mobile-first; the content column is centered and width-capped.
 */
export function Layout({ children }: LayoutProps) {
  return (
    <div className="flex min-h-full flex-col bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800">
        <div className="mx-auto flex w-full max-w-md items-center gap-2 px-4 py-3">
          <span className="text-xl" aria-hidden>
            ✊
          </span>
          <h1 className="text-lg font-semibold tracking-tight">じゃんけんルーム</h1>
        </div>
      </header>

      <main className="mx-auto w-full max-w-md flex-1 px-4 py-6">{children}</main>

      <footer className="border-t border-slate-800">
        <div className="mx-auto w-full max-w-md px-4 py-3 text-center text-xs text-slate-500">
          リアルタイムじゃんけん · MVP
        </div>
      </footer>
    </div>
  );
}
