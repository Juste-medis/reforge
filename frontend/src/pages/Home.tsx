import { useEffect, useState } from "react";
import { ApiError, getSamples } from "../api";
import { StepMatArt, StepModelArt, StepPhotoArt } from "../components/Art";
import { Compare, EvidenceLegend, Spinner } from "../components/ui";
import { defaultAi, launch } from "../lib/launch";
import { href } from "../lib/route";
import type { Credit as Credit_, Health, Sample } from "../types";

function SampleCard({ sample, health }: { sample: Sample; health: Health | null | undefined }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ai = !!health?.meta_key_configured;
  async function run() {
    setBusy(true);
    setError(null);
    try {
      await launch({ sample: sample.id }, { thickness_mm: sample.thickness_mm, prompt: "plastic part", ...defaultAi(health) }, sample.title);
    } catch (err) {
      setError(err instanceof ApiError ? err.body.message : "Couldn't start the example.");
      setBusy(false);
    }
  }
  const t = sample.truth;
  return (
    <article className="sample">
      <div className="sample-media">
        <img src={sample.thumb_url} alt={`Example photo, rectified: ${sample.title}`} loading="lazy" />
        <span className="sample-flag" title={sample.label}>{sample.rendered ? "Rendered example" : "Real part · real photo"}</span>
      </div>
      <div className="sample-body">
        <h3>{sample.title}</h3>
        <p>{sample.story}</p>
        <p className="sample-truth">
          True size, known exactly: <strong>{t.length_mm.toFixed(2)} × {t.width_mm.toFixed(2)} mm</strong>
        </p>
        {sample.credit && <Credit credit={sample.credit} />}
        {sample.provided_by === "user" && <p className="credit">Photo supplied by the user for the examples</p>}
        <button type="button" className="button button-secondary" onClick={run} disabled={busy || health === null}>
          {busy ? <><Spinner /> Starting…</> : "Run this example"}
        </button>
        <p className="sample-note">{ai ? "Runs the full pipeline, with AI, on this image." : "Runs the full pipeline without AI on this server."}</p>
        {error && <p className="field-error" role="alert">{error}</p>}
      </div>
    </article>
  );
}

export function Credit({ credit }: { credit: Credit_ }) {
  return (
    <p className="credit">
      Photo: <a href={credit.page} target="_blank" rel="noreferrer noopener">{credit.author}</a> ·{" "}
      {credit.licence_url.startsWith("https://creativecommons.org") ? (
        <a href={credit.licence_url} target="_blank" rel="noreferrer noopener">{credit.licence}</a>
      ) : credit.licence} · Wikimedia Commons
    </p>
  );
}

function HeroShowcase() {
  return (
    <figure className="hero-showcase">
      <div className="hero-stage">
        <Compare before="/hero/sprocket-photo.jpg" after="/hero/sprocket-measured.jpg" beforeLabel="Photo" afterLabel="Rebuilt" />
        <div className="hero-readout" aria-hidden="true">
          <span className="readout-row"><span className="sw sw-observed" /> 70.08 × 68.26 mm</span>
          <span className="readout-row">bore + 21 teeth · 663 mm² rebuilt</span>
          <span className="readout-row muted">±0.39 mm, estimated</span>
        </div>
      </div>
      <figcaption>
        Re-Forge's actual output on a real broken sprocket, photographed by the user. Drag to compare: blue is
        measured, orange is rebuilt by mirror. Placed on the mat as a synthetic composite, so its true size is
        known: 70.23 × 68.31 mm.
      </figcaption>
    </figure>
  );
}

