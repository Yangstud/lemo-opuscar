# core/ · 共用制作管线

所有命令在仓库根目录运行；Python 用 `.venv/bin/python`（共享环境，**不要往里装包**）。

## 页面约定
demo 是一个静态页面 `styles/<slug>/demo/index.html`（仓库根作为静态服务根，可引用 `/core/...`、`/node_modules/three/...`），页面必须暴露：
- `window.READY = true`（资源加载完）
- `window.render(t)`：画出第 t 秒的画面（确定性，不依赖真实时间）
- `window.DUR`：总时长（秒）
- 可选 `window.EV = [{t, type, ...}]`：音效/对白/配乐 cue 事件，`events.mjs` 导出给混音脚本

## 渲染
| 命令 | 作用 |
|---|---|
| `node core/render/still.mjs <demo> 1.5 3 [--range 0:50:2.5] [--q 'k=v'] [--prefix t_] [--out dir]` | 渲静帧；页面报错立即退出 |
| `node core/render/video.mjs <demo> --fps 24 [--workers 3] [--q 'k=v'] [--out <demo>/out/video24.mp4]` | 逐帧渲视频。多片并行时 workers 保持 3 |
| `node core/render/events.mjs <demo>` | 导出 `<demo>/events.json`（dur + EV） |
| `.venv/bin/python core/render/sheet.py out.jpg img... [--cols 4] [--w 480]` | 缩略图总览（审片） |
| `.venv/bin/python core/render/srt.py cues.json out.srt` | 字幕导出（cues = [{t0,t1,text}]） |
| `sh core/render/mux.sh video.mp4 mix.wav out.mp4 24 [grain]` | 合成成片：两遍 loudnorm −14 LUFS；grain 默认 2，0 = 不加颗粒；结尾打印 ebur128 实测 |

## 音频
| 文件 | 作用 |
|---|---|
| `core/tts/tts.py lines.json out_dir` | Kokoro 英文配音（`voice`、`speed`），输出 wav + dur.json |
| `core/tts/asr_check.py lines.json voices_dir` | whisper 逐句校对（补静音、`asr` 字段覆盖期望文本），输出 words.json 逐词时间戳 |
| `core/audio/sfx.py` | 程序化音效与混音工具：滤波、包络、click/whoosh/thump/ding…、`compress`、`limit`、`add(buf, x, at, gain, pan)` |
| `core/audio/sampler.py`、`pluck.py` | 采样乐器 + 物理建模拨弦（见 `core/audio/INSTRUMENTS.md`，最后一行 `STATUS: READY` 才可用） |

## 生成运动（可选）
| 文件 | 作用 |
|---|---|
| `core/gen/genvideo.py shots.json out_dir [--provider fal\|replicate\|mock] [--fps 24] [--force id,..]` | 以代码渲出的首/尾帧做图生视频，切帧缓存到 `out_dir/<id>/`，索引 `clips.json`；`mock` 离线叠化用于调时间 |
| `core/gen/clip.js` | `loadClips(base)`、`drawClip(ctx, clips, id, lt, x, y, w, h, {fit, span, step})`：在 render(t) 里按时间确定性取帧 |

## 画面
| 文件 | 作用 |
|---|---|
| `core/lib.js` | 确定性随机 `mulberry`、`hash`、`vnoise`、缓动（ss/eio/eo/back/spring）、单调三次插值 `monotone`/`track`、包络 `env` |
| `core/three/post.js` | three.js 后期：物理景深、GTAO、辉光、调色、2× 超采样（见 brick-toy） |
| `core/post/crt.js` | WebGL2 CRT/录像带后期（扫描线、光栅、色度渗色、荧光辉光、开机、跟踪噪声），2D 画布输入 |
| `core/fonts/` | Fredoka、ZCOOL KuaiLe；其它字体自行下载 OFL 字体放进自己的 demo/fonts/ |
| `core/assets/polyhaven/` | CC0 HDRI、胡桃木桌面、台灯、茶具（见 SOURCES.md） |

## 参考实现
- `styles/brick-toy/`：3D（three.js）+ 物理 + 景深，STYLE.md 是标准格式
- `styles/scifi-toon/`：2D 矢量卡通、角色口型、原创配乐
- `styles/cel-anime-80s/`：2D 赛璐璐、角色设定表流程、CRT 后期、配乐 fork 子 agent
- 三者 `STYLE.md` 的 §8 记录了踩过的坑，开工前读
