import { Evidence } from "../components/ui";
import { fmt, pm, seconds } from "../lib/format";
import { STAGE_COPY } from "../lib/copy";
import type { Check, Files, Health, JobRequest, Pose, Report } from "../types";

const FOCAL_SOURCE: Record<Pose["focal_source"], string> = {
  "exif+homography": "from the photo's EXIF, confirmed by the mat's perspective",
  exif: "from the photo's EXIF",
  homography: "measured from the mat's perspective",
  prior: "assumed (no EXIF, view too parallel to measure)",
};

const NOTE_MARK = { info: "✓", warning: "!", rejected: "✕" } as const;

function CheckRow({ check }: { check: Check }) {
  const state = check.passed ? "pass" : check.severity === "warning" ? "warn" : "fail";
  return (
    <li className={`vcheck vcheck-${state}`}>
      <span className="vcheck-mark" aria-hidden="true">{state === "pass" ? "✓" : state === "warn" ? "!" : "✕"}</span>
      <span className="vcheck-name">{check.name.replaceAll("_", " ")}</span>
      <span className="vcheck-detail">{check.detail}</span>
      <span className="visually-hidden">{state === "pass" ? "passed" : state === "warn" ? "warning" : "failed"}</span>
    </li>
  );
}

function AiTag({ ai }: { ai: boolean }) {
  return <span className={`ai-tag ${ai ? "is-ai" : ""}`}>{ai ? "AI" : "not AI"}</span>;
}

