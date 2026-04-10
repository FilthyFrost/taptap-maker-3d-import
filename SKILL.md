# TapTap Maker 3D 模型导入 — 主入口

**一句话：用户给你 3D 模型文件，你帮他加到游戏里。**

本 Skill 自动识别用户意图，路由到正确的子文档，完成 3D 模型的导入和配置。

---

## 意图识别决策树

**核心原则：先判断用途（需要动画吗？），再看格式。格式不决定用途。**

FBX 也可以是角色动画，GLB 也可以是静态家具。不要按格式分流。

```
第 1 步：判断用途 — 这个模型需要动吗？
│
├─ 需要动画（角色/人物/NPC/怪物/宠物会动的）
│  │
│  │  关键词：角色、人物、NPC、怪物、玩家、动画、
│  │         Idle、Walk、Run、Attack、状态机、
│  │         Meshy AI、Mixamo、骨骼动画
│  │
│  └─ → 读取 skill-animated-character.md
│       （不管文件是 .glb 还是 .fbx，都走这条路）
│
├─ 不需要动画（静态物件/场景道具）
│  │
│  │  关键词：雕像、摆件、道具、装饰、花瓶、
│  │         家具、沙发、桌子、椅子、建筑、
│  │         地板、门、窗、墙、场景、房间
│  │
│  └─ 第 2 步：看文件格式
│     │
│     ├─ .fbx 文件 → 读取 skill-scene-fbx.md
│     │  （FBX 可以直接加载，最简单）
│     │
│     └─ .glb / .gltf 文件 → 读取 skill-static-prop.md
│        （GLB 需要转换为 MDL 或用 CustomGeometry）
│
├─ 用户没说清楚用途
│  │
│  └─ 检查文件内容判断：
│     ├─ 文件包含 skin（骨骼）+ animation 数据 → skill-animated-character.md
│     ├─ 文件只有 mesh 数据，无骨骼 → skill-static-prop.md 或 skill-scene-fbx.md
│     └─ 仍不确定 → 问用户："这个模型需要播放动画吗？"
│
├─ 用户说模型出问题了
│  │
│  │  关键词：看不到、不显示、白色、碎裂、崩溃、
│  │         不动、没有动画、报错
│  │
│  └─ → 读取 skill-troubleshooting.md
│
└─ 遇到任何技术问题
   └─ → 读取 skill-troubleshooting.md
```

---

## 快速判断表

| 用户意图 | 关键词 | 路由到 | 格式无关 |
|---------|--------|--------|---------|
| 会动的角色 | 角色、人物、NPC、动画、Idle/Walk/Run | skill-animated-character.md | .glb .fbx 都走这里 |
| 不动的物件 | 雕像、道具、摆件、装饰 | skill-static-prop.md | .glb 走这里 |
| 场景搭建 | 家具、建筑、地板、门窗、房间 | skill-scene-fbx.md（FBX）或 skill-static-prop.md（GLB） | 按格式选子文档 |
| 出了问题 | 不显示、碎裂、白色、崩溃、不动 | skill-troubleshooting.md | 任何格式 |

---

## 子文档一览

| 文档 | 用途 | 支持格式 | 复杂度 |
|------|------|---------|--------|
| **skill-animated-character.md** | 会动的角色（骨骼动画+状态机） | .glb / .fbx | 复杂 |
| **skill-static-prop.md** | 不动的 GLB 物件（雕像、道具） | .glb | 中等 |
| **skill-scene-fbx.md** | 不动的 FBX 场景素材（家具、建筑） | .fbx | 最简单 |
| **skill-troubleshooting.md** | 问题排查（不可见、碎裂、白膜等） | 任何 | 按需 |

---

## 通用规则（所有子文档都遵守）

### 引擎环境
- 引擎：UrhoX（基于 Urho3D 1.8）
- 脚本语言：Lua 5.4
- 平台：WASM（浏览器）
- 渲染：PBR 管线

### API 安全警告

**以下方法在 UrhoX 中不存在，调用会导致崩溃：**

```lua
-- 这些会崩溃！绝对不要用！
animation:GetTrackName(index)       -- 不存在
animation:GetTrackBoneName(index)   -- 不存在
animModel:GetAnimationName()        -- 不存在
animCtrl:GetCurrentAnimation()      -- 不存在
```

### 组件选择规则

| 模型类型 | 使用组件 |
|---------|---------|
| 静态物件（不动的） | `StaticModel` |
| 骨骼动画角色（会动的） | `AnimatedModel` |

**永远不要给骨骼动画角色用 StaticModel，否则动画不会播放。**

### 文件放置规则

```
workspace/
├── assets/                 ← 游戏资源（会被部署）
│   ├── Models/             ← 模型文件 (.mdl, .fbx)
│   ├── Textures/           ← 纹理文件 (.png, .jpg)
│   └── Animations/         ← 动画文件 (.ani)
├── 3d-models/              ← 原始 GLB 文件（不部署，仅转换用）
├── tools/                  ← 转换工具脚本
└── scripts/                ← Lua 游戏脚本
```
