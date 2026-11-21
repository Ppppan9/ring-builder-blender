# UA Game Kit — 解环玩法定制底座

Blender 解环玩法买量广告一键式制作工具箱（沿用「买量工坊 UA Studio」同架构）。

> 目标版本：Blender 4.5+（在本机 Blender 5.1.2 上开发与全量测试通过）
> 当前版本：**0.2.0**（解环玩法库 ring_lib + 冒烟测试适配）

## 关于

本项目由 **AI 全程编写**——基于 GLM 大模型驱动的编程 Agent，从需求分析、架构设计、逐模块实现、物理调参到自动化测试全部由 AI 完成，人类负责提需求、验收效果和决策方向。

- AI 模型：GLM（智谱）
- Agent 框架：ZCode CLI
- 人类角色：产品经理 + 测试验收

## 与关卡搭建器（ring_level_builder）的分工

| 层 | 工具 | 职责 |
|---|---|---|
| 模型/关卡层 | **ring_level_builder v1.7.0**（前端搭建器 + Blender 插件） | 关卡建模、解谜逻辑动画（`apply_unlock`/`bake_level`）、俯拍相机灯光地面 |
| 买量表演层 | **本工具（ua_game_kit）** | 手指引导、拔环回弹、飞槽爽点、感叹词、彩带、运镜、HUD、结尾卡、渲染出片 |

两层桥接：搭建器发送到 Blender 的关卡对象（集合属性 `rp_tag == "ring_level_builder"`、对象属性 `rp_kind/rp_id/rp_asset`）可直接用本工具的
`ring_lib.scan_rings()` 扫出、逐环 `ring_lib.ring_pull()` 编排表演；也可完全脱离搭建器，用
`ring_lib.build_demo_cluster()` 一键生成演示簇出片。

## 安装

**方式一（推荐）**：双击 `install.command`（macOS），自动构建并安装到 Blender。

**方式二**：Blender → 编辑 → 偏好设置 → 插件 → 右上角箭头 → 从磁盘安装，选择 `dist/ua_game_kit-*.zip`（无 zip 时先运行 `blender --command extension build --source-dir . --output-dir dist`）。

安装后：3D 视口按 `N` 打开右侧栏 → 找到 **「买量工坊」** 面板。

## 🎯 解环玩法库（core/ring_lib.py）

- **生成器**：`make_c_ring`（圆管 C 环 + 半球圆头，缺口 58°，糖果材质）、`make_clasp`（银色卡扣箍）、`make_hub`（花心大 C 环 / 奶油圆角立方体双风格）、`make_slot` / `make_slot_row`（顶部颜色槽：环座 + 深洞 + 可填充圆片）
- **演示簇**：`build_demo_cluster` 一键生成「花心 + 放射 C 环 + 卡扣」完整画面
- **表演动作**：
  - `ring_pull(obj, slot)` — 拔出大回弹（外弹 1.15 倍 + BACK 回缩）→ 弧线飞向颜色槽 → 缩入落槽（无槽则飞出画面）
  - `ring_wiggle(objs)` — 邻环连锁轻晃（拔环前预备）
  - `word_pop("Nice!")` — 感叹词戳（彩色字身 + 白描边，弹入弹出）
  - `slot_fill(slot)` — 颜色槽填充闪光
  - `confetti()` — 彩带庆祝
- **配色**：与搭建器素材同源六色（red/orange/green/blue/cyan/purple）+ 银 + 奶油

## 一键广告模板（① 工程页顶部）

| 模板 | 内容 |
|---|---|
| 示例模板 | 展示编排模式的最小示例（金币 → 点击 → 收集 → 飞分彩带） |
| 解环拔环 | C 环簇弹入推近 → 两次点按拔环（Nice!/Great!）→ 最后一拔白闪彩带（Excellent!）→ 三槽填满 → HUD → 结尾卡 |

## 工作流（面板自上而下）

| 分页 | 内容 |
|---|---|
| ⚙ 前置插件 | 状态红绿灯 + 一键启用/安装（Cell Fracture 等自动装） |
| ① 工程 | 一键新建买量工程（1080×1920@30 / 渐变穹幕 / 展台 / 三点布光 / 相机）+ **一键模板** |
| ② 资产 | 12 种买量常用几何、散布/网格/环形阵列、FBX/OBJ/GLB 导入归一化、3D 文字 |
| ③ 材质 | 11 种一键材质，主色可调 |
| ④ 动画 | 入场（弹出/坠落/滑入/旋转，自动错帧）、循环、缓动库、卡点标记 |
| 🎮 假玩法 | 手指点击、收集飞入、+100 飞分、HUD、贴纸、白闪转场、文字气泡 |
| ⑤ 物理 | 掉落堆叠 / 冲击 / 破碎 / 彩带 / 星尘 / 旗帜 / 果冻 / 绳索 / 流体 / 一键烘焙 |
| ⑥ 相机 | 推近 / 环绕 / 震屏 / 构图安全区 |
| ⑦ 渲染 | MP4 / PNG 透明序列、批量渲染、**多尺寸矩阵**（9:16/1:1/16:9）、封面导出、画质与风格 |
| ⑧ 结尾卡 | 独立场景三模板 + logo + CTA |
| 🎬 分镜与音效 | 四段分镜、跳转分镜、音效需求清单导出 |

## 典型 15 秒广告流程

1. ① 工程页点 **「解环拔环」** 模板（或先跑关卡搭建器建模，再用 ring_lib 扫环编排）
2. 微调环颜色 / 感叹词文案 / HUD 分数（全部可改）
3. 🎬 分镜页检查节奏，⑦「多尺寸矩阵 3 画幅」出片

## 前置插件说明

- **内置启用**：Node Wrangler、FBX/glTF 导入器
- **自动联网安装**：Cell Fracture（破碎）、Extra Mesh Objects、LoopTools、Scatter Objects 等（首次使用对应功能时自动装）
- 一键安装需要开启 Blender 的「在线访问」（面板里有一键开启按钮）

## 测试

```bash
blender --command extension build --source-dir . --output-dir dist
blender -b --command extension install-file -r user_default -e dist/ua_game_kit-0.2.0.zip
blender -b -P tests/smoke_test.py
```

冒烟测试覆盖：工程创建、12 种几何、材质、动画/运镜、刚体/破碎/粒子、布料/流体、结尾卡、渲染出图、
**解环专项（C 环网格/卡扣/双基座/颜色槽/scan 桥接/拔环关键帧/感叹词/槽填充/演示簇/解环模板）**。

## 目录结构

```
core/    纯逻辑库（…/ring_lib.py 解环玩法库 /其余同买量工坊架构）
ops/     Operator 薄封装（每模块一文件）
ui/      N 面板（依赖状态条 + ①~⑧ 分页）
tests/   headless 冒烟测试
```

## 已知注意事项

- 5.x API 差异（EEVEE 引擎 ID、Action 槽位化 F 曲线、粒子属性名）已在 `core/util.py` / `anim_lib.py` 内适配
- 渲染走 CLI 子进程（先存副本再 `blender -b` 渲染），规避依赖图时序问题
- `ring_pull` 会清掉环对象已有动画（避免与搭建器烘焙的解环关键帧叠加），表演层与解谜层二选一编排
