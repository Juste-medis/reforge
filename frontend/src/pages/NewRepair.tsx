import { useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";
import { ApiError } from "../api";
import { BarsArt, TipArt } from "../components/Art";
import { InfoTip, Spinner, Tip } from "../components/ui";
import { errorCopy } from "../lib/copy";
import { defaultAi, launch } from "../lib/launch";
import type { ApiErrorBody, Health } from "../types";

const ACCEPTED = ["image/jpeg", "image/png", "image/webp"];
const MAX_BYTES = 20 * 1024 * 1024;
const MIN_MEGAPIXELS = 4;

interface PhotoCheck {
  level: "ok" | "warn" | "bad";
  text: string;
}

function checkFile(file: File): PhotoCheck[] {
  const checks: PhotoCheck[] = [];
  const heic = /\.(heic|heif)$/i.test(file.name) || /heic|heif/i.test(file.type);
  if (heic) {
    checks.push({ level: "bad", text: "HEIC photos aren't read yet. On iPhone choose Settings → Camera → Formats → Most Compatible, or export as JPEG." });
  } else if (file.type && !ACCEPTED.includes(file.type)) {
    checks.push({ level: "bad", text: "Use a JPEG, PNG or WebP photo." });
  }
  if (file.size > MAX_BYTES) checks.push({ level: "bad", text: "Larger than 20 MB." });
  return checks;
}

const TIPS: { kind: "above" | "flat" | "light" | "alone"; title: string; avoid: string }[] = [
  { kind: "above", title: "Straight from above", avoid: "Hold the phone parallel to the mat; the 2× lens and a step back help." },
  { kind: "flat", title: "All 12 markers, mat flat", avoid: "Don't cut markers off, and don't let a corner curl." },
  { kind: "light", title: "Soft, even light", avoid: "No flash, no harsh sun or glare on the paper." },
  { kind: "alone", title: "One part, in the middle", avoid: "Keep it away from the black squares and the mat's edge." },
];

export function NewRepair({ health }: { health: Health | null | undefined }) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [checks, setChecks] = useState<PhotoCheck[]>([]);
  const [dragging, setDragging] = useState(false);
  const [thickness, setThickness] = useState("");
  const [barX, setBarX] = useState("");
  const [barY, setBarY] = useState("");
  const ai = defaultAi(health);
  const [segmenter, setSegmenter] = useState<"sam" | "classical">(ai.segmenter);
  const [interpreter, setInterpreter] = useState<"spark" | "geometric">(ai.interpreter);
  const [prompt, setPrompt] = useState("plastic part");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiErrorBody | null>(null);
  const [touched, setTouched] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const aiAvailable = !!health?.meta_key_configured;

  useEffect(() => {
    setSegmenter(ai.segmenter);
    setInterpreter(ai.interpreter);
  }, [ai.segmenter, ai.interpreter]);

  useEffect(() => {
    if (!file) {
      setPreview(null);
      setChecks([]);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    const base = checkFile(file);
    setChecks(base);
    if (base.some((c) => c.level === "bad")) return;
    const img = new Image();
    img.onload = () => {
      const mp = (img.naturalWidth * img.naturalHeight) / 1e6;
      const format: PhotoCheck = file.type === "image/jpeg"
        ? { level: "ok", text: "JPEG photo: if it's the phone's original file, its lens information helps the height correction." }
        : { level: "ok", text: "Image opened. A phone's original JPEG is best: it carries the lens information." };
      setChecks([...base, format, mp < MIN_MEGAPIXELS
        ? { level: "warn", text: `Only ${mp.toFixed(1)} megapixels: the mat may be too small to measure precisely. Use the camera's full resolution.` }
        : { level: "ok", text: `${img.naturalWidth} × ${img.naturalHeight} px: enough detail.` }]);
    };
    img.onerror = () => setChecks([...base, { level: "bad", text: "This file can't be opened as an image." }]);
    img.src = url;
    // the object URL stays alive for the progress view; it is released when the tab closes
  }, [file]);

  const t = Number(thickness);
  const thicknessError = thickness === "" ? "Enter the part's thickness." : !(t > 0.4 && t <= 200) ? "Between 0.5 and 200 mm." : null;
  const barError = (v: string) => (v === "" ? null : !(Number(v) >= 90 && Number(v) <= 110) ? "A bar reads about 100 mm. Leave empty if not measured." : null);
  const photoBad = checks.some((c) => c.level === "bad");
  const canSubmit = !!file && !photoBad && !thicknessError && !barError(barX) && !barError(barY) && !busy;

  function pick(files: FileList | null) {
    const f = files?.[0];
    if (f) {
      setFile(f);
      setError(null);
    }
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    pick(e.dataTransfer.files);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (!canSubmit || !file) return;
    setBusy(true);
    setError(null);
    try {
      await launch({ photo: file }, {
        thickness_mm: t,
        bar_x_mm: barX ? Number(barX) : undefined,
        bar_y_mm: barY ? Number(barY) : undefined,
        segmenter, interpreter, prompt: prompt.trim() || "plastic part",
      }, file.name.replace(/\.[^.]+$/, "") || "My part", preview ?? undefined);
    } catch (err) {
      setError(err instanceof ApiError ? err.body : { code: "NETWORK", message: String(err), hint: null });
      setBusy(false);
    }
  }

  const copy = error ? errorCopy(error.code) : null;

  return (
    <div className="page new-repair">
      <header className="page-head">
        <p className="eyebrow">New repair</p>
        <h1>Your broken part, on the mat.</h1>
        <p className="lead">One photo and one caliper reading. Everything else is measured for you.</p>
      </header>

      <form className="new-grid" onSubmit={submit} noValidate>
        <div className="new-main">
          <section className="panel" aria-labelledby="photo-title">
            <div className="panel-head">
              <span className="panel-num">1</span>
              <h2 id="photo-title">Your photo</h2>
            </div>
            <label className={`dropzone ${dragging ? "is-dragging" : ""} ${file ? "has-file" : ""}`}
                   onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                   onDragLeave={() => setDragging(false)} onDrop={onDrop}>
              <input ref={input} type="file" accept="image/jpeg,image/png,image/webp,.heic,.heif" className="visually-hidden"
                     onChange={(e) => pick(e.target.files)} aria-describedby="photo-help" />
              {preview && !photoBad ? (
                <img src={preview} alt="The photo you chose" className="dropzone-preview" />
              ) : (
                <span className="dropzone-empty">
                  <span className="dropzone-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24" width="28" height="28"><path d="M12 16V4m0 0-4.5 4.5M12 4l4.5 4.5M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>
                  </span>
                  <strong>Drop your photo here, or choose one</strong>
                  <span id="photo-help" className="muted">JPEG or PNG, straight from the phone · up to 20 MB</span>
                </span>
              )}
            </label>
            {file && (
              <div className="file-row">
                <span className="file-name" title={file.name}>{file.name}</span>
                <button type="button" className="button button-ghost button-sm" onClick={() => input.current?.click()}>Choose another</button>
              </div>
            )}
            {checks.length > 0 && (
              <ul className="checks-list" aria-live="polite">
                {checks.map((c, i) => <li key={i} className={`check-${c.level}`}>{c.text}</li>)}
              </ul>
            )}
            {touched && !file && <p className="field-error" role="alert">Choose a photo of the part on the mat.</p>}
            <p className="muted small">
              No mat yet? Print it at 100 %: <a href="/api/mat/A4.pdf" download>A4</a> · <a href="/api/mat/Letter.pdf" download>Letter</a>.
              Your photo is re-encoded without its location data before anything else happens.
            </p>
          </section>

          <section className="panel" aria-labelledby="thick-title">
            <div className="panel-head">
              <span className="panel-num">2</span>
              <h2 id="thick-title">Thickness</h2>
              <InfoTip label="Why thickness?">
                A photo from above can't see how thick the part is. Measure it once with a caliper, on a flat area.
              </InfoTip>
            </div>
            <label className="field">
              <span className="field-label">Thickness, from a caliper</span>
              <span className="input-unit">
                <input type="number" inputMode="decimal" step="0.01" min="0.5" max="200" value={thickness}
                       onChange={(e) => setThickness(e.target.value)} onBlur={() => setTouched(true)}
                       placeholder="e.g. 3.00" aria-invalid={touched && !!thicknessError} aria-describedby="thick-err" />
                <span aria-hidden="true">mm</span>
              </span>
            </label>
            {touched && thicknessError && <p className="field-error" id="thick-err" role="alert">{thicknessError}</p>}
          </section>

          <details className="panel disclosure">
            <summary>
              <span className="panel-num panel-num-soft">+</span>
              <span>
                <strong>Improve accuracy: check the print scale</strong>
                <span className="muted small block">Optional, once per printed mat. Recommended for a tight fit.</span>
              </span>
            </summary>
            <div className="disclosure-body bars">
              <BarsArt />
              <div>
                <p>
                  Printers rarely print exactly at 100 %. Measure the two 100 mm bars printed on the mat with your
                  caliper, end tick to end tick. Without this, sizes carry an assumed ±0.5 % scale uncertainty.
                </p>
                <div className="field-row">
                  <label className="field">
                    <span className="field-label">Bar X: the horizontal bar, "100 mm (X)"</span>
                    <span className="input-unit">
                      <input type="number" inputMode="decimal" step="0.01" value={barX} onChange={(e) => setBarX(e.target.value)} placeholder="100.00" aria-invalid={!!barError(barX)} />
                      <span aria-hidden="true">mm</span>
                    </span>
                  </label>
                  <label className="field">
                    <span className="field-label">Bar Y: the vertical bar on the left</span>
                    <span className="input-unit">
                      <input type="number" inputMode="decimal" step="0.01" value={barY} onChange={(e) => setBarY(e.target.value)} placeholder="100.00" aria-invalid={!!barError(barY)} />
                      <span aria-hidden="true">mm</span>
                    </span>
                  </label>
                </div>
                {(barError(barX) || barError(barY)) && <p className="field-error" role="alert">{barError(barX) ?? barError(barY)}</p>}
              </div>
            </div>
          </details>

          <details className="panel disclosure">
            <summary>
              <span className="panel-num panel-num-soft">+</span>
              <span>
                <strong>Advanced options</strong>
                <span className="muted small block">Choose where AI is used. The defaults are best for most parts.</span>
              </span>
            </summary>
            <div className="disclosure-body">
              <fieldset className="choice">
                <legend>Find the part</legend>
                <label className={!aiAvailable ? "is-disabled" : undefined}>
                  <input type="radio" name="seg" checked={segmenter === "sam"} disabled={!aiAvailable} onChange={() => setSegmenter("sam")} />
                  <span><strong>With AI</strong> <span className="muted">Meta SAM 3.1 segments the part</span></span>
                </label>
                <label>
                  <input type="radio" name="seg" checked={segmenter === "classical"} onChange={() => setSegmenter("classical")} />
                  <span><strong>Without AI</strong> <span className="muted">colour contrast; can catch shadows</span></span>
                </label>
              </fieldset>
              <fieldset className="choice">
                <legend>Read the damage</legend>
                <label className={!aiAvailable ? "is-disabled" : undefined}>
                  <input type="radio" name="int" checked={interpreter === "spark"} disabled={!aiAvailable} onChange={() => setInterpreter("spark")} />
                  <span><strong>With AI</strong> <span className="muted">Meta Muse Spark names the part and its broken edges; geometry checks it</span></span>
                </label>
                <label>
                  <input type="radio" name="int" checked={interpreter === "geometric"} onChange={() => setInterpreter("geometric")} />
                  <span><strong>Without AI</strong> <span className="muted">a fixed geometric rule</span></span>
                </label>
              </fieldset>
              {segmenter === "sam" && (
                <label className="field">
                  <span className="field-label">What is the part? <span className="muted">(a short phrase, used only if needed)</span></span>
                  <input type="text" maxLength={60} value={prompt} onChange={(e) => setPrompt(e.target.value)} />
                </label>
              )}
              {!aiAvailable && health !== undefined && (
                <p className="muted small">This server has no Meta Model API key, so both steps run without AI.</p>
              )}
            </div>
          </details>
        </div>

        <aside className="new-side" aria-label="Photo guide">
          <div className="panel guide">
            <h2 className="guide-title">A good photo in four checks</h2>
            <ul className="guide-tips">
              {TIPS.map((tip) => (
                <li key={tip.kind}>
                  <TipArt kind={tip.kind} />
                  <div>
                    <strong>{tip.title}</strong>
                    <span>{tip.avoid}</span>
                  </div>
                </li>
              ))}
            </ul>
          </div>
          <Tip title="Why the mat and a top view?">
            The mat's markers are the ruler: they turn pixels into true millimetres. A view from above keeps the outline
            undistorted; Re-Forge still corrects the small tilt and the part's own height.
          </Tip>
        </aside>

        <div className="submit-bar">
          {error && copy && (
            <div className="alert alert-bad" role="alert">
              <strong>{copy.title}</strong>
              <span>{error.message}</span>
            </div>
          )}
          {touched && !canSubmit && !busy && (
            <p className="field-error submit-error" role="alert">
              {!file ? "Choose a photo first." : photoBad ? "This photo can't be used: see the check under it." : "Check the values marked above."}
            </p>
          )}
          <button type="submit" className="button button-primary button-lg" disabled={busy}>
            {busy ? <><Spinner /> Uploading…</> : "Analyse my part"}
          </button>
          <p className="muted small">The analysis runs on the server: about half a minute with AI, a few seconds without.</p>
        </div>
      </form>
    </div>
  );
}
