---
name: animated-character-import
description: "将外部 GLB 骨骼动画角色模型一键导入 UrhoX 游戏。覆盖 GLB→MDL/ANI 转换、纹理提取、裂纹修复、可见性修复、AnimationState 动画播放的完整流程。适用于 Meshy AI、Mixamo、Blender 导出的骨骼动画角色。"
---

# 骨骼动画角色导入（GLB 角色 + 动画状态机）

> **面向 TapTap Maker (UrhoX) 用户的完整解决方案**
>
> 本文档让你：放入 GLB 文件 → 运行几条命令 → 角色就在游戏里跑起来了。
> 所有踩过的坑都已记录，照做即可。

---

## 目录

1. [适用场景](#1-适用场景)
2. [整体流程总览](#2-整体流程总览)
3. [环境准备（一次性）](#3-环境准备一次性)
4. [Step 1：放置 GLB 源文件](#4-step-1放置-glb-源文件)
5. [Step 2：转换模型（GLB → MDL）](#5-step-2转换模型glb--mdl)
6. [Step 3：转换动画（GLB → ANI）](#6-step-3转换动画glb--ani)
7. [Step 4：提取纹理](#7-step-4提取纹理)
8. [Step 5：Lua 中加载和播放动画](#8-step-5lua-中加载和播放动画)
9. [Step 6：构建并预览](#9-step-6构建并预览)
10. [完整一键脚本](#10-完整一键脚本)
11. [裂纹问题全解（最重要的坑）](#11-裂纹问题全解)
12. [模型不显示全解（第二大坑）](#12-模型不显示全解)
13. [Meshy AI 模型专项指南](#13-meshy-ai-模型专项指南)
14. [MDL 诊断工具](#14-mdl-诊断工具)
15. [常见陷阱速查表](#15-常见陷阱速查表)
16. [完整代码示例](#16-完整代码示例)
17. [FAQ](#17-faq)

---

## 1. 适用场景

**本文档适用于**：
- 带骨骼动画的 3D 角色模型（Idle、Walk、Run、Attack 等）
- GLB 格式的骨骼蒙皮模型（Skinned Mesh）
- Meshy AI、Mixamo、Blender 导出的角色模型
- 需要在 UrhoX 游戏中加载自定义角色并播放动画

**不适用于**（请使用对应文档）：
- 静态场景素材（地板、门、沙发、建筑等）→ `skill-scene-fbx.md`
- 无骨骼动画的 GLB 装饰模型 → `skill-static-prop.md`

---

## 2. 整体流程总览

```
┌──────────────────────────────────────────────────────────────┐
│                用户只需做这 6 步                               │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  1. 把 .glb 文件放到项目里                                    │
│                    ↓                                         │
│  2. 运行一条命令：转换模型（GLB → MDL）                        │
│     python3 tools/raw_convert.py input.glb assets/Model.mdl  │
│                    ↓                                         │
│  3. 运行命令：转换动画（每个动画一条命令）                      │
│     python3 tools/glb_to_urho.py input.glb --ani-only xx.ani │
│                    ↓                                         │
│  4. 运行命令：提取纹理                                        │
│     python3 tools/glb_to_urho.py input.glb --texture dir/    │
│                    ↓                                         │
│  5. 在 Lua 代码中加载模型、设置材质、播放动画                   │
│                    ↓                                         │
│  6. 调用 build 工具构建 → 预览                                │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. 环境准备（一次性）

### 3.1 安装 Python 依赖

```bash
pip3 install numpy scipy fast-simplification
```

### 3.2 确认工具文件存在

```
workspace/
├── tools/
│   ├── glb_to_urho.py          # 完整转换器（模型+动画+纹理）
│   ├── raw_convert.py          # 零处理模型转换器（防裂纹，推荐）
│   └── diagnose_mdl.py         # MDL 诊断工具（排查问题用）
```

### 3.3 raw_convert.py（零处理转换器）

如果项目中没有此文件，创建 `tools/raw_convert.py`：

```python
#!/usr/bin/env python3
"""
零处理 GLB → MDL 转换器。
不做降面、不做焊接、不做间隙修复。
只做坐标系转换（Z 轴翻转 + 三角面绕序反转）。
这是最安全的转换方式，保证不会产生模型裂纹。
"""
import sys
sys.path.insert(0, '.')
from glb_to_urho import (
    parse_glb, extract_mesh, extract_skeleton,
    flip_z_position, flip_z_normal, flip_winding_order,
    write_mdl
)
import numpy as np
import os

def raw_convert(glb_path, mdl_path):
    print(f"RAW convert: {glb_path} -> {mdl_path}")
    print("  NO decimation, NO welding, NO gap-closing")

    gltf, bin_data = parse_glb(glb_path)
    positions, normals, texcoords, joints, weights, indices = extract_mesh(gltf, bin_data)
    print(f"  Raw vertices: {len(positions)}")
    print(f"  Raw indices: {len(indices)} ({len(indices)//3} triangles)")

    # 归一化骨骼权重（安全操作，不改变拓扑）
    weight_sums = weights.sum(axis=1, keepdims=True)
    weight_sums[weight_sums < 1e-8] = 1.0
    weights = weights / weight_sums

    # 坐标系转换（glTF 右手 → UrhoX 左手）
    positions = flip_z_position(positions)
    normals = flip_z_normal(normals)
    indices = flip_winding_order(indices)

    bb_min = positions.min(axis=0)
    bb_max = positions.max(axis=0)
    bones, armature_scale = extract_skeleton(gltf, bin_data)

    os.makedirs(os.path.dirname(mdl_path) or '.', exist_ok=True)
    write_mdl(mdl_path, positions, normals, texcoords, joints, weights, indices,
              bones, bb_min, bb_max)

    print(f"\n  VERIFY: output vertices = {len(positions)} (should == GLB vertices)")
    print(f"  VERIFY: output indices = {len(indices)} (should == GLB indices)")

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python3 raw_convert.py <input.glb> <output.mdl>")
        sys.exit(1)
    raw_convert(sys.argv[1], sys.argv[2])
```

---

## 4. Step 1：放置 GLB 源文件

```
workspace/
├── 3d-models/                    # 原始 GLB 文件（不会被部署）
│   ├── Character_Idle.glb        # 带 Idle 动画的 GLB
│   ├── Character_Walking.glb     # 带 Walking 动画的 GLB
│   └── Character_Running.glb     # 带 Running 动画的 GLB
```

**Meshy AI 用户注意**：Meshy AI 生成的每个动画是单独的 GLB 文件，每个文件都包含完整的模型 + 一段动画。这是正常的，我们的工具链支持这种结构。

---

## 5. Step 2：转换模型（GLB → MDL）

### 推荐方式：零处理转换（不会裂纹）

```bash
cd /workspace/tools

# 从任意一个 GLB 转换模型（所有 GLB 共享同一个模型网格）
python3 raw_convert.py \
    ../3d-models/Character_Idle.glb \
    ../assets/MyCharacter/Character.mdl
```

**关键点**：
- 只需要从**一个** GLB 转换模型（因为所有动画 GLB 里的模型网格是相同的）
- 零处理转换保留所有原始顶点，**不会产生裂纹**
- 缺点是文件较大（Meshy AI 百万面模型约 70-80MB），但渲染完全正确

### 备选方式：带降面转换（文件更小，但可能裂纹）

```bash
# 降面到原始的 2%（百万面 → 约 2 万面）
python3 glb_to_urho.py \
    ../3d-models/Character_Idle.glb \
    --mdl ../assets/MyCharacter/Character.mdl \
    --decimate 0.02
```

> ⚠️ **警告**：QEM 降面算法在 UV 接缝处可能产生裂纹。如果降面后模型碎裂，请退回零处理方式。详见 [§11 裂纹问题全解](#11-裂纹问题全解)。

---

## 6. Step 3：转换动画（GLB → ANI）

每个动画单独转换：

```bash
cd /workspace/tools

# Idle 动画
python3 glb_to_urho.py \
    ../3d-models/Character_Idle.glb \
    --ani-only ../assets/MyCharacter/CharacterIdle.ani \
    --ani-name "Idle"

# Walking 动画
python3 glb_to_urho.py \
    ../3d-models/Character_Walking.glb \
    --ani-only ../assets/MyCharacter/CharacterWalking.ani \
    --ani-name "Walking"

# Running 动画
python3 glb_to_urho.py \
    ../3d-models/Character_Running.glb \
    --ani-only ../assets/MyCharacter/CharacterRunning.ani \
    --ani-name "Running"
```

**参数说明**：
- `--ani-only`：只转换动画，不转换模型
- `--ani-name`：动画名称，会写入 ANI 文件头部

---

## 7. Step 4：提取纹理

```bash
cd /workspace/tools

# 从任一 GLB 提取纹理（所有 GLB 内嵌的纹理相同）
python3 glb_to_urho.py \
    ../3d-models/Character_Idle.glb \
    --texture ../assets/Textures/
```

输出：`assets/Textures/` 目录下的纹理图片（通常是 `texture_0.png`、`texture_1.png` 等）

---

## 8. Step 5：Lua 中加载和播放动画

### 8.1 基础加载（AnimationState 方式，推荐）

```lua
-- ============================================================
-- 角色配置
-- ============================================================
local CONFIG = {
    CharacterModel = "MyCharacter/Character.mdl",
    CharacterAnims = {
        Idle    = "MyCharacter/CharacterIdle.ani",
        Walk    = "MyCharacter/CharacterWalking.ani",
        Run     = "MyCharacter/CharacterRunning.ani",
    },
    CharacterTexture = "Textures/texture_0.png",
}

-- ============================================================
-- 加载模型
-- ============================================================
local characterNode = scene_:CreateChild("Character")
characterNode.position = Vector3(0, 0, 0)

-- 重要：使用 AnimatedModel（不是 StaticModel！）
local animModel = characterNode:CreateComponent("AnimatedModel")
local modelRes = cache:GetResource("Model", CONFIG.CharacterModel)
animModel:SetModel(modelRes)
animModel:SetCastShadows(true)
animModel:SetUpdateInvisible(true)  -- 确保不在视野内也更新骨骼

-- ============================================================
-- 设置 PBR 材质（使用提取的纹理）
-- ============================================================
local mat = Material:new()
mat:SetTechnique(0, cache:GetResource("Technique", "Techniques/PBR/PBRDiff.xml"))
mat:SetTexture(0, cache:GetResource("Texture2D", CONFIG.CharacterTexture))
mat:SetShaderParameter("Roughness", Variant(0.7))
mat:SetShaderParameter("Metallic", Variant(0.0))
animModel:SetMaterial(mat)

-- ============================================================
-- 播放初始动画（AnimationState 方式）
-- ============================================================
local currentAnimState = nil
local currentAnimName = ""

local function PlayAnimation(animName, looped)
    if animName == currentAnimName then return end

    -- 移除旧动画
    if currentAnimState then
        animModel:RemoveAnimationState(currentAnimState)
        currentAnimState = nil
    end

    -- 加载并播放新动画
    local animPath = CONFIG.CharacterAnims[animName]
    if not animPath then return end

    local anim = cache:GetResource("Animation", animPath)
    if anim == nil then
        print("WARNING: Animation not found: " .. animPath)
        return
    end

    currentAnimState = animModel:AddAnimationState(anim)
    currentAnimState:SetWeight(1.0)
    currentAnimState:SetLooped(looped ~= false)  -- 默认循环
    currentAnimName = animName
end

-- 初始播放 Idle
PlayAnimation("Idle", true)

-- ============================================================
-- 每帧更新动画
-- ============================================================
function HandleUpdate(eventType, eventData)
    local dt = eventData["TimeStep"]:GetFloat()

    -- 推进动画时间
    if currentAnimState then
        currentAnimState:AddTime(dt)
    end

    -- 根据输入切换动画
    if input:GetKeyDown(KEY_W) then
        if input:GetKeyDown(KEY_SHIFT) then
            PlayAnimation("Run", true)
        else
            PlayAnimation("Walk", true)
        end
    else
        if currentAnimName ~= "Idle" then
            PlayAnimation("Idle", true)
        end
    end
end
```

### 8.2 为什么用 AnimationState 而不是 AnimationController？

| 特性 | AnimationState | AnimationController |
|------|---------------|---------------------|
| 兼容性 | ✅ 转换后的 ANI 文件完全兼容 | ⚠️ 可能有兼容问题 |
| 控制精度 | ✅ 逐帧手动控制 | 自动管理 |
| 已知 bug | ✅ 无 | ⚠️ GetTrackName 崩溃风险 |
| 适用场景 | 自定义角色、少量动画 | 标准引擎资源 |
| 推荐度 | **推荐** | 备选 |

---

## 9. Step 6：构建并预览

代码写完后，调用 UrhoX MCP `build` 工具构建项目，然后在预览窗口查看效果。

---

## 10. 完整一键脚本

保存为 `convert_character.sh`，一键完成所有转换：

```bash
#!/bin/bash
# ============================================================
# 一键角色转换脚本
# 用法: bash convert_character.sh <glb目录> <角色名>
# 示例: bash convert_character.sh 3d-models MyGirl
# ============================================================

set -e

GLB_DIR="${1:?用法: bash convert_character.sh <glb目录> <角色名>}"
CHAR_NAME="${2:?请提供角色名}"
TOOLS_DIR="tools"
OUTPUT_MDL="assets/${CHAR_NAME}/${CHAR_NAME}.mdl"
OUTPUT_ANIM_DIR="assets/${CHAR_NAME}Anims"
OUTPUT_TEX_DIR="assets/Textures"

echo "=========================================="
echo "  角色转换: ${CHAR_NAME}"
echo "  GLB 目录: ${GLB_DIR}"
echo "=========================================="

# 找到所有 GLB 文件
GLB_FILES=(${GLB_DIR}/*.glb)
if [ ${#GLB_FILES[@]} -eq 0 ]; then
    echo "ERROR: 在 ${GLB_DIR} 中没有找到 .glb 文件"
    exit 1
fi

FIRST_GLB="${GLB_FILES[0]}"
echo "找到 ${#GLB_FILES[@]} 个 GLB 文件"
echo ""

# Step 1: 转换模型（零处理，防裂纹）
echo "[1/3] 转换模型: ${FIRST_GLB} → ${OUTPUT_MDL}"
mkdir -p "$(dirname ${OUTPUT_MDL})"
cd ${TOOLS_DIR}
python3 raw_convert.py "../${FIRST_GLB}" "../${OUTPUT_MDL}"
cd ..
echo ""

# Step 2: 提取纹理
echo "[2/3] 提取纹理 → ${OUTPUT_TEX_DIR}/"
mkdir -p "${OUTPUT_TEX_DIR}"
cd ${TOOLS_DIR}
python3 glb_to_urho.py "../${FIRST_GLB}" --texture "../${OUTPUT_TEX_DIR}/"
cd ..
echo ""

# Step 3: 转换所有动画
echo "[3/3] 转换动画..."
mkdir -p "${OUTPUT_ANIM_DIR}"
for glb in "${GLB_FILES[@]}"; do
    filename=$(basename "$glb" .glb)
    # 提取动画名关键词（兼容 Meshy AI 命名）
    anim_name=$(echo "$filename" | sed 's/.*Animation_//;s/_withSkin//;s/.*_//')
    if [ -z "$anim_name" ]; then
        anim_name="$filename"
    fi
    ani_output="${OUTPUT_ANIM_DIR}/${CHAR_NAME}${anim_name}.ani"
    echo "  ${filename} → ${anim_name}"
    cd ${TOOLS_DIR}
    python3 glb_to_urho.py "../${glb}" \
        --ani-only "../${ani_output}" \
        --ani-name "${anim_name}" 2>/dev/null || echo "    ⚠️ 动画转换失败: ${filename}"
    cd ..
done

echo ""
echo "=========================================="
echo "  转换完成！"
echo "  模型: ${OUTPUT_MDL}"
echo "  动画: ${OUTPUT_ANIM_DIR}/"
echo "  纹理: ${OUTPUT_TEX_DIR}/"
echo "  下一步: 在 Lua 中加载（见 §8）"
echo "=========================================="
```

**使用方法**：`bash convert_character.sh 3d-models MyGirl`

---

## 11. 裂纹问题全解

### 症状

模型表面出现大量裂纹/碎片，像碎玻璃一样。三角面之间有明显的缝隙。

### 根本原因

**QEM（Quadric Error Metrics）降面算法在 UV 接缝处产生错误的顶点索引重映射。**

具体机制：
1. GLB 模型在 UV 接缝处会有"共享位置但不同 UV"的顶点对
2. QEM 边折叠算法合并顶点时，可能将接缝两侧的三角面重映射到错误的顶点
3. 即使添加 pre-weld、post-weld、close_boundary_gaps，仍无法完全消除问题
4. 这是 `fast-simplification` 库的已知限制

### 解决方案

```
模型碎裂？
  │
  ├── 方案 A（推荐）: 使用 raw_convert.py 零处理转换
  │   → 不做降面 → 保证不碎裂
  │   → 文件大（Meshy AI 约 70-80MB），但渲染完全正确
  │
  ├── 方案 B: 调高降面比例
  │   → --decimate 0.1（保留 10%）或 --decimate 0.2（保留 20%）
  │   → 保留比例越高，碎裂风险越低，但文件越大
  │
  └── 方案 C: 在 Blender 中手动降面后再导出 GLB
      → Blender 的 Decimate Modifier 质量更好
      → 降面后导出新的 GLB → 再用 raw_convert.py 转换
```

### 碎裂排查四步法

```
Step 1: 确认是否使用了降面
  └── 是 → 用 raw_convert.py 重新转换，看碎裂是否消失
       └── 碎裂消失 → 使用零处理版本即可
       └── 碎裂仍在 → 进入 Step 2

Step 2: 运行 MDL 诊断工具
  python3 tools/diagnose_mdl.py assets/MyCharacter/Character.mdl
  └── 检查：boundary edges、顶点 NaN/Inf、索引越界

Step 3: 验证原始 GLB 是否正常
  └── 去 https://gltf-viewer.donmccurdy.com/ 在线查看
  └── GLB 本身碎裂 → 模型源文件问题

Step 4: 检查坐标系转换
  └── 模型镜像/翻转 → 检查 flip_z 和 winding_order
```

---

## 12. 模型不显示全解

### 症状

模型加载无报错，但场景中完全看不到角色。

### 排查流程

```
模型不显示？
  │
  ├── 检查 1: 资源路径是否正确？
  │   print(cache:GetResource("Model", "MyCharacter/Character.mdl"))
  │   └── nil → 路径错误，检查文件是否在 assets/ 下
  │
  ├── 检查 2: 是否使用了 AnimatedModel？
  │   └── StaticModel → 改为 AnimatedModel
  │
  ├── 检查 3: BONECOLLISION_SPHERE 是否设置？
  │   └── 骨骼必须设置 collision mask = 1
  │   └── 否则 WorldBoundingBox = NaN → 引擎剔除
  │   └── 我们的转换器已内置此设置
  │
  ├── 检查 4: 材质是否正确？
  │   └── 没有材质 → 可能完全透明
  │
  ├── 检查 5: 模型缩放是否正确？
  │   └── 模型极小 → 检查 node.scale
  │
  └── 检查 6: 相机是否对准模型？
      └── 调整相机位置
```

### BONECOLLISION_SPHERE 详解

```
UrhoX 引擎内部机制：
  AnimatedModel::UpdateBoneBoundingBox()
    遍历所有骨骼
      如果 collisionMask & SPHERE → 用骨骼位置扩展 BoundingBox
      如果 collisionMask == 0 → 跳过
    如果没有任何骨骼参与 → BoundingBox = 未初始化 → NaN → 被剔除

转换器中的实现：
  BONECOLLISION_SPHERE = 1
  f.write(struct.pack('<B', BONECOLLISION_SPHERE))  # collision mask
  f.write(struct.pack('<f', bone_radius))            # sphere radius
```

---

## 13. Meshy AI 模型专项指南

### 特点 1: 超高面数

Meshy AI 生成的模型通常有 **100 万+** 顶点。零处理转换后 MDL 约 70-80MB。

### 特点 2: Armature 缩放因子

Meshy AI 模型的 Armature 根节点有 `scale: [0.01, 0.01, 0.01]`（厘米 → 米转换）。转换器已自动处理。

### 特点 3: 动画分离

每个动画是单独的 GLB 文件。模型只从一个 GLB 转换，动画从各自的 GLB 分别提取。

### 特点 4: 纹理嵌入

纹理嵌入在 GLB 二进制数据中，需要用 `--texture` 参数提取。

### 特点 5: 文件命名

```bash
# 建议用简短的动画名
--ani-name "Idle"       # 不要用 "Meshy_AI_biped_Animation_Idle_withSkin"
```

### 特点 6: 骨骼缩放不一致（动画切换时角色大小变化）🔴

**症状**：角色在 Idle 状态下比 Running 状态大约 17.6%，切换动画时角色会"突然变大/变小"。

**根本原因**：Meshy AI 在不同动画 GLB 中，对 `Hips`（根骨骼）写入了不同的 `scale` 关键帧：

| 动画 | Hips 骨骼 Scale | 视觉效果 |
|------|-----------------|---------|
| Idle | `[1.1765, 1.1765, 1.1765]` | 角色变大 17.6% |
| Walking_Woman | `[1.1765, 1.1765, 1.1765]` | 角色变大 17.6% |
| Running | `[1.0, 1.0, 1.0]` | 正常大小 |

**修复方案**：在 `glb_to_urho.py` 的 `extract_animation` 函数中，强制将所有骨骼的 `scale` 关键帧归一化为 `[1.0, 1.0, 1.0]`：

```python
# glb_to_urho.py → extract_animation() → 处理 scale channel 时
# 修改前（有问题）：
kf['scale'] = scl.copy()

# 修改后（已修复）：
# 强制骨骼缩放为 1.0 —— Meshy AI 部分动画在 Hips 骨骼上
# 嵌入了非标准缩放值（如 1.1765），导致切换动画时角色大小变化。
kf['scale'] = np.array([1.0, 1.0, 1.0], dtype=np.float32)
```

**验证方法**：
```bash
python3 -c "
from tools.glb_to_urho import parse_glb, extract_animation
gltf, bin_data = parse_glb('3d-models/YourIdle.glb')
tracks = extract_animation(gltf, bin_data)[0]
for t in tracks:
    if t['bone_name'] == 'Hips':
        for kf in t['keyframes'][:3]:
            print(f\"Hips scale: {kf.get('scale', 'N/A')}\")
"
# 修复前: Hips scale: [1.1765, 1.1765, 1.1765]
# 修复后: Hips scale: [1.0, 1.0, 1.0]
```

### 综合速查

| 特点 | 处理方式 |
|------|---------|
| 百万面高精度模型（50-80MB） | 用 `raw_convert.py` 零处理，或 `--decimate 0.02` |
| 每个动画是单独的 GLB | 从任一 GLB 转模型，每个 GLB 单独转动画 |
| 内嵌纹理 | `--texture` 参数自动提取 |
| Armature 缩放不一致 | 转换器自动归一化 |
| 骨骼 scale 不一致（1.1765 问题） | 转换器已内置强制归一化 |
| 9000+ 边界边（非水密网格） | 正常特征，不影响显示 |

---

## 14. MDL 诊断工具

```bash
python3 tools/diagnose_mdl.py assets/MyCharacter/Character.mdl
```

**关键指标**：

| 指标 | 正常值 | 异常处理 |
|------|--------|---------|
| boundary edges | 0-1 | > 100 = 网格有大量缝隙（Meshy AI 正常） |
| NaN/Inf vertices | 0 | > 0 = 数据损坏，重新转换 |
| out-of-range indices | 0 | > 0 = 索引错误，重新转换 |
| collisionMask | 1 (每个骨骼) | 0 = 模型不可见 |
| degenerate triangles | < 1% | 少量可接受 |

---

## 15. 常见陷阱速查表

| # | 陷阱 | 症状 | 原因 | 解决 |
|---|------|------|------|------|
| 1 | QEM 降面碎裂 | 模型碎裂如碎玻璃 | UV 接缝处索引错误 | `raw_convert.py` 零处理 |
| 2 | 模型被剔除不显示 | 加载无报错但看不到 | 骨骼无 BONECOLLISION_SPHERE | 用最新转换器（已内置） |
| 3 | Armature 缩放没应用 | 模型极小（1/100） | Meshy AI 0.01 缩放因子 | 转换器自动处理 |
| 4 | 骨骼结构不匹配 | 动画时模型扭曲 | 不同来源的 GLB 骨骼不同 | 使用同一来源的 GLB |
| 5 | 用了 StaticModel | 模型不动 | StaticModel 无骨骼动画 | 改为 AnimatedModel |
| 6 | 纹理路径错误 | 白色/紫色模型 | 纹理未提取或路径错 | `--texture` 提取后检查路径 |
| 7 | AnimationController 不兼容 | 动画无法播放 | ANI 不完全兼容 | 改用 AnimationState |
| 8 | 路径加了 assets/ 前缀 | Resource not found | assets/ 是根目录不需前缀 | 直接写 `"MyChar/Char.mdl"` |
| 9 | 动画切换时大小突变 🔴 | Idle 比 Run 大 17.6% | Meshy AI Hips 骨骼非标准缩放 | 最新转换器已内置归一化 |

---

## 16. 完整代码示例

### 最小可运行示例

```lua
-- main.lua — 最小可运行示例：加载自定义角色 + 播放动画

local scene_ = nil
local animModel_ = nil
local currentAnimState_ = nil
local currentAnimName_ = "Idle"

function Start()
    -- 创建场景
    scene_ = Scene()
    scene_:CreateComponent("Octree")

    -- 灯光
    local lightNode = scene_:CreateChild("Light")
    lightNode.position = Vector3(0, 10, -5)
    lightNode.direction = Vector3(0.5, -1.0, 0.5)
    local light = lightNode:CreateComponent("Light")
    light.lightType = LIGHT_DIRECTIONAL
    light.brightness = 1.0

    -- 地面
    local floorNode = scene_:CreateChild("Floor")
    floorNode.scale = Vector3(50, 1, 50)
    local floorModel = floorNode:CreateComponent("StaticModel")
    floorModel:SetModel(cache:GetResource("Model", "Models/Box.mdl"))

    -- 角色
    local characterNode = scene_:CreateChild("Character")
    characterNode.position = Vector3(0, 0.5, 0)

    animModel_ = characterNode:CreateComponent("AnimatedModel")
    animModel_:SetModel(cache:GetResource("Model", "MyCharacter/Character.mdl"))
    animModel_:SetCastShadows(true)
    animModel_:SetUpdateInvisible(true)

    -- 材质
    local mat = Material:new()
    mat:SetTechnique(0, cache:GetResource("Technique", "Techniques/PBR/PBRDiff.xml"))
    mat:SetTexture(0, cache:GetResource("Texture2D", "Textures/texture_0.png"))
    mat:SetShaderParameter("Roughness", Variant(0.7))
    mat:SetShaderParameter("Metallic", Variant(0.0))
    animModel_:SetMaterial(mat)

    -- 播放 Idle
    PlayAnim("Idle", true)

    -- 相机
    local cameraNode = scene_:CreateChild("Camera")
    cameraNode.position = Vector3(0, 3, -5)
    cameraNode:LookAt(Vector3(0, 1, 0))
    local camera = cameraNode:CreateComponent("Camera")
    renderer:SetViewport(0, Viewport:new(scene_, camera))

    SubscribeToEvent("Update", "HandleUpdate")
end

function PlayAnim(name, looped)
    if currentAnimState_ then
        animModel_:RemoveAnimationState(currentAnimState_)
        currentAnimState_ = nil
    end

    local paths = {
        Idle = "MyCharacter/CharacterIdle.ani",
        Walk = "MyCharacter/CharacterWalking.ani",
        Run  = "MyCharacter/CharacterRunning.ani",
    }

    local anim = cache:GetResource("Animation", paths[name])
    if anim == nil then return end

    currentAnimState_ = animModel_:AddAnimationState(anim)
    currentAnimState_:SetWeight(1.0)
    currentAnimState_:SetLooped(looped ~= false)
    currentAnimName_ = name
end

function HandleUpdate(eventType, eventData)
    local dt = eventData["TimeStep"]:GetFloat()
    if currentAnimState_ then
        currentAnimState_:AddTime(dt)
    end

    local moving = input:GetKeyDown(KEY_W) or input:GetKeyDown(KEY_UP)
    local running = input:GetKeyDown(KEY_SHIFT)

    if moving and running then
        if currentAnimName_ ~= "Run" then PlayAnim("Run", true) end
    elseif moving then
        if currentAnimName_ ~= "Walk" then PlayAnim("Walk", true) end
    else
        if currentAnimName_ ~= "Idle" then PlayAnim("Idle", true) end
    end
end
```

### 转换后的文件结构

```
workspace/
├── assets/
│   ├── MyCharacter/
│   │   ├── Character.mdl              # 模型（raw_convert.py 生成）
│   │   ├── CharacterIdle.ani          # Idle 动画
│   │   ├── CharacterWalking.ani       # Walking 动画
│   │   └── CharacterRunning.ani       # Running 动画
│   └── Textures/
│       └── texture_0.png              # 提取的纹理
├── scripts/
│   └── main.lua                       # 游戏代码
└── tools/
    ├── glb_to_urho.py                 # 完整转换器
    ├── raw_convert.py                 # 零处理转换器
    └── diagnose_mdl.py                # 诊断工具
```

---

## 17. FAQ

### Q: 零处理转换的文件太大（70-80MB），能优化吗？

A: 三种方法：
1. 在 Meshy AI 生成时选择更低精度
2. 用 Blender 打开 GLB → Decimate Modifier 降面 → 导出新 GLB → 再用 `raw_convert.py`
3. 尝试 `glb_to_urho.py --decimate 0.05`（保留 5%），不碎裂就用

### Q: 动画看起来卡顿/不流畅？

A: 检查：
1. `HandleUpdate` 中是否每帧调用了 `currentAnimState:AddTime(dt)`
2. dt 是否正确获取（`eventData["TimeStep"]:GetFloat()`）
3. ANI 文件是否转换成功（关键帧数量应 > 0）

### Q: 可以用 AnimationController 代替 AnimationState 吗？

A: 可以尝试，但转换后的 ANI 文件可能不完全兼容。如果 AnimationController 不工作，请使用 AnimationState 手动驱动。

### Q: Mixamo 模型也能用这个流程吗？

A: 可以。Mixamo 导出的 GLB/FBX 和 Meshy AI 类似，都能用这个转换流程。唯一区别是 Mixamo 模型面数通常较低，不需要降面。

### Q: 引擎不是原生支持 FBX 吗？为什么还要转换？

A: UrhoX 确实支持 FBX 运行时加载。如果 FBX 直接加载正常就不需要转换。但以下情况需要转换：
- GLB 格式（不是 FBX）
- 加载后碎裂或不显示
- 模型面数过高需要降面
- 需要精确控制输出质量

### Q: 多个角色怎么处理？

A: 每个角色独立转换：
```bash
bash convert_character.sh 3d-models/warrior Warrior
bash convert_character.sh 3d-models/mage Mage
```

---

更多问题请查看 `skill-troubleshooting.md`
