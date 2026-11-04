// Plain-language copy for the simple view. The server's own message is always shown too, under "Details".

export interface ErrorCopy {
  title: string;
  tips: string[];
  /** Offer to run the same photo again without the AI service. */
  offerNoAi?: boolean;
  /** Point back to the photo guide. */
  reshoot?: boolean;
}

const MAT_TIPS = [
  "All 12 black squares of the printed mat should be in the photo, uncovered.",
  "Lay the mat flat on a hard table. A curled corner or a binder underneath bends it.",
  "Avoid glare on the paper: diffuse daylight, no flash.",
];

const AI_DOWN: ErrorCopy = {
  title: "The AI service didn't answer",
  tips: ["This is usually temporary. Try again in a moment.", "Or run the same photo without AI: the outline is then found by colour contrast."],
  offerNoAi: true,
};

export const ERROR_COPY: Record<string, ErrorCopy> = {
  UPLOAD_EMPTY: { title: "That file is empty", tips: ["Choose the photo again."] },
  UPLOAD_TOO_LARGE: { title: "That photo is too large", tips: ["Photos up to 20 MB are accepted. Use your phone's original JPEG."] },
  UPLOAD_NOT_IMAGE: {
    title: "That file isn't a photo Re-Forge can read",
    tips: ["Use a JPEG or PNG.", "On iPhone, HEIC photos aren't read yet: set Settings → Camera → Formats → Most Compatible, or export the photo as JPEG."],
  },
  UPLOAD_TOO_MANY_PIXELS: { title: "That photo has too many pixels", tips: ["Photos up to 40 megapixels are accepted."] },
  CAL_MARKERS_INSUFFICIENT: { title: "We couldn't find the mat", tips: MAT_TIPS, reshoot: true },
  CAL_MAT_NOT_FLAT: {
    title: "The mat isn't lying flat",
    tips: ["Lay it on a hard, flat table, not on a book or a binder.", "Tape the corners down if the paper curls."],
    reshoot: true,
  },
  CAL_HOMOGRAPHY_FAILED: { title: "The mat's markers don't line up", tips: MAT_TIPS, reshoot: true },
  CAL_LAYOUT_AMBIGUOUS: { title: "Too little of the mat is visible", tips: MAT_TIPS, reshoot: true },
  CAL_MARKERS_CLUSTERED: { title: "Too little of the mat is visible", tips: MAT_TIPS, reshoot: true },
  CAL_MARKERS_REJECTED: { title: "Some of the mat's markers disagree", tips: MAT_TIPS, reshoot: true },
  CAL_SCALE_OUT_OF_RANGE: {
    title: "A check-bar reading looks wrong",
    tips: [
      "Each printed bar should measure about 100 mm. Leave the fields empty if you haven't measured them.",
      "If a bar really measures much less, the mat was printed with \"fit to page\": reprint it at 100 % (actual size).",
    ],
  },
  SEG_NO_PART: {
    title: "We couldn't find a part on the mat",
    tips: ["Place the part inside the corner marks, away from the black squares.", "A part that contrasts with the white paper works best."],
    reshoot: true,
  },
  TRACE_PARTIAL: {
    title: "Only part of the object was traced",
    tips: ["Photograph one part alone on the mat.", "Multi-coloured or patterned objects can't be traced as one outline yet."],
    reshoot: true,
  },
  FAMILY_UNSUPPORTED: {
    title: "This isn't a part Re-Forge can rebuild yet",
    tips: [
      "Re-Forge rebuilds flat parts of even thickness: brackets, plates, clips, spacers, washers.",
      "Rounded, hollow or 3D objects need more than one photo, which isn't supported yet. Nothing was built, on purpose.",
    ],
  },
  PROFILE_EMPTY_MASK: { title: "We couldn't trace the part's edge", tips: ["Try a part that contrasts with the white paper, in even light."], reshoot: true },
  PROFILE_NO_CONTOUR: { title: "We couldn't trace the part's edge", tips: ["Try a part that contrasts with the white paper, in even light."], reshoot: true },
  PROFILE_NO_BACKGROUND: { title: "We couldn't see the mat around the part", tips: ["Keep the part away from the mat's edges and markers."], reshoot: true },
  PROFILE_MASK_SHAPE: { title: "We couldn't trace the part's edge", tips: ["Try again; if it repeats, reshoot the photo."] },
  HEIGHT_CORRECTION_FAILED: {
    title: "The camera position couldn't be worked out",
    tips: ["Shoot from directly above, holding the phone parallel to the mat.", "Upload the original photo file, not a screenshot."],
    reshoot: true,
  },
  POSE_INVALID: { title: "The camera position couldn't be worked out", tips: ["Shoot from directly above, holding the phone parallel to the mat."], reshoot: true },
  SPEC_INVALID: { title: "The traced shape can't be built", tips: ["A wall or a hole came out thinner than a printer can make. Check the photo, or reduce the hole allowance."] },
  IMAGE_INVALID: { title: "The photo couldn't be read", tips: ["Try another JPEG or PNG."] },
  META_KEY_MISSING: {
    title: "AI isn't set up on this server",
    tips: ["Run without AI (Advanced options), or set the Meta Model API key on the server."],
    offerNoAi: true,
  },
  META_TIMEOUT: AI_DOWN,
  META_UNREACHABLE: AI_DOWN,
  META_ERROR: AI_DOWN,
  META_RATE_LIMITED: { ...AI_DOWN, title: "The AI service is busy" },
  META_AUTH: { title: "The AI service refused this server's key", tips: ["The server's Meta Model API key needs checking.", "You can still run without AI."], offerNoAi: true },
  META_FORBIDDEN: { title: "The AI service refused this server's key", tips: ["The server's Meta Model API key needs checking.", "You can still run without AI."], offerNoAi: true },
  BUDGET_EXCEEDED: { title: "Today's AI budget is used up", tips: ["Run without AI, or come back tomorrow."], offerNoAi: true },
  CONTRIBUTOR_TIER_BLOCKED: { title: "That AI model isn't allowed for uploads", tips: ["The server is configured to protect uploaded photos."] },
  SERVER_BUSY: { title: "Re-Forge is busy", tips: ["Several parts are being analysed right now. Try again in a minute."] },
  JOB_INTERRUPTED: { title: "This analysis was interrupted", tips: ["The server restarted while it ran. Run it again."] },
  JOB_NOT_FOUND: { title: "That analysis isn't on this server any more", tips: ["Upload the photo again."] },
  JOB_OUTDATED: { title: "This analysis was made by an older version", tips: ["Its report lacks the uncertainty estimates this page shows. Run it again on the same photo."] },
  NETWORK: { title: "Can't reach Re-Forge", tips: ["Check your connection, and that the server is running."] },
  INTERNAL_ERROR: { title: "Something went wrong on our side", tips: ["Try again. If it happens again, note the job id below."] },
  REQUEST_INVALID: { title: "Some values aren't valid", tips: ["Check the thickness and the bar readings."] },
};

