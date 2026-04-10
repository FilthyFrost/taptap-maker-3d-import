# 3D 模型问题排查手册

## 使用方法

按你遇到的**症状**找到对应章节，按步骤排查。

---

## 症状 1：模型完全不可见

```
排查流程：
│
├── 1. 资源路径正确吗？
│   print(cache:GetResource("Model", "你的路径"))
│   └── 返回 nil → 路径错误，检查文件是否在 assets/ 下
│   └── 有值 → 继续
│
├── 2. 骨骼动画模型用了 StaticModel？
│   └── 是 → 改为 AnimatedModel
│
├── 3. 骨骼碰撞 collisionMask = 0？（仅 AnimatedModel）
│   └── MDL 中每个骨骼的 collisionMask 必须 = 1 (BONECOLLISION_SPHERE)
│   └── 否则 WorldBoundingBox = NaN → 引擎剔除 → 不可见
│   └── 修复：用最新版 raw_convert.py 重新转换
│
├── 4. 材质没设置？
│   └── 没有材质 → 可能完全透明
│   └── 手动创建 PBR 材质并绑定
│
├── 5. 模型极小看不到？
│   └── 检查 node.scale，尝试放大到 Vector3(10, 10, 10)
│
└── 6. 相机没对准？
    └── 调整相机位置，或打印 characterNode.position 确认模型在哪
```

### BONECOLLISION_SPHERE 详解

UrhoX 引擎内部机制：
```
AnimatedModel::UpdateBoneBoundingBox()：
  遍历所有骨骼
    如果 collisionMask & SPHERE → 用骨骼位置扩展包围盒
    如果 collisionMask == 0 → 跳过
  如果没有任何骨骼参与 → BoundingBox 未初始化 → NaN → 被剔除
```

**修复代码**（在转换器 Python 中）：
```python
# 每个骨骼写入碰撞数据
BONECOLLISION_SPHERE = 1
f.write(struct.pack('<B', BONECOLLISION_SPHERE))  # collisionMask = 1
f.write(struct.pack('<f', 0.1))                   # radius = 0.1
```

---

## 症状 2：模型碎裂/破碎

```
排查流程：
│
├── 1. 是否使用了降面（--decimate）？
│   └── 是 → 用 raw_convert.py 重新转换（零处理）
│   └── 碎裂消失 → 问题在 QEM 降面算法，使用零处理即可
│   └── 碎裂仍在 → 继续
│
├── 2. 原始 GLB 本身碎裂吗？
│   └── 去 https://gltf-viewer.donmccurdy.com/ 在线查看
│   └── GLB 本身碎裂 → 模型源文件问题（Meshy AI 常见）
│   └── GLB 正常 → 转换器问题，继续
│
├── 3. 检查顶点数据是否正确
│   python3 tools/diagnose_mdl.py 你的模型.mdl
│   └── boundary edges > 0 → 有接缝（Meshy AI 正常现象）
│   └── NaN/Inf in vertices → 转换数据错误
│   └── index out of range → 索引重映射出错
│
├── 4. T-Pose 就碎？（不播动画也碎）
│   └── 是 → 问题在顶点数据写入，检查：
│       a. blendIndices 是 4×unsigned byte（不是 float/uint）
│       b. blendWeights 归一化为 sum = 1.0
│       c. 顶点属性写入顺序：Position→Normal→UV→Weights→Indices
│
└── 5. 动画后才碎？（T-Pose 正常）
    └── 问题在 offsetMatrix（逆绑定矩阵），检查：
        a. GLB 的 inverseBindMatrices 是 4×4 列主序
        b. 转换为 Urho3D 的 Matrix3x4 行主序
```

### 碎裂修复速查

| 碎裂情况 | 最可能原因 | 修复 |
|---------|-----------|------|
| 降面后碎裂 | QEM 在 UV 接缝处索引错误 | 用 `raw_convert.py` 零处理 |
| 零处理也碎裂 | blendIndices 格式错误 | 确保是 4×unsigned byte |
| T-Pose 碎裂 | 权重未归一化 | 确保 4 个权重 sum = 1.0 |
| 动画后碎裂 | offsetMatrix 转换错误 | 检查矩阵行列序转换 |
| 只有边缘碎裂 | Meshy AI 模型固有接缝 | 正常现象，不影响使用 |

---

## 症状 3：白色/无纹理

