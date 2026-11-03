import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, getJob, modelUrl } from "../api";
import { EmptyArt } from "../components/Art";
import type { SpecLines } from "../components/StlViewer";
import { Compare, Evidence, InfoTip, Spinner, Tip } from "../components/ui";
import { errorCopy, hasCopy, STAGE_COPY, WARNING_COPY } from "../lib/copy";
import { fmt, pm, seconds, sentence } from "../lib/format";
import { update } from "../lib/history";
import { defaultAi, launch, previewFor } from "../lib/launch";
import { href } from "../lib/route";
import type { ApiErrorBody, Dimension, Files, Health, JobStatus, Report, Sample } from "../types";
import { Advanced } from "./Advanced";

const StlViewer = lazy(() => import("../components/StlViewer"));
const POLL_MS = 700;

// ---------------------------------------------------------------------------------------------------------------
// Processing: the pipeline's real stage events, with their measured durations.

function Processing({ status, health }: { status: JobStatus; health: Health | null | undefined }) {
  const req = status.request;
  const ai = { segment: req.segmenter === "sam", interpret: req.interpreter === "spark" };
  const models = health ? { seg: health.segmentation_model, reason: health.reasoning_model } : undefined;
  const preview = previewFor(status.job_id) ?? req.sample_info?.thumb_url;
  const [tick, setTick] = useState(0);
  const base = useRef({ elapsed: status.elapsed_s ?? 0, at: performance.now() });
  useEffect(() => {
    base.current = { elapsed: status.elapsed_s ?? 0, at: performance.now() };
  }, [status.elapsed_s]);
  useEffect(() => {
    const id = window.setInterval(() => setTick((t) => t + 1), 200);
    return () => window.clearInterval(id);
  }, []);
  const elapsed = status.state === "queued" ? 0 : base.current.elapsed + (performance.now() - base.current.at) / 1000;
  const running = status.stages.find((s) => s.state === "running");
  void tick;
  return (
    <section className="processing" aria-live="polite">
      <div className="processing-media">
        {preview ? <img src={preview} alt="The photo being analysed" /> : <EmptyArt />}
        <span className="scan" aria-hidden="true" />
      </div>
      <div className="processing-body">
        <p className="eyebrow">{status.state === "queued" ? "Waiting for a free slot" : "Analysing your part"}</p>
        <h1>{running ? STAGE_COPY[running.id]?.label ?? running.id : status.state === "queued" ? "In the queue…" : "Starting…"}</h1>
        <p className="muted">{running ? STAGE_COPY[running.id]?.detail(ai) : "Your photo is uploaded."}</p>
        <ol className="stages">
          {status.stages.map((s) => {
            const copy = STAGE_COPY[s.id];
            const model = copy?.model?.(ai, models);
            return (
              <li key={s.id} className={`stage stage-${s.state}`}>
                <span className="stage-mark" aria-hidden="true">
                  {s.state === "done" ? "✓" : s.state === "running" ? <Spinner /> : ""}
                </span>
                <span className="stage-label">
                  {copy?.label ?? s.id}
                  {model && <span className="model-tag">{model}</span>}
                </span>
                <span className="stage-time">{s.state === "done" ? seconds(s.seconds) : ""}</span>
                <span className="visually-hidden">{s.state === "done" ? "done" : s.state === "running" ? "in progress" : "waiting"}</span>
              </li>
            );
          })}
        </ol>
        <p className="elapsed">{seconds(elapsed)} elapsed · times shown are measured on the server</p>
        <p className="muted small">You can leave this page: the analysis continues and stays in <a href={href({ name: "repairs" })}>My repairs</a>.</p>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------------------------------------------
// Failure: what happened, what to do, and the technical code underneath.

function Failure({ status, error, health }: { status?: JobStatus; error: ApiErrorBody; health: Health | null | undefined }) {
  const copy = errorCopy(error.code);
  const [busy, setBusy] = useState(false);
  const req = status?.request;
  async function rerunWithoutAi() {
    if (!status || !req?.thickness_mm) return;
    setBusy(true);
    try {
      await launch({ fromJob: status.job_id }, { thickness_mm: req.thickness_mm, bar_x_mm: req.bar_x_mm ?? undefined,
        bar_y_mm: req.bar_y_mm ?? undefined, segmenter: "classical", interpreter: "geometric", prompt: req.prompt ?? "plastic part" },
        `${req.sample_info?.title ?? "My part"} (no AI)`);
    } catch {
      setBusy(false);
    }
  }
  async function rerun() {
    if (!status || !req?.thickness_mm) return;
    setBusy(true);
    try {
      await launch({ fromJob: status.job_id }, { thickness_mm: req.thickness_mm, bar_x_mm: req.bar_x_mm ?? undefined,
        bar_y_mm: req.bar_y_mm ?? undefined, segmenter: req.segmenter ?? defaultAi(health).segmenter,
        interpreter: req.interpreter ?? defaultAi(health).interpreter, prompt: req.prompt ?? "plastic part" },
        req.sample_info?.title ?? "My part");
    } catch {
      setBusy(false);
    }
  }
  const canRerun = !!status && !!req?.thickness_mm && error.code !== "JOB_NOT_FOUND";
  const refused = error.code === "FAMILY_UNSUPPORTED" || error.code === "TRACE_PARTIAL";
  return (
    <section className={`failure ${refused ? "failure-refused" : ""}`} role="alert">
      <div className="failure-icon" aria-hidden="true">{refused ? "◇" : "!"}</div>
      <div className="failure-body">
        <p className="eyebrow">{refused ? "Not rebuilt, on purpose" : "The analysis stopped"}</p>
        <h1>{copy.title}</h1>
        <p className="failure-message">{error.message}</p>
        {error.hint && !hasCopy(error.code) && <p className="muted">{error.hint}</p>}
        <ul className="failure-tips">
          {copy.tips.map((t) => <li key={t}>{t}</li>)}
        </ul>
        <div className="actions">
          <a className="button button-primary" href={href({ name: "new" })}>{copy.reshoot ? "Try another photo" : "New repair"}</a>
          {copy.offerNoAi && canRerun && (
            <button type="button" className="button button-secondary" onClick={rerunWithoutAi} disabled={busy}>
              {busy ? <><Spinner /> Starting…</> : "Run again without AI"}
            </button>
          )}
          {!copy.offerNoAi && canRerun && ["JOB_INTERRUPTED", "INTERNAL_ERROR", "SERVER_BUSY", "JOB_OUTDATED"].includes(error.code) && (
            <button type="button" className="button button-secondary" onClick={rerun} disabled={busy}>Run it again</button>
          )}
        </div>
        <details className="tech">
          <summary>Technical details</summary>
          <dl className="kv">
            <dt>Code</dt><dd><code>{error.code}</code></dd>
            {error.hint && hasCopy(error.code) && (<><dt>Server hint</dt><dd>{error.hint}</dd></>)}
            {status && (<><dt>Job</dt><dd><code>{status.job_id}</code></dd></>)}
          </dl>
        </details>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------------------------------------------
// Result: the simple view, with the technical details one click away.

interface Verdict {
  kind: "rebuilt" | "intact" | "not-rebuilt" | "invalid";
  title: string;
  text: string;
}

function clean(reason: string): string {
  return sentence(reason.replace(/^geometric rule:\s*/i, ""));
}

function verdictOf(report: Report): Verdict {
  const r = report.reconstruction;
  const a = r.interpretation.analysis;
  const rejected = r.verification.filter((n) => n.level === "rejected");
  if (!report.validation.valid) {
    return { kind: "invalid", title: "The model didn't pass its checks", text: `Failed: ${report.validation.errors.join(", ").replaceAll("_", " ")}. Don't print it.` };
  }
  if (r.completion) {
    return { kind: "rebuilt", title: "Rebuilt, ready for your check",
      text: `The missing piece, ${fmt(r.completion.added_area_mm2, 0)} mm², was rebuilt as a mirror image of the intact side. It's shown in orange.` };
  }
  if (a.is_broken && rejected.length) {
    return { kind: "not-rebuilt", title: "Built as photographed, not rebuilt",
      text: `A break was reported, but the geometry didn't confirm a safe rebuild: ${rejected[0].message}` };
  }
  if (a.is_broken && r.axes.length === 0) {
    return { kind: "not-rebuilt", title: "Built as photographed, not rebuilt",
      text: "A break was reported, but the outline doesn't show a symmetry strong enough to rebuild from, so nothing was invented: the part is built exactly as photographed." };
  }
  if (a.is_broken) {
    return { kind: "not-rebuilt", title: "Built as photographed, not rebuilt",
      text: `A break was reported, but no mirror axis passed the checks needed to rebuild it, so the part is built exactly as photographed. ${clean(a.symmetry_reason)}` };
  }
  return { kind: "intact", title: "Measured and ready to print", text: "No damage was found, so the part is built exactly as photographed." };
}

const HOLE_ALLOWANCES = [0, 0.1, 0.2, 0.3, 0.4];

function DimensionRow({ d }: { d: Dimension }) {
  const why = d.terms.length > 0 && (
    <InfoTip label={`Where the ${d.label.toLowerCase()} uncertainty comes from`}>
      <span className="why">
        {d.u_mm !== null && <strong>{pm(d.u_mm)} mm is a modelled 2σ estimate.</strong>}
        {d.terms.filter((t) => t.sigma_mm > 0.0005).sort((x, y) => y.sigma_mm - x.sigma_mm).map((t) => (
          <span key={t.name} className="why-term"><span>{t.name}</span><span>{fmt(2 * t.sigma_mm, 3)} mm</span></span>
        ))}
      </span>
    </InfoTip>
  );
  return (
    <li className="dim-row">
      <span className="dim-label">{d.label.replace(/^Hole (H\d+) Ø$/, "Hole $1 diameter")}</span>
      <span className="dim-value">
        {d.value_mm === null ? "traced shape" : <>{fmt(d.value_mm, 2)} <span className="unit">mm</span></>}
        {d.u_mm !== null && <span className="dim-u">{pm(d.u_mm)}</span>}
      </span>
      <Evidence status={d.status} />
      <span className="dim-why">{why}</span>
    </li>
  );
}

function KnownAnswer({ sample, report }: { sample: Sample; report: Report }) {
  const t = sample.truth;
  const size = report.part.size_mm;
  const dims = Object.fromEntries(report.confidence.dimensions.map((d) => [d.id, d]));
  const rows = [
    { label: "Length", truth: t.length_mm, got: size.length, u: dims.length?.u_mm ?? null },
    { label: "Width", truth: t.width_mm, got: size.width, u: dims.width?.u_mm ?? null },
  ];
  return (
    <section className="card known" aria-labelledby="known-title">
      <h2 id="known-title" className="card-title">Known answer</h2>
      <p className="muted small">{sample.label} Truth: {t.basis}; {t.photographed}.</p>
      <div className="table-wrap">
      <table className="table">
        <thead><tr><th>Size</th><th>True</th><th>Re-Forge</th><th>Difference</th><th>Within ±U?</th></tr></thead>
        <tbody>
          {rows.map((r) => {
            const delta = r.got - r.truth;
            const inside = r.u !== null ? Math.abs(delta) <= r.u : null;
            return (
              <tr key={r.label}>
                <td>{r.label}</td>
                <td className="num">{fmt(r.truth, 2)} mm</td>
                <td className="num">{fmt(r.got, 2)} {r.u !== null && <span className="dim-u">{pm(r.u)}</span>}</td>
                <td className="num">{delta >= 0 ? "+" : ""}{fmt(delta, 2)} mm</td>
                <td>{inside === null ? "—" : inside ? "Yes" : "No"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      </div>
      <p className="muted small">
        Holes in the true part: {t.holes.map((h) => (h.diameter_mm ? `${h.count} × Ø${fmt(h.diameter_mm, 1)} mm` : `${h.count} slot ${h.slot_mm?.join(" × ")} mm`)).join(", ")}.
        Re-Forge built {report.part.holes.length} hole(s): {report.part.holes.map((h) => (h.kind === "circle" ? `Ø${fmt(h.diameter_mm, 2)}` : "a traced slot")).join(", ") || "none"}.
      </p>
    </section>
  );
}

const MEASUREMENT_WORDS: Record<string, (t: string) => string> = {
  overall_length: () => "the overall length",
  overall_width: () => "the overall width",
  hole_diameter: (t) => (t ? `the diameter of hole ${t}` : "the hole diameters"),
  hole_spacing: () => "the spacing between holes",
};

/** The AI's suggested caliper checks, in words; the ones that name outline segments stay in the technical view. */
function measurementText(kind: string, target: string): string | null {
  const words = MEASUREMENT_WORDS[kind];
  if (!words) return null;
  return words(/^H\d+$/.test(target) ? target : "");
}

function Result({ status, report, files, health }: { status: JobStatus; report: Report; files: Files; health: Health | null | undefined }) {
  const [advanced, setAdvanced] = useState(false);
  const [allowance, setAllowance] = useState(0);
  const [allowanceError, setAllowanceError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const [ack, setAck] = useState(false);
  const [lines, setLines] = useState<SpecLines | null>(null);
  const verdict = verdictOf(report);
  const r = report.reconstruction;
  const a = r.interpretation.analysis;
  const req = status.request;
  const sample = req.sample_info;
  const size = report.part.size_mm;
  const dims = report.confidence.dimensions;
  const byId = Object.fromEntries(dims.map((d) => [d.id, d]));
  const name = r.interpretation.is_ai && a.object_name && a.object_name !== "part" ? sentence(a.object_name) : sample?.title ?? "Your part";
  const holes = report.part.holes;
  const uncertainRuns = r.completion?.runs.filter((x) => x.status === "UNCERTAIN") ?? [];
  const uncertainMm = uncertainRuns.reduce((s, x) => s + x.length_mm, 0);
  const excluded = report.part.excluded_candidates;
  const warnings = [...report.calibration.warnings, ...report.pose.warnings, ...report.refinement.warnings];
  const ambiguous = r.verification.filter((n) => n.code === "AXIS_OFFSET_AMBIGUOUS");
  const needsAck = uncertainRuns.length > 0 || excluded.length > 0 || ambiguous.length > 0;
  const exportReady = !needsAck || ack;
  const sizeU = Math.max(byId.length?.u_mm ?? 0, byId.width?.u_mm ?? 0);
  const dominant = byId.length?.dominant;
  const budget = report.confidence.budget;

  useEffect(() => {
    let alive = true;
    fetch(files["spec.json"]).then((res) => (res.ok ? res.json() : null)).then((spec) => {
      if (!alive || !spec) return;
      setLines({
        points: spec.outline.points,
        runs: spec.outline.runs,
        thickness: spec.thickness.value,
        holes: spec.holes.filter((h: { kind: string }) => h.kind === "circle").map((h: { center_x: { value: number }; center_y: { value: number }; diameter: { value: number; status: string } }) => ({
          x: h.center_x.value, y: h.center_y.value, d: h.diameter.value, status: h.diameter.status,
        })),
      });
    }).catch(() => undefined);
    return () => { alive = false; };
  }, [files]);

  const viewerDims = useMemo(() => ({ length: size.length, width: size.width }), [size.length, size.width]);
  const stlUrl = modelUrl(files["model.stl"], allowance);
  const scadUrl = modelUrl(files["model.scad"], allowance);

  async function chooseAllowance(value: number) {
    setAllowanceError(null);
    if (value === 0) return setAllowance(0);
    setChecking(true);
    try {
      const res = await fetch(modelUrl(files["model.stl"], value));
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        setAllowanceError(body?.error?.message ?? "This allowance can't be applied to this part.");
        return;
      }
      setAllowance(value);
    } finally {
      setChecking(false);
    }
  }

  const suggested = [...new Set(a.required_measurements.map((m) => measurementText(m.kind, m.target_id)).filter((t): t is string => !!t))].slice(0, 3);
  const tone = verdict.kind === "rebuilt" ? "ember" : verdict.kind === "intact" ? "ok" : verdict.kind === "invalid" ? "bad" : "neutral";

  return (
    <div className="result">
      <section className={`verdict verdict-${tone}`}>
        <div className="verdict-copy">
          <p className="eyebrow">{name}{sample && <span className="flag">Synthetic example</span>}</p>
          <h1>{verdict.title}</h1>
          <p className="lead">{verdict.text}</p>
        </div>
        <dl className="verdict-stats">
          <div><dt>Size</dt><dd>{fmt(size.length, 1)} × {fmt(size.width, 1)} <span className="unit">mm</span><span className="stat-note">{fmt(size.thickness, 2)} mm thick</span></dd></div>
          <div><dt>Holes</dt><dd>{holes.length}</dd></div>
          <div><dt>Accuracy</dt><dd>{sizeU ? <>{pm(sizeU)} <span className="unit">mm</span></> : "—"}<span className="stat-note">estimated</span></dd></div>
        </dl>
      </section>

      <div className="result-visuals">
        <section className="card card-flush viewer-card" aria-label="3D model">
          <Suspense fallback={<div className="viewer"><div className="viewer-status"><Spinner /> Loading the 3D viewer…</div></div>}>
            <StlViewer url={stlUrl} lines={lines} angleDeg={size.angle_deg} dims={viewerDims} />
          </Suspense>
        </section>
        <section className="card card-flush compare-card" aria-label="Before and after">
          <Compare before={files["photo.jpg"]} after={files["overlay.png"]} beforeLabel="Your photo" afterLabel="What was built" />
          <p className="compare-legend">
            <span><i className="sw sw-observed" /> measured from the photo</span>
            {r.completion && <span><i className="sw sw-inferred" /> rebuilt by symmetry</span>}
            {(uncertainRuns.length > 0) && <span><i className="sw sw-uncertain" /> uncertain</span>}
            {excluded.length > 0 && <span><i className="sw sw-left-out" /> hole left out</span>}
          </p>
        </section>
      </div>

      <div className="result-grid">
        <section className="card" aria-labelledby="know-title">
          <h2 id="know-title" className="card-title">What we know about your part</h2>
          <ul className="dims">
            {dims.filter((d) => !d.id.endsWith(".position")).map((d) => <DimensionRow key={d.id} d={d} />)}
          </ul>
          {r.completion && (
            <p className="note note-ember">
              <Evidence status="INFERRED" /> {fmt(r.completion.added_area_mm2, 0)} mm² rebuilt as a mirror image. {fmt(r.completion.confirmed_mm, 0)} mm of surviving
              outline confirm the symmetry, for {fmt(r.completion.inferred_outline_mm, 0)} mm of edge it adds.
            </p>
          )}
          {uncertainRuns.length > 0 && (
            <p className="note note-bad"><Evidence status="UNCERTAIN" /> {uncertainRuns.length} short spot(s), {fmt(uncertainMm, 1)} mm in total, where the rebuilt edge meets the photographed one.</p>
          )}
          {excluded.map((c) => (
            <p className="note note-bad" key={c.hole}><Evidence status="UNCERTAIN" /> A possible hole: {c.reason}.</p>
          ))}
          {ambiguous.map((n) => <p className="note note-bad" key={n.code}><Evidence status="UNCERTAIN" /> {n.message}</p>)}
          <p className="muted small">
            Length and width are the sides of the smallest rectangle that fits around the part.
            ± values are 2σ estimates from this photo's error budget, not guarantees.
            {dominant === "print scale" && !budget.scale_checked && " Most of it comes from the unchecked print scale: measuring the mat's two bars once tightens it."}
            {dominant === "calibration" && " Most of it comes from the mat not lying perfectly flat."}
          </p>
          {warnings.length > 0 && (
            <div className="photo-notes">
              <h3 className="mini-title">About this photo</h3>
              <ul>{warnings.map((w) => <li key={w.code}>{WARNING_COPY[w.code] ?? w.message}</li>)}</ul>
            </div>
          )}
        </section>

        <section className="card" aria-labelledby="check-title">
          <h2 id="check-title" className="card-title">Before you print</h2>
          <ol className="checklist">
            {r.completion && <li>Look over the <strong className="t-ember">orange</strong> section: it was rebuilt, not photographed. Compare it with the broken-off piece or with the device it fits, if you can.</li>}
            {needsAck && <li>Decide whether the <strong className="t-bad">uncertain</strong> spots listed opposite matter for the fit.</li>}
            {holes.length > 0 && <li>Printed holes usually come out slightly small. Add an allowance below if the part fits over screws or pins.</li>}
            {suggested.length > 0 && <li>If the fit is tight, check with a caliper: {suggested.join("; ")}.</li>}
            <li>Print one piece and test the fit before you rely on it. Not for safety-critical uses.</li>
          </ol>
          {holes.length > 0 && (
            <div className="allowance">
              <span className="field-label" id="allow-label">
                Hole allowance <InfoTip label="What is the hole allowance?">Added to every hole's diameter when the files are built, to make up for a printer that prints holes small. 0.1 to 0.3 mm is typical for FDM printers.</InfoTip>
              </span>
              <div className="segmented" role="radiogroup" aria-labelledby="allow-label">
                {HOLE_ALLOWANCES.map((v) => (
                  <button key={v} type="button" role="radio" aria-checked={allowance === v} disabled={checking}
                          onClick={() => chooseAllowance(v)}>{v === 0 ? "None" : `+${v.toFixed(1)}`}</button>
                ))}
              </div>
              <span className="muted small">{allowance ? `Files rebuilt with holes +${allowance.toFixed(1)} mm; the model is re-validated.` : "Holes as measured."}</span>
              {allowanceError && <p className="field-error" role="alert">{allowanceError}</p>}
            </div>
          )}
          {needsAck && (
            <label className="ack">
              <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
              <span>I've looked at the uncertain spots and want the files anyway.</span>
            </label>
          )}
        </section>

        <section className="card downloads" aria-labelledby="dl-title">
          <h2 id="dl-title" className="card-title">Your files</h2>
          {!exportReady && <p className="note note-bad">Tick the box under "Before you print" to unlock the downloads.</p>}
          <ul className="files">
            <li>
              <a className={`file ${exportReady ? "" : "is-locked"}`} href={exportReady ? stlUrl : undefined} aria-disabled={!exportReady} download>
                <span className="file-ext">STL</span>
                <span><strong>Print it</strong><span className="muted">For your slicer: PrusaSlicer, Cura, Bambu Studio, OrcaSlicer. In millimetres, lying flat.</span></span>
              </a>
            </li>
            <li>
              <a className={`file ${exportReady ? "" : "is-locked"}`} href={exportReady ? scadUrl : undefined} aria-disabled={!exportReady} download>
                <span className="file-ext">SCAD</span>
                <span><strong>Edit it</strong><span className="muted">OpenSCAD source: every dimension is a named value at the top, with where it came from.</span></span>
              </a>
            </li>
            <li>
              <a className="file" href={files["report.json"]} download>
                <span className="file-ext">JSON</span>
                <span><strong>The evidence</strong><span className="muted">Every number with its status, uncertainty and source.</span></span>
              </a>
            </li>
          </ul>
          <Tip title="After downloading" tone="neutral">
            Open the STL in your slicer and print one test piece. To change a size, open the .scad file in OpenSCAD (free) and edit the values at the top.
          </Tip>
        </section>

        {sample && <KnownAnswer sample={sample} report={report} />}
      </div>

      <div className="advanced-toggle">
        <button type="button" className="button button-ghost" aria-expanded={advanced} aria-controls="advanced" onClick={() => setAdvanced((v) => !v)}>
          {advanced ? "Hide technical details" : "Show technical details"}
        </button>
        <span className="muted small">Calibration, AI reading, uncertainty budget, validation and timings.</span>
      </div>
      {advanced && <Advanced id="advanced" report={report} files={files} request={req} health={health} />}
      <p className="disclaimer">{report.disclaimer}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------------------

export function JobPage({ id, health }: { id: string; health: Health | null | undefined }) {
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [error, setError] = useState<ApiErrorBody | null>(null);

  useEffect(() => {
    let alive = true;
    let timer = 0;
    let failures = 0;
    async function poll() {
      try {
        const s = await getJob(id);
        if (!alive) return;
        failures = 0;
        setStatus(s);
        setError(null);
        if (s.state === "queued" || s.state === "running") {
          timer = window.setTimeout(poll, POLL_MS);
        } else if (s.state === "done" && s.result) {
          const rep = s.result.report;
          const z = rep.part.size_mm ?? { length: rep.part.overall_mm[0], width: rep.part.overall_mm[1], thickness: rep.part.overall_mm[2] };
          const it = rep.reconstruction.interpretation;
          update(id, { state: "done", size: `${z.length.toFixed(1)} × ${z.width.toFixed(1)} × ${z.thickness.toFixed(1)} mm`,
            rebuilt: !!rep.reconstruction.completion,
            ...(it.is_ai && it.analysis.object_name !== "part" ? { title: sentence(it.analysis.object_name) } : {}) });
        } else {
          update(id, { state: "failed" });
        }
      } catch (err) {
        if (!alive) return;
        if (err instanceof ApiError && err.status === 404) {
          setError({ code: "JOB_NOT_FOUND", message: "There is no analysis with this id on this server.", hint: null });
          return;
        }
        failures += 1;
        if (failures >= 4) setError(err instanceof ApiError ? err.body : { code: "NETWORK", message: "Lost contact with the server.", hint: null });
        timer = window.setTimeout(poll, POLL_MS * Math.min(failures + 1, 6));
      }
    }
    poll();
    window.scrollTo({ top: 0 });
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [id]);

  if (error && (!status || error.code === "JOB_NOT_FOUND")) return <div className="page"><Failure error={error} health={health} /></div>;
  if (!status) return <div className="page center"><Spinner label="Loading" /> <span className="muted">Loading…</span></div>;
  if (status.state === "queued" || status.state === "running") return <div className="page"><Processing status={status} health={health} /></div>;
  if (status.state === "done" && status.result) {
    const report = status.result.report;
    if (!report.confidence || !report.part?.size_mm) {  // a report from before the Confidence Engine
      return <div className="page"><Failure status={status} health={health} error={{ code: "JOB_OUTDATED",
        message: "This report was written before every dimension carried an uncertainty estimate.", hint: null }} /></div>;
    }
    return <div className="page page-wide"><Result status={status} report={report} files={status.result.files} health={health} /></div>;
  }
  return <div className="page"><Failure status={status} error={status.error ?? { code: "INTERNAL_ERROR", message: "The analysis stopped.", hint: null }} health={health} /></div>;
}
