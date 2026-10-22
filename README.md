# NaiWa Mouse v1.0 · 奶蛙鼠标

（vibe coding 产物，水课上用了四小时：3 小时找素材，1 小时编写 + 整理代码）

**奶蛙**（NaiWa Mouse）是一只黄绿黑的小怪物，现在被做成了 Windows 鼠标指针：
默认探头张望，按住左键举手，右键托腮，系统转圈时打滚。
皮肤是逐像素透明的分层窗口，跟随真实指针、点击穿透、不抢焦点。

当前版本 **1.0.0**，支持 Windows 10 / 11 64 位。

## 效果

启动后皮肤自动生效，只留一个设置窗口：

| 模式 | 表现 |
| --- | --- |
| 极简模式 | 所有状态都是同一枚黄绿黑圆盘（`default.png`，22px），安静不抢眼 |
| 完整模式 | 默认探头；按下左键举手、右键托腮；系统忙时打滚（其余姿态比默认大 1.2 倍） |

完整模式的四个状态：

| 状态 | 触发 | 图像 | 尺寸 |
| --- | --- | --- | --- |
| 默认 | 无操作 | `glimpse.png`（探头） | 22px |
| 左键 | 按下 / 长按 | `left_hand.png`（举手） | 26px |
| 右键 | 按下 | `thinking.png`（托腮） | 26px |
| 等待 | 系统转圈时 | `laugh_sheet.png`（打滚，176 帧） | 29px |

松开按键后自动回到默认状态：左键 90ms，右键 320ms（留出右键菜单的停留感）。

**“等待”不是静置**，而是系统正在忙：光标位置出现转圈圈（`IDC_WAIT` / `IDC_APPSTARTING`）时，
角色切成 `laugh` 循环动画。判定方式是比对当前光标句柄——`SetSystemCursor` 只换掉每个系统
光标槽里的**位图**，槽本身的句柄不变，所以即便皮肤把光标藏成了 1×1 透明，依然能读出系统
此刻在画哪一种。

**窗口关闭 = 最小化到托盘**，皮肤继续生效；要真正退出（并恢复系统鼠标），必须右键
**右下角托盘图标 → 退出（恢复系统鼠标）**。

## 快速开始

### 用源码运行

```bash
pip install -r requirements.txt
python app.py              # 设置窗口 + 皮肤
python app.py --headless   # 只跑皮肤，不要窗口
python app.py --debug      # 带控制台和调试日志
python -m naiwa            # 等价于 python app.py
```

也可以双击 `scripts/run.bat`，它会检查依赖并静默启动。

退出：托盘右键 → 退出，或 `Ctrl+Alt+Q`。

### 用打包好的 exe

`dist/` 是本地构建产物（已加入 `.gitignore`），clone 下来后需要自己打包：

```bash
pip install -r requirements-dev.txt
python tools/build_exe.py            # 单文件 → dist/NaiWaMouse.exe
python tools/build_exe.py --onedir   # 文件夹 → dist/NaiWaMouse/NaiWaMouse.exe
```

| 版本 | 启动耗时 | 适合 |
| --- | --- | --- |
| 文件夹版 | ~0.6s | 日常使用 |
| 单文件版 | ~5s（每次解包到临时目录） | 便携、放 U 盘 |

首次运行 Windows 可能弹 SmartScreen 或杀软提示（exe 没有代码签名），
点「更多信息 → 仍要运行」；文件夹版首次启动约 25s，是杀软在扫描新解压的文件。

## 热键

| 热键 | 作用 |
| --- | --- |
| `Ctrl+Alt+Q` | 退出（并恢复系统光标） |
| `Ctrl+Alt+S` | 显示 / 隐藏皮肤 |
| `Ctrl+Alt+H` | 临时显示 / 隐藏系统光标 |

## 配置

根目录的 `config.json`（打包后位于 exe 旁边）：

```json
"mode": "full",
"modes": {
  "minimal": { "asset": "default.png", "height": 22, "anchor": "center" },
  "full":    { "others_scale": 1.2 }
},
"states": {
  "idle":  { "asset": "glimpse.png",   "height": 22, "anchor": "center" },
  "left":  { "asset": "left_hand.png", "height": 22, "anchor": "bottom", "press_offset": 1 },
  "right": { "asset": "thinking.png",  "height": 22, "anchor": "bottom" },
  "wait":  { "sheet": "laugh_sheet.png", "scale": 1.1, "anchor": "center" }
}
```