export const hasCopy = (code: string): boolean => code in ERROR_COPY;

export function errorCopy(code: string): ErrorCopy {
  if (ERROR_COPY[code]) return ERROR_COPY[code];
  if (code.startsWith("META_")) return AI_DOWN;
  if (code.startsWith("CAL_")) return { title: "We couldn't use the mat in this photo", tips: MAT_TIPS, reshoot: true };
  if (code.startsWith("RULER_")) return {
    title: "We couldn't use the entered length",
    tips: ["Enter the part's longest side in mm, measured with a ruler.",
           "Photograph the whole part straight from above on a plain contrasting background."],
    reshoot: true,
  };
  return { title: "The analysis stopped", tips: ["Try again, or try another photo."] };
}

/** Photo-quality warnings, in plain words. The server's message stays available under the technical details. */
export const WARNING_COPY: Record<string, string> = {
  CAL_HIGH_RESIDUAL: "The mat may not be perfectly flat, which can shift measurements by a few tenths of a millimetre.",
  CAL_STRONG_TILT: "The photo was taken at an angle. Straight from above is more accurate.",
  CAL_LOW_RESOLUTION: "The photo is low on detail. Step back less, or use the 2× lens.",
  CAL_OVEREXPOSED: "Part of the mat is overexposed. Avoid direct light or flash.",
  CAL_MARKERS_REJECTED: "Some of the mat's markers were ignored because they disagreed. Is a corner lifted?",
  CAL_PARTIAL_MARKERS: "Some of the mat's markers weren't found.",
  CAL_MARKERS_CLUSTERED: "The markers found are bunched together, so the mat's geometry is less certain.",
  POSE_FOCAL_ASSUMED: "The photo carries no lens information, so the height correction used a typical phone lens. Upload the original file for the best result.",
  POSE_FOCAL_MISMATCH: "The photo's lens information didn't match the mat's perspective, so the mat's was used.",
  PROFILE_LOW_CONTRAST: "The part's edge has low contrast against the paper, so its outline is less precise.",
  PROFILE_NONUNIFORM_COLOUR: "The part isn't a single colour, which can confuse the outline.",
  PROFILE_PARTIAL: "Part of the outline couldn't be refined.",
  PROFILE_MULTIPLE_REGIONS: "Several separate objects were found; the largest was measured.",
  PROFILE_BAND_SATURATED: "Part of the edge is very bright or very dark, so it's less precise.",
};

