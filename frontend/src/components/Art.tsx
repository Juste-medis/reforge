import type { ReactElement } from "react";

// Original illustrations for Re-Forge. They explain how the product works; none of them is a result.
// The visual language is the product's own: solid lines are measured, dashed ember lines are rebuilt.

type ArtProps = { className?: string; title?: string };

const MARKER_BITS = ["1011", "0110", "1101", "0100"];

function Marker({ x, y, s, seed = 0 }: { x: number; y: number; s: number; seed?: number }) {
  const c = s / 6;
  const cells: ReactElement[] = [];
  MARKER_BITS.forEach((row, r) =>
    row.split("").forEach((bit, k) => {
      const on = (bit === "1") !== ((r + k + seed) % 3 === 0);
      if (on) cells.push(<rect key={`${r}-${k}`} x={x + c * (k + 1)} y={y + c * (r + 1)} width={c} height={c} fill="#fff" />);
    }),
  );
  return (
    <g>
      <rect x={x} y={y} width={s} height={s} rx={s * 0.06} fill="var(--ink)" />
      {cells}
    </g>
  );
}

export function Mark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" className="mark">
      <path d="M16 6H9a5 5 0 0 0-5 5v10a5 5 0 0 0 5 5h7" fill="none" stroke="var(--ink)" strokeWidth="2.6" strokeLinecap="round" />
      <path d="M16 6h7a5 5 0 0 1 5 5v10a5 5 0 0 1-5 5h-7" fill="none" stroke="var(--ember)" strokeWidth="2.6" strokeLinecap="round" strokeDasharray="3.2 2.6" />
      <circle cx="10.5" cy="16" r="2.4" fill="none" stroke="var(--ink)" strokeWidth="2.2" />
      <circle cx="21.5" cy="16" r="2.4" fill="none" stroke="var(--ember)" strokeWidth="2.2" strokeDasharray="2 1.6" />
      <path d="M16 3v26" stroke="var(--ink-3)" strokeWidth="1.2" strokeDasharray="1.6 1.8" />
    </svg>
  );
}

function Grid({ x, y, w, h, step = 10 }: { x: number; y: number; w: number; h: number; step?: number }) {
  const lines: ReactElement[] = [];
  for (let gx = x + step; gx < x + w; gx += step)
    lines.push(<line key={`v${gx}`} x1={gx} y1={y} x2={gx} y2={y + h} className={(gx - x) % (step * 5) === 0 ? "grid-major" : "grid-minor"} />);
  for (let gy = y + step; gy < y + h; gy += step)
    lines.push(<line key={`h${gy}`} x1={x} y1={gy} x2={x + w} y2={gy} className={(gy - y) % (step * 5) === 0 ? "grid-major" : "grid-minor"} />);
  return <g>{lines}</g>;
}

/** Hero: a broken bracket on the mat; the missing end is rebuilt as a mirror of the intact one. */
export function HeroArt({ className }: ArtProps) {
  // Bracket 300 × 104 units centred on the mirror axis at x = 300; the right end is broken off at x ≈ 372.
  const jag = "L372 150 L364 162 L376 176 L366 190 L378 204 L368 218 L380 232 L372 254";
  return (
    <svg className={`art hero-art ${className ?? ""}`} viewBox="0 0 600 420" role="img"
         aria-label="Illustration: a broken bracket on the calibration mat. The surviving outline is drawn solid; the missing end is rebuilt as a dashed mirror image of the intact end.">
      <defs>
        <pattern id="hatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width="8" height="8" fill="var(--ember-wash)" />
          <line x1="0" y1="0" x2="0" y2="8" stroke="var(--ember)" strokeWidth="2.2" opacity="0.55" />
        </pattern>
        <linearGradient id="part" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#3a3f47" />
          <stop offset="1" stopColor="#24272d" />
        </linearGradient>
        <filter id="soft" x="-10%" y="-10%" width="120%" height="130%">
          <feDropShadow dx="0" dy="10" stdDeviation="12" floodColor="#1d2430" floodOpacity="0.14" />
        </filter>
      </defs>
      <g filter="url(#soft)">
        <rect x="40" y="30" width="520" height="360" rx="18" fill="var(--paper-hi)" />
      </g>
      <Grid x={40} y={30} w={520} h={360} step={13} />
      <Marker x={62} y={52} s={34} />
      <Marker x={504} y={52} s={34} seed={1} />
      <Marker x={62} y={334} s={34} seed={2} />
      <Marker x={504} y={334} s={34} seed={3} />
      {/* the rebuilt end: mirrored from the intact left end */}
      <path className="rebuilt-fill" d="M372 150 L410 150 A26 26 0 0 1 436 176 L436 228 A26 26 0 0 1 410 254 L372 254 L380 232 L368 218 L378 204 L366 190 L376 176 L364 162 Z" fill="url(#hatch)" />
      {/* the surviving part */}
      <path d={`M190 150 L372 150 ${jag} L190 254 A26 26 0 0 1 164 228 L164 176 A26 26 0 0 1 190 150 Z`} fill="url(#part)" />
      <circle cx="206" cy="202" r="15" fill="var(--paper-hi)" />
      <circle cx="394" cy="202" r="15" fill="var(--paper-hi)" className="rebuilt-hole" />
      {/* evidence lines */}
      <path d={`M372 150 L190 150 A26 26 0 0 0 164 176 L164 228 A26 26 0 0 0 190 254 L372 254`} className="line-observed" />
      <circle cx="206" cy="202" r="15" className="line-observed" />
      <path d="M372 150 L410 150 A26 26 0 0 1 436 176 L436 228 A26 26 0 0 1 410 254 L372 254" className="line-rebuilt draw" />
      <circle cx="394" cy="202" r="15" className="line-rebuilt draw" />
      <line x1="300" y1="112" x2="300" y2="292" className="line-axis" />
      {/* dimension */}
      <g className="dim">
        <line x1="164" y1="122" x2="164" y2="138" />
        <line x1="436" y1="122" x2="436" y2="138" />
        <line x1="164" y1="130" x2="436" y2="130" markerStart="none" />
      </g>
      <g className="callout callout-observed" transform="translate(96 284)">
        <rect width="150" height="30" rx="15" />
        <circle cx="16" cy="15" r="4.5" />
        <text x="28" y="20">Measured from photo</text>
      </g>
      <g className="callout callout-rebuilt" transform="translate(372 284)">
        <rect width="150" height="30" rx="15" />
        <circle cx="16" cy="15" r="4.5" />
        <text x="28" y="20">Rebuilt by symmetry</text>
      </g>
    </svg>
  );
}

