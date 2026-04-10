# 骨骼动画角色导入（GLB 角色 + 动画状态机）

## 适用场景

- GLB 格式的**带骨骼动画**角色模型（Idle、Walk、Run、Attack 等）
- 来自 Meshy AI、Mixamo、Blender 的骨骼蒙皮角色
- 需要在游戏中播放多个动画并通过状态机切换

**不适用于**：静态物件 → 用 `skill-static-prop.md`；FBX 场景素材 → 用 `skill-scene-fbx.md`

---

## 整体流程

```
1. 放置 GLB 文件到项目
         ↓
2. 转换模型：GLB → MDL（一次）
         ↓
3. 转换动画：GLB → ANI（每个动画一次）
         ↓
4. 提取纹理：GLB → PNG
         ↓
5. Lua 中加载模型 + 材质 + 播放动画
         ↓
6. 构建并预览
```

---

## Step 1：放置 GLB 源文件

```
workspace/
├── 3d-models/                        ← 原始 GLB（不部署）
│   ├── Character_Idle.glb
│   ├── Character_Walking.glb
│   ├── Character_Running.glb
│   └── Character_Attack.glb
```

**Meshy AI 用户注意**：Meshy AI 每个动画是单独的 GLB 文件（每个包含完整模型 + 一段动画），这是正常的，工具链支持这种结构。

---

## Step 2：转换模型（GLB → MDL）

```bash
cd /workspace/tools

# 推荐：零处理转换（不会碎裂）
python3 raw_convert.py \
    ../3d-models/Character_Idle.glb \
    ../assets/MyCharacter/Character.mdl
```

**只需从任意一个 GLB 转换模型**（所有动画 GLB 的模型网格相同）。

备选（带降面，文件更小但可能碎裂）：
```bash
python3 glb_to_urho.py \
    ../3d-models/Character_Idle.glb \
    --mdl ../assets/MyCharacter/Character.mdl \
    --decimate 0.02
```

---

## Step 3：转换动画（GLB → ANI）

每个动画单独转换：

```bash
# Idle
python3 glb_to_urho.py ../3d-models/Character_Idle.glb \
    --ani-only ../assets/MyCharacter/CharacterIdle.ani --ani-name "Idle"

# Walking
python3 glb_to_urho.py ../3d-models/Character_Walking.glb \
    --ani-only ../assets/MyCharacter/CharacterWalking.ani --ani-name "Walking"

# Running
python3 glb_to_urho.py ../3d-models/Character_Running.glb \
    --ani-only ../assets/MyCharacter/CharacterRunning.ani --ani-name "Running"

# Attack
python3 glb_to_urho.py ../3d-models/Character_Attack.glb \
    --ani-only ../assets/MyCharacter/CharacterAttack.ani --ani-name "Attack"
```

---

## Step 4：提取纹理

```bash
python3 glb_to_urho.py ../3d-models/Character_Idle.glb --texture ../assets/Textures/
```

---

## Step 5：Lua 加载与动画播放

### 核心代码

```lua
-- ============================================================
-- 角色配置
-- ============================================================
local CONFIG = {
    Model = "MyCharacter/Character.mdl",
    Anims = {
        Idle    = "MyCharacter/CharacterIdle.ani",
        Walk    = "MyCharacter/CharacterWalking.ani",
        Run     = "MyCharacter/CharacterRunning.ani",
        Attack  = "MyCharacter/CharacterAttack.ani",
    },
    Texture = "Textures/texture_0.png",
}

-- ============================================================
-- 加载模型
-- ============================================================
local characterNode = scene_:CreateChild("Character")
characterNode.position = Vector3(0, 0, 0)

-- !! 必须用 AnimatedModel，不是 StaticModel !!
local animModel = characterNode:CreateComponent("AnimatedModel")
animModel:SetModel(cache:GetResource("Model", CONFIG.Model))
animModel:SetCastShadows(true)
animModel:SetUpdateInvisible(true)

-- ============================================================
-- PBR 材质
-- ============================================================
local mat = Material:new()
mat:SetTechnique(0, cache:GetResource("Technique", "Techniques/PBR/PBRDiff.xml"))
mat:SetTexture(0, cache:GetResource("Texture2D", CONFIG.Texture))
mat:SetShaderParameter("Roughness", Variant(0.7))
mat:SetShaderParameter("Metallic", Variant(0.0))
animModel:SetMaterial(mat)

-- ============================================================
-- 动画播放系统（AnimationState 方式）
-- ============================================================
local currentAnimState = nil
local currentAnimName = ""

function PlayAnimation(animName, looped)
    if animName == currentAnimName then return end

    -- 移除旧动画
    if currentAnimState then
        animModel:RemoveAnimationState(currentAnimState)
        currentAnimState = nil
    end

    -- 加载并播放新动画
    local animPath = CONFIG.Anims[animName]
    if not animPath then return end

    local anim = cache:GetResource("Animation", animPath)
    if anim == nil then
        print("WARNING: Animation not found: " .. animPath)
        return
    end

    currentAnimState = animModel:AddAnimationState(anim)
    currentAnimState:SetWeight(1.0)
    currentAnimState:SetLooped(looped ~= false)
    currentAnimName = animName
end

-- 初始播放 Idle
PlayAnimation("Idle", true)

-- ============================================================
-- 每帧更新
-- ============================================================
function HandleUpdate(eventType, eventData)
    local dt = eventData["TimeStep"]:GetFloat()

    -- 推进动画
    if currentAnimState then
        currentAnimState:AddTime(dt)
    end

    -- 输入切换动画
    if input:GetKeyDown(KEY_W) then
        if input:GetKeyDown(KEY_SHIFT) then
            PlayAnimation("Run", true)
        else
            PlayAnimation("Walk", true)
        end
    elseif input:GetKeyPress(KEY_J) then
        PlayAnimation("Attack", false)  -- 攻击：播放一次
    else
        if currentAnimName ~= "Attack" or
           (currentAnimState and not currentAnimState:GetLooped() and
            currentAnimState:GetTime() >= currentAnimState:GetLength()) then
            PlayAnimation("Idle", true)
        end
    end
end
```

