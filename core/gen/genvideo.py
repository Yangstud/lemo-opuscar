"""Generate video clips from keyframes drawn in code, for use inside render(t).

The code still owns the look: every clip starts (and optionally ends) on a frame
rendered by the film's own page. The model only animates between them. Clips are
downloaded, cut into JPEG frames and cached, so render(t) stays deterministic.

  python core/gen/genvideo.py shots.json out_dir [--provider fal|replicate|mock] [--fps 24] [--force id,...]

shots.json:
  [{"id": "s03", "prompt": "the paper boat drifts left, water ripples, camera still",
    "first": "stills/t_12.00.jpg", "last": "stills/t_16.00.jpg",   # last is optional
    "dur": 5, "seed": 7,
    "model": "fal-ai/kling-video/v2.1/pro/image-to-video",          # optional
    "args": {"negative_prompt": "text, watermark"},                  # passed through to the model
    "keys": {"first": "image_url", "last": "tail_image_url"}}]       # model's input names, optional

Output: out_dir/<id>/f_00001.jpg … and out_dir/clips.json {id: {fps, n, dur, w, h}},
read by core/gen/clip.js. Inputs are hashed: an unchanged shot is never re-generated.
Keys: FAL_KEY or REPLICATE_API_TOKEN in the environment. Standard library + Pillow only.
"""
import argparse, base64, hashlib, json, mimetypes, os, shutil, subprocess, sys, time, urllib.request

DEFAULT_MODEL = {
    'fal': 'fal-ai/kling-video/v2.1/pro/image-to-video',
    'replicate': 'kwaivgi/kling-v2.1',
    'mock': 'crossfade',
}
DEFAULT_KEYS = {
    'fal': {'first': 'image_url', 'last': 'tail_image_url'},
    'replicate': {'first': 'start_image', 'last': 'end_image'},
    'mock': {'first': 'first', 'last': 'last'},
}


def data_uri(path):
    mime = mimetypes.guess_type(path)[0] or 'image/jpeg'
    return f'data:{mime};base64,' + base64.b64encode(open(path, 'rb').read()).decode()


def http(method, url, headers, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={'Content-Type': 'application/json', **headers})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read())


def poll(fn, what, every=5, limit=1800):
    t0 = time.time()
    while time.time() - t0 < limit:
        done, res = fn()
        if done: return res
        print(f'\r  {what}: waiting {time.time() - t0:4.0f}s', end='', flush=True)
        time.sleep(every)
    sys.exit(f'\n{what}: timed out after {limit}s')


def gen_fal(shot, inputs):
    key = os.environ.get('FAL_KEY') or sys.exit('set FAL_KEY')
    h = {'Authorization': f'Key {key}'}
    job = http('POST', f'https://queue.fal.run/{shot["model"]}', h, inputs)
    def check():
        s = http('GET', job['status_url'], h)
        if s.get('status') == 'COMPLETED': return True, http('GET', job['response_url'], h)
        if s.get('status') in ('FAILED', 'ERROR'): sys.exit(f'\nfal: {s}')
        return False, None
    res = poll(check, shot['id']); print()
    return res['video']['url']


def gen_replicate(shot, inputs):
    key = os.environ.get('REPLICATE_API_TOKEN') or sys.exit('set REPLICATE_API_TOKEN')
    h = {'Authorization': f'Bearer {key}'}
    p = http('POST', f'https://api.replicate.com/v1/models/{shot["model"]}/predictions', h, {'input': inputs})
    def check():
        s = http('GET', p['urls']['get'], h)
        if s['status'] == 'succeeded': return True, s['output']
        if s['status'] in ('failed', 'canceled'): sys.exit(f'\nreplicate: {s.get("error")}')
        return False, None
    out = poll(check, shot['id']); print()
    return out[0] if isinstance(out, list) else out


