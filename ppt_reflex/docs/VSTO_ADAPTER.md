# VSTO/COM Adapter Specification
# PPT Reflex Engine — Phase 2 Bridge

## 目标

将 Day 1 验证过的 Reflex Engine（python-pptx 文件级操作）
升级为 PowerPoint 进程内实时操作。

## 为什么需要 VSTO/COM 而不是只依赖 python-pptx

| 能力 | python-pptx | VSTO/COM |
|------|------------|----------|
| 文件读写 | ✓ | ✓ |
| 实时操作（不关文件） | ✗ | ✓ |
| 文本渲染尺寸 | ✗ | ✓ TextFrame2.TextRange.BoundWidth |
| 文本溢出检测 | ✗ | ✓ |
| 图片裁剪状态 | ✗ | ✓ |
| 页面导出为 PNG | ✗ | ✓ Slide.Export() |
| 人工拖动感知 | ✗ | ✓ WindowSelectionChange 事件 |
| SmartArt/Chart 读取 | 部分 | ✓ |
| Z-order 可靠读写 | 部分 | ✓ |
| 锁定/选择操作 | ✗ | ✓ |

## 架构

```
┌─────────────────────────────────┐
│  Agent (Claude/GPT/DeepSeek)     │
│  MCP 协议调用 19 个工具           │
└──────────┬──────────────────────┘
           │ MCP JSON-RPC (stdio/HTTP)
           ▼
┌─────────────────────────────────┐
│  MCP Server (mcp_server.py)     │  Python，已实现 ✓
│  ┌───────────────────────────┐  │
│  │ Session 管理               │  │
│  │ Tool 分发                  │  │
│  │ 协议序列化                  │  │
│  └───────────┬───────────────┘  │
│              │                    │
│  ┌───────────▼───────────────┐  │
│  │ Reflex Engine             │  │  已实现 ✓
│  │  ┌─────┐ ┌──────┐ ┌────┐ │  │
│  │  │Geo  │ │Rules │ │Lay │ │  │
│  │  └─────┘ └──────┘ └────┘ │  │
│  │  ┌─────┐ ┌──────┐        │  │
│  │  │Nudge│ │Jrnl  │        │  │
│  │  └─────┘ └──────┘        │  │
│  └───────────┬───────────────┘  │
│              │ 调用              │
│  ┌───────────▼───────────────┐  │
│  │ Host Adapter (适配层)      │  │  本次设计 ★
│  │ ┌─────────┐ ┌──────────┐  │  │
│  │ │COM Bridge│ │Render Eng│  │  │
│  │ └────┬────┘ └─────┬────┘  │  │
│  └──────┼────────────┼──────┘  │
└─────────┼────────────┼──────────┘
          │ Named Pipe │
          │ (localhost) │
          ▼            ▼
┌─────────────────────────────────┐
│  PPT Host Service (C# .NET)     │  本次设计 ★
│  ┌───────────────────────────┐  │
│  │ Pipe Server               │  │  接收 Python→C# 调用
│  │ ┌─────────┐ ┌──────────┐  │  │
│  │ │PPT COM  │ │Renderer  │  │  │
│  │ │Controller│ │(ExportPNG)│  │  │
│  │ └────┬────┘ └─────┬────┘  │  │
│  └──────┼────────────┼──────┘  │
└─────────┼────────────┼──────────┘
          │            │
          ▼            ▼
┌─────────────────────────────────┐
│  Microsoft PowerPoint           │
│  PowerPoint.Application COM     │
│  ┌──────────┐ ┌──────────────┐  │
│  │Shape Ops │ │Slide.Export  │  │
│  │Selection │ │(PNG render)  │  │
│  │Events    │ │              │  │
│  └──────────┘ └──────────────┘  │
└─────────────────────────────────┘
```

## Host Adapter 接口

### Python 侧调用接口（Named Pipe → C#）

```python
# adapter.py — 即将实现

class HostAdapter:
    \"\"\"Abstracts COM/VSTO operations behind a pipe protocol.\"\"\"

    # ── 连接 ──
    def connect(self, pipe_name: str = "ppt_reflex_pipe")
    def disconnect(self)
    def ping(self) -> bool

    # ── 文件 ──
    def open_presentation(self, path: str) -> dict
        # → {"slides": 15, "slide_width_pt": 960, ...}

    def save_presentation(self, path: str | None = None) -> dict

    # ── 元素读取（增强 python-pptx 读不到的信息） ──
    def read_elements(self, slide_idx: int) -> list[dict]
        # 补全 python-pptx 读不到的数据：
        #   - text_overflow: bool (实际渲染边界对比文本框)
        #   - actual_font_size: float (如果 auto-fit 缩小了)
        #   - crop_state: dict (图片裁剪)
        #   - has_animation: bool
        #   - is_grouped: bool

    def read_element_rendered_bounds(self, elem_id: str) -> dict
        # → {"actual_text_width_pt": 380, "actual_text_height_pt": 95,
        #    "overflow": True, "overflow_lines": 2}

    # ── 写入 ──
    def apply_positions(self, updates: list[dict]) -> dict
        # updates: [{"id": "shape-05", "left_pt": 36, "top_pt": 140, ...}, ...]

    def apply_text(self, elem_id: str, text: str, font_pt: float = None)

    def delete_element(self, elem_id: str)

    # ── 渲染 ──
    def render_slide_png(self, slide_idx: int, dpi: int = 200) -> bytes
        # 通过 Slide.Export() 导出 PNG，
        # 精度远超 LibreOffice headless 渲染

    # ── 事件 ──
    def poll_state_change(self) -> dict | None
        # 返回人工编辑信息或 None
        # → {"changed": ["shape-03"], "new_positions": {...}}
```

