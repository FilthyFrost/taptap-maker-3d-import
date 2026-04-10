#!/usr/bin/env python3
"""
GLB to Urho3D MDL + ANI converter.
Supports skinned meshes with skeletal animation.
Includes mesh decimation via fast-simplification.

Usage:
    python3 glb_to_urho.py <input.glb> --mdl <output.mdl> --ani <output.ani>
    python3 glb_to_urho.py <input.glb> --ani-only <output.ani>
    python3 glb_to_urho.py <input.glb> --texture <output_dir>
"""

import struct
import json
import numpy as np
import os
import sys
import argparse

# ============================================================
# GLB Parser
# ============================================================

def parse_glb(filepath):
    """Parse a GLB file, return (gltf_json, binary_buffer)."""
    with open(filepath, 'rb') as f:
        magic = f.read(4)
        assert magic == b'glTF', f"Not a GLB file: {magic}"
        version = struct.unpack('<I', f.read(4))[0]
        length = struct.unpack('<I', f.read(4))[0]

        # JSON chunk
        chunk_len = struct.unpack('<I', f.read(4))[0]
        chunk_type = f.read(4)
        assert chunk_type == b'JSON', f"Expected JSON chunk, got {chunk_type}"
        json_data = f.read(chunk_len)
        gltf = json.loads(json_data)

        # Binary chunk
        bin_data = b''
        if f.tell() < length:
            chunk_len = struct.unpack('<I', f.read(4))[0]
            chunk_type = f.read(4)
            assert chunk_type == b'BIN\x00', f"Expected BIN chunk, got {chunk_type}"
            bin_data = f.read(chunk_len)

    return gltf, bin_data


def read_accessor(gltf, bin_data, accessor_idx):
    """Read an accessor's data from the binary buffer."""
    acc = gltf['accessors'][accessor_idx]
    bv = gltf['bufferViews'][acc['bufferView']]

    offset = bv.get('byteOffset', 0) + acc.get('byteOffset', 0)
    count = acc['count']
    comp_type = acc['componentType']
    acc_type = acc['type']

    # Component sizes
    comp_sizes = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}
    comp_dtypes = {5120: np.int8, 5121: np.uint8, 5122: np.int16,
                   5123: np.uint16, 5125: np.uint32, 5126: np.float32}

    # Number of components per element
    type_counts = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}

    n_comps = type_counts[acc_type]
    dtype = comp_dtypes[comp_type]
    stride = bv.get('byteStride', 0)
    elem_size = comp_sizes[comp_type] * n_comps

    if stride and stride != elem_size:
        # Strided access
        data = np.zeros((count, n_comps), dtype=dtype)
        for i in range(count):
            start = offset + i * stride
            chunk = bin_data[start:start + elem_size]
            data[i] = np.frombuffer(chunk, dtype=dtype, count=n_comps)
    else:
        data_bytes = bin_data[offset:offset + count * elem_size]
        data = np.frombuffer(data_bytes, dtype=dtype).reshape(count, n_comps)

    return data.copy()


def read_buffer_view_raw(gltf, bin_data, bv_idx):
    """Read raw bytes from a buffer view."""
    bv = gltf['bufferViews'][bv_idx]
    offset = bv.get('byteOffset', 0)
    length = bv['byteLength']
    return bin_data[offset:offset + length]


# ============================================================
# Mesh Decimation
# ============================================================