```
排查流程：
│
├── 1. 是否设置了材质？
│   └── 没有 → 手动创建 PBR 材质
│
├── 2. 使用了 PBRNoTexture.xml？
│   └── 是 → 改为 PBRDiff.xml 并绑定纹理
│
├── 3. 纹理文件存在吗？
│   └── 检查 assets/Textures/ 下是否有纹理文件
│   └── 没有 → 运行纹理提取命令
│
└── 4. 纹理路径正确吗？
    └── print(cache:GetResource("Texture2D", "你的纹理路径"))
    └── nil → 路径错误
```

### 修复代码
```lua
-- 提取纹理后设置材质
local mat = Material:new()
mat:SetTechnique(0, cache:GetResource("Technique", "Techniques/PBR/PBRDiff.xml"))
mat:SetTexture(0, cache:GetResource("Texture2D", "Textures/texture_0.png"))
mat:SetShaderParameter("Roughness", Variant(0.7))
mat:SetShaderParameter("Metallic", Variant(0.0))
model:SetMaterial(mat)
```

---

## 症状 4：动画不播放（模型静止）

```
排查流程：
│
├── 1. 使用了 StaticModel？
│   └── 是 → 改为 AnimatedModel
│
├── 2. 代码中调用了不存在的方法？
│   └── GetTrackName() → 删除！这个方法不存在，会崩溃
│   └── 遍历 animation tracks → 删除！不需要
│
├── 3. 使用了 AnimationController？
│   └── 改为 AnimationState 方式（更可靠）
│   └── 见 skill-animated-character.md
│
├── 4. 每帧调用了 AddTime 吗？
│   └── 没有 → 动画不会自动前进
│   └── 在 HandleUpdate 中添加 currentAnimState:AddTime(dt)
│
├── 5. ANI 文件正确吗？
│   └── 检查动画 tracks 数是否等于骨骼数
│   └── 检查 track 名称是否与 MDL 骨骼名一致
│
└── 6. 动画权重为 0？
    └── 确保 currentAnimState:SetWeight(1.0)
```

---

## 症状 5：引擎崩溃

```
排查流程：
│
├── 1. 检查是否调用了不存在的 API
│   └── GetTrackName() → 不存在
│   └── GetTrackBoneName() → 不存在
│   └── GetCurrentAnimation() → 不存在
│   └── 解决：删除所有对这些方法的调用
│
├── 2. 崩溃发生在 CreateCharacter？
│   └── 第几步崩溃？检查那一步用到了什么 API
│   └── 常见：在第 7 步遍历 track 时崩溃 → 删除遍历代码
│
└── 3. 资源加载时崩溃？
    └── MDL 文件可能损坏 → 重新转换
    └── ANI 文件可能不完整 → 重新转换
```

---

## 症状 6：模型大小/位置/方向不对

| 问题 | 解决 |
|------|------|
| 模型太大 | `node.scale = Vector3(0.01, 0.01, 0.01)` |
| 模型太小 | `node.scale = Vector3(10, 10, 10)` |
| 模型在地下 | `node.position = Vector3(0, 1, 0)` 抬高 Y 值 |
| 模型背对相机 | `adjNode.rotation = Quaternion(180, Vector3.UP)` |
| 模型侧躺 | 坐标系转换问题，检查 Z 轴翻转和 winding order |

---

## 诊断工具使用

### MDL 诊断
```bash
python3 tools/diagnose_mdl.py assets/MyModel.mdl
```
输出关键信息：顶点数、三角面数、骨骼数、collisionMask、边界边数、NaN 检查。

### GLB 在线查看
上传到 https://gltf-viewer.donmccurdy.com/ 确认原始模型是否正常。

### 运行时调试（Lua）
```lua
-- 打印模型信息
print("WorldBB:", animModel:GetWorldBoundingBox())
print("NumBones:", animModel:GetSkeleton():GetNumBones())
print("NumGeometries:", animModel:GetNumGeometries())

-- 打印骨骼信息
local skeleton = animModel:GetSkeleton()
for i = 0, skeleton:GetNumBones() - 1 do
    local bone = skeleton:GetBone(i)
    print("Bone[" .. i .. "]: " .. bone.name)
end

-- 打印动画信息
local anim = cache:GetResource("Animation", "MyCharacter/CharacterIdle.ani")
print("Duration:", anim:GetLength())
print("NumTracks:", anim:GetNumTracks())
```
