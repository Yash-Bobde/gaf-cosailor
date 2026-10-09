'use client';

/**
 * Small form primitives for the run panel: a labelled field wrapper and an
 * accessible segmented control (buttons with aria-pressed, 40px+ targets).
 */
import React from 'react';

interface FieldProps {
  label: string;
  htmlFor?: string;
  /** Span both mobile columns (segmented controls need the width). */
  wide?: boolean;
  children: React.ReactNode;
}

export function Field({ label, htmlFor, wide, children }: FieldProps) {
  return (
    <div className={`flex flex-col gap-1.5 ${wide ? 'col-span-2 lg:col-span-1' : ''}`}>
      <label htmlFor={htmlFor} className="text-xs font-semibold uppercase tracking-wider text-ink-soft">
        {label}
      </label>
      {children}
    </div>
  );
}

interface SegmentedProps<T extends string | number> {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
  disabled?: boolean;
}

export function Segmented<T extends string | number>({ label, value, options, onChange, disabled }: SegmentedProps<T>) {
  return (
    <div role="group" aria-label={label} className="flex rounded-lg border border-line-strong bg-card p-0.5">
      {options.map((opt) => {
        const active = opt.value === value;
        return (
          <button
            key={String(opt.value)}
            type="button"
            aria-pressed={active}
            disabled={disabled}
            onClick={() => onChange(opt.value)}
            className={`h-10 flex-1 cursor-pointer whitespace-nowrap rounded-md px-3 text-sm transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-50 ${
              active ? 'bg-ink font-semibold text-paper' : 'text-ink-soft hover:text-ink'
            }`}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
