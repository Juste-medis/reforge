import { useEffect, useState, type FormEvent } from "react";
import { ApiError, getHealth, runJob } from "./api";
import { StlViewer } from "./StlViewer";
import type { ApiErrorBody, Check, Health, JobResponse } from "./types";

const fmt = (value: number | null | undefined, digits = 2) =>
  value === null || value === undefined || Number.isNaN(value) ? "—" : value.toFixed(digits);

function StatusChip({ status }: { status: string }) {
  return <span className={`chip chip-${status.toLowerCase()}`}>{status}</span>;
}

function CheckRow({ check }: { check: Check }) {
  const state = check.passed ? "pass" : check.severity === "warning" ? "warn" : "fail";
  return (
    <li className={`check check-${state}`}>
      <span className="check-mark" aria-hidden>{state === "pass" ? "✓" : state === "warn" ? "!" : "✕"}</span>
      <span className="check-name">{check.name.replaceAll("_", " ")}</span>
      <span className="check-detail">{check.detail}</span>
    </li>
  );
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [thickness, setThickness] = useState("");
  const [barX, setBarX] = useState("");
  const [barY, setBarY] = useState("");
  const [segmenter, setSegmenter] = useState<"sam" | "classical">("sam");
  const [prompt, setPrompt] = useState("plastic part");
  const [running, setRunning] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [result, setResult] = useState<JobResponse | null>(null);
  const [error, setError] = useState<ApiErrorBody | null>(null);

  useEffect(() => {
    getHealth()
      .then((h) => {
        setHealth(h);
        if (!h.meta_key_configured) setSegmenter("classical");
      })
      .catch(() => setHealth(null));
  }, []);

  useEffect(() => {
    if (!file) return setPreview(null);
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  useEffect(() => {
    if (!running) return;
    const started = performance.now();
    const id = window.setInterval(() => setElapsed((performance.now() - started) / 1000), 100);
    return () => window.clearInterval(id);
  }, [running]);

  const samAvailable = health?.meta_key_configured ?? false;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    const form = new FormData();
    form.append("photo", file);
    form.append("thickness_mm", thickness);
    if (barX) form.append("bar_x_mm", barX);
    if (barY) form.append("bar_y_mm", barY);
    form.append("segmenter", segmenter);
    form.append("prompt", prompt);
    setRunning(true);
    setElapsed(0);
    setError(null);
    setResult(null);
    try {
      setResult(await runJob(form));
    } catch (err) {
      setError(err instanceof ApiError ? err.body : { code: "NETWORK", message: String(err), hint: "Is the API running?" });
    } finally {
      setRunning(false);
    }
  }

  const report = result?.report;
  const timingTotal = report ? Object.values(report.timings_s).reduce((a, b) => a + b, 0) : 0;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden>◆</span>
          <div>
            <h1>RE-FORGE AI</h1>
            <p>Photo of a broken part → measured, printable model</p>
          </div>
        </div>
        <div className="health">
          {health === null ? (
            <span className="chip chip-uncertain">API offline</span>
          ) : samAvailable ? (
            <span className="chip chip-measured">{health.segmentation_model} ready</span>
          ) : (
            <span className="chip chip-inferred">No Meta API key: classical fallback only</span>
          )}
          <span className="milestone">M1 · observed geometry</span>
        </div>
      </header>

      <div className="layout">
        <aside className="sidebar">
          <section className="step">
            <h2><span className="step-n">1</span>Print the mat</h2>
            <p>Print at <strong>100 % / actual size</strong>, tape it flat, and caliper-check both 100 mm bars.</p>
            <div className="links">
              <a href="/api/mat/A4.pdf">A4 mat (PDF)</a>
              <a href="/api/mat/Letter.pdf">Letter mat (PDF)</a>
            </div>
          </section>

          <section className="step">
            <h2><span className="step-n">2</span>Photograph</h2>
            <ul className="tips">
              <li>Part flat inside the corner marks, all 12 markers visible</li>
              <li>Phone roughly parallel, about 40 cm away, diffuse light, no flash</li>
            </ul>
          </section>

          <form className="step" onSubmit={submit}>
            <h2><span className="step-n">3</span>Measure &amp; run</h2>
            <label className="field">
              <span>Photo</span>
              <input type="file" accept="image/*" required onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            </label>
            {preview && <img className="preview" src={preview} alt="Selected photo" />}
            <label className="field">
              <span>Thickness (caliper, mm)</span>
              <input type="number" step="0.01" min="0.41" max="200" required value={thickness}
                     onChange={(e) => setThickness(e.target.value)} placeholder="e.g. 3.02" />
            </label>
            <div className="field-row">
              <label className="field">
                <span>Bar X (mm)</span>
                <input type="number" step="0.01" min="90" max="110" value={barX} onChange={(e) => setBarX(e.target.value)}
                       placeholder="100.00" />
              </label>
              <label className="field">
                <span>Bar Y (mm)</span>
                <input type="number" step="0.01" min="90" max="110" value={barY} onChange={(e) => setBarY(e.target.value)}
                       placeholder="100.00" />
              </label>
            </div>
            <fieldset className="field segmenter">
              <legend>Segmentation</legend>
              <label className={!samAvailable ? "disabled" : undefined}>
                <input type="radio" name="seg" value="sam" disabled={!samAvailable} checked={segmenter === "sam"}
                       onChange={() => setSegmenter("sam")} />
                SAM 3.1 (Meta Model API)
              </label>
              <label>
                <input type="radio" name="seg" value="classical" checked={segmenter === "classical"}
                       onChange={() => setSegmenter("classical")} />
                Classical fallback (not AI)
              </label>
            </fieldset>
            {segmenter === "sam" && (
              <label className="field">
                <span>What is it? (SAM noun phrase)</span>
                <input type="text" maxLength={60} value={prompt} onChange={(e) => setPrompt(e.target.value)} />
              </label>
            )}
            <button className="primary" type="submit" disabled={running || !file || !thickness}>
              {running ? `Running… ${elapsed.toFixed(1)} s` : "Measure & build STL"}
            </button>
          </form>
        </aside>

        <main className="workspace">
          {!report && !error && !running && (
            <div className="empty">
              <h2>No part yet</h2>
              <p>Upload a photo of the part on the mat. The result shows the calibrated measurements, the detected
                outline and holes, the validated 3D model, and where every number came from.</p>
            </div>
          )}
          {running && <div className="empty"><h2>Running the pipeline</h2><p>{elapsed.toFixed(1)} s elapsed</p></div>}
          {error && (
            <div className="error" role="alert">
              <strong>{error.code}</strong>
              <p>{error.message}</p>
              {error.hint && <p className="hint">{error.hint}</p>}
            </div>
          )}

          {report && result && (
            <>
              <section className="summary">
                <div className={`verdict ${report.validation.valid ? "ok" : "bad"}`}>
                  {report.validation.valid ? "Valid, watertight model" : "Model failed validation"}
                </div>
                <div className="metric"><span>Overall</span><strong>{report.part.overall_mm.map((v) => fmt(v, 2)).join(" × ")} mm</strong></div>
                <div className="metric"><span>Holes</span><strong>{report.part.holes.length}</strong></div>
                <div className="metric"><span>Pipeline</span><strong>{fmt(timingTotal, 2)} s</strong></div>
                <div className="downloads">
                  <a className="primary" href={result.files["model.stl"]}>Download STL</a>
                  <a href={result.files["model.scad"]}>OpenSCAD</a>
                  <a href={result.files["report.json"]}>Report</a>
                </div>
              </section>

              <div className="grid">
                <section className="card span-2">
                  <h3>3D model</h3>
                  <StlViewer url={result.files["model.stl"]} />
                </section>

                <section className="card">
                  <h3>Detected outline</h3>
                  <img className="overlay" src={result.files["overlay.png"]} alt="Rectified photo with the measured outline and holes" />
                  <p className="caption">Rectified top view. Blue: refined outline. Green: through-holes.</p>
                </section>

                <section className="card">
                  <h3>Measurements</h3>
                  <table>
                    <thead><tr><th>Feature</th><th>Value</th><th>Status</th></tr></thead>
                    <tbody>
                      <tr><td>Thickness</td><td className="num">{fmt(report.part.overall_mm[2], 2)} mm</td><td><StatusChip status="MEASURED" /></td></tr>
                      <tr><td>Length × width</td><td className="num">{fmt(report.part.overall_mm[0], 2)} × {fmt(report.part.overall_mm[1], 2)} mm</td><td><StatusChip status="OBSERVED" /></td></tr>
                      {report.part.holes.map((h) => (
                        <tr key={h.id}>
                          <td>{h.id} {h.kind === "circle" ? "Ø" : "(traced)"}</td>
                          <td className="num">{h.kind === "circle" ? `${fmt(h.diameter_mm, 3)} mm @ (${fmt(h.center_mm?.[0], 2)}, ${fmt(h.center_mm?.[1], 2)})` : h.source}</td>
                          <td><StatusChip status="OBSERVED" /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {report.part.excluded_candidates.map((c) => (
                    <p className="note" key={c.hole}><StatusChip status="UNCERTAIN" /> {c.hole}: {c.reason}</p>
                  ))}
                  <p className="caption">Uncertainty intervals (±) arrive with the Confidence Engine (M2).</p>
                </section>

                <section className="card">
                  <h3>Calibration</h3>
                  <dl className="kv">
                    <dt>Markers</dt><dd>{report.calibration.markers} / 12 ({report.calibration.page})</dd>
                    <dt>Resolution</dt><dd>{fmt(report.calibration.px_per_mm, 1)} px/mm</dd>
                    <dt>Fit residual</dt><dd>{fmt(report.calibration.fit_rms_mm, 3)} mm RMS</dd>
                    <dt>Leave-one-out</dt><dd>{fmt(report.calibration.loo_rms_mm, 3)} mm RMS</dd>
                    <dt>Tilt indicator</dt><dd>{fmt(report.calibration.perspective_ratio, 2)}×</dd>
                    <dt>Print scale</dt><dd>{report.calibration.scale_correction.map((s) => fmt(s, 4)).join(" / ")}</dd>
                  </dl>
                  {[...report.calibration.warnings, ...report.refinement.warnings].map((w) => (
                    <p className="note warn" key={w.code}><strong>{w.code}</strong> {w.message}</p>
                  ))}
                </section>

                <section className="card">
                  <h3>Segmentation</h3>
                  <dl className="kv">
                    <dt>Method</dt>
                    <dd>{report.segmentation.method} <span className={`chip ${report.segmentation.is_ai ? "chip-observed" : "chip-inferred"}`}>{report.segmentation.is_ai ? "AI" : "not AI"}</span></dd>
                    <dt>Confidence</dt><dd>{fmt(report.segmentation.confidence, 3)}</dd>
                    <dt>Latency</dt><dd>{fmt(report.segmentation.latency_s, 2)} s</dd>
                    <dt>API cost</dt><dd>${fmt(report.segmentation.cost_usd, 4)}</dd>
                    <dt>Edge refinement</dt><dd>{report.refinement.refined ? `ΔE ${fmt(report.refinement.contrast_delta_e, 0)}, moved ≤ ${fmt(report.refinement.coarse_shift_max_mm, 2)} mm` : "not refined (low contrast)"}</dd>
                  </dl>
                </section>

                <section className="card">
                  <h3>Validation</h3>
                  <ul className="checks">{report.validation.checks.map((c) => <CheckRow key={c.name} check={c} />)}</ul>
                </section>

                <section className="card">
                  <h3>Timings</h3>
                  <dl className="kv">
                    {Object.entries(report.timings_s).map(([k, v]) => [<dt key={`${k}-k`}>{k.replaceAll("_", " ")}</dt>, <dd key={`${k}-v`}>{fmt(v, 3)} s</dd>])}
                  </dl>
                </section>
              </div>
              <p className="disclaimer">{report.disclaimer}</p>
            </>
          )}
        </main>
      </div>
    </div>
  );
}