export function StepMatArt({ className }: ArtProps) {
  return (
    <svg className={`art ${className ?? ""}`} viewBox="0 0 220 150" aria-hidden="true">
      <rect x="40" y="12" width="140" height="126" rx="8" fill="var(--paper-hi)" className="art-card" />
      <Grid x={40} y={12} w={140} h={126} step={9} />
      <Marker x={50} y={22} s={16} />
      <Marker x={154} y={22} s={16} seed={1} />
      <Marker x={50} y={112} s={16} seed={2} />
      <Marker x={154} y={112} s={16} seed={3} />
      <line x1="76" y1="128" x2="144" y2="128" className="bar" />
      <line x1="76" y1="124" x2="76" y2="132" className="bar" />
      <line x1="144" y1="124" x2="144" y2="132" className="bar" />
      <g transform="translate(150 70)">
        <rect x="-26" y="-14" width="52" height="28" rx="14" className="badge" />
        <text x="0" y="5" textAnchor="middle" className="badge-text">100 %</text>
      </g>
    </svg>
  );
}

export function StepPhotoArt({ className }: ArtProps) {
  return (
    <svg className={`art ${className ?? ""}`} viewBox="0 0 220 150" aria-hidden="true">
      <rect x="30" y="118" width="160" height="12" rx="3" fill="var(--paper-hi)" className="art-card" />
      <rect x="92" y="110" width="36" height="8" rx="2" fill="#2d3137" />
      <rect x="66" y="20" width="88" height="14" rx="5" fill="var(--ink)" />
      <rect x="104" y="24" width="12" height="6" rx="3" fill="#59606b" />
      <path d="M110 36 L110 106" className="line-axis" />
      <path d="M78 38 L44 116 M142 38 L176 116" className="ray" />
      <g transform="translate(166 64)">
        <circle r="13" className="ok-dot" />
        <path d="M-5 0 l3.5 3.5 l6.5 -7" className="ok-tick" />
      </g>
    </svg>
  );
}

export function StepModelArt({ className }: ArtProps) {
  return (
    <svg className={`art ${className ?? ""}`} viewBox="0 0 220 150" aria-hidden="true">
      <g transform="translate(110 78)">
        <path d="M-78 -6 L6 -40 L78 -10 L-6 24 Z" className="iso-top" />
        <path d="M-78 -6 L-6 24 L-6 40 L-78 10 Z" className="iso-side" />
        <path d="M-6 24 L78 -10 L78 6 L-6 40 Z" className="iso-front" />
        <ellipse cx="-36" cy="-7" rx="11" ry="5.5" className="iso-hole" />
        <ellipse cx="38" cy="-9" rx="11" ry="5.5" className="iso-hole" />
        <path d="M6 -40 L78 -10" className="line-rebuilt" />
      </g>
      <g transform="translate(20 116)">
        <rect width="38" height="20" rx="6" className="file-badge" />
        <text x="19" y="14" textAnchor="middle" className="file-text">STL</text>
      </g>
      <g transform="translate(64 116)">
        <rect width="46" height="20" rx="6" className="file-badge" />
        <text x="23" y="14" textAnchor="middle" className="file-text">SCAD</text>
      </g>
    </svg>
  );
}

