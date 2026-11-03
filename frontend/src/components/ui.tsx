import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { STATUS_COPY } from "../lib/copy";
import type { Status } from "../types";

/** An evidence chip: colour, line pattern and words, so it never relies on colour alone. */
export function Evidence({ status, long = false }: { status: Status | string; long?: boolean }) {
  const copy = STATUS_COPY[status] ?? { label: status, short: status, explain: "" };
  return (
    <span className={`evidence evidence-${status.toLowerCase()}`} title={copy.explain}>
      <span className="evidence-swatch" aria-hidden="true" />
      {long ? copy.label : copy.short}
    </span>
  );
}

export function EvidenceLegend({ compact = false }: { compact?: boolean }) {
  const order: Status[] = ["MEASURED", "OBSERVED", "INFERRED", "UNCERTAIN"];
  return (
    <ul className={`legend ${compact ? "legend-compact" : ""}`}>
      {order.map((s) => (
        <li key={s}>
          <span className={`legend-line legend-${s.toLowerCase()}`} aria-hidden="true" />
          <span>
            <strong>{STATUS_COPY[s].label}</strong>
            {!compact && <span className="legend-explain">{STATUS_COPY[s].explain}</span>}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** A small "?" that explains a term. Opens on hover, focus or tap; Escape closes it. */
export function InfoTip({ label, children }: { label: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    const onClick = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, [open]);
  return (
    <span className="infotip" ref={ref} onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button type="button" className="infotip-button" aria-label={label} aria-expanded={open} aria-describedby={open ? id : undefined}
              onClick={() => setOpen((v) => !v)} onFocus={() => setOpen(true)} onBlur={() => setOpen(false)}>
        ?
      </button>
      {open && (
        <span role="tooltip" id={id} className="infotip-bubble">
          {children}
        </span>
      )}
    </span>
  );
}

export function Tip({ title, children, tone = "neutral", icon }: { title?: string; children: ReactNode; tone?: "neutral" | "ember" | "warn" | "ok"; icon?: ReactNode }) {
  return (
    <div className={`tip tip-${tone}`}>
      <span className="tip-icon" aria-hidden="true">{icon ?? "i"}</span>
      <div>
        {title && <strong className="tip-title">{title}</strong>}
        <div className="tip-body">{children}</div>
      </div>
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return <span className="spinner" role={label ? "status" : undefined} aria-label={label} />;
}

/** Same framing for both images: drag the handle (or use the arrow keys) to compare. */
export function Compare({ before, after, beforeLabel, afterLabel }: { before: string; after: string; beforeLabel: string; afterLabel: string }) {
  const [pos, setPos] = useState(50);
  return (
    <div className="compare" style={{ ["--pos" as string]: `${pos}%` }}>
      <img src={after} alt={afterLabel} className="compare-img" draggable={false} />
      <img src={before} alt={beforeLabel} className="compare-img compare-top" draggable={false} />
      <span className="compare-tag compare-tag-left">{beforeLabel}</span>
      <span className="compare-tag compare-tag-right">{afterLabel}</span>
      <span className="compare-handle" aria-hidden="true" />
      <input type="range" min={0} max={100} value={pos} onChange={(e) => setPos(Number(e.target.value))}
             aria-label={`Compare: ${beforeLabel} and ${afterLabel}`} className="compare-range" />
    </div>
  );
}
