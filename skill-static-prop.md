# 静态 3D 物件导入（GLB 雕像/道具/装饰）

## 适用场景

- GLB 格式的**无骨骼动画**模型（雕像、花瓶、道具、宠物摆件等）
- 只需要在场景中放置，不需要播放动画
- 来自 Meshy AI、Tripo AI、Blender 等工具生成的静态模型

**不适用于**：带骨骼动画的角色 → 请用 `skill-animated-character.md`

---

## 两种方案

| 方案 | 适用情况 | 复杂度 |
|------|---------|--------|
| **方案 A：GLB → MDL 转换** | 推荐，效果最好 | 中等 |
| **方案 B：CustomGeometry** | 模型简单时可用 | 简单 |

---

## 方案 A：GLB → MDL 转换（推荐）

### Step 1：放置 GLB 文件

```
workspace/
├── 3d-models/
│   └── my_statue.glb       ← 原始 GLB 文件
```

### Step 2：转换模型

```bash
cd /workspace/tools

# 零处理转换（推荐，不会碎裂）
python3 raw_convert.py ../3d-models/my_statue.glb ../assets/Models/statue.mdl

# 或带降面（文件更小，但可能碎裂）
python3 glb_to_urho.py ../3d-models/my_statue.glb --mdl ../assets/Models/statue.mdl --decimate 0.1
```

### Step 3：提取纹理

```bash
python3 glb_to_urho.py ../3d-models/my_statue.glb --texture ../assets/Textures/
```

### Step 4：Lua 代码加载

```lua
-- =============================================
-- 加载静态 GLB 物件（转换后的 MDL）
-- =============================================

-- 创建节点
local statueNode = scene_:CreateChild("MyStatue")
statueNode.position = Vector3(5, 0, 3)        -- 位置
statueNode.rotation = Quaternion(0, 45, 0)     -- 旋转（Y 轴转 45 度）
statueNode.scale = Vector3(1, 1, 1)            -- 缩放

-- 加载模型（静态物件用 StaticModel）
local model = statueNode:CreateComponent("StaticModel")
model:SetModel(cache:GetResource("Model", "Models/statue.mdl"))
model:SetCastShadows(true)

-- 设置 PBR 材质
local mat = Material:new()
mat:SetTechnique(0, cache:GetResource("Technique", "Techniques/PBR/PBRDiff.xml"))
mat:SetTexture(0, cache:GetResource("Texture2D", "Textures/texture_0.png"))
mat:SetShaderParameter("Roughness", Variant(0.7))
mat:SetShaderParameter("Metallic", Variant(0.0))
model:SetMaterial(mat)
```

### Step 5：添加物理碰撞（可选）

```lua
-- 如果需要角色不穿过这个物件
local body = statueNode:CreateComponent("RigidBody")
body:SetCollisionLayer(2)
-- mass = 0 表示静态物体，不会被推动

local shape = statueNode:CreateComponent("CollisionShape")
shape:SetTriangleMesh(model:GetModel())
-- 或者用简单形状（性能更好）：
-- shape:SetBox(Vector3(1, 2, 1))  -- 长宽高
-- shape:SetSphere(0.5)            -- 半径
```

---

## 方案 B：CustomGeometry（无需转换工具）

适用于没有转换工具或模型非常简单的情况。

### Step 1：Python 提取 GLB 数据为 Lua 模块

```bash
python3 extract_glb.py assets/Models/my_statue.glb scripts/statue_mesh_data.lua
```

生成的 Lua 文件格式：
```lua
-- statue_mesh_data.lua（自动生成）
local M = {}
M.positions = {x1,y1,z1, x2,y2,z2, ...}    -- 顶点坐标
M.normals   = {nx1,ny1,nz1, nx2,ny2,nz2, ...}  -- 法线
M.uvs       = {u1,v1, u2,v2, ...}            -- UV 坐标
M.indices   = {i1,i2,i3, ...}                -- 三角面索引（1-based）
return M
```

### Step 2：Lua 加载

```lua
local meshData = require("statue_mesh_data")
local GLBLoader = require("glb_loader")

local statueNode = GLBLoader.LoadFromData(scene_, meshData, {
    position = Vector3(5, 0, 3),
    diffuseTexture = "Textures/statue_color.png",
    metallic = 0.0,
    roughness = 0.8,
})
```

---

## 材质预设表

不同材质类型推荐的 PBR 参数：

| 材质类型 | Roughness | Metallic | 说明 |
|---------|-----------|----------|------|
| 石头/石像 | 0.8 | 0.0 | 粗糙、无金属感 |
| 大理石 | 0.3 | 0.0 | 较光滑 |
| 金属/铜像 | 0.4 | 1.0 | 金属质感 |
| 金色 | 0.3 | 1.0 | 光滑金属 |
| 木头 | 0.7 | 0.0 | 中等粗糙 |
| 玻璃 | 0.1 | 0.0 | 非常光滑 |
| 塑料 | 0.5 | 0.0 | 中等 |
| 布料 | 0.9 | 0.0 | 非常粗糙 |

使用方法：
```lua
mat:SetShaderParameter("Roughness", Variant(0.8))   -- 石头
mat:SetShaderParameter("Metallic", Variant(0.0))
```

---

## 批量放置多个物件

```lua
-- 配置表：一次放置多个物件
local PROPS = {
    { model = "Models/vase.mdl",    pos = Vector3(2, 0, 3),    scale = 0.5 },
    { model = "Models/lamp.mdl",    pos = Vector3(-1, 1.5, 0), scale = 1.0 },
    { model = "Models/plant.mdl",   pos = Vector3(4, 0, -2),   scale = 0.8 },
    { model = "Models/statue.mdl",  pos = Vector3(0, 0, 5),    scale = 1.2 },
}

for _, prop in ipairs(PROPS) do
    local node = scene_:CreateChild("Prop")
    node.position = prop.pos
    node.scale = Vector3(prop.scale, prop.scale, prop.scale)

    local model = node:CreateComponent("StaticModel")
    model:SetModel(cache:GetResource("Model", prop.model))
    model:SetCastShadows(true)

    -- 统一材质（或每个物件单独设置）
    local mat = Material:new()
    mat:SetTechnique(0, cache:GetResource("Technique", "Techniques/PBR/PBRDiff.xml"))
    mat:SetShaderParameter("Roughness", Variant(0.7))
    mat:SetShaderParameter("Metallic", Variant(0.0))
    model:SetMaterial(mat)
end
```

---

## 常见问题

遇到问题请查看 `skill-troubleshooting.md`，常见的有：
- 模型不可见 → 检查路径、检查缩放
- 白色无纹理 → 需要手动设置材质和纹理
- 模型太大/太小 → 调整 `node.scale`
- 模型碎裂 → 使用 `raw_convert.py` 零处理转换
