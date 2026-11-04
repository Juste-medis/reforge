import { useEffect, useMemo, useState, type FormEvent, type MouseEvent } from "react";
import { ApiError, getJob, postDeskew, postFeedback, postReshape } from "../api";
import ShapeEditor, { type ShapeEditorData } from "../components/ShapeEditor";
import { InfoTip, Spinner, Tip } from "../components/ui";
import { remember } from "../lib/history";
import { go } from "../lib/route";
import { errorCopy } from "../lib/copy";
import { fmt } from "../lib/format";
import { defaultAi, launch, previewFor } from "../lib/launch";
import { href } from "../lib/route";
import type { ApiErrorBody, FeedbackEntry, GuideOptions, Health, JobStatus, ReconstructionDoc } from "../types";

// ---------------------------------------------------------------------------------------------------------------
// Feedback: was this result right? Stored on the job, shown with it.

export function Feedback({ jobId, initial }: { jobId: string; initial: FeedbackEntry[] }) {
  const [entries, setEntries] = useState(initial);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(verdict: "ok" | "wrong") {
    setBusy(true);
    setError(null);
    try {
      await postFeedback(jobId, verdict, note.trim().slice(0, 500));
      setEntries((es) => [...es, { created_at: new Date().toISOString(), verdict, note: note.trim().slice(0, 500) }]);
      setNote("");
    } catch (err) {
      setError(err instanceof ApiError ? err.body.message : "Couldn't save your feedback.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="card" aria-labelledby="feedback-title">
      <h2 id="feedback-title" className="card-title">Was this right?</h2>
      <p className="muted small">Your verdict stays on this analysis and steers which rebuilds and refusals to trust next.</p>
      <div className="feedback-row">
        <button type="button" className="button button-secondary" disabled={busy} onClick={() => submit("ok")} aria-label="Yes, this result is right">
          👍 Yes
        </button>
        <button type="button" className="button button-secondary" disabled={busy} onClick={() => submit("wrong")} aria-label="No, this result is wrong">
          👎 No
        </button>
        <input type="text" maxLength={500} value={note} onChange={(e) => setNote(e.target.value)}
               placeholder="What was right or wrong? (optional)" aria-label="Feedback note" className="feedback-note" />
      </div>
      {error && <p className="field-error" role="alert">{error}</p>}
      {entries.length > 0 && (
        <ul className="feedback-list">
          {entries.map((e, i) => (
            <li key={i}>
              <span aria-hidden="true">{e.verdict === "ok" ? "👍" : "👎"}</span>
              <span className="muted small">{new Date(e.created_at).toLocaleString()}</span>
              {e.note && <span>{e.note}</span>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------------------------------------------
// Guide: steer a finished job. You pick the axis, the break and the holes; the geometry still judges.

type Pivot = { mode: "centroid" } | { mode: "hole"; hole: string } | { mode: "point"; x: string; y: string };

function splitIds(value: string | null | undefined): string[] {
  return (value ?? "").split(/[\s,]+/).filter(Boolean);
}

function Guide({ id, health }: { id: string; health: Health | null | undefined }) {
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [error, setError] = useState<ApiErrorBody | null>(null);
  const [axis, setAxis] = useState("");
  const [assertAngle, setAssertAngle] = useState("");
  const [pivot, setPivot] = useState<Pivot>({ mode: "centroid" });
  const [fracture, setFracture] = useState<Set<string>>(new Set());
  const [excluded, setExcluded] = useState<Set<string>>(new Set());
  const [holesMode, setHolesMode] = useState<"auto" | "pick">("auto");
  const [build, setBuild] = useState<Set<string>>(new Set());
  const [damage, setDamage] = useState<Set<string>>(new Set());
  const [override, setOverride] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [submitError, setSubmitError] = useState<ApiErrorBody | null>(null);
  const [touched, setTouched] = useState(false);

  useEffect(() => {
    let alive = true;
    getJob(id).then((s) => {
      if (!alive) return;
      setStatus(s);
      const req = s.request;
      if (req.guide_axis) setAxis(req.guide_axis);
      if (req.guide_assert_angle != null) {
        setAxis("assert");
        setAssertAngle(String(req.guide_assert_angle));
      }
      if (req.guide_assert_x_mm != null && req.guide_assert_y_mm != null) {
        setPivot({ mode: "point", x: String(req.guide_assert_x_mm), y: String(req.guide_assert_y_mm) });
      }
      setFracture(new Set(splitIds(req.guide_fracture)));
      setExcluded(new Set(splitIds(req.guide_exclude)));
      setDamage(new Set(splitIds(req.guide_damage)));
      const sources = splitIds(req.guide_sources);
      if (sources.length || splitIds(req.guide_damage).length) setHolesMode("pick");
      setOverride(!!req.guide_family_override);
      setNote(req.guide_note ?? "");
      const recon = s.reconstruction;
      if (recon && sources.length === 0) {
        setBuild(new Set(recon.all_holes.filter((h) => !h.doubted).map((h) => h.id)));
      } else {
        setBuild(new Set(sources));
      }
    }).catch((err: unknown) => alive && setError(err instanceof ApiError ? err.body : { code: "NETWORK", message: String(err), hint: null }));
    return () => { alive = false; };
  }, [id]);

  const recon: ReconstructionDoc | undefined = status?.reconstruction;
  const files = status?.result?.files ?? status?.files ?? {};
  const setofmark = files["setofmark.png"];
  const rough = useMemo(() => (recon?.segments ?? []).filter((s) => s.kind === "irregular" || s.kind === "broken"), [recon]);
  const smooth = useMemo(() => (recon?.segments ?? []).filter((s) => s.kind !== "irregular" && s.kind !== "broken"), [recon]);
  const rejections = useMemo(() => (recon?.verification ?? []).filter((n) => n.level === "rejected"), [recon]);
  const family = recon?.interpretation.analysis.family ?? "";

  function toggleSpan(v: string, asExcluded: boolean) {
    // A span is either the break to rebuild or designed asymmetry to keep, never both.
    const f = new Set(fracture);
    const x = new Set(excluded);
    if (asExcluded) {
      if (x.has(v)) x.delete(v); else { x.add(v); f.delete(v); }
    } else if (f.has(v)) f.delete(v); else { f.add(v); x.delete(v); }
    setFracture(f);
    setExcluded(x);
  }

  const angle = Number(assertAngle);
  const pivotValid = pivot.mode !== "point" || (pivot.x.trim() !== "" && pivot.y.trim() !== ""
    && Number.isFinite(Number(pivot.x)) && Number.isFinite(Number(pivot.y)));
  const angleValid = axis !== "assert" || (assertAngle.trim() !== "" && Number.isFinite(angle) && angle >= 0 && angle < 180);
  const somethingSet = axis !== "" || fracture.size > 0 || excluded.size > 0
    || (holesMode === "pick" && (damage.size > 0 || build.size > 0)) || override || note.trim() !== "";
  const canSubmit = !!status && !!recon && somethingSet && angleValid && pivotValid && !busy;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (!canSubmit || !status) return;
    const req = status.request;
    const guide: GuideOptions = {};
    if (axis !== "" && axis !== "assert") guide.axis = axis;
    if (axis === "assert") {
      guide.assert_angle = angle;
      if (pivot.mode === "hole") {
        const hole = recon?.all_holes.find((h) => h.id === pivot.hole);
        if (hole) {
          guide.assert_x_mm = hole.centre_mm[0];
          guide.assert_y_mm = hole.centre_mm[1];
        }
      } else if (pivot.mode === "point") {
        guide.assert_x_mm = Number(pivot.x);
        guide.assert_y_mm = Number(pivot.y);
      }
    }
    if (fracture.size) guide.fracture = [...fracture];
    if (excluded.size) guide.exclude = [...excluded];
    if (holesMode === "pick") {
      if (damage.size) guide.damage = [...damage];
      const sources = [...build].filter((b) => !damage.has(b));
      if (sources.length) guide.sources = sources;
    }
    if (override) guide.family_override = true;
    if (note.trim()) guide.note = note.trim();
    setBusy(true);
    setSubmitError(null);
    try {
      const ai = defaultAi(health);
      await launch({ fromJob: id }, {
        thickness_mm: req.thickness_mm ?? 3,
        known_length_mm: req.known_length_mm ?? undefined,
        deskew_px_per_mm: req.deskew_px_per_mm ?? undefined,
        segmenter: req.segmenter ?? ai.segmenter,
        interpreter: req.interpreter ?? ai.interpreter,
        prompt: req.prompt ?? "plastic part",
        guide,
      }, `${req.sample_info?.title ?? "My part"} (guided)`, previewFor(id));
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.body : { code: "NETWORK", message: String(err), hint: null });
      setBusy(false);
    }
  }

  if (error) {
    const copy = errorCopy(error.code);
    return (
      <div className="page"><section className="failure" role="alert">
        <div className="failure-icon" aria-hidden="true">!</div>
        <div className="failure-body">
          <p className="eyebrow">Studio</p>
          <h1>{copy.title}</h1>
          <p className="failure-message">{error.message}</p>
          <div className="actions"><a className="button button-primary" href={href({ name: "repairs" })}>My repairs</a></div>
        </div>
      </section></div>
    );
  }
  if (!status) return <div className="page center"><Spinner label="Loading" /> <span className="muted">Loading…</span></div>;
  if (status.state === "queued" || status.state === "running") {
    return (
      <div className="page"><section className="panel" aria-live="polite">
        <h1>This analysis is still running.</h1>
        <p className="muted">The Studio opens once the candidates exist. <a href={href({ name: "job", id })}>Watch it finish</a>, then come back.</p>
      </section></div>
    );
  }
  if (!recon) {
    return (
      <div className="page"><section className="panel">
        <h1>Nothing to steer here.</h1>
        <p className="muted">This analysis stopped before any outline existed
          ({status.error ? `${status.error.code}: ${status.error.message}` : "no part found"}), so there are no
          axes, edges or holes to pick from. Try another photo.</p>
        <div className="actions"><a className="button button-primary" href={href({ name: "new" })}>New repair</a></div>
      </section></div>
    );
  }

  const copy = submitError ? errorCopy(submitError.code) : null;
  return (
    <div className="page page-wide">
      <header className="page-head">
        <p className="eyebrow">Studio · human in the loop</p>
        <h1>Steer this rebuild.</h1>
        <p className="lead">
          You pick the mirror axis, the broken edges and the holes. The geometry still judges: it rebuilds only
          what the numbers confirm, and it says why when it refuses. Same photo, same segmentation as
          <a href={href({ name: "job", id })}> the original run</a>.
        </p>
      </header>
      {rejections.length > 0 && (
        <div className="alert alert-bad" role="note">
          <strong>Why it {recon.completion ? "only built this much" : "didn't rebuild"}:</strong>
          <ul>{rejections.map((n) => <li key={n.code}>{n.message}</li>)}</ul>
        </div>
      )}
      <div className="studio-grid">
        <section className="panel studio-mark" aria-label="Labelled candidates">
          {setofmark ? (
            <a href={setofmark} target="_blank" rel="noreferrer">
              <img src={setofmark} alt="The part with outline segments (S), candidate axes (A) and holes (H) labelled" />
            </a>
          ) : <p className="muted">No labelled view for this run.</p>}
          <p className="muted small">Click to enlarge. S: outline edges · A: candidate mirror axes · H: through-holes.</p>
        </section>
        <form className="studio-form" onSubmit={submit} noValidate>
          <section className="panel" aria-labelledby="axis-title">
            <div className="panel-head"><span className="panel-num">1</span><h2 id="axis-title">Mirror axis</h2>
              <InfoTip label="What is the mirror axis?">The line the intact side is mirrored across. Pick a measured
                candidate, or assert your own angle: your axis skips the support gate, but a contradicted axis still
                fails, and the report shows its measured support.</InfoTip>
            </div>
            <div className="choice" role="radiogroup" aria-label="Mirror axis">
              <label>
                <input type="radio" name="axis" checked={axis === ""} onChange={() => setAxis("")} />
                <span><strong>Automatic.</strong> <span className="muted">Let the reader pick.</span></span>
              </label>
              {recon.axes.map((a) => (
                <label key={a.id}>
                  <input type="radio" name="axis" checked={axis === a.id} onChange={() => setAxis(a.id)} />
                  <span><strong>{a.id}</strong> <span className="muted">{a.angle_deg.toFixed(1)}° · support {(a.support * 100).toFixed(0)}% · {a.holes_matched} hole(s) agree{a.holes_contradicting ? `, ${a.holes_contradicting} contradict` : ""}</span></span>
                </label>
              ))}
              <label>
                <input type="radio" name="axis" checked={axis === "assert"} onChange={() => setAxis("assert")} />
                <span><strong>Assert my own (U0).</strong> <span className="muted">Your angle, your responsibility.</span></span>
              </label>
            </div>
            {axis === "assert" && (
              <div className="assert-box">
                <label className="field">
                  <span className="field-label">Angle in degrees (0–180, 90 is vertical)</span>
                  <span className="input-unit">
                    <input type="number" inputMode="decimal" step="0.5" min="0" max="179.9" value={assertAngle}
                           onChange={(e) => setAssertAngle(e.target.value)} placeholder="e.g. 90" aria-invalid={touched && !angleValid} />
                    <span aria-hidden="true">°</span>
                  </span>
                </label>
                {touched && !angleValid && <p className="field-error" role="alert">Enter an angle from 0 up to (not including) 180.</p>}
                <fieldset className="choice">
                  <legend>Pivot: what the axis passes through</legend>
                  <label>
                    <input type="radio" name="pivot" checked={pivot.mode === "centroid"} onChange={() => setPivot({ mode: "centroid" })} />
                    <span><strong>The outline's centre.</strong> <span className="muted">Best when the break is small.</span></span>
                  </label>
                  <label>
                    <input type="radio" name="pivot" checked={pivot.mode === "hole"} onChange={() => setPivot({ mode: "hole", hole: recon.all_holes[0]?.id ?? "" })} />
                    <span><strong>A hole's centre.</strong> <span className="muted">For a wheel: the hub bore.</span></span>
                  </label>
                  {pivot.mode === "hole" && (
                    <select value={pivot.hole} onChange={(e) => setPivot({ mode: "hole", hole: e.target.value })} aria-label="Pivot hole">
                      {recon.all_holes.map((h) => (
                        <option key={h.id} value={h.id}>{h.id} · {h.kind} · {fmt(h.area_mm2, 0)} mm²{h.doubted ? " · doubted" : ""}</option>
                      ))}
                    </select>
                  )}
                  <label>
                    <input type="radio" name="pivot" checked={pivot.mode === "point"} onChange={() => setPivot({ mode: "point", x: "", y: "" })} />
                    <span><strong>Exact coordinates</strong> <span className="muted">in mm, photo frame.</span></span>
                  </label>
                  {pivot.mode === "point" && (
                    <span className="field-row">
                      <label className="field"><span className="field-label">X</span>
                        <input type="number" inputMode="decimal" step="0.1" value={pivot.x} onChange={(e) => setPivot({ ...pivot, x: e.target.value })} placeholder="mm" /></label>
                      <label className="field"><span className="field-label">Y</span>
                        <input type="number" inputMode="decimal" step="0.1" value={pivot.y} onChange={(e) => setPivot({ ...pivot, y: e.target.value })} placeholder="mm" /></label>
                    </span>
                  )}
                </fieldset>
                {touched && !pivotValid && <p className="field-error" role="alert">Enter both X and Y, in millimetres.</p>}
              </div>
            )}
          </section>

          <section className="panel" aria-labelledby="frac-title">
            <div className="panel-head"><span className="panel-num">2</span><h2 id="frac-title">Broken edges</h2>
              <InfoTip label="What are broken edges?">The outline segments where the part broke. Only the mirror next
                to these edges may add material; everything else must already match its mirror image.</InfoTip>
            </div>
            {rough.length === 0 && smooth.length === 0 && <p className="muted">No outline segments in this run.</p>}
            {rough.length > 0 && (
              <>
                <p className="muted small">Rough edges (red on the labelled view) — tick the broken ones:</p>
                <div className="check-grid" role="group" aria-label="Rough edges">
                  {rough.map((s) => (
                    <label key={s.id} className="check-chip">
                      <input type="checkbox" checked={fracture.has(s.id)} onChange={() => toggleSpan(s.id, false)} />
                      <span><strong>{s.id}</strong> <span className="muted">{s.kind} · {fmt(s.length_mm, 1)} mm</span></span>
                    </label>
                  ))}
                </div>
              </>
            )}
            {smooth.length > 0 && (
              <details className="disclosure">
                <summary><strong>Smooth edges ({smooth.length})</strong> <span className="muted small">— only if the break runs through them</span></summary>
                <div className="check-grid" role="group" aria-label="Smooth edges">
                  {smooth.map((s) => (
                    <label key={s.id} className="check-chip">
                      <input type="checkbox" checked={fracture.has(s.id)} onChange={() => toggleSpan(s.id, false)} />
                      <span><strong>{s.id}</strong> <span className="muted">{s.kind} · {fmt(s.length_mm, 1)} mm</span></span>
                    </label>
                  ))}
                </div>
              </details>
            )}
            {(rough.length > 0 || smooth.length > 0) && (
              <details className="disclosure">
                <summary><strong>Designed asymmetry</strong> <span className="muted small">— kept as photographed, its mirror never counts (a side electrode, an engraving)</span></summary>
                <div className="check-grid" role="group" aria-label="Designed asymmetry">
                  {[...rough, ...smooth].map((s) => (
                    <label key={s.id} className="check-chip">
                      <input type="checkbox" checked={excluded.has(s.id)} onChange={() => toggleSpan(s.id, true)} />
                      <span><strong>{s.id}</strong> <span className="muted">{s.kind} · {fmt(s.length_mm, 1)} mm</span></span>
                    </label>
                  ))}
                </div>
              </details>
            )}
          </section>

          <section className="panel" aria-labelledby="holes-title">
            <div className="panel-head"><span className="panel-num">3</span><h2 id="holes-title">Holes</h2>
              <InfoTip label="What do the hole roles mean?">Build: this is a real hole, mirror from it and put it in
                the model (this overrules a doubt). Damage: this is a void left by the break, not a hole — drop it
                from the model and let mirrors fill it. Left out: keep it out of the model entirely.</InfoTip>
            </div>
            {recon.all_holes.length === 0 && <p className="muted">No holes found in this photo.</p>}
            {recon.all_holes.length > 0 && (
              <div className="choice" role="radiogroup" aria-label="Hole mode">
                <label>
                  <input type="radio" name="holes" checked={holesMode === "auto"} onChange={() => setHolesMode("auto")} />
                  <span><strong>Automatic.</strong> <span className="muted">Build the confident holes, leave out the doubted ones.</span></span>
                </label>
                <label>
                  <input type="radio" name="holes" checked={holesMode === "pick"} onChange={() => setHolesMode("pick")} />
                  <span><strong>I pick the holes.</strong> <span className="muted">Your eyes overrule the doubt heuristic.</span></span>
                </label>
              </div>
            )}
            {holesMode === "pick" && recon.all_holes.length > 0 && (
              <ul className="hole-list">
                {recon.all_holes.map((h) => {
                  const role = damage.has(h.id) ? "damage" : build.has(h.id) ? "build" : "skip";
                  return (
                    <li key={h.id} className="hole-row">
                      <span className="hole-id"><strong>{h.id}</strong> <span className="muted">{h.kind} · {fmt(h.area_mm2, 0)} mm²{h.doubted ? " · doubted" : ""}</span></span>
                      <span className="segmented" role="radiogroup" aria-label={`Role of ${h.id}`}>
                        {(["build", "damage", "skip"] as const).map((r) => (
                          <button key={r} type="button" role="radio" aria-checked={role === r}
                                  onClick={() => {
                                    const b = new Set(build);
                                    const d = new Set(damage);
                                    b.delete(h.id);
                                    d.delete(h.id);
                                    if (r === "build") b.add(h.id);
                                    if (r === "damage") d.add(h.id);
                                    setBuild(b);
                                    setDamage(d);
                                  }}>
                            {r === "build" ? "Build" : r === "damage" ? "Damage" : "Skip"}
                          </button>
                        ))}
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          <section className="panel" aria-labelledby="family-title">
            <div className="panel-head"><span className="panel-num">4</span><h2 id="family-title">Flat model</h2></div>
            <p className="muted small">This run reads the part as <strong>{family.replaceAll("_", " ") || "unknown"}</strong>.</p>
            <label className="ack">
              <input type="checkbox" checked={override} onChange={(e) => setOverride(e.target.checked)} />
              <span>Model it flat anyway. <span className="muted">This is then an approximation of a part the AI did not
                read as flat — not a measured replacement. The report says so.</span></span>
            </label>
            <label className="field">
              <span className="field-label">A note for the report (optional)</span>
              <input type="text" maxLength={500} value={note} onChange={(e) => setNote(e.target.value)}
                     placeholder="e.g. the white blob is the missing chunk" />
            </label>
          </section>

          <div className="submit-bar">
            {submitError && copy && (
              <div className="alert alert-bad" role="alert">
                <strong>{copy.title}</strong>
                <span>{submitError.message}</span>
              </div>
            )}
            {touched && !somethingSet && (
              <p className="field-error submit-error" role="alert">Pick at least one thing to steer: an axis, broken edges, holes, or the flat-model override.</p>
            )}
            <button type="submit" className="button button-primary button-lg" disabled={busy || !canSubmit}>
              {busy ? <><Spinner /> Starting…</> : "Rebuild with my guidance"}
            </button>
            <p className="muted small">Same photo, same segmentation — only the reading changes. The guided run keeps your choices in its report.</p>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------------------
// Flatten: a perspective photo of a rectangular part back to top-down, then a normal job from it.

function Flatten({ health }: { health: Health | null | undefined }) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [natural, setNatural] = useState<[number, number] | null>(null);
  const [corners, setCorners] = useState<[number, number][]>([]);
  const [longSide, setLongSide] = useState("");
  const [shortSide, setShortSide] = useState("");
  const [flat, setFlat] = useState<{ url: string; pxPerMm: number; lengthMm: number } | null>(null);
  const [flatFile, setFlatFile] = useState<File | null>(null);
  const [thickness, setThickness] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiErrorBody | null>(null);
  const [touched, setTouched] = useState(false);

  useEffect(() => {
    if (!file) {
      setPreview(null);
      setNatural(null);
      setCorners([]);
      setFlat(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    setCorners([]);
    setFlat(null);
    const img = new Image();
    img.onload = () => setNatural([img.naturalWidth, img.naturalHeight]);
    img.src = url;
  }, [file]);

  function click(e: MouseEvent<HTMLDivElement>) {
    if (!natural || corners.length >= 4) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * natural[0];
    const y = ((e.clientY - rect.top) / rect.height) * natural[1];
    setCorners((cs) => [...cs, [Math.round(x), Math.round(y)]]);
    setFlat(null);
    setError(null);
  }

  const long = Number(longSide);
  const short = Number(shortSide);
  const sidesError = longSide === "" || shortSide === "" ? "Measure both sides of the intact rectangle."
    : !(long > 0 && long <= 5000 && short > 0 && short <= 5000) ? "Both sides in mm, up to 5000." : null;
  const canFlatten = !!file && corners.length === 4 && !sidesError && !busy;
  const t = Number(thickness);
  const thicknessError = thickness === "" ? "Enter the part's thickness." : !(t > 0.4 && t <= 200) ? "Between 0.5 and 200 mm." : null;

  async function flatten() {
    setTouched(true);
    if (!canFlatten || !file) return;
    setBusy(true);
    setError(null);
    try {
      const res = await postDeskew(file, corners, long, short);
      // Decode in-page: a data-URL round-trip through fetch() fails on very large images in some browsers.
      const bin = atob(res.png_b64);
      const bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      const blob = new Blob([bytes], { type: "image/png" });
      const out = new File([blob], `flattened-${file.name.replace(/\.[^.]+$/, "")}.png`, { type: "image/png" });
      setFlat({ url: URL.createObjectURL(out), pxPerMm: res.px_per_mm, lengthMm: res.length_mm });
      setFlatFile(out);
    } catch (err) {
      setError(err instanceof ApiError ? err.body : { code: "NETWORK", message: String(err), hint: null });
    } finally {
      setBusy(false);
    }
  }

  async function doAnalyse() {
    setTouched(true);
    if (!flat || !flatFile || thicknessError || busy) return;
    setBusy(true);
    setError(null);
    try {
      const ai = defaultAi(health);
      await launch({ photo: flatFile }, {
        thickness_mm: t, known_length_mm: flat.lengthMm, deskew_px_per_mm: flat.pxPerMm,
        segmenter: ai.segmenter, interpreter: ai.interpreter, prompt: "plastic part",
      }, flatFile.name.replace(/\.[^.]+$/, "") || "Flattened part", flat.url);
    } catch (err) {
      setError(err instanceof ApiError ? err.body : { code: "NETWORK", message: String(err), hint: null });
      setBusy(false);
    }
  }

  function analyse(e: FormEvent) {
    e.preventDefault();
    void doAnalyse();
  }

  const copy = error ? errorCopy(error.code) : null;
  return (
    <div className="studio-grid">
      <section className="panel" aria-labelledby="flat-photo-title">
        <div className="panel-head"><span className="panel-num">1</span><h2 id="flat-photo-title">Photo + four corners</h2></div>
        <label className="field">
          <span className="field-label">A perspective photo of a rectangular part</span>
          <span className="file-pick">
            <span className="button button-secondary button-sm" aria-hidden="true">Choose a photo</span>
            <input type="file" accept="image/jpeg,image/png,image/webp" className="visually-hidden"
                   onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            <span className="file-name" title={file?.name ?? ""}>{file ? file.name : "No photo chosen"}</span>
          </span>
        </label>
        {preview && natural && (
          <div className="corner-picker" onClick={click} role="button" tabIndex={0} aria-label="Click the part's four corners"
               onKeyDown={(e) => { if (e.key === "Backspace") setCorners((cs) => cs.slice(0, -1)); }}>
            <img src={preview} alt="Click the part's four corners, in any order" />
            {corners.map(([x, y], i) => (
              <span key={i} className="corner-dot" style={{ left: `${(x / natural[0]) * 100}%`, top: `${(y / natural[1]) * 100}%` }}>{i + 1}</span>
            ))}
          </div>
        )}
        <p className="muted small">Click the rectangle's four corners in any order ({corners.length}/4).
          {corners.length > 0 && <> <button type="button" className="button button-ghost button-sm" onClick={() => setCorners([])}>Start over</button></>}</p>
        <div className="field-row">
          <label className="field">
            <span className="field-label">Long side, measured</span>
            <span className="input-unit"><input type="number" inputMode="decimal" step="0.1" min="1" max="5000" value={longSide}
              onChange={(e) => setLongSide(e.target.value)} placeholder="e.g. 300" /><span aria-hidden="true">mm</span></span>
          </label>
          <label className="field">
            <span className="field-label">Short side, measured</span>
            <span className="input-unit"><input type="number" inputMode="decimal" step="0.1" min="1" max="5000" value={shortSide}
              onChange={(e) => setShortSide(e.target.value)} placeholder="e.g. 200" /><span aria-hidden="true">mm</span></span>
          </label>
        </div>
        {touched && sidesError && <p className="field-error" role="alert">{sidesError}</p>}
        <div className="actions">
          <button type="button" className="button button-secondary" onClick={flatten} disabled={!canFlatten}>
            {busy && !flat ? <><Spinner /> Flattening…</> : "Flatten this photo"}
          </button>
        </div>
      </section>
      <section className="panel" aria-labelledby="flat-check-title">
        <div className="panel-head"><span className="panel-num">2</span><h2 id="flat-check-title">Check + analyse</h2></div>
        {!flat && <p className="muted">The flattened top-down view appears here. Check that the part looks straight and undistorted before analysing it.</p>}
        {flat && (
          <form onSubmit={analyse} noValidate>
            <img src={flat.url} alt="The flattened top-down view" className="flat-preview" />
            <p className="muted small">Scale is exact by construction ({flat.pxPerMm.toFixed(3)} px/mm): the torn
              outline can't rescale it. If the part looks skewed, its corners were off — start over.</p>
            <label className="field">
              <span className="field-label">Thickness, from a caliper</span>
              <span className="input-unit">
                <input type="number" inputMode="decimal" step="0.01" min="0.5" max="200" value={thickness}
                       onChange={(e) => setThickness(e.target.value)} placeholder="e.g. 3.00" aria-invalid={touched && !!thicknessError} />
                <span aria-hidden="true">mm</span>
              </span>
            </label>
            {touched && thicknessError && <p className="field-error" role="alert">{thicknessError}</p>}
            <div className="actions">
              <button type="submit" className="button button-primary" disabled={busy}>
                {busy ? <><Spinner /> Starting…</> : "Analyse the flattened photo"}
              </button>
            </div>
          </form>
        )}
        {error && copy && (
          <div className="alert alert-bad" role="alert">
            <strong>{copy.title}</strong>
            <span>{error.message}</span>
            <span>
              <button type="button" className="button button-secondary button-sm" disabled={busy}
                      onClick={() => (flat ? doAnalyse() : flatten())}>
                Try again
              </button>
            </span>
          </div>
        )}
      </section>
    </div>
  );
}

export function Studio({ id, health }: { id?: string; health: Health | null | undefined }) {
  const [tab, setTab] = useState<"guide" | "reshape" | "flatten">(id ? "guide" : "flatten");
  useEffect(() => { setTab(id ? "guide" : "flatten"); }, [id]);
  return (
    <div className="page page-wide">
      <header className="page-head">
        <p className="eyebrow">Studio</p>
        <h1>You steer, geometry judges.</h1>
        <p className="lead">For difficult photos: flatten a perspective shot, redraw the outline yourself, or
          pick the axis, the break and the holes. Every choice lands in the report; the checks still apply.</p>
      </header>
      <div className="segmented studio-tabs" role="tablist" aria-label="Studio tools">
        <button type="button" role="tab" aria-selected={tab === "guide"} onClick={() => id && setTab("guide")} disabled={!id}
                title={id ? "Steer this analysis" : "Open the Studio from an analysis to steer it"}>
          Guide a rebuild
        </button>
        <button type="button" role="tab" aria-selected={tab === "reshape"} onClick={() => id && setTab("reshape")}
                disabled={!id} title={id ? "Redraw this outline" : "Open the Studio from an analysis to reshape it"}>
          Reshape the outline
        </button>
        <button type="button" role="tab" aria-selected={tab === "flatten"} onClick={() => setTab("flatten")}>
          Flatten a photo
        </button>
      </div>
      {tab === "guide" && id && <Guide id={id} health={health} />}
      {tab === "reshape" && id && <Reshape id={id} />}
      {tab === "guide" && !id && (
        <Tip title="Pick an analysis first">
          Guiding starts from an existing run — its outline, axes and holes become your candidates.
          Find one in <a href={href({ name: "repairs" })}>My repairs</a>, or flatten a perspective photo below.
        </Tip>
      )}
      {tab === "flatten" && <Flatten health={health} />}
    </div>
  );
}

function Reshape({ id }: { id: string }) {
  const [data, setData] = useState<ShapeEditorData | null>(null);
  const [error, setError] = useState<ApiErrorBody | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    setData(null);
    setError(null);
    (async () => {
      try {
        const status = await getJob(id);
        const report = status.result?.report;
        const files = status.result?.files;
        const texture = report?.texture;
        if (status.state !== "done" || !report || !texture || !files?.["photo.jpg"] || !files?.["spec.json"]) {
          throw new ApiError({ code: "RESHAPE_NO_PARENT",
            message: "Reshaping starts from a finished analysis with a built outline.",
            hint: "Open a finished analysis, then come back here." });
        }
        const spec = await (await fetch(files["spec.json"])).json();
        const outlineMm = spec?.outline?.points as [number, number][] | undefined;
        if (!outlineMm || outlineMm.length < 8) {
          throw new ApiError({ code: "RESHAPE_NO_PARENT", message: "This analysis has no outline to reshape.",
            hint: null });
        }
        if (live) {
          setData({ photoUrl: files["photo.jpg"], widthPx: texture.size_px[0], heightPx: texture.size_px[1],
                     outlineMm, u: texture.u, v: texture.v, pxPerMm: texture.u[1] });
        }
      } catch (err) {
        if (live) setError(err instanceof ApiError ? err.body : { code: "NETWORK", message: String(err), hint: null });
      }
    })();
    return () => { live = false; };
  }, [id]);

  async function submit(outlinePx: number[][], baselinePx: number[][]) {
    setBusy(true);
    setError(null);
    try {
      const res = await postReshape(id, outlinePx, baselinePx);
      remember({ id: res.job_id, createdAt: new Date().toISOString(), title: `Reshape of ${id.slice(0, 8)}`,
                 state: "running" });
      go({ name: "job", id: res.job_id });
    } catch (err) {
      setError(err instanceof ApiError ? err.body : { code: "NETWORK", message: String(err), hint: null });
      setBusy(false);
    }
  }

  if (error) {
    const copy = errorCopy(error.code);
    return (
      <div className="alert alert-bad" role="alert">
        <strong>{copy?.title ?? "Reshaping stopped"}</strong>
        <span>{error.message}</span>
        {error.hint && <span className="muted">{error.hint}</span>}
      </div>
    );
  }
  if (!data) return <p className="muted"><Spinner /> Loading the outline…</p>;
  return (
    <section className="card" aria-label="Reshape the outline">
      <h2><span className="step-n">1</span> Pull the border where the photo misled it</h2>
      <p className="muted">The grey outline is the built shape; the blue one is yours. Undo and redo never lose
        a version, and rebuilding re-checks everything — your border is recorded, never silently trusted.</p>
      <ShapeEditor data={data} onSubmit={submit} busy={busy} />
    </section>
  );
}