- `mode` — 当前模式，界面上切换时写回，下次启动沿用
- `modes.minimal` — 极简模式的唯一姿态，四个状态全部套用它（同一张图、同一尺寸）
- `modes.full.others_scale` — 完整模式下**除 `idle` 外**所有姿态的放大倍数（1.2 → 26 / 29px）
- `asset` — `assets/` 里的 PNG 文件名（可用相对子目录，如 `poses/hug.png`）
- `sheet` — `assets/` 里的贴图集；同名 `.json` 里有帧数、网格和帧间隔，自动循环
- `height` — 图像**可见部分**的目标高度（px，会自动乘 DPI 缩放）
- `scale` — 没写 `height` 时，按 `idle` 高度的倍数算（`wait` 是 1.1 倍 → 24px）
- `anchor` — 指针锚点：`center`（指针在图像中心）/ `bottom`（脚踩指针）/ `top`
- `press_offset` — 按下时额外的垂直位移，做出“下沉”的手感

`idle` 保持 22px，和 Windows 指针（32px 画框、常见箭头约 22px 视觉高度）同级；
想让动作更明显，把 `modes.full.others_scale` 调到 2~3 即可，不用逐个改 `height`。

### 换姿势

`assets/poses/` 里准备了 6 个备用姿态：

```text
amazing  big_love  handup  hug  right_hand  sayyes
```

把任意一个填进 `asset` 就能换动作，例如：

```json
"right": { "asset": "poses/hug.png", "height": 22, "anchor": "bottom" }
```

这些备用图不会打进 exe（`tools/build_exe.py` 只收集 `assets/` 顶层的运行期素材），
想用的话从源码运行，或者在 `config.json` 里保留默认素材。

### 换素材

处理后的透明 PNG 已随仓库提交，运行不需要原始素材。要重新生成，需要把原始渲染图
（`.jpg` 静态图、`.gif` 动图）放在**仓库上一级目录**，然后：

```bash
python tools/build_assets.py            # 全部重建
python tools/build_assets.py thinking   # 只重建一张
python tools/build_assets.py laugh      # 只重建一个动图
```

动图会被拆成贴图集：`laugh` → `assets/laugh_sheet.png`（16 列网格）+ `laugh_sheet.json`
（帧数 / 网格 / 帧间隔），另出一份 `assets/laugh_preview.png`（APNG）给预览页用。
新增动图只需在 `tools/build_assets.py` 的 `FLIPBOOKS` 里加一条，再在 `config.json`
里用 `sheet` 引用它。

浏览器里的交互预览：打开 `docs/preview.html`（直接读 `../assets/`，不需要服务器）。

## 打包与分发

```bash
python tools/package.py
```

产出两个压缩包，都解压成单个 `NaiWaMouse/` 文件夹，双击 exe 即用：

| 压缩包 | 内容 | 适合 |
| --- | --- | --- |
| `dist/NaiWaMouse-文件夹版.zip` | exe + `_internal/` | 日常使用，启动快 |
| `dist/NaiWaMouse-单文件版.zip` | 一个 exe + 配置 | 只要一个文件、便携 |

包里已经带了 `使用说明.txt` 和 `恢复光标.bat`。对方需要知道的只有三件事：

1. 解压后双击 `NaiWaMouse.exe`
2. `Ctrl+Alt+Q` 退出（会自动恢复系统光标）
3. 被 SmartScreen 拦就点「更多信息 → 仍要运行」

仅支持 Windows 10/11 64 位；exe 未做代码签名，部分杀软可能误报。

## 目录结构