def pre_weld_vertices(positions, normals, texcoords, joints, weights, indices, epsilon=None):
    """Merge vertices at the same position before decimation."""
    from scipy.spatial import cKDTree

    if epsilon is None:
        bbox_size = np.max(positions.max(axis=0) - positions.min(axis=0))
        epsilon = bbox_size * 1e-6
        print(f"  Pre-weld epsilon: {epsilon:.8f} (bbox_size={bbox_size:.2f})")

    tree = cKDTree(positions)
    pairs = tree.query_pairs(epsilon)

    if not pairs:
        print(f"  Pre-weld: no duplicate vertices found")
        return positions, normals, texcoords, joints, weights, indices

    parent = list(range(len(positions)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            if ra > rb:
                ra, rb = rb, ra
            parent[rb] = ra

    for a, b in pairs:
        union(a, b)

    root_to_new = {}
    new_idx = 0
    old_to_new = np.zeros(len(positions), dtype=np.int32)

    for i in range(len(positions)):
        root = find(i)
        if root not in root_to_new:
            root_to_new[root] = new_idx
            new_idx += 1
        old_to_new[i] = root_to_new[root]

    merged_count = len(positions) - new_idx
    if merged_count == 0:
        print(f"  Pre-weld: no vertices to merge")
        return positions, normals, texcoords, joints, weights, indices

    new_positions = np.zeros((new_idx, 3), dtype=np.float32)
    new_normals = np.zeros((new_idx, 3), dtype=np.float32)
    new_texcoords = np.zeros((new_idx, 2), dtype=np.float32)
    new_joints = np.zeros((new_idx, 4), dtype=np.uint8)
    new_weights = np.zeros((new_idx, 4), dtype=np.float32)

    seen = set()
    for i in range(len(positions)):
        ni = old_to_new[i]
        if ni not in seen:
            seen.add(ni)
            new_positions[ni] = positions[i]
            new_normals[ni] = normals[i]
            new_texcoords[ni] = texcoords[i]
            new_joints[ni] = joints[i]
            new_weights[ni] = weights[i]

    new_indices = old_to_new[indices].astype(np.uint32)

    faces = new_indices.reshape(-1, 3)
    valid = (faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 0] != faces[:, 2])
    degen = int((~valid).sum())
    faces = faces[valid]
    new_indices = faces.flatten().astype(np.uint32)

    print(f"  Pre-weld: merged {merged_count} duplicate vertices, removed {degen} degenerate triangles")
    print(f"  After pre-weld: {new_idx} vertices, {len(faces)} faces")

    return new_positions, new_normals, new_texcoords, new_joints, new_weights, new_indices


def post_weld_vertices(positions, normals, texcoords, joints, weights, indices, epsilon=None):
    """Close small gaps after decimation by merging very close vertices."""
    from scipy.spatial import cKDTree

    if epsilon is None:
        bbox_size = np.max(positions.max(axis=0) - positions.min(axis=0))
        epsilon = bbox_size * 1e-4
        print(f"  Post-weld epsilon: {epsilon:.8f} (bbox_size={bbox_size:.2f})")

    tree = cKDTree(positions)
    pairs = tree.query_pairs(epsilon)

    if not pairs:
        print(f"  Post-weld: no close vertices found")
        return positions, normals, texcoords, joints, weights, indices

    parent = list(range(len(positions)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            if ra > rb:
                ra, rb = rb, ra
            parent[rb] = ra

    for a, b in pairs:
        union(a, b)

    root_to_new = {}
    new_idx = 0
    old_to_new = np.zeros(len(positions), dtype=np.int32)

    for i in range(len(positions)):
        root = find(i)
        if root not in root_to_new:
            root_to_new[root] = new_idx
            new_idx += 1
        old_to_new[i] = root_to_new[root]

    merged_count = len(positions) - new_idx
    if merged_count == 0:
        print(f"  Post-weld: no vertices to merge")
        return positions, normals, texcoords, joints, weights, indices

    new_positions = np.zeros((new_idx, 3), dtype=np.float32)
    new_normals = np.zeros((new_idx, 3), dtype=np.float32)
    new_texcoords = np.zeros((new_idx, 2), dtype=np.float32)
    new_joints = np.zeros((new_idx, 4), dtype=np.uint8)
    new_weights = np.zeros((new_idx, 4), dtype=np.float32)

    vertex_counts = np.zeros(new_idx, dtype=np.int32)
    for i in range(len(positions)):
        ni = old_to_new[i]
        new_positions[ni] += positions[i]
        new_normals[ni] += normals[i]
        vertex_counts[ni] += 1

    seen = set()
    for i in range(len(positions)):
        ni = old_to_new[i]
        if ni not in seen:
            seen.add(ni)
            new_texcoords[ni] = texcoords[i]
            new_joints[ni] = joints[i]
            new_weights[ni] = weights[i]

    for ni in range(new_idx):
        cnt = vertex_counts[ni]
        if cnt > 0:
            new_positions[ni] /= cnt
        nrm_len = np.linalg.norm(new_normals[ni])
        if nrm_len > 1e-10:
            new_normals[ni] /= nrm_len

    new_indices = old_to_new[indices].astype(np.uint32)

    faces = new_indices.reshape(-1, 3)
    valid = (faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 0] != faces[:, 2])
    degen = int((~valid).sum())
    faces = faces[valid]
    new_indices = faces.flatten().astype(np.uint32)

    print(f"  Post-weld: merged {merged_count} vertices, removed {degen} degenerate triangles")
    print(f"  After post-weld: {new_idx} vertices, {len(faces)} faces")

    return new_positions, new_normals, new_texcoords, new_joints, new_weights, new_indices


def close_boundary_gaps(positions, normals, texcoords, joints, weights, indices, epsilon=None):
    """Close geometric boundary gaps by merging nearby boundary vertices."""
    from scipy.spatial import cKDTree
    from collections import defaultdict

    if epsilon is None:
        bbox_size = np.max(positions.max(axis=0) - positions.min(axis=0))
        epsilon = bbox_size * 5e-3
        print(f"  Gap-close epsilon: {epsilon:.6f} (bbox_size={bbox_size:.2f})")

    num_tris = len(indices) // 3
    faces = indices.reshape(-1, 3)

    def pos_key(idx):
        return positions[idx].tobytes()

    edge_tris = defaultdict(int)
    edge_idx_map = defaultdict(set)

    for ti in range(num_tris):
        i0, i1, i2 = faces[ti]
        pk0, pk1, pk2 = pos_key(i0), pos_key(i1), pos_key(i2)
        for (pka, pkb), (ia, ib) in [
            (tuple(sorted([pk0, pk1])), (i0, i1)),
            (tuple(sorted([pk1, pk2])), (i1, i2)),
            (tuple(sorted([pk0, pk2])), (i0, i2)),
        ]:
            edge_tris[(pka, pkb)] += 1
            edge_idx_map[(pka, pkb)].add(ia)
            edge_idx_map[(pka, pkb)].add(ib)

    boundary_vertex_set = set()
    for edge_key, count in edge_tris.items():
        if count == 1:
            boundary_vertex_set.update(edge_idx_map[edge_key])

    if not boundary_vertex_set:
        print(f"  Gap-close: no boundary vertices found, mesh is watertight")
        return positions, normals, texcoords, joints, weights, indices

    boundary_verts = sorted(boundary_vertex_set)
    print(f"  Gap-close: {len(boundary_verts)} boundary vertices, {sum(1 for c in edge_tris.values() if c == 1)} boundary edges")

    boundary_positions = positions[boundary_verts]
    tree = cKDTree(boundary_positions)
    pairs = tree.query_pairs(epsilon)

    if not pairs:
        print(f"  Gap-close: no close boundary vertex pairs within epsilon={epsilon:.6f}")
        return positions, normals, texcoords, joints, weights, indices

    parent = {}
    for bv in boundary_verts:
        parent[bv] = bv

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            if ra > rb:
                ra, rb = rb, ra
            parent[rb] = ra

    for (bi0, bi1) in pairs:
        vi0 = boundary_verts[bi0]
        vi1 = boundary_verts[bi1]
        union(vi0, vi1)

    remap = {}
    groups = defaultdict(list)
    for bv in boundary_verts:
        root = find(bv)
        groups[root].append(bv)

    merged_count = 0
    for root, members in groups.items():
        if len(members) > 1:
            avg_pos = np.mean(positions[members], axis=0)
            avg_nrm = np.mean(normals[members], axis=0)
            nrm_len = np.linalg.norm(avg_nrm)
            if nrm_len > 1e-10:
                avg_nrm /= nrm_len
            positions[root] = avg_pos
            normals[root] = avg_nrm
            for m in members:
                if m != root:
                    remap[m] = root
                    merged_count += 1

    if merged_count == 0:
        print(f"  Gap-close: no vertices to merge")
        return positions, normals, texcoords, joints, weights, indices

    new_indices = indices.copy()
    for i in range(len(new_indices)):
        idx = int(new_indices[i])
        if idx in remap:
            new_indices[i] = remap[idx]

    new_faces = new_indices.reshape(-1, 3)
    valid = (new_faces[:, 0] != new_faces[:, 1]) & \
            (new_faces[:, 1] != new_faces[:, 2]) & \
            (new_faces[:, 0] != new_faces[:, 2])
    degen = int((~valid).sum())
    new_faces = new_faces[valid]
    new_indices = new_faces.flatten().astype(np.uint32)

    print(f"  Gap-close: merged {merged_count} boundary vertices, removed {degen} degenerate triangles")

    return positions, normals, texcoords, joints, weights, new_indices


def decimate_mesh(positions, normals, texcoords, joints, weights, indices, target_ratio=0.05):
    """Decimate a skinned mesh using QEM edge-collapse (fast_simplification)."""
    import fast_simplification
    from scipy.spatial import cKDTree

    orig_positions = positions.copy()
    orig_texcoords = texcoords.copy()
    orig_joints = joints.copy()
    orig_weights = weights.copy()

    positions, normals, texcoords, joints, weights, indices = pre_weld_vertices(
        positions, normals, texcoords, joints, weights, indices
    )

    faces = indices.reshape(-1, 3)
    n_faces = len(faces)
    n_target = max(int(n_faces * target_ratio), 100)

    if n_target >= n_faces:
        print(f"  Decimation skipped: target {n_target} >= original {n_faces} faces")
        return positions, normals, texcoords, joints, weights, indices

    target_reduction = 1.0 - target_ratio
    print(f"  Decimating (QEM): {n_faces} faces -> target ~{n_target} faces (reduction={target_reduction:.3f})")

    out_verts, out_faces = fast_simplification.simplify(
        positions.astype(np.float64),
        faces.astype(np.int64),
        target_reduction=target_reduction,
        agg=5,
    )
    out_verts = out_verts.astype(np.float32)
    out_faces = out_faces.astype(np.int32)

    print(f"  QEM result: {len(out_verts)} vertices, {len(out_faces)} faces")

    tree = cKDTree(orig_positions)
    dists, nearest_idx = tree.query(out_verts)

    joints_out = orig_joints[nearest_idx]
    weights_out = orig_weights[nearest_idx]
    texcoords_out = orig_texcoords[nearest_idx]

    avg_dist = dists.mean()
    max_dist = dists.max()
    print(f"  Attribute mapping: avg_dist={avg_dist:.6f}, max_dist={max_dist:.6f}")

    indices_flat = out_faces.flatten().astype(np.uint32)
    out_verts, normals_placeholder, texcoords_out, joints_out, weights_out, indices_flat = post_weld_vertices(
        out_verts,
        np.zeros_like(out_verts),
        texcoords_out, joints_out, weights_out, indices_flat
    )
    out_faces = indices_flat.reshape(-1, 3)

    v0 = out_verts[out_faces[:, 0]]
    v1 = out_verts[out_faces[:, 1]]
    v2 = out_verts[out_faces[:, 2]]
    face_normals = np.cross(v1 - v0, v2 - v0)
    face_norm_len = np.linalg.norm(face_normals, axis=1, keepdims=True)
    face_norm_len[face_norm_len < 1e-10] = 1.0
    face_normals = face_normals / face_norm_len

    recomputed_normals = np.zeros_like(out_verts)
    for fi in range(len(out_faces)):
        for vi in out_faces[fi]:
            recomputed_normals[vi] += face_normals[fi]
    norm_len = np.linalg.norm(recomputed_normals, axis=1, keepdims=True)
    norm_len[norm_len < 1e-10] = 1.0
    normals_out = (recomputed_normals / norm_len).astype(np.float32)

    indices_out = out_faces.flatten().astype(np.uint32)

    print(f"  Final: {len(out_verts)} vertices, {len(out_faces)} faces")

    return out_verts, normals_out, texcoords_out, joints_out, weights_out, indices_out


# ============================================================
# Coordinate System Conversion (glTF RH -> Urho3D LH)
# ============================================================

def flip_z_position(pos):
    """Negate Z component of position/translation."""
    result = pos.copy()
    if result.ndim == 1:
        result[2] = -result[2]
    else:
        result[:, 2] = -result[:, 2]
    return result


def flip_z_normal(norm):
    """Negate Z component of normal."""
    return flip_z_position(norm)


def flip_z_quaternion_gltf(quat_xyzw):
    """Convert glTF quaternion (x,y,z,w) from RH to LH. Result in Urho3D order (w,x,y,z)."""
    x, y, z, w = quat_xyzw
    return np.array([w, -x, -y, z], dtype=np.float32)


def flip_z_matrix4x4_colmajor(mat_cm):
    """Convert a 4x4 column-major matrix from RH to LH (Z-flip). Returns 3x4 row-major."""
    mat = np.array(mat_cm, dtype=np.float32).reshape(4, 4).T
    S = np.diag([1.0, 1.0, -1.0, 1.0]).astype(np.float32)
    mat_flipped = S @ mat @ S
    return mat_flipped[:3, :].flatten()


def flip_winding_order(indices):
    """Reverse triangle winding order after Z-flip."""
    faces = indices.reshape(-1, 3)
    faces_flipped = faces[:, [0, 2, 1]]
    return faces_flipped.flatten()


# ============================================================
# Urho3D MDL Writer
# ============================================================

MASK_POSITION = 0x001
MASK_NORMAL = 0x002
MASK_COLOR = 0x004
MASK_TEXCOORD1 = 0x008
MASK_TEXCOORD2 = 0x010
MASK_CUBETEXCOORD1 = 0x020
MASK_CUBETEXCOORD2 = 0x040
MASK_TANGENT = 0x080
MASK_BLENDWEIGHTS = 0x100
MASK_BLENDINDICES = 0x200

BONECOLLISION_NONE = 0
BONECOLLISION_SPHERE = 1
BONECOLLISION_BOX = 2


def compute_vertex_size(element_mask):
    """Compute vertex size in bytes from element mask."""
    size = 0
    if element_mask & MASK_POSITION: size += 12
    if element_mask & MASK_NORMAL: size += 12
    if element_mask & MASK_COLOR: size += 4
    if element_mask & MASK_TEXCOORD1: size += 8
    if element_mask & MASK_TEXCOORD2: size += 8
    if element_mask & MASK_TANGENT: size += 16
    if element_mask & MASK_BLENDWEIGHTS: size += 16
    if element_mask & MASK_BLENDINDICES: size += 4
    return size


def write_string(f, s):
    """Write a null-terminated string."""
    f.write(s.encode('utf-8') + b'\x00')


def write_mdl(filepath, positions, normals, texcoords, joints, weights, indices,
              bones, bounding_box_min, bounding_box_max):
    """Write an Urho3D MDL file for a skinned mesh."""
    vertex_count = len(positions)
    index_count = len(indices)
    num_bones = len(bones)

    element_mask = MASK_POSITION | MASK_NORMAL | MASK_TEXCOORD1 | MASK_BLENDWEIGHTS | MASK_BLENDINDICES
    vertex_size = compute_vertex_size(element_mask)

    bone_mapping = list(range(num_bones))

    with open(filepath, 'wb') as f:
        f.write(b'UMDL')
        f.write(struct.pack('<I', 1))  # numVertexBuffers

        f.write(struct.pack('<I', vertex_count))
        f.write(struct.pack('<I', element_mask))
        f.write(struct.pack('<I', 0))  # morphRangeStart
        f.write(struct.pack('<I', 0))  # morphRangeCount

        for i in range(vertex_count):
            f.write(struct.pack('<3f', *positions[i]))
            f.write(struct.pack('<3f', *normals[i]))
            f.write(struct.pack('<2f', *texcoords[i]))
            f.write(struct.pack('<4f', *weights[i]))
            f.write(struct.pack('<4B', *joints[i]))

        f.write(struct.pack('<I', 1))  # numIndexBuffers

        large_indices = vertex_count > 65535
        index_size = 4 if large_indices else 2
        f.write(struct.pack('<I', index_count))
        f.write(struct.pack('<I', index_size))

        if large_indices:
            for idx in indices:
                f.write(struct.pack('<I', int(idx)))
        else:
            for idx in indices:
                f.write(struct.pack('<H', int(idx)))

        f.write(struct.pack('<I', 1))  # numGeometries

        f.write(struct.pack('<I', len(bone_mapping)))
        for bm in bone_mapping:
            f.write(struct.pack('<I', bm))

        f.write(struct.pack('<I', 1))  # numLodLevels
        f.write(struct.pack('<f', 0.0))
        f.write(struct.pack('<I', 0))  # TRIANGLE_LIST
        f.write(struct.pack('<I', 0))
        f.write(struct.pack('<I', 0))
        f.write(struct.pack('<I', 0))
        f.write(struct.pack('<I', index_count))

        f.write(struct.pack('<I', 0))  # numMorphs

        f.write(struct.pack('<I', num_bones))
        for bone in bones:
            write_string(f, bone['name'])
            f.write(struct.pack('<I', bone['parent_index']))
            f.write(struct.pack('<3f', *bone['position']))
            f.write(struct.pack('<4f', *bone['rotation']))
            f.write(struct.pack('<3f', *bone['scale']))
            f.write(struct.pack('<12f', *bone['offset_matrix']))
            f.write(struct.pack('<B', BONECOLLISION_SPHERE))
            f.write(struct.pack('<f', bone.get('radius', 0.1)))

        f.write(struct.pack('<3f', *bounding_box_min))
        f.write(struct.pack('<3f', *bounding_box_max))

    print(f"  MDL written: {filepath} ({os.path.getsize(filepath)} bytes)")
    print(f"    Vertices: {vertex_count}, Indices: {index_count}, Bones: {num_bones}")


# ============================================================
# Urho3D ANI Writer
# ============================================================

CHANNEL_POSITION = 1
CHANNEL_ROTATION = 2
CHANNEL_SCALE = 4


def write_ani(filepath, anim_name, duration, tracks):
    """Write an Urho3D ANI file."""
    with open(filepath, 'wb') as f:
        f.write(b'UANI')
        write_string(f, anim_name)
        f.write(struct.pack('<f', duration))
        f.write(struct.pack('<I', len(tracks)))

        for track in tracks:
            write_string(f, track['name'])
            f.write(struct.pack('<B', track['channel_mask']))
            f.write(struct.pack('<I', len(track['keyframes'])))

            for kf in track['keyframes']:
                f.write(struct.pack('<f', kf['time']))
                if track['channel_mask'] & CHANNEL_POSITION:
                    f.write(struct.pack('<3f', *kf['position']))
                if track['channel_mask'] & CHANNEL_ROTATION:
                    f.write(struct.pack('<4f', *kf['rotation']))
                if track['channel_mask'] & CHANNEL_SCALE:
                    f.write(struct.pack('<3f', *kf['scale']))

    print(f"  ANI written: {filepath} ({os.path.getsize(filepath)} bytes)")
    print(f"    Name: {anim_name}, Duration: {duration:.3f}s, Tracks: {len(tracks)}")


# ============================================================
# GLB -> Urho3D Conversion
# ============================================================

def quat_to_rotation_matrix(wxyz):
    """Convert quaternion (w,x,y,z) to 3x3 rotation matrix."""
    w, x, y, z = wxyz
    return np.array([
        [1 - 2*(y*y + z*z), 2*(x*y - w*z), 2*(x*z + w*y)],
        [2*(x*y + w*z), 1 - 2*(x*x + z*z), 2*(y*z - w*x)],
        [2*(x*z - w*y), 2*(y*z + w*x), 1 - 2*(x*x + y*y)]
    ], dtype=np.float32)


def make_transform_4x4(pos, rot_wxyz, scale):
    """Create a 4x4 transform matrix from position, quaternion (wxyz), scale."""
    R = quat_to_rotation_matrix(rot_wxyz)
    S = np.diag(scale).astype(np.float32)
    mat = np.eye(4, dtype=np.float32)
    mat[:3, :3] = R @ S
    mat[:3, 3] = pos
    return mat


def detect_armature_scale(gltf, skin_idx=0):
    """Detect the Armature node's uniform scale factor."""
    skin = gltf['skins'][skin_idx]
    joint_indices = skin['joints']
    nodes = gltf['nodes']

    parent_map = {}
    for ni, node in enumerate(nodes):
        for child in node.get('children', []):
            parent_map[child] = ni

    root_joint_node = joint_indices[0]
    cur = root_joint_node
    while cur in parent_map:
        parent_ni = parent_map[cur]
        parent_node = nodes[parent_ni]
        parent_name = parent_node.get('name', '')
        parent_scale = parent_node.get('scale', [1, 1, 1])

        if parent_ni not in set(joint_indices):
            sx, sy, sz = parent_scale
            if abs(sx - sy) < 1e-6 and abs(sy - sz) < 1e-6 and abs(sx - 1.0) > 1e-6:
                print(f"  Detected Armature node '{parent_name}' with uniform scale {sx:.6f}")
                return float(sx)
        cur = parent_ni

    return 1.0


def extract_skeleton(gltf, bin_data, skin_idx=0):
    """Extract skeleton from glTF skin."""
    skin = gltf['skins'][skin_idx]
    joint_indices = skin['joints']
    nodes = gltf['nodes']
    num_joints = len(joint_indices)

    armature_scale = detect_armature_scale(gltf, skin_idx)

    node_to_joint = {}
    for ji, ni in enumerate(joint_indices):
        node_to_joint[ni] = ji

    parent_map = {}
    for ni, node in enumerate(nodes):
        for child in node.get('children', []):
            parent_map[child] = ni

    bones = []
    for ji in range(num_joints):
        node_idx = joint_indices[ji]
        node = nodes[node_idx]

        name = node.get('name', f'bone_{ji}')

        parent_joint_idx = ji
        cur = node_idx
        while cur in parent_map:
            cur = parent_map[cur]
            if cur in node_to_joint:
                parent_joint_idx = node_to_joint[cur]
                break

        pos = np.array(node.get('translation', [0, 0, 0]), dtype=np.float32)
        rot = np.array(node.get('rotation', [0, 0, 0, 1]), dtype=np.float32)
        scl = np.array(node.get('scale', [1, 1, 1]), dtype=np.float32)

        pos_scaled = pos * armature_scale
        pos_urho = flip_z_position(pos_scaled)
        rot_urho = flip_z_quaternion_gltf(rot)
        scl_urho = scl.copy()

        bones.append({
            'name': name,
            'parent_index': parent_joint_idx,
            'position': pos_urho,
            'rotation': rot_urho,
            'scale': scl_urho,
            'offset_matrix': None,
        })

    global_transforms = [None] * num_joints

    for ji in range(num_joints):
        bone = bones[ji]
        local_mat = make_transform_4x4(bone['position'], bone['rotation'], bone['scale'])

        parent_idx = bone['parent_index']
        if parent_idx == ji or parent_idx >= num_joints:
            global_transforms[ji] = local_mat
        else:
            global_transforms[ji] = global_transforms[parent_idx] @ local_mat

    for ji in range(num_joints):
        inv_global = np.linalg.inv(global_transforms[ji])
        bones[ji]['offset_matrix'] = inv_global[:3, :].flatten().astype(np.float32)

    children_map = {}
    for ji in range(num_joints):
        pi = bones[ji]['parent_index']
        if pi != ji and pi < num_joints:
            parent_pos = global_transforms[pi][:3, 3]
            child_pos = global_transforms[ji][:3, 3]
            dist = float(np.linalg.norm(child_pos - parent_pos))
            if pi not in children_map:
                children_map[pi] = []
            children_map[pi].append(dist)

    for ji in range(num_joints):
        if ji in children_map:
            bones[ji]['radius'] = max(children_map[ji]) * 0.6
        else:
            bones[ji]['radius'] = 0.05

    if num_joints > 0:
        b0 = bones[0]
        print(f"  Root bone '{b0['name']}': pos=({b0['position'][0]:.4f}, {b0['position'][1]:.4f}, {b0['position'][2]:.4f})")

    return bones, armature_scale


def extract_mesh(gltf, bin_data, mesh_idx=0, prim_idx=0):
    """Extract mesh data from glTF."""
    mesh = gltf['meshes'][mesh_idx]
    prim = mesh['primitives'][prim_idx]
    attrs = prim['attributes']

    positions = read_accessor(gltf, bin_data, attrs['POSITION']).astype(np.float32)
    normals = read_accessor(gltf, bin_data, attrs['NORMAL']).astype(np.float32)
    texcoords = read_accessor(gltf, bin_data, attrs.get('TEXCOORD_0', attrs.get('TEXCOORD_0')))
    if texcoords is None:
        texcoords = np.zeros((len(positions), 2), dtype=np.float32)
    else:
        texcoords = texcoords.astype(np.float32)

    joints = read_accessor(gltf, bin_data, attrs['JOINTS_0']).astype(np.uint8)
    weights = read_accessor(gltf, bin_data, attrs['WEIGHTS_0']).astype(np.float32)

    indices = read_accessor(gltf, bin_data, prim['indices']).flatten().astype(np.uint32)

    return positions, normals, texcoords, joints, weights, indices


def extract_animation(gltf, bin_data, anim_idx=0, armature_scale=1.0):
    """Extract animation data from glTF."""
    anim = gltf['animations'][anim_idx]
    nodes = gltf['nodes']

    anim_name = anim.get('name', f'Animation_{anim_idx}')

    bone_data = {}

    for channel in anim['channels']:
        target = channel['target']
        node_idx = target['node']
        path = target['path']
        node_name = nodes[node_idx].get('name', f'node_{node_idx}')

        sampler = anim['samplers'][channel['sampler']]
        times = read_accessor(gltf, bin_data, sampler['input']).flatten().astype(np.float32)
        values = read_accessor(gltf, bin_data, sampler['output']).astype(np.float32)

        if node_name not in bone_data:
            bone_data[node_name] = {}

        bone_data[node_name][path] = (times, values)

    duration = 0.0
    for sampler in anim['samplers']:
        acc = gltf['accessors'][sampler['input']]
        if 'max' in acc:
            duration = max(duration, acc['max'][0])

    tracks = []
    for bone_name, channels in bone_data.items():
        channel_mask = 0
        if 'translation' in channels:
            channel_mask |= CHANNEL_POSITION
        if 'rotation' in channels:
            channel_mask |= CHANNEL_ROTATION
        if 'scale' in channels:
            channel_mask |= CHANNEL_SCALE

        all_times = set()
        for path, (times, values) in channels.items():
            for t in times:
                all_times.add(float(t))
        all_times = sorted(all_times)

        keyframes = []
        for t in all_times:
            kf = {'time': t}

            if 'translation' in channels:
                times_t, values_t = channels['translation']
                pos = interpolate_values(times_t, values_t, t)
                pos_scaled = pos * armature_scale
                kf['position'] = flip_z_position(pos_scaled)

            if 'rotation' in channels:
                times_r, values_r = channels['rotation']
                rot = interpolate_values(times_r, values_r, t)
                kf['rotation'] = flip_z_quaternion_gltf(rot)

            if 'scale' in channels:
                times_s, values_s = channels['scale']
                scl = interpolate_values(times_s, values_s, t)
                # Force bone scale to 1.0 — some Meshy AI animations embed
                # non-uniform scale (e.g. 1.1765) on the Hips bone, causing
                # the character to change size when switching animations.
                kf['scale'] = np.array([1.0, 1.0, 1.0], dtype=np.float32)

            keyframes.append(kf)

        if keyframes and keyframes[0]['time'] > 1e-6:
            kf0 = {}
            for k, v in keyframes[0].items():
                if isinstance(v, np.ndarray):
                    kf0[k] = v.copy()
                else:
                    kf0[k] = v
            kf0['time'] = 0.0
            keyframes.insert(0, kf0)

        tracks.append({
            'name': bone_name,
            'channel_mask': channel_mask,
            'keyframes': keyframes,
        })

    return anim_name, duration, tracks


def interpolate_values(times, values, t):
    """Simple linear interpolation for animation values."""
    if len(times) == 1:
        return values[0].copy()

    if t <= times[0]:
        return values[0].copy()
    if t >= times[-1]:
        return values[-1].copy()

    for i in range(len(times) - 1):
        if times[i] <= t <= times[i + 1]:
            alpha = (t - times[i]) / (times[i + 1] - times[i])
            return values[i] * (1 - alpha) + values[i + 1] * alpha

    return values[-1].copy()


def extract_texture(gltf, bin_data, output_dir):
    """Extract embedded textures from GLB."""
    os.makedirs(output_dir, exist_ok=True)
    extracted = []

    for i, image in enumerate(gltf.get('images', [])):
        if 'bufferView' in image:
            raw = read_buffer_view_raw(gltf, bin_data, image['bufferView'])
            mime = image.get('mimeType', 'image/png')
            ext = '.png' if 'png' in mime else '.jpg'
            name = image.get('name', f'texture_{i}')
            filepath = os.path.join(output_dir, f'{name}{ext}')
            with open(filepath, 'wb') as f:
                f.write(raw)
            print(f"  Texture extracted: {filepath} ({len(raw)} bytes)")
            extracted.append(filepath)

    return extracted


# ============================================================
# Main
# ============================================================

def convert_glb_to_mdl(glb_path, mdl_path, decimate_ratio=0.02):
    """Convert GLB skinned mesh to Urho3D MDL."""
    print(f"Converting mesh: {glb_path} -> {mdl_path}")

    gltf, bin_data = parse_glb(glb_path)

    print("  Extracting mesh data...")
    positions, normals, texcoords, joints, weights, indices = extract_mesh(gltf, bin_data)
    print(f"  Original: {len(positions)} vertices, {len(indices)//3} triangles")

    if decimate_ratio < 1.0:
        positions, normals, texcoords, joints, weights, indices = decimate_mesh(
            positions, normals, texcoords, joints, weights, indices, decimate_ratio
        )

    weight_sums = weights.sum(axis=1, keepdims=True)
    weight_sums[weight_sums < 1e-8] = 1.0
    weights = weights / weight_sums

    positions = flip_z_position(positions)
    normals = flip_z_normal(normals)
    indices = flip_winding_order(indices)

    print("  Closing boundary gaps...")
    positions, normals, texcoords, joints, weights, indices = close_boundary_gaps(
        positions, normals, texcoords, joints, weights, indices
    )

    bb_min = positions.min(axis=0)
    bb_max = positions.max(axis=0)

    print("  Extracting skeleton...")
    bones, armature_scale = extract_skeleton(gltf, bin_data)

    os.makedirs(os.path.dirname(mdl_path), exist_ok=True)
    write_mdl(mdl_path, positions, normals, texcoords, joints, weights, indices,
              bones, bb_min, bb_max)


def convert_glb_to_ani(glb_path, ani_path, anim_name_override=None):
    """Convert GLB animation to Urho3D ANI."""
    print(f"Converting animation: {glb_path} -> {ani_path}")

    gltf, bin_data = parse_glb(glb_path)

    armature_scale = detect_armature_scale(gltf)

    anim_name, duration, tracks = extract_animation(gltf, bin_data, armature_scale=armature_scale)

    if anim_name_override:
        anim_name = anim_name_override

    os.makedirs(os.path.dirname(ani_path), exist_ok=True)
    write_ani(ani_path, anim_name, duration, tracks)


def main():
    parser = argparse.ArgumentParser(description='GLB to Urho3D MDL/ANI converter')
    parser.add_argument('input', help='Input GLB file')
    parser.add_argument('--mdl', help='Output MDL file path')
    parser.add_argument('--ani', help='Output ANI file path')
    parser.add_argument('--ani-only', help='Output ANI file (skip mesh)', dest='ani_only')
    parser.add_argument('--ani-name', help='Override animation name', dest='ani_name')
    parser.add_argument('--texture', help='Output directory for textures')
    parser.add_argument('--decimate', type=float, default=0.02,
                        help='Decimation ratio (0.02 = keep 2%% of faces)')

    args = parser.parse_args()

    if args.texture:
        gltf, bin_data = parse_glb(args.input)
        extract_texture(gltf, bin_data, args.texture)

    if args.mdl:
        convert_glb_to_mdl(args.input, args.mdl, args.decimate)

    if args.ani:
        convert_glb_to_ani(args.input, args.ani, args.ani_name)

    if args.ani_only:
        convert_glb_to_ani(args.input, args.ani_only, args.ani_name)


if __name__ == '__main__':
    main()
