# 技术方法：片子是怎么做出来的

本库每一支片子都是用代码做的：不用素材库画面，默认也不用视频生成。遇到手画成本很高的运动（水、烟、布料、人群、转头），可以让视频模型在**代码画好的关键帧之间**补运动（见 §13），画风仍由代码决定。这一页讲清楚整条管线，你可以用 `core/` 里的现成工具，也可以在自己的技术栈里重做。配合 [导演方法](DIRECTOR.md) 和某个风格的 `styles/<slug>/STYLE.md` 一起用。English: [TECHNIQUE.md](../../TECHNIQUE.md)

```
时间线（唯一的数据来源）
   ├─► 画面：网页暴露 render(t) ──► 无头 Chrome 逐帧截图 ──► video.mp4
   ├─► 配音：逐句 TTS ──► 语音识别校对 ──► 逐词时间戳
   ├─► 配乐：按同一时间线写谱（采样 + 合成）──► 分轨
   ├─► 音效：在事件时间点程序化生成拟音
   └─► 字幕：.srt + 烧录字幕
混音（让路、压缩、配平）──► ffmpeg 合成，两遍 loudnorm 到 −14 LUFS ──► 成片.mp4
```

## 1. 环境

| 工具 | 用途 |
|---|---|
| Node 20+ | 渲染页面：`npm install` 安装 `playwright-core` 和 `three`，再用 `npx playwright-core install chromium-headless-shell` 下载无头浏览器 |
| ffmpeg | 编码、合成、响度、黑帧检查 |
| Python 3.11+（我们用 [uv](https://docs.astral.sh/uv/)） | `uv venv && uv pip install -r requirements.txt`（numpy、scipy、soundfile、soxr、librosa、pillow、kokoro-onnx、edge-tts、faster-whisper） |

大文件不在 git 里，用到哪一步再下载：

```sh
sh tools/fetch.sh voice          # Kokoro 配音模型（约 340 MB）→ core/tts/
sh tools/fetch.sh instruments    # CC0 / CC BY 采样库（约 1.35 GB）→ core/audio/instruments/
sh tools/fetch.sh hdri           # 3D 风格用的 Poly Haven 环境光 → core/assets/polyhaven/
```

## 2. 画面是时间的函数

每支片子是一个静态网页，暴露：

```js
window.DUR = 54.2;                 // 总时长（秒）
window.render = (t) => { ... };    // 画出第 t 秒，确定性
window.READY = true;               // 字体、图片加载完后设置
window.EV = [{t, type, ...}];      // 可选：给混音用的音效 / 卡点事件
```

让它可靠的几条规则：

- **确定性**：不用 `Date.now()`，随机数一律带种子（`core/lib.js` 有 `mulberry`、`hash`），不依赖上一帧的状态。任何一帧都能单独、按任意顺序、由任意 worker 渲出来。
- **引擎**：大多数 2D 风格用 Canvas 2D；3D 用 three.js（`core/three/post.js`：物理景深、GTAO、辉光、调色、2× 超采样）；后期用 WebGL2 着色器（胶片老化、CRT、墨线重画）。
- **按风格需要做"一拍二"**（定格、像素、赛璐璐用 12 fps 步进），但机位和光每帧都要平滑。机位也步进，会被看成卡顿。
- **只用一个世界坐标 → 画面坐标的函数**。所有跟着主体走的效果（光圈、推镜、追光）都经过它，不要手填画面坐标。

截图渲染（`core/render/`）：

```sh
node core/render/still.mjs <demo> 1.5 12 --range 0:50:2   # 审片静帧；页面报错立即退出
node core/render/video.mjs <demo> --fps 24 --workers 3     # 渲全部帧 → out/video24.mp4
node core/render/events.mjs <demo>                         # 导出 DUR + EV → events.json
```

提速的关键：**截图用 JPEG**（比 PNG 快约 8 倍）；**每个 worker 各开一个浏览器**（共用一个浏览器几乎不并行）；**胶片颗粒在 ffmpeg 里加**，不要画在页面里，否则每一帧都压缩不动，很慢。

## 3. 一条时间线驱动一切

段落、速度、拍子、卡点都写在一个文件里（`timeline.js`），导出成 JSON，配乐、混音、字幕和检查脚本都读同一套数字：

```js
export const SECS = [{ id: 'chase', t: 12.0, bpm: 144, beats: 12 }, ...];
export const HIT  = { pratfall: ['chase', 6], ... };   // 段落 + 第几拍
```

用一个小脚本（好几支样片里的 `tools/cuecheck.py`）比对每个画面卡点和它应该落上的音乐 cue，目标偏差 0 毫秒。

## 4. 配音

- **TTS 只是默认素材**。用户给了录音或指定了声线，就用用户的。否则：
  - **英文**：[Kokoro](https://github.com/thewh1teagle/kokoro-onnx) 在本地运行，声线好（`af_heart`、`bm_george`、`am_michael` 等）。`core/tts/tts.py lines.json out/` 每句输出一个 WAV 和时长表。
  - **中文**：[edge-tts](https://github.com/rany2/edge-tts)，用微软的神经网络声线（`zh-CN-XiaoxiaoNeural`、`zh-CN-YunxiNeural` 等），需要联网。逐句语速和去首尾静音的写法见 `styles/paper-lantern/demo/tts.py`。音频要商用前，先看微软的使用条款。
- 数字在 TTS 文本里拼写成单词，字幕里写阿拉伯数字。
- **逐句校对**：`core/tts/asr_check.py` 用 faster-whisper 转写每个 WAV 并和脚本比对，不通过就重新生成，直到全部通过。它同时输出逐词时间戳，用来摆放台词和字幕。
- **混音前**：TTS 峰均比很高，先压缩人声，再按 RMS 配平，人声比音乐高约 10 dB。

## 5. 配乐

按 cue map 写原创配乐。不要随手用通用的钢琴加弦乐；每个风格有自己的编制（见 `STYLE.md` §6）。

- **采样**：`core/audio/sampler.py` 用免费采样库演奏真乐器：[VSCO 2 CE](https://github.com/sgossner/VSCO-2-CE) 和 [VCSL](https://github.com/sgossner/VCSL)（CC0）、[FreePats](https://freepats.zenvoid.org)（CC0）、[Karoryfer](https://github.com/sfzinstruments)（CC0）、Salamander 三角钢琴（CC BY 3.0）、MuldjordKit 鼓组（CC BY 4.0）。谱子写成事件 `(时间, 乐器, 音高, 时值, 力度, 声像)`；长音无缝延长，多采样轮换避免"机关枪"感。完整清单见 `core/audio/INSTRUMENTS.md`。
- **拨弦和民族弦乐**（古琴、琵琶、三味线、班卓琴……）：`core/audio/pluck.py`，物理建模（Karplus–Strong），支持滑音和揉弦。
- **合成**：芯片音乐、铺底、效果音用 numpy 合成。
- **控制低频**：合成配乐很容易低频过重。混完按频段算能量，20–120 Hz 相对其余频段保持在 −3 dB 左右；铺底跳过 MIDI 48 以下的音；贝斯加二、三次谐波，小喇叭上也听得见。

## 6. 音效与混音

- `core/audio/sfx.py` 程序化合成拟音（click、whoosh、thump、ding、纸张、噪声底……），带滤波、包络和 `add(buffer, sound, at, gain, pan)`。用 `window.EV` 驱动，每个声音都精确落在它那一帧上。
- 三层：环境底、拟音、音乐。人声和关键拟音出现时，音乐让路。静音要事先设计。
- **母带**：`sh core/render/mux.sh video.mp4 mix.wav out.mp4 24 [grain]` 合成音画，两遍 loudnorm 到 −14 LUFS 并限制真峰值，在 ffmpeg 里加颗粒，最后打印实测响度。浅色底的片子颗粒要少一些。
- 画面里自带颗粒的片子压缩效率很差，用 `-tune grain` 和更高的 CRF 重新编码。

## 7. 字幕

- 用 `core/render/srt.py cues.json out.srt` 导出 `.srt`（cues = `[{t0, t1, text}]`），样式化的字幕直接画在页面里：字幕设计也是风格的一部分。
- 时长规则见导演方法 §7（至少 1.8 秒，且不短于语音 + 0.6 秒）。

## 8. 审片流程

1. 缩略图总览：用 `still.mjs --range` 每 1–2 秒渲一帧，再用 `core/render/sheet.py` 拼图。至少完整看两轮。
2. 每个关键动作按 0.2 秒抽帧：交接、摔倒、撞击。
3. 成片文件上：`ffmpeg -af ebur128`（响度）、`blackdetect`（空白帧）；有人声的话，对最终混音再跑一次 whisper。
4. 带声音、全速完整看一遍。

## 9. 3D 要点

- three.js r170 通过 WebGL2 在 GPU 上无头渲染；物理景深和 GTAO 用 `core/three/post.js`，按 2 倍分辨率渲染再缩小。
- 光：柔光面光源加低强度的 Poly Haven 环境光，比明亮的环境光更"真"。
- 正交相机做深度效果要用 `orthographicDepthToViewZ`（用透视版本，景深会悄悄失效）。

## 10. 代码画的角色

- 2.5D 骨骼（躯干、头、四肢逐帧求解）足够做哑剧表演。姿势用关键帧加缓动混合。
- 肩关节先外展、再前屈；顺序反过来，举起的双臂会交叉成 X。
- 抬手时肩带要上提、前移；手臂压在躯干上的那段不要描轮廓线。那条线正是关节看起来像木偶接缝的原因。
- 做镜头动画前，先画一张大尺寸动作测试表（前伸、举手、跑、跪）。

## 11. 素材与署名

只用 CC0、CC BY、OFL 素材，每条都写进片子的 `CREDITS`，注明来源和授权。`core/audio/sampler.py` 的 `credits(names)` 会按你用到的乐器生成必须写的署名行。字体用 Google Fonts（OFL），放进项目自托管，中日韩字体按用到的字做子集。

## 12. 去哪个样片里找参考

| 你需要…… | 看这里 |
|---|---|
| 2D 角色动画和口型 | `styles/scifi-toon/`、`styles/cel-anime-80s/` |
| 时间线驱动的配乐和卡点检查 | `styles/microgame/`、`styles/silent-film/` |
| 画面转墨线重画和胶片老化后期 | `styles/silent-film/demo/engine/` |
| 笔刷 / 笔触引擎 | `styles/watercolor/`、`styles/ink-wash/`、`styles/impasto/` |
| 带景深和真实材质的 3D | `styles/brick-toy/`、`styles/paper-popup/` |
| CRT / 录像带质感 | `core/post/crt.js`、`styles/ascii-crt/`、`styles/backrooms/` |

每个风格 `STYLE.md` 的 §9 记录了这支样片是怎么做的。我们的样片是参考实现：读它们，看某个技法怎么实现，再写你自己的片子。它们不是用来重建我们原片的套件。

## 13. 生成运动（可选）

视频模型只用于个别镜头，不取代页面：代码画定画风的帧，模型只补运动。

1. **关键帧来自页面。** 用 `still.mjs` 按成片分辨率渲出镜头首帧（有落点时再渲尾帧），不加颗粒和字幕。
2. **生成。** 在 `shots.json` 里列镜头（`id`、`prompt`、`first`、`last`、`dur`、`seed`，可选 `model`、`args`、`keys`），运行
   ```sh
   python core/gen/genvideo.py films/<name>/shots.json films/<name>/gen --provider fal   # 或 replicate；需 FAL_KEY / REPLICATE_API_TOKEN
   python core/gen/genvideo.py films/<name>/shots.json films/<name>/gen --provider mock  # 免费离线叠化，先对好时间
   ```
   片段切成 JPEG 帧并按输入哈希缓存，只重发改过的镜头（`--force s03` 重抽）。
3. **在 render(t) 里播放。** `core/gen/clip.js`：`READY` 前 `loadClips('gen/')`，之后 `drawClip(ctx, clips, 's03', t - t0, 0, 0, W, H, { fit: 'stretch', span })`。调色、纸纹、描线、字幕和后期仍在上面由代码画，让生成镜头和手画镜头属于同一部片。一拍二的风格用 `step: 12`。
4. **像审其它镜头一样审。** 每 0.2 s 出一张联系表：颜色、线宽或角色设计漂移、手部融化、凭空出现的文字都判废。换 seed 重抽、缩短时长，或改回手画。

提示词只写运动（"纸船向左漂，涟漪散开，机位固定"），画风已在关键帧里。生成镜头要短（2–5 s）且少。每个片段的服务商、模型和提示词记入该片 `CREDITS`（工具会写进 `gen/clips.json`），并遵守模型对输出的许可条款。