### C# 侧实现要点

```csharp
// PPTReflexService — 核心类

public class PPTReflexService
{
    PowerPoint.Application _powerpoint;
    NamedPipeServerStream _pipe;

    // 启动：连接 PowerPoint + 打开命名管道
    void Start(string pipeName);

    // 主循环：等待 Python 调用
    async Task ProcessRequestAsync(PipeRequest req);

    // ── COM 操作 ──
    SlideInfo GetSlideInfo(int index);
    ElementInfo[] ReadElements(int slideIndex);
    RenderedBounds GetTextBounds(string elementId);
    void ApplyPositions(PositionUpdate[] updates);
    byte[] ExportSlidePng(int slideIndex, int dpi);

    // ── 事件监听 ──
    // PowerPoint 的 WindowSelectionChange 不稳定，
    // 改用轮询：每 500ms 检查 active slide 的元素坐标
    // 对照本地缓存 → 发现差异 → 生成 change event
    Dictionary<string, Rect> _lastKnownPositions;
}
```

## 命名管道协议

### 消息格式

```json
{
  "id": "req-0042",
  "method": "read_elements",
  "params": {"slide_idx": 3}
}
```

```json
{
  "id": "req-0042",
  "status": "ok",
  "result": {
    "elements": [
      {
        "id": "shape-05",
        "bbox_emu": {"left": 457200, "top": 1016000, "width": 3556000, "height": 2235200},
        "text_overflow": false,
        "actual_font_size_pt": 12.0,
        "is_visible": true,
        "z_order": 3
      }
    ]
  }
}
```

### 协议要点

- **二进制模式**：渲染 PNG 用二进制帧（长度前缀 + 数据）
- **JSON 模式**：元数据和控制消息
- **超时**：常规操作 5s，PNG 渲染 30s
- **重连**：Pipe 断开自动重连，最多 3 次

## 实现优先级

### P0 — 必须（对应 Day 1 已验证能力）
```
✓ connect / open / save
✓ read_elements（含 python-pptx 读不到的信息）
✓ apply_positions
✓ poll_state_change（轮询模式）
```

### P1 — 尽快
```
○ render_slide_png（Slide.Export）
○ read_element_rendered_bounds（TextFrame2）
○ apply_text
○ delete_element
```

### P2 — 后续
```
○ 图片裁剪状态读写
○ SmartArt/Chart 读写
○ 事件驱动（非轮询）
○ 选择/高亮元素
```

## 与现有项目 mcp-server-ppt 的关系

[mcp-server-ppt](https://github.com/trsdn/mcp-server-ppt) (35★, C#)
已经实现了 COM 通道的基础设施，但缺少 QA 层。

我们的策略：
- **不 fork** mcp-server-ppt——它的 MCP Server 和 CLI 层与我们的协议不同
- **参考** 它的 COM 封装模式（session 管理、错误处理）
- **复用** 业已证明可行的技术路径：
  - PowerPoint.Application 单例管理
  - Named Pipe 通信（他们已经验证可行）
  - Slide.Export() PNG 渲染（他们已经实现）

## 已有代码改动量估计

| 文件 | 性质 | 行数估计 |
|------|------|---------|
| `adapter.py` | 新增 — Host Adapter Python 层 | ~200 |
| `mcp_server.py` | 修改 — session 中切换到 COM 模式 | ~50 |
| `PPTReflexService/` | 新增 — C# 项目 | ~800 (含 Pipe Server + COM Ctrl) |
| `reflex.py` | 修改 — 支持 COM 数据源 | ~30 |
| `bridge.py` | 保留 — 作为 fallback 模式 | 0 |

## 开发顺序

```
1. adapter.py            Python 侧 Host Adapter 接口
2. PPTReflexService.cs   最小 C# 实现（connect/open/save/read/apply）
3. adapter.py → 集成     连接到 mcp_server.py 的 session
4. render_slide_png      渲染管线
5. poll_state_change     人工编辑感知
6. 端到端测试            用 broken.pptx 跑完整闭环
```