def gen_mock(shot, inputs, cdir, fps):
    """Offline stand-in: a slow push-in cross-dissolve between the keyframes. Tests the pipeline for free."""
    from PIL import Image
    a = Image.open(shot['first']).convert('RGB')
    b = Image.open(shot['last']).convert('RGB').resize(a.size) if shot.get('last') else a
    n = max(1, round(shot['dur'] * fps)); W, H = a.size
    for i in range(n):
        u = i / max(1, n - 1); z = 1 + 0.06 * u
        f = Image.blend(a, b, u)
        cw, ch = W / z, H / z
        f = f.crop(((W - cw) / 2, (H - ch) / 2, (W + cw) / 2, (H + ch) / 2)).resize((W, H), Image.LANCZOS)
        f.save(os.path.join(cdir, f'f_{i + 1:05d}.jpg'), quality=92)


def to_frames(mp4, cdir, fps):
    if not shutil.which('ffmpeg'): sys.exit('ffmpeg is required to cut clips into frames')
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', mp4, '-vf', f'fps={fps}', '-q:v', '2',
                    os.path.join(cdir, 'f_%05d.jpg')], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('shots'); ap.add_argument('out')
    ap.add_argument('--provider', default='fal', choices=list(DEFAULT_MODEL))
    ap.add_argument('--fps', type=int, default=24)
    ap.add_argument('--force', default='', help='comma-separated shot ids to regenerate')
    a = ap.parse_args()
    base = os.path.dirname(os.path.abspath(a.shots))
    shots = json.load(open(a.shots)); force = set(filter(None, a.force.split(',')))
    os.makedirs(a.out, exist_ok=True)
    idx_path = os.path.join(a.out, 'clips.json')
    index = json.load(open(idx_path)) if os.path.exists(idx_path) else {}

    for shot in shots:
        shot = {'dur': 5, 'model': DEFAULT_MODEL[a.provider], **shot}
        for k in ('first', 'last'):
            if shot.get(k): shot[k] = os.path.join(base, shot[k])
        keys = {**DEFAULT_KEYS[a.provider], **shot.get('keys', {})}
        hs = hashlib.sha256(json.dumps([a.provider, a.fps, shot['model'], shot['prompt'], shot['dur'],
                                        shot.get('seed'), shot.get('args')], sort_keys=True).encode())
        for k in ('first', 'last'):
            if shot.get(k): hs.update(open(shot[k], 'rb').read())
        digest = hs.hexdigest()[:16]
        cdir = os.path.join(a.out, shot['id'])
        if index.get(shot['id'], {}).get('hash') == digest and shot['id'] not in force and os.path.isdir(cdir):
            print(f'= {shot["id"]} cached'); continue

        print(f'→ {shot["id"]} ({a.provider}: {shot["model"]})')
        shutil.rmtree(cdir, ignore_errors=True); os.makedirs(cdir)
        inputs = {'prompt': shot['prompt'], 'duration': shot['dur'], **shot.get('args', {})}
        if shot.get('seed') is not None: inputs['seed'] = shot['seed']
        if a.provider == 'mock':
            gen_mock(shot, inputs, cdir, a.fps)
        else:
            inputs[keys['first']] = data_uri(shot['first'])
            if shot.get('last'): inputs[keys['last']] = data_uri(shot['last'])
            url = (gen_fal if a.provider == 'fal' else gen_replicate)(shot, inputs)
            mp4 = os.path.join(cdir, 'source.mp4')
            urllib.request.urlretrieve(url, mp4)
            to_frames(mp4, cdir, a.fps)

        frames = sorted(f for f in os.listdir(cdir) if f.startswith('f_'))
        from PIL import Image
        w, h = Image.open(os.path.join(cdir, frames[0])).size
        index[shot['id']] = {'fps': a.fps, 'n': len(frames), 'dur': len(frames) / a.fps, 'w': w, 'h': h,
                             'hash': digest, 'provider': a.provider, 'model': shot['model'], 'prompt': shot['prompt']}
        json.dump(index, open(idx_path, 'w'), indent=1, ensure_ascii=False)
        print(f'  {len(frames)} frames {w}×{h}')


if __name__ == '__main__':
    main()
