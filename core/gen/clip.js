// Play generated clips (core/gen/genvideo.py) inside a deterministic render(t).
//   const clips = await loadClips('gen/');                // reads gen/clips.json, preloads every frame
//   drawClip(ctx, clips, 's03', t - 12.0, 0, 0, W, H, { fit: 'stretch', span: 4.0 });
// Frames are picked by time, never by wall clock, so any frame renders alone and in any order.
export async function loadClips(base, ids) {
  if (!base.endsWith('/')) base += '/';
  const index = await (await fetch(base + 'clips.json')).json();
  const out = {};
  await Promise.all(Object.entries(index).filter(([id]) => !ids || ids.includes(id)).map(async ([id, c]) => {
    const frames = await Promise.all(Array.from({ length: c.n }, (_, i) => new Promise((ok, bad) => {
      const img = new Image();
      img.onload = () => ok(img); img.onerror = () => bad(new Error(`clip ${id}: frame ${i + 1} missing`));
      img.src = `${base}${id}/f_${String(i + 1).padStart(5, '0')}.jpg`;
    })));
    out[id] = { ...c, frames };
  }));
  return out;
}

// Frame for local time lt (seconds since the shot starts).
//   fit 'hold'    : play at native speed, hold the last frame (default)
//   fit 'stretch' : retime the whole clip to last `span` seconds (fit a generated 5 s clip to a 3.2 s beat)
//   fit 'loop'    : loop at native speed
//   step          : fps to step at (e.g. 12 for styles animated on twos)
export function clipFrame(clip, lt, { fit = 'hold', span = clip.dur, step = 0 } = {}) {
  let u = fit === 'stretch' ? (lt / span) * clip.dur : lt;
  if (fit === 'loop') u = ((u % clip.dur) + clip.dur) % clip.dur;
  if (step) u = Math.floor(u * step) / step;
  const i = Math.min(clip.n - 1, Math.max(0, Math.floor(u * clip.fps + 1e-6)));
  return clip.frames[i];
}

// Draw it cover-fitted into (x, y, w, h). Grade, grain and overlays stay in your own code, drawn on top.
export function drawClip(ctx, clips, id, lt, x, y, w, h, opt = {}) {
  const clip = clips[id]; if (!clip) throw new Error(`no clip ${id}`);
  const img = clipFrame(clip, lt, opt);
  const s = Math.max(w / img.width, h / img.height), sw = w / s, sh = h / s;
  ctx.drawImage(img, (img.width - sw) / 2, (img.height - sh) / 2, sw, sh, x, y, w, h);
  return img;
}