---

## 为什么用 AnimationState 而不是 AnimationController？

| 特性 | AnimationState（推荐） | AnimationController |
|------|----------------------|---------------------|
| 转换后 ANI 兼容性 | ✅ 完全兼容 | ⚠️ 可能有兼容问题 |
| 控制精度 | ✅ 逐帧手动控制 | 自动管理 |
| 已知 bug | ✅ 无 | ⚠️ GetTrackName 崩溃风险 |
| 推荐度 | **推荐** | 备选 |

---

## 一键转换脚本

保存为 `convert_character.sh`，一键完成所有转换：

```bash
#!/bin/bash
# 用法: bash convert_character.sh <glb目录> <角色名>
# 示例: bash convert_character.sh 3d-models MyGirl

set -e
GLB_DIR="${1:?用法: bash convert_character.sh <glb目录> <角色名>}"
CHAR_NAME="${2:?请提供角色名}"
TOOLS="tools"
OUT_MDL="assets/${CHAR_NAME}/${CHAR_NAME}.mdl"
OUT_ANIM="assets/${CHAR_NAME}Anims"
OUT_TEX="assets/Textures"

GLB_FILES=(${GLB_DIR}/*.glb)
FIRST_GLB="${GLB_FILES[0]}"
echo "找到 ${#GLB_FILES[@]} 个 GLB 文件"

# 1. 转换模型
echo "[1/3] 模型: ${FIRST_GLB} → ${OUT_MDL}"
mkdir -p "$(dirname ${OUT_MDL})"
cd ${TOOLS} && python3 raw_convert.py "../${FIRST_GLB}" "../${OUT_MDL}" && cd ..

# 2. 提取纹理
echo "[2/3] 纹理 → ${OUT_TEX}/"
mkdir -p "${OUT_TEX}"
cd ${TOOLS} && python3 glb_to_urho.py "../${FIRST_GLB}" --texture "../${OUT_TEX}/" && cd ..

# 3. 转换所有动画
echo "[3/3] 动画..."
mkdir -p "${OUT_ANIM}"
for glb in "${GLB_FILES[@]}"; do
    filename=$(basename "$glb" .glb)
    anim_name=$(echo "$filename" | sed 's/.*Animation_//;s/_withSkin//;s/.*_//')
    [ -z "$anim_name" ] && anim_name="$filename"
    echo "  ${filename} → ${anim_name}"
    cd ${TOOLS} && python3 glb_to_urho.py "../${glb}" \
        --ani-only "../${OUT_ANIM}/${CHAR_NAME}${anim_name}.ani" \
        --ani-name "${anim_name}" 2>/dev/null && cd .. || cd ..
done

echo "完成！模型: ${OUT_MDL}, 动画: ${OUT_ANIM}/, 纹理: ${OUT_TEX}/"
```

---

## ⚠️ 关键 Bug 和陷阱

### Bug 1：GetTrackName 崩溃

**绝对不要在代码中调用这些方法**（它们不存在，会崩溃）：
```lua
-- 全部会崩溃！
animation:GetTrackName(index)
animation:GetTrackBoneName(index)
```

### Bug 2：模型不可见（NaN BoundingBox）

**原因**：MDL 文件中骨骼的 `collisionMask = 0` → WorldBoundingBox 计算为 NaN → 引擎剔除模型。

**修复**：转换器中每个骨骼必须设置 `BONECOLLISION_SPHERE`：
```python
# glb_to_urho.py 中每个骨骼的碰撞数据：
f.write(struct.pack('<B', 1))    # BONECOLLISION_SPHERE
f.write(struct.pack('<f', 0.1))  # radius
```

我们的 `raw_convert.py` 和 `glb_to_urho.py` 已内置此修复。

### Bug 3：模型碎裂

**原因**：QEM 降面算法在 UV 接缝处索引重映射错误。

**解决**：使用 `raw_convert.py`（零处理转换），不降面就不碎裂。

### Bug 4：Meshy AI 模型动画时缩放突变

**原因**：Meshy AI 的 Armature 节点有非单位缩放，不同动画 GLB 的 Armature 缩放不一致。

**解决**：转换器已内置骨骼缩放归一化处理。

---

## Meshy AI 专项指南

Meshy AI 生成的模型有以下特点需要特殊处理：

| 特点 | 处理方式 |
|------|---------|
| 百万面高精度模型（50-80MB） | 用 `raw_convert.py` 零处理，或 `--decimate 0.02` |
| 每个动画是单独的 GLB | 从任一 GLB 转模型，每个 GLB 单独转动画 |
| 内嵌纹理 | `--texture` 参数自动提取 |
| Armature 缩放不一致 | 转换器自动归一化 |
| 9000+ 边界边（非水密网格） | 正常特征，不影响显示 |

---

## MDL 诊断工具

遇到问题时运行诊断：

```bash
python3 tools/diagnose_mdl.py assets/MyCharacter/Character.mdl
```

检查报告中的：
- `boundary edges > 0` → 模型有接缝（Meshy AI 正常现象）
- `collisionMask = 0` → 骨骼未设碰撞 → 模型不可见
- `NaN/Inf in vertices` → 转换数据错误
- `index out of range` → 索引重映射出错

---

## 常见问题

遇到其他问题请查看 `skill-troubleshooting.md`