export function Advanced({ id, report, files, request, health }: { id: string; report: Report; files: Files; request: JobRequest; health: Health | null | undefined }) {
  const { calibration: cal, segmentation: seg, refinement: ref, pose, height_correction: hc, reconstruction: r, confidence } = report;
  const it = r.interpretation;
  const a = it.analysis;
  const axis = r.axes.find((x) => x.id === a.mirror_axis_id);
  const total = Object.values(report.timings_s).reduce((s, v) => s + v, 0);
  const aiCost = (seg.cost_usd ?? 0) + (it.cost_usd ?? 0);
  const attempts = (seg.detail?.attempts as { prompt: string; source: string; instances: number }[] | undefined) ?? [];
  void health;
  return (
    <section id={id} className="advanced" aria-label="Technical details">
      <div className="adv-grid">
        <article className="card adv-wide">
          <h3 className="card-title">Uncertainty budget</h3>
          <p className="muted small">{confidence.note}.</p>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Dimension</th><th>Value</th><th>±U (2σ)</th><th>Status</th><th>Largest term</th></tr></thead>
              <tbody>
                {confidence.dimensions.map((d) => (
                  <tr key={d.id}>
                    <td>{d.label}</td>
                    <td className="num">{d.value_mm === null ? "—" : `${fmt(d.value_mm, 3)} mm`}</td>
                    <td className="num">{d.u_mm === null ? "—" : pm(d.u_mm)}</td>
                    <td><Evidence status={d.status} /></td>
                    <td>{d.dominant ?? d.note ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <dl className="kv kv-2">
            <dt>Calibration (1σ)</dt><dd>{fmt(confidence.budget.calibration_mm, 3)} mm · {confidence.budget.calibration_basis}</dd>
            <dt>Print scale (1σ)</dt><dd>{fmt(confidence.budget.scale_rel * 100, 3)} % · {confidence.budget.scale_basis}</dd>
            <dt>Edges (1σ)</dt><dd>{fmt(confidence.budget.edge_mm, 3)} mm · {confidence.budget.edge_basis}</dd>
            <dt>Height correction (1σ)</dt><dd>{fmt(confidence.budget.height_mm, 3)} mm · camera pose from the mat</dd>
          </dl>
        </article>

        <article className="card adv-wide">
          <h3 className="card-title">Part reading <AiTag ai={it.is_ai} /></h3>
          <div className="adv-split">
            <figure className="adv-figure">
              <img src={files["setofmark.png"]} alt="The marked view the interpreter answered in: outline segments S, candidate mirror axes A, holes H" loading="lazy" />
              <figcaption className="muted small">What the interpreter saw: segments S#, candidate mirror axes A#, holes H#. It may answer only with these ids, through a strict schema; geometry then checks the answer.</figcaption>
            </figure>
            <div>
              <dl className="kv">
                <dt>Read by</dt><dd>{it.method}{it.is_ai ? ` · ${fmt(it.latency_s, 1)} s · $${fmt(it.cost_usd, 4)}` : ""}</dd>
                {it.fallback_reason && (<><dt>Fallback</dt><dd>{it.fallback_reason.code}: the geometric rule was used instead</dd></>)}
                <dt>Object</dt><dd>{a.object_name}</dd>
                <dt>Family</dt><dd>{a.family.replaceAll("_", " ")} · {a.family_reason}</dd>
                <dt>Broken</dt><dd>{a.is_broken ? `yes: fracture ${a.fracture_segment_ids.join(", ") || "not located"}` : "no"}{a.fracture_reason ? ` · ${a.fracture_reason}` : ""}</dd>
                <dt>Symmetry</dt><dd>{a.symmetry}{axis ? ` about ${axis.id} (support ${fmt(axis.support * 100, 0)} %, ${axis.holes_matched} holes matched)` : ""}{a.symmetry_reason ? ` · ${a.symmetry_reason}` : ""}</dd>
                {r.completion && (
                  <>
                    <dt>Rebuilt</dt><dd>{fmt(r.completion.added_area_mm2, 1)} mm²{(r.completion.method ?? "mirror") === "bridge" ? " by smooth bridge" : ` about ${r.completion.axis}`} · {(r.completion.method ?? "mirror") === "bridge" ? "bridge" : "mirror"} ±{fmt(r.completion.inferred_u_mm_2sigma, 3)} mm (2σ)</dd>
                    <dt>Evidence</dt><dd>{fmt(r.completion.confirmed_mm, 0)} mm {(r.completion.method ?? "mirror") === "bridge" ? "of intact edges stand under the bridge" : "confirm the mirror"}, for {fmt(r.completion.inferred_outline_mm, 0)} mm it invents</dd>
                  </>
                )}
              </dl>
              <ul className="notes">
                {r.verification.map((n) => (
                  <li key={n.code + n.message} className={`vnote vnote-${n.level}`}><strong>{NOTE_MARK[n.level]} {n.code}</strong> {n.message}</li>
                ))}
              </ul>
              {a.required_measurements.length > 0 && (
                <>
                  <h4 className="mini-title">Caliper measurements requested</h4>
                  <ol className="requests">
                    {a.required_measurements.map((m, i) => <li key={i}><code>{m.kind}{m.target_id !== "none" ? ` ${m.target_id}` : ""}</code> {m.why}</li>)}
                  </ol>
                </>
              )}
            </div>
          </div>
          {r.axes.length > 0 && (
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Axis</th><th>Angle</th><th>Support</th><th>Holes for / against</th><th>Outline confirming</th></tr></thead>
                <tbody>
                  {r.axes.map((x) => (
                    <tr key={x.id}><td>{x.id}</td><td className="num">{fmt(x.angle_deg, 2)}°</td><td className="num">{fmt(x.support * 100, 1)} %</td>
                      <td className="num">{x.holes_matched} / {x.holes_contradicting}</td><td className="num">{fmt(x.outline_confirming_mm, 1)} mm</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </article>

        <article className="card">
          <h3 className="card-title">Calibration</h3>
          <dl className="kv">
            <dt>Markers</dt><dd>{cal.markers} / 12 ({cal.page})</dd>
            <dt>Resolution</dt><dd>{fmt(cal.px_per_mm, 1)} px/mm</dd>
            <dt>Fit residual</dt><dd>{fmt(cal.fit_rms_mm, 3)} mm RMS</dd>
            <dt>Leave-one-out</dt><dd>{cal.loo_rms_mm === null ? "—" : `${fmt(cal.loo_rms_mm, 3)} mm RMS`}</dd>
            <dt>Tilt indicator</dt><dd>{fmt(cal.perspective_ratio, 2)}×</dd>
            <dt>Print scale</dt><dd>{cal.scale_correction.map((s) => fmt(s, 4)).join(" / ")}{request.bar_x_mm || request.bar_y_mm ? " (from your bar readings)" : " (not checked)"}</dd>
            <dt>Corner bias</dt><dd>{fmt(cal.corner_bias_px, 2)} px</dd>
          </dl>
          {cal.warnings.map((w) => <p className="vnote vnote-warning" key={w.code}><strong>{w.code}</strong> {w.message}</p>)}
        </article>

        <article className="card">
          <h3 className="card-title">Height and lens</h3>
          <dl className="kv">
            <dt>Photographed</dt><dd>{hc.photographed_extent_mm.map((v) => fmt(v, 2)).join(" × ")} mm</dd>
            <dt>Footprint</dt><dd>{hc.footprint_extent_mm.map((v) => fmt(v, 2)).join(" × ")} mm</dd>
            <dt>Parallax removed</dt><dd>up to {fmt(hc.max_shift_mm, 2)} mm (±{fmt(hc.u_persp_mm_2sigma, 2)} mm, 2σ)</dd>
            <dt>Camera</dt><dd>{fmt(pose.camera_height_mm, 0)} ± {fmt(pose.camera_height_sigma_mm, 0)} mm above the mat</dd>
            <dt>Lens</dt><dd>{fmt(pose.focal_35mm, 0)} mm equiv., {FOCAL_SOURCE[pose.focal_source]}</dd>
          </dl>
          {pose.warnings.map((w) => <p className="vnote vnote-warning" key={w.code}><strong>{w.code}</strong> {w.message}</p>)}
        </article>

        <article className="card">
          <h3 className="card-title">Outline <AiTag ai={seg.is_ai} /></h3>
          <dl className="kv">
            <dt>Method</dt><dd>{seg.method}</dd>
            <dt>Confidence</dt><dd>{seg.confidence === null ? "—" : fmt(seg.confidence, 3)}</dd>
            <dt>Latency</dt><dd>{fmt(seg.latency_s, 2)} s</dd>
            <dt>Prompts</dt><dd>{attempts.length ? attempts.map((p) => `${p.prompt} (${p.source}): ${p.instances} instance(s)`).join("; ") : "—"}</dd>
            <dt>Edge refinement</dt><dd>{ref.refined ? `ΔE ${fmt(ref.contrast_delta_e, 0)}, moved ≤ ${fmt(ref.coarse_shift_max_mm, 2)} mm` : "not refined (low contrast)"}</dd>
            <dt>Edge blur</dt><dd>{ref.edge_sigma_mm === null ? "not measured" : `σ ${fmt(ref.edge_sigma_mm, 3)} mm`}</dd>
          </dl>
          {ref.warnings.map((w) => <p className="vnote vnote-warning" key={w.code}><strong>{w.code}</strong> {w.message}</p>)}
        </article>

        <article className="card">
          <h3 className="card-title">Validation</h3>
          <ul className="vchecks">{report.validation.checks.map((c) => <CheckRow key={c.name} check={c} />)}</ul>
          {report.artifact && (
            <>
              <h4 className="mini-title">Files as handed out: {report.artifact.artifact_status.replace("_", " ")}</h4>
              <ul className="vchecks">{report.artifact.rows.map((row) => <CheckRow key={row.check} check={{ name: row.check, passed: row.status === "pass", detail: row.detail, severity: row.status === "warn" ? "warning" : "error" }} />)}</ul>
              <dl className="kv">
                {report.replay && <><dt>Replay</dt><dd>built covers {(report.replay.coverage * 100).toFixed(1)}% of the photographed outline (IoU {report.replay.iou.toFixed(2)})</dd></>}
                <dt>Photo sha256</dt><dd><code>{(report.photo_sha256 ?? report.artifact.photo_sha256 ?? "—").slice(0, 16)}…</code></dd>
                <dt>STL sha256</dt><dd><code>{(report.artifact.files["model.stl"] ?? "—").slice(0, 16)}…</code></dd>
                <dt>Checked</dt><dd>{report.artifact.validated_at}{files["validation.json"] && <> · <a href={files["validation.json"]} download>validation.json</a></>}</dd>
              </dl>
            </>
          )}
        </article>

        <article className="card">
          <h3 className="card-title">Timings and AI use</h3>
          <dl className="kv">
            {Object.entries(report.timings_s).map(([k, v]) => [<dt key={`${k}-k`}>{STAGE_COPY[k]?.label ?? k}</dt>, <dd key={`${k}-v`}>{seconds(v)}</dd>])}
            <dt>Total</dt><dd>{seconds(total)}</dd>
            <dt>AI cost, this job</dt><dd>${fmt(aiCost, 4)} (estimated from the API's token and image counts)</dd>
          </dl>
        </article>
      </div>
    </section>
  );
}
