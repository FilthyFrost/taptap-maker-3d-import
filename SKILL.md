# TapTap Maker 3D 模型导入 — 主入口

**一句话：用户给你 3D 模型文件，你帮他加到游戏里。**

本 Skill 自动识别用户意图，路由到正确的子文档，完成 3D 模型的导入和配置。

---

## 意图识别决策树

收到用户的 3D 模型导入请求后，按以下规则判断：

```
用户给了什么文件/描述了什么需求？
│
├─ 文件是 .fbx 格式
│  └─ → 读取 skill-scene-fbx.md（FBX 场景素材）
│
├─ 文件是 .glb 或 .gltf 格式
│  │
│  ├─ 用户说"角色""人物""NPC""怪物"或要播放动画（Idle/Walk/Run/Attack）
│  │  └─ → 读取 skill-animated-character.md（骨骼动画角色）
│  │
│  ├─ 用户说"雕像""摆件""道具""装饰""宠物（不动的）"
│  │  └─ → 读取 skill-static-prop.md（静态物件）
│  │
│  ├─ 用户没说清楚 → 检查 GLB 文件内容：
│  │  ├─ 文件包含 skin + animation 数据 → skill-animated-character.md
│  │  └─ 文件只有 mesh 数据 → skill-static-prop.md
│  │
│  └─ 用户说"场景""家具""建筑""房间"
│     └─ → 读取 skill-static-prop.md
│
├─ 用户只描述了意图，没给文件
│  ├─ "我要加载一个会动的角色" → skill-animated-character.md
│  ├─ "我要放一个雕像/道具" → skill-static-prop.md
│  ├─ "我要搭建场景/放家具" → skill-scene-fbx.md
│  └─ "模型出问题了/不显示/碎裂" → skill-troubleshooting.md
│
└─ 遇到任何问题
   └─ → 读取 skill-troubleshooting.md（问题排查）
```

---

## 快速判断表

| 用户关键词 | 文件格式 | 路由到 |
|-----------|---------|--------|
| 角色、人物、NPC、怪物、玩家 | .glb | skill-animated-character.md |
| 动画、Idle、Walk、Run、Attack、状态机 | .glb | skill-animated-character.md |
| Meshy AI、Mixamo、骨骼动画 | .glb | skill-animated-character.md |
| 雕像、摆件、道具、装饰品、花瓶 | .glb | skill-static-prop.md |
| 地板、门、窗、墙、栏杆、桥 | .fbx / .glb | skill-scene-fbx.md |
| 沙发、桌子、椅子、家具、建筑 | .fbx | skill-scene-fbx.md |
| 看不到、不显示、白色、碎裂、崩溃 | 任何 | skill-troubleshooting.md |

---

## 子文档一览

| 文档 | 用途 | 复杂度 |
|------|------|--------|
| **skill-static-prop.md** | GLB 静态物件（雕像、道具、装饰） | 简单 |
| **skill-animated-character.md** | GLB 骨骼动画角色（需要转换+状态机） | 复杂 |
| **skill-scene-fbx.md** | FBX 场景素材（家具、建筑，直接加载） | 最简单 |
| **skill-troubleshooting.md** | 问题排查（不可见、碎裂、白膜、动画不播放） | 按需 |

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
