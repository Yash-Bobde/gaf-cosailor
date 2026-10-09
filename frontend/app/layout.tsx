import type { Metadata, Viewport } from 'next';
import localFont from 'next/font/local';
import './globals.css';

// Fonts are bundled from app/fonts (latin subsets of the SIL OFL-licensed Google
// Fonts families), so dev, build and the demo never depend on fonts.googleapis.com.
// Each file is a variable font, so one file covers every weight used.
const newsreader = localFont({
  src: [
    { path: './fonts/newsreader-latin.woff2', weight: '500 600', style: 'normal' },
    { path: './fonts/newsreader-italic-latin.woff2', weight: '500 600', style: 'italic' },
  ],
  variable: '--font-newsreader',
  display: 'swap',
  fallback: ['Georgia', 'Times New Roman', 'serif'],
});

const jakarta = localFont({
  src: './fonts/plus-jakarta-sans-latin.woff2',
  weight: '400 700',
  variable: '--font-jakarta',
  display: 'swap',
  fallback: ['system-ui', 'Segoe UI', 'Arial', 'sans-serif'],
});

const jetbrainsMono = localFont({
  src: './fonts/jetbrains-mono-latin.woff2',
  weight: '400 500',
  variable: '--font-jetbrains',
  display: 'swap',
  fallback: ['ui-monospace', 'Consolas', 'monospace'],
});

export const metadata: Metadata = {
  title: 'Cosailor Insights',
  description: 'A ranked call sheet of GAF roofing contractors for distributor sales reps',
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#f6f4ef',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body
        className={`${newsreader.variable} ${jakarta.variable} ${jetbrainsMono.variable} min-h-screen antialiased`}
      >
        {children}
        <footer className="mx-auto max-w-6xl px-4 pb-8 pt-4 text-center text-xs text-ink-faint sm:px-6">
          Built by{' '}
          <a
            href="https://github.com/Yash-Bobde"
            target="_blank"
            rel="noopener noreferrer"
            className="underline decoration-line-strong underline-offset-4 hover:text-ink"
          >
            Yash
          </a>
        </footer>
      </body>
    </html>
  );
}
