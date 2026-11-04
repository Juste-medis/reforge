import { useCallback, useEffect, useMemo, useRef, useState } from "react";

// The outline editor: the built outline over the photo, with draggable handles. Dragging a handle moves it and
// eases its neighbours (linear in index between handles), so borders bend smoothly instead of spiking. Every
// release is an undo step; the report records the measured drag.
export interface ShapeEditorData {
  photoUrl: string;
  widthPx: number;
  heightPx: number;
  outlineMm: [number, number][];
  u: [number, number, number];
  v: [number, number, number];
  pxPerMm: number;
}

const MAX_HANDLES = 48;
const HISTORY_CAP = 50;

function toPx(p: [number, number], u: [number, number, number], v: [number, number, number]): [number, number] {
  return [u[0] + u[1] * p[0] + u[2] * p[1], v[0] + v[1] * p[0] + v[2] * p[1]];
}

export default function ShapeEditor({ data, onSubmit, busy }: {
  data: ShapeEditorData;
  onSubmit: (outlinePx: number[][], baselinePx: number[][]) => void;
  busy: boolean;
}) {
  const base = useMemo(() => data.outlineMm.map((p) => toPx(p, data.u, data.v)), [data]);
  const n = base.length;
  const handles = useMemo(() => {
    const step = Math.max(1, Math.ceil(n / MAX_HANDLES));
    const idx: number[] = [];
    for (let i = 0; i < n; i += step) idx.push(i);
    return idx;
  }, [n]);
  const hCount = handles.length;
  const [offsets, setOffsets] = useState<number[][]>(() => handles.map(() => [0, 0]));
  const [past, setPast] = useState<number[][][]>([]);
  const [future, setFuture] = useState<number[][][]>([]);
  const drag = useRef<{ k: number; before: number[][] } | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const shown = useMemo(() => {
    if (!hCount) return base;
    return base.map(([x, y], i) => {
      let k = 0;
      while (k + 1 < hCount && handles[k + 1] <= i) k++;
      const a = handles[k];
      const b = k + 1 < hCount ? handles[k + 1] : handles[0] + n;
      const t = b === a ? 0 : (i - a) / (b - a);
      const o0 = offsets[k];
      const o1 = offsets[(k + 1) % hCount];
      return [x + o0[0] + (o1[0] - o0[0]) * t, y + o0[1] + (o1[1] - o0[1]) * t] as [number, number];
    });
  }, [base, handles, hCount, n, offsets]);

  const moved = useMemo(() => {
    let maxPx = 0;
    for (let i = 0; i < n; i++) {
      maxPx = Math.max(maxPx, Math.hypot(shown[i][0] - base[i][0], shown[i][1] - base[i][1]));
    }
    return maxPx / data.pxPerMm;
  }, [shown, base, n, data.pxPerMm]);

  const svgPoint = useCallback((clientX: number, clientY: number): [number, number] => {
    const rect = svgRef.current!.getBoundingClientRect();
    return [
      (clientX - rect.left) * (data.widthPx / rect.width),
      (clientY - rect.top) * (data.heightPx / rect.height),
    ];
  }, [data.widthPx, data.heightPx]);

  function endDrag() {
    if (!drag.current) return;
    const { before } = drag.current;
    drag.current = null;
    setOffsets((cur) => {
      if (JSON.stringify(cur) === JSON.stringify(before)) return cur;
      setPast((p) => [...p.slice(-HISTORY_CAP + 1), before]);
      setFuture([]);
      return cur;
    });
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
        e.preventDefault();
        if (e.shiftKey) redo(); else undo();
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y") {
        e.preventDefault();
        redo();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  function undo() {
    setPast((p) => {
      if (!p.length) return p;
      const prev = p[p.length - 1];
      setOffsets((cur) => {
        setFuture((f) => [...f, cur]);
        return prev;
      });
      return p.slice(0, -1);
    });
  }

  function redo() {
    setFuture((f) => {
      if (!f.length) return f;
      const next = f[f.length - 1];
      setOffsets((cur) => {
        setPast((p) => [...p, cur]);
        return next;
      });
      return f.slice(0, -1);
    });
  }

  function reset() {
    setOffsets((cur) => {
      if (cur.every((o) => o[0] === 0 && o[1] === 0)) return cur;
      setPast((p) => [...p.slice(-HISTORY_CAP + 1), cur]);
      setFuture([]);
      return handles.map(() => [0, 0]);
    });
  }

  const round2 = (pts: [number, number][]): number[][] => pts.map(([x, y]) => [Math.round(x * 100) / 100, Math.round(y * 100) / 100]);
  const dirty = moved > 0.005;

  return (
    <div className="shape-editor">
      <div className="shape-toolbar" role="toolbar" aria-label="Outline editing">
        <button type="button" className="button button-secondary button-sm" onClick={undo} disabled={!past.length || busy}>
          Undo
        </button>
        <button type="button" className="button button-secondary button-sm" onClick={redo} disabled={!future.length || busy}>
          Redo
        </button>
        <button type="button" className="button button-secondary button-sm" onClick={reset} disabled={!dirty || busy}>
          Reset
        </button>
        <span className="shape-readout" aria-live="polite">
          {dirty ? `Border moved by up to ${moved.toFixed(2)} mm` : "Drag the white dots to pull the border"}
        </span>
      </div>
      <svg
        ref={svgRef}
        className="shape-canvas"
        viewBox={`0 0 ${data.widthPx} ${data.heightPx}`}
        onPointerMove={(e) => {
          if (!drag.current || busy) return;
          const { k } = drag.current;
          const [x, y] = svgPoint(e.clientX, e.clientY);
          const [bx, by] = base[handles[k]];
          const cx = Math.min(data.widthPx, Math.max(0, x));
          const cy = Math.min(data.heightPx, Math.max(0, y));
          setOffsets((cur) => {
            const next = cur.map((o) => [...o]);
            next[k] = [cx - bx, cy - by];
            return next;
          });
        }}
        onPointerUp={endDrag}
        onPointerLeave={endDrag}
      >
        <image href={data.photoUrl} x={0} y={0} width={data.widthPx} height={data.heightPx} />
        <polygon points={base.map(([x, y]) => `${x},${y}`).join(" ")} className="shape-baseline" />
        <polygon points={shown.map(([x, y]) => `${x},${y}`).join(" ")} className="shape-edited" />
        {handles.map((idx, k) => {
          const isMoved = offsets[k][0] !== 0 || offsets[k][1] !== 0;
          return (
            <circle
              key={idx}
              cx={shown[idx][0]}
              cy={shown[idx][1]}
              r={6}
              className={`shape-handle${isMoved ? " is-moved" : ""}`}
              onPointerDown={(e) => {
                if (busy) return;
                e.preventDefault();
                (e.target as Element).setPointerCapture?.(e.pointerId);
                drag.current = { k, before: offsets.map((o) => [...o]) };
              }}
            />
          );
        })}
      </svg>
      <div className="shape-submit">
        <button
          type="button"
          className="button button-primary"
          disabled={!dirty || busy}
          onClick={() => onSubmit(round2(shown), round2(base))}
        >
          {busy ? "Rebuilding…" : "Rebuild with my shape"}
        </button>
        <p className="muted small">The pipeline re-runs on the same photo with your border; the report records how far you pulled it.</p>
      </div>
    </div>
  );
}