export interface StageCopy {
  label: string;
  detail: (ai: { segment: boolean; interpret: boolean }) => string;
  model?: (ai: { segment: boolean; interpret: boolean }, health?: { seg: string; reason: string }) => string | null;
}

export const STAGE_COPY: Record<string, StageCopy> = {
  load: { label: "Reading your photo", detail: () => "Checking the image and the lens information it carries." },
  calibrate_rectify: {
    label: "Finding the mat",
    detail: () => "Its 12 printed markers turn pixels into true millimetres and undo the camera's perspective.",
  },
  segment: {
    label: "Finding your part",
    detail: (ai) => (ai.segment ? "AI separates the part from the mat." : "Colour contrast separates the part from the mat (no AI)."),
    model: (ai, h) => (ai.segment ? h?.seg ?? "SAM 3.1" : null),
  },
  refine: {
    label: "Tracing the edges",
    detail: () => "Edges are located to a fraction of a pixel; holes are found and measured.",
  },
  pose_height: {
    label: "Correcting for height",
    detail: () => "The part's top face sits closer to the camera, so it looks slightly bigger. That is removed.",
  },
  interpret_reconstruct: {
    label: "Reading the damage",
    detail: (ai) =>
      ai.interpret
        ? "AI looks for broken edges and symmetry. Geometry then checks every claim before anything is rebuilt."
        : "A geometric rule looks for broken edges and symmetry (no AI).",
    model: (ai, h) => (ai.interpret ? h?.reason ?? "Muse Spark" : null),
  },
  spec_build_validate: { label: "Building the 3D model", detail: () => "A watertight solid is built and checked for printing." },
  write: { label: "Preparing your files", detail: () => "The printable STL, the editable OpenSCAD file and the evidence report." },
};

export const STATUS_COPY: Record<string, { label: string; short: string; explain: string }> = {
  MEASURED: { label: "Measured by you", short: "Measured", explain: "You entered it from a caliper reading." },
  OBSERVED: { label: "Measured from the photo", short: "From photo", explain: "Computed from the calibrated photo." },
  INFERRED: {
    label: "Rebuilt by symmetry",
    short: "Rebuilt",
    explain: "Not in the photo: mirrored from the intact side, after the symmetry was checked against the surviving outline.",
  },
  UNCERTAIN: { label: "Uncertain", short: "Uncertain", explain: "Not enough evidence. Check it before you rely on it." },
};