export function Home({ health, anchor }: { health: Health | null | undefined; anchor?: string }) {
  const [samples, setSamples] = useState<Sample[] | null>(null);
  useEffect(() => {
    getSamples().then(setSamples).catch(() => setSamples([]));
  }, []);
  useEffect(() => {
    if (anchor) document.getElementById(anchor)?.scrollIntoView({ behavior: "smooth", block: "start" });
    else window.scrollTo({ top: 0 });
  }, [anchor]);

  return (
    <div className="home">
      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow">Photo → measured, printable replacement</p>
          <h1>Rebuild the part that broke.</h1>
          <p className="lead">
            Photograph the broken piece on a printed mat. Re-Forge measures what survived, rebuilds what's missing by
            symmetry, and tells you which is which. Then it hands you a model you can print.
          </p>
          <div className="hero-actions">
            <a className="button button-primary button-lg" href={href({ name: "new" })}>Start a repair</a>
            <a className="button button-ghost button-lg" href={href({ name: "home", anchor: "examples" })}>Try an example</a>
          </div>
          <ul className="hero-facts">
            <li><span><strong>True millimetres</strong>, from a printed mat</span></li>
            <li><span><strong>Every number labelled</strong> measured or estimated</span></li>
            <li><span><strong>STL, OpenSCAD, DXF and SVG</strong>, to print, edit or cut</span></li>
          </ul>
        </div>
        <HeroShowcase />
      </section>

      <section className="section" id="how" aria-labelledby="how-title">
        <p className="eyebrow">How it works</p>
        <h2 id="how-title">Three steps.</h2>
        <ol className="steps">
          <li className="step-card">
            <StepMatArt />
            <span className="step-num">1</span>
            <h3>Print the mat</h3>
            <p>Print it at 100 % on A4 or Letter. Its markers turn your photo into true millimetres. No printer? You can skip it and enter one measured length instead.</p>
            <p className="step-links">
              <a href="/api/mat/A4.pdf" download>A4 mat (PDF)</a>
              <a href="/api/mat/Letter.pdf" download>Letter mat (PDF)</a>
            </p>
          </li>
          <li className="step-card">
            <StepPhotoArt />
            <span className="step-num">2</span>
            <h3>Photograph from above</h3>
            <p>Lay the part flat in the middle of the mat and shoot straight down, in soft light.</p>
          </li>
          <li className="step-card">
            <StepModelArt />
            <span className="step-num">3</span>
            <h3>Check, then print</h3>
            <p>Review what was measured and what was rebuilt, then download an STL for your slicer or an editable OpenSCAD file.</p>
          </li>
        </ol>
      </section>

      <section className="section evidence-section" aria-labelledby="evidence-title">
        <div className="evidence-copy">
          <p className="eyebrow">Evidence, not guesses</p>
          <h2 id="evidence-title">Every number says where it came from.</h2>
          <p>
            AI finds the part and reads the damage, but it never sets a dimension. Sizes come from the calibrated photo,
            and every claim the AI makes is checked against the geometry before anything is rebuilt. Where evidence is
            missing, Re-Forge says so instead of inventing it.
          </p>
        </div>
        <EvidenceLegend />
      </section>

      <section className="section" id="examples" aria-labelledby="examples-title">
        <p className="eyebrow">Successes</p>
        <h2 id="examples-title">No mat yet? Run one that worked.</h2>
        <p className="section-lead">
          Every example below is verified end to end: broken ones rebuild against their known truth — a rendered
          flange with its lost holes back, a real sprocket's missing half back — and intact ones measure against it
          with nothing invented. Real photos, one rendered part, all through the same pipeline as your photos.
        </p>
        {samples === null ? (
          <p className="muted"><Spinner /> Loading examples…</p>
        ) : samples.length === 0 ? (
          <p className="muted">No examples on this server.</p>
        ) : (
          <div className="samples">
            {samples.map((s) => <SampleCard key={s.id} sample={s} health={health} />)}
          </div>
        )}
      </section>

      <section className="section scope" aria-labelledby="scope-title">
        <p className="eyebrow">What it can rebuild</p>
        <h2 id="scope-title">Flat parts, honestly.</h2>
        <div className="scope-grid">
          <div className="scope-card scope-yes">
            <h3>Works well</h3>
            <ul>
              <li>Flat parts of even thickness: brackets, plates, clips, spacers, washers, covers</li>
              <li>Through-holes and slots</li>
              <li>A broken part whose surviving half shows its symmetry</li>
            </ul>
          </div>
          <div className="scope-card scope-no">
            <h3>Refused, with a reason</h3>
            <ul>
              <li>Rounded, hollow or 3D objects: knobs, pipes, caps, tools of varying thickness</li>
              <li>Parts with threads, ribs or several thicknesses</li>
              <li>Anything safety-critical</li>
            </ul>
          </div>
        </div>
      </section>

      <section className="cta-band">
        <h2>Ready when your part is.</h2>
        <a className="button button-primary button-lg" href={href({ name: "new" })}>Start a repair</a>
      </section>
    </div>
  );
}