/** Capture tips: each tile shows the good practice. */
export function TipArt({ kind }: { kind: "above" | "flat" | "light" | "alone" }) {
  return (
    <svg className="art tip-art" viewBox="0 0 120 80" aria-hidden="true">
      {kind === "above" && (
        <>
          <rect x="22" y="64" width="76" height="6" rx="2" fill="var(--paper-hi)" className="art-card" />
          <rect x="40" y="12" width="40" height="8" rx="3" fill="var(--ink)" />
          <path d="M60 22 V60" className="line-axis" />
          <path d="M52 58 h16" className="line-observed" />
        </>
      )}
      {kind === "flat" && (
        <>
          <rect x="18" y="12" width="84" height="56" rx="5" fill="var(--paper-hi)" className="art-card" />
          <Marker x={24} y={18} s={11} />
          <Marker x={85} y={18} s={11} seed={1} />
          <Marker x={24} y={51} s={11} seed={2} />
          <Marker x={85} y={51} s={11} seed={3} />
          <text x="60" y="44" textAnchor="middle" className="tip-num">12</text>
        </>
      )}
      {kind === "light" && (
        <>
          <circle cx="60" cy="30" r="13" className="sun" />
          {[0, 45, 90, 135, 180, 225, 270, 315].map((a) => (
            <line key={a} x1={60 + 18 * Math.cos((a * Math.PI) / 180)} y1={30 + 18 * Math.sin((a * Math.PI) / 180)}
                  x2={60 + 24 * Math.cos((a * Math.PI) / 180)} y2={30 + 24 * Math.sin((a * Math.PI) / 180)} className="sun-ray" />
          ))}
          <rect x="22" y="62" width="76" height="8" rx="2" fill="var(--paper-hi)" className="art-card" />
        </>
      )}
      {kind === "alone" && (
        <>
          <rect x="18" y="12" width="84" height="56" rx="5" fill="var(--paper-hi)" className="art-card" />
          <rect x="44" y="30" width="32" height="20" rx="5" fill="#2d3137" />
          <circle cx="52" cy="40" r="3" fill="var(--paper-hi)" />
          <path d="M36 22 h48 v36 h-48 z" className="zone" />
        </>
      )}
    </svg>
  );
}

export function BarsArt() {
  // Portrait mat, as printed: the X bar runs along the top strip, the Y bar down the left strip.
  return (
    <svg className="art bars-art" viewBox="0 0 170 220" aria-hidden="true">
      <rect x="15" y="8" width="140" height="204" rx="8" fill="var(--paper-hi)" className="art-card" />
      <Marker x={22} y={15} s={14} />
      <Marker x={78} y={15} s={14} seed={1} />
      <Marker x={134} y={15} s={14} seed={2} />
      <Marker x={22} y={191} s={14} seed={3} />
      <Marker x={78} y={191} s={14} />
      <Marker x={134} y={191} s={14} seed={1} />
      <Marker x={22} y={77} s={14} seed={2} />
      <Marker x={22} y={129} s={14} seed={3} />
      <Marker x={134} y={77} s={14} />
      <Marker x={134} y={129} s={14} seed={1} />
      <g className="bar-hi">
        <line x1="50" y1="38" x2="120" y2="38" />
        <line x1="50" y1="34" x2="50" y2="42" />
        <line x1="120" y1="34" x2="120" y2="42" />
        <line x1="44" y1="76" x2="44" y2="146" />
        <line x1="40" y1="76" x2="48" y2="76" />
        <line x1="40" y1="146" x2="48" y2="146" />
      </g>
      <text x="85" y="56" textAnchor="middle" className="bar-label">X · 100 mm</text>
      <text x="56" y="114" className="bar-label">Y · 100 mm</text>
    </svg>
  );
}

export function EmptyArt() {
  return (
    <svg className="art empty-art" viewBox="0 0 200 120" aria-hidden="true">
      <path d="M100 30 H62 a16 16 0 0 0 -16 16 v28 a16 16 0 0 0 16 16 H100" className="line-observed faint" />
      <path d="M100 30 H138 a16 16 0 0 1 16 16 v28 a16 16 0 0 1 -16 16 H100" className="line-rebuilt" />
      <circle cx="70" cy="60" r="8" className="line-observed faint" />
      <circle cx="130" cy="60" r="8" className="line-rebuilt" />
      <line x1="100" y1="18" x2="100" y2="102" className="line-axis" />
    </svg>
  );
}
