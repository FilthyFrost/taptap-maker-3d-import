# FBX 场景素材导入（家具/建筑/环境）

## 适用场景

- **FBX 格式**的静态 3D 素材（家具、建筑、地板、门窗等）
- UrhoX 引擎原生支持 FBX，**一行代码直接加载**，无需转换
- 适用于室内装饰、建筑构件、场景搭建

**不适用于**：GLB 格式 → 用 `skill-static-prop.md`；骨骼动画角色 → 用 `skill-animated-character.md`

---

## 最简方案：FBX 直接加载

### Step 1：放置文件

```
workspace/
├── assets/
│   └── Models/
│       ├── sofa.fbx
│       ├── door.fbx
│       ├── floor_tile.fbx
│       └── Textures/          ← 配套纹理（如果有）
│           ├── sofa_color.png
│           └── door_color.png
```

### Step 2：一行代码加载

```lua
-- 加载沙发
local sofaNode = scene_:CreateChild("Sofa")
sofaNode.position = Vector3(3, 0, 2)
sofaNode.rotation = Quaternion(0, 45, 0)  -- Y 轴旋转 45 度

local sofaModel = sofaNode:CreateComponent("StaticModel")
sofaModel:SetModel(cache:GetResource("Model", "Models/sofa.fbx"))
sofaModel:SetCastShadows(true)
```

**就这么简单。** FBX 是 UrhoX 原生支持的格式。

---

## 设置材质和纹理

### 方式 1：FBX 自带材质（大部分情况）

如果 FBX 文件内嵌了材质和纹理，引擎会自动加载，不需要额外代码。

### 方式 2：手动设置 PBR 材质

如果显示为白色或紫色，手动设置材质：

```lua
local mat = Material:new()
mat:SetTechnique(0, cache:GetResource("Technique", "Techniques/PBR/PBRDiff.xml"))

-- 加载颜色纹理
mat:SetTexture(0, cache:GetResource("Texture2D", "Textures/sofa_color.png"))

-- PBR 参数
mat:SetShaderParameter("Roughness", Variant(0.6))
mat:SetShaderParameter("Metallic", Variant(0.0))

sofaModel:SetMaterial(mat)
```

### 方式 3：纯色材质（无纹理时）

```lua
local mat = Material:new()
mat:SetTechnique(0, cache:GetResource("Technique", "Techniques/PBR/PBRNoTexture.xml"))
mat:SetShaderParameter("MatDiffColor", Variant(Color(0.8, 0.6, 0.4, 1.0)))  -- 木色
mat:SetShaderParameter("Roughness", Variant(0.7))
mat:SetShaderParameter("Metallic", Variant(0.0))
sofaModel:SetMaterial(mat)
```

---

## 常用材质颜色预设

```lua
-- 材质颜色预设
local COLORS = {
    Wood     = Color(0.55, 0.35, 0.17, 1.0),   -- 木头棕
    Metal    = Color(0.75, 0.75, 0.75, 1.0),   -- 银灰色
    White    = Color(0.95, 0.95, 0.95, 1.0),   -- 白色墙壁
    Brick    = Color(0.65, 0.30, 0.20, 1.0),   -- 砖红色
    Concrete = Color(0.60, 0.60, 0.60, 1.0),   -- 水泥灰
    Grass    = Color(0.30, 0.55, 0.20, 1.0),   -- 草绿色
    Glass    = Color(0.80, 0.90, 1.00, 0.3),   -- 玻璃（半透明）
}
```

---

## 批量加载场景素材

```lua
-- 场景配置表
local SCENE_PROPS = {
    -- { 模型路径, 位置, 旋转(Y轴), 缩放 }
    { "Models/floor.fbx",      Vector3(0, 0, 0),     0,    Vector3(10, 1, 10)   },
    { "Models/wall_back.fbx",  Vector3(0, 1.5, 5),   0,    Vector3(10, 3, 0.2)  },
    { "Models/wall_left.fbx",  Vector3(-5, 1.5, 0),  90,   Vector3(10, 3, 0.2)  },
    { "Models/sofa.fbx",       Vector3(2, 0, 3),      45,   Vector3(1, 1, 1)     },
    { "Models/table.fbx",      Vector3(0, 0, 2),      0,    Vector3(1, 1, 1)     },
    { "Models/lamp.fbx",       Vector3(-1, 1.5, 0),   0,    Vector3(0.5, 0.5, 0.5) },
    { "Models/door.fbx",       Vector3(-5, 0, 3),     90,   Vector3(1, 1, 1)     },
}

for i, prop in ipairs(SCENE_PROPS) do
    local node = scene_:CreateChild("Prop_" .. i)
    node.position = prop[2]
    node.rotation = Quaternion(0, prop[3], 0)
    node.scale = prop[4]

    local model = node:CreateComponent("StaticModel")
    model:SetModel(cache:GetResource("Model", prop[1]))
    model:SetCastShadows(true)
end
```

---

## 尺寸调整

不同来源的 FBX 使用不同的单位：

| 来源 | 单位 | scale 参数 |
|------|------|-----------|
| Blender（默认） | 米 | `Vector3(1, 1, 1)` |
| 3ds Max | 厘米 | `Vector3(0.01, 0.01, 0.01)` |
| Maya | 厘米 | `Vector3(0.01, 0.01, 0.01)` |
| SketchUp | 英寸 | `Vector3(0.0254, 0.0254, 0.0254)` |
| 毫米单位 | 毫米 | `Vector3(0.001, 0.001, 0.001)` |

```lua
-- 模型太大？缩小
node.scale = Vector3(0.01, 0.01, 0.01)

-- 模型太小？放大
node.scale = Vector3(100, 100, 100)
```

---

## 添加物理碰撞

```lua
-- 让角色不能穿过家具
local body = sofaNode:CreateComponent("RigidBody")
body:SetCollisionLayer(2)
-- mass = 0 = 静态物体

local shape = sofaNode:CreateComponent("CollisionShape")
shape:SetBox(Vector3(2, 1, 1))  -- 长宽高
```

---

## FBX 加载失败时的备选方案

如果 FBX 文件引擎无法正常加载（少数情况），可以转换为 MDL：

```bash
# 先转成 GLB（用 Blender 或在线工具），再转 MDL
python3 tools/raw_convert.py input.glb output.mdl
```

然后用 `skill-static-prop.md` 的方式加载 MDL。

---

## 常见问题

| 问题 | 解决 |
|------|------|
| 模型显示为白色 | 手动设置 PBR 材质（见上方"方式 2"） |
| 模型显示为紫色 | Technique 路径错误，检查 `Techniques/PBR/PBRDiff.xml` |
| 模型完全不显示 | 检查文件路径，检查 scale（可能太小看不到） |
| 模型位置不对 | 调整 `node.position`，UrhoX 使用 Y 轴向上 |
| 模型太大/太小 | 调整 `node.scale`，参考尺寸调整表 |
| 纹理不显示 | 把纹理文件放到 `assets/Textures/` 下 |

更多问题请查看 `skill-troubleshooting.md`