```text
mouse/
├─ app.py                    启动入口（PyInstaller 入口，一行转进 naiwa.app）
├─ naiwa/                    应用包
│  ├─ app.py                 单实例、日志、DPI、命令行
│  ├─ gui.py                 设置窗口 + 托盘图标（关窗=收进托盘）
│  ├─ config.py              配置合并 / 记住模式
│  ├─ engine.py              状态机、跟随、动画计时、模式切换
│  ├─ hook.py                全局鼠标钩子 + 系统光标替换 + 忙状态判定
│  ├─ skin.py                加载 PNG / 贴图集 → 预乘 BGRA
│  ├─ window.py              分层窗口 + DIB surface（支持逐帧改写）
│  ├─ ui.py                  GDI 绘图 + 托盘（Shell_NotifyIconW）
│  ├─ win32.py               ctypes 声明与常量
│  └─ __main__.py            `python -m naiwa`
├─ assets/                   运行期素材（随仓库提交）
│  ├─ glimpse.png            默认姿态
│  ├─ left_hand.png          左键姿态
│  ├─ thinking.png           右键姿态
│  ├─ default.png            极简模式圆盘
│  ├─ laugh_sheet.png/.json  等待动画贴图集
│  ├─ laugh_preview.png      预览页用 APNG
│  ├─ app.ico                窗口 / 托盘 / exe 图标
│  └─ poses/                 6 个备用姿态（不打包）
├─ tools/
│  ├─ build_assets.py        抠图、GIF 拆帧、贴图集
│  ├─ build_exe.py           PyInstaller 打包（图标 / 版本信息 / 素材筛选）
│  └─ package.py             打成两个可分发的 zip
├─ packaging/                分发包里附带的 使用说明.txt、恢复光标.bat
├─ scripts/                  源码模式启动 / 强制停止 / 恢复光标
├─ docs/preview.html         浏览器交互预览
├─ config.json               模式 / 状态 / 尺寸 / 时序 / 热键
├─ requirements.txt          运行依赖
├─ requirements-dev.txt      打包依赖（PyInstaller）
└─ dist/                     构建产物（git-ignored）
```

## 实现要点

1. **逐像素透明**：`WS_EX_LAYERED` + `UpdateLayeredWindow`，直接提交预乘 BGRA 的
   DIB，所以角色边缘是柔和抗锯齿的，不是色键抠图的硬边。
2. **不挡操作**：窗口带 `WS_EX_TRANSPARENT`（点击穿透）、`WS_EX_NOACTIVATE`（不抢焦点）、
   `WS_EX_TOOLWINDOW`（不占任务栏）。
3. **按键识别**：`WH_MOUSE_LL` 低级鼠标钩子，回调里只改标志，绘制交给定时器，
   不会拖慢鼠标。
4. **替换指针**：把 14 种系统光标全部换成 1×1 全透明光标，退出时用
   `SystemParametersInfo(SPI_SETCURSORS)` 整体还原。
5. **抠图**：从图像边界做连通域填充得到背景掩码（保护角色内部的浅色区域），
   膨胀 1px 吃掉白边，高斯羽化，再按 `c = a·F + (1-a)·B` 反解前景色，消除
   白/黄光晕；最后丢弃零散连通块，水印会一起消失。
6. **等待状态**：每 80ms 用 `GetCursorInfo` 取当前光标句柄，和启动时记下的
   `IDC_WAIT` / `IDC_APPSTARTING` 句柄比对。`SetSystemCursor` 只替换光标槽里的位图、
   句柄不变，所以藏成 1×1 之后照样能判断系统是否在转圈。
7. **动画**：176 帧的 `laugh` 共用一张 DIB，换帧只是一次 `memmove`，
   窗口不用重建，CPU 占用和静态态几乎一样。
8. **界面**：没有引入 Tk/Qt，设置窗口直接用 GDI 画：圆角卡片、ClearType 文字、
   `AlphaBlend` 贴角色预览图，双缓冲防闪烁。托盘图标用 `Shell_NotifyIconW` 实现，
   和主窗口共用同一个消息循环，没有跨线程状态。
9. **模式切换**：两套图层各自缓存，切换只是换指针；切回上一次的模式不再重新解码图片，
   也不会释放仍在缓存里的 GDI surface。退出时统一释放。

## 出问题了？

- **鼠标指针不见了**：双击 `scripts/restore_cursor.bat`，或 `scripts/stop.bat`，
  打包版运行 `NaiWaMouse.exe --restore-cursor`，源码模式跑
  `python -m naiwa --restore-cursor`。程序正常退出会自己恢复，只有被任务管理器
  强杀才需要这一步。
- **热键没反应**：可能被其他软件占用，日志里会写 `hotkey ... is already taken`，
  改 `config.json` 里的组合即可。
- **什么都没出现**：看 exe 同目录的 `naiwa-mouse.log`。
