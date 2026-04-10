#!/usr/bin/env python3
"""
Diagnose an Urho3D MDL file for mesh integrity issues.
Checks:
1. Header and magic validation
2. Vertex data: NaN/Inf, range checks
3. Index data: out-of-range references
4. Vertex stride alignment
5. Mesh connectivity: detect "cracks" (edges shared by only 1 triangle)
6. Duplicate vertex detection (same position, different index)
"""

import struct
import sys
import numpy as np
from collections import defaultdict


def read_string(f):
    """Read null-terminated string."""
    chars = []
    while True:
        c = f.read(1)
        if c == b'\x00' or c == b'':
            break
        chars.append(c)
    return b''.join(chars).decode('utf-8')


def diagnose_mdl(filepath):
    issues = []
    warnings = []
    info = []

    with open(filepath, 'rb') as f:
        # === Magic ===
        magic = f.read(4)
        if magic != b'UMDL':
            issues.append(f"FATAL: Invalid magic: {magic} (expected UMDL)")
            return issues, warnings, info
        info.append(f"Magic: UMDL OK")

        # === Vertex Buffers ===
        num_vb = struct.unpack('<I', f.read(4))[0]
        info.append(f"Vertex buffers: {num_vb}")

        all_positions = []
        all_normals = []
        all_texcoords = []
        all_weights = []
        all_joints = []
        vertex_count_total = 0

        for vb_idx in range(num_vb):
            vcount = struct.unpack('<I', f.read(4))[0]
            elem_mask = struct.unpack('<I', f.read(4))[0]
            morph_start = struct.unpack('<I', f.read(4))[0]
            morph_count = struct.unpack('<I', f.read(4))[0]

            info.append(f"  VB[{vb_idx}]: {vcount} vertices, elemMask=0x{elem_mask:03x}, morph={morph_start}/{morph_count}")

            # Compute expected vertex size from elem_mask
            expected_size = 0
            has_position = bool(elem_mask & 0x001)
            has_normal = bool(elem_mask & 0x002)
            has_color = bool(elem_mask & 0x004)
            has_texcoord1 = bool(elem_mask & 0x008)
            has_texcoord2 = bool(elem_mask & 0x010)
            has_tangent = bool(elem_mask & 0x080)
            has_blendweights = bool(elem_mask & 0x100)
            has_blendindices = bool(elem_mask & 0x200)

            if has_position: expected_size += 12
            if has_normal: expected_size += 12
            if has_color: expected_size += 4
            if has_texcoord1: expected_size += 8
            if has_texcoord2: expected_size += 8
            if has_tangent: expected_size += 16
            if has_blendweights: expected_size += 16
            if has_blendindices: expected_size += 4

            info.append(f"    Expected vertex size: {expected_size} bytes")
            info.append(f"    Elements: pos={has_position} norm={has_normal} col={has_color} "
                        f"tc1={has_texcoord1} tc2={has_texcoord2} tan={has_tangent} "
                        f"bw={has_blendweights} bi={has_blendindices}")

            # Read all vertex data
            positions = []
            normals = []
            texcoords = []
            blend_weights = []
            blend_indices = []

            nan_count = 0
            inf_count = 0
            bad_normal_count = 0
            bad_weight_count = 0
            zero_weight_count = 0

            for vi in range(vcount):
                vertex_start = f.tell()

                # Read in element mask order
                pos = None
                nrm = None
                tc = None
                bw = None
                bi = None

                if has_position:
                    pos = struct.unpack('<3f', f.read(12))
                    if any(np.isnan(v) for v in pos):
                        nan_count += 1
                    if any(np.isinf(v) for v in pos):
                        inf_count += 1

                if has_normal:
                    nrm = struct.unpack('<3f', f.read(12))
                    nrm_len = (nrm[0]**2 + nrm[1]**2 + nrm[2]**2) ** 0.5
                    if nrm_len < 0.5 or nrm_len > 1.5:
                        bad_normal_count += 1

                if has_color:
                    f.read(4)  # skip

                if has_texcoord1:
                    tc = struct.unpack('<2f', f.read(8))

                if has_texcoord2:
                    f.read(8)  # skip

                if has_tangent:
                    f.read(16)  # skip

                if has_blendweights:
                    bw = struct.unpack('<4f', f.read(16))
                    wsum = sum(bw)
                    if abs(wsum - 1.0) > 0.01:
                        bad_weight_count += 1
                    if wsum < 1e-8:
                        zero_weight_count += 1

                if has_blendindices:
                    bi = struct.unpack('<4B', f.read(4))

                # Verify stride
                actual_size = f.tell() - vertex_start
                if actual_size != expected_size:
                    issues.append(f"FATAL: Vertex {vi}: read {actual_size} bytes, expected {expected_size}")
                    return issues, warnings, info

                if pos:
                    positions.append(pos)
                if nrm:
                    normals.append(nrm)
                if tc:
                    texcoords.append(tc)
                if bw:
                    blend_weights.append(bw)
                if bi:
                    blend_indices.append(bi)

            vertex_count_total = vcount

            if nan_count > 0:
                issues.append(f"  VB[{vb_idx}]: {nan_count} vertices with NaN positions!")
            if inf_count > 0:
                issues.append(f"  VB[{vb_idx}]: {inf_count} vertices with Inf positions!")
            if bad_normal_count > 0:
                warnings.append(f"  VB[{vb_idx}]: {bad_normal_count} vertices with non-unit normals (len < 0.5 or > 1.5)")
            if bad_weight_count > 0:
                warnings.append(f"  VB[{vb_idx}]: {bad_weight_count} vertices with weight sum != 1.0 (tolerance 0.01)")
            if zero_weight_count > 0:
                issues.append(f"  VB[{vb_idx}]: {zero_weight_count} vertices with zero weight sum!")

            all_positions = positions
            all_normals = normals
            all_texcoords = texcoords
            all_weights = blend_weights
            all_joints = blend_indices

        # === Index Buffers ===
        num_ib = struct.unpack('<I', f.read(4))[0]
        info.append(f"Index buffers: {num_ib}")

        all_indices = []
        for ib_idx in range(num_ib):
            icount = struct.unpack('<I', f.read(4))[0]
            isize = struct.unpack('<I', f.read(4))[0]
            info.append(f"  IB[{ib_idx}]: {icount} indices, size={isize} bytes each")

            if isize not in (2, 4):
                issues.append(f"  IB[{ib_idx}]: Invalid index size {isize} (must be 2 or 4)")
                return issues, warnings, info

            indices = []
            out_of_range = 0
            for ii in range(icount):
                if isize == 2:
                    idx = struct.unpack('<H', f.read(2))[0]
                else:
                    idx = struct.unpack('<I', f.read(4))[0]
                indices.append(idx)
                if idx >= vertex_count_total:
                    out_of_range += 1

            if out_of_range > 0:
                issues.append(f"  IB[{ib_idx}]: {out_of_range} indices out of range (>= {vertex_count_total})!")

            all_indices = indices

        # === Check bone indices vs skeleton ===
        # Need to read skeleton to get bone count
        # Skip geometries first
        num_geom = struct.unpack('<I', f.read(4))[0]
        info.append(f"Geometries: {num_geom}")

        for gi in range(num_geom):
            num_bone_map = struct.unpack('<I', f.read(4))[0]
            for _ in range(num_bone_map):
                f.read(4)  # bone mapping entry
            num_lod = struct.unpack('<I', f.read(4))[0]
            for _ in range(num_lod):
                f.read(4)  # distance
                f.read(4)  # primitive type
                f.read(4)  # vb ref
                f.read(4)  # ib ref
                f.read(4)  # index start
                f.read(4)  # index count

        # Morphs
        num_morphs = struct.unpack('<I', f.read(4))[0]
        info.append(f"Morphs: {num_morphs}")
        # Skip morphs if any (not handling here for simplicity)

        # Skeleton
        num_bones = struct.unpack('<I', f.read(4))[0]
        info.append(f"Bones: {num_bones}")

        # Check if any blend index references a bone >= num_bones
        if all_joints:
            max_joint_idx = max(max(bi) for bi in all_joints)
            info.append(f"Max bone index in vertices: {max_joint_idx}")
            if max_joint_idx >= num_bones:
                issues.append(f"FATAL: Max bone index {max_joint_idx} >= num_bones {num_bones}!")
            else:
                info.append(f"  Bone index range OK (0..{num_bones-1})")

    # === Mesh connectivity analysis ===
    info.append("")
    info.append("=== Mesh Connectivity Analysis ===")

    if all_positions and all_indices:
        positions_np = np.array(all_positions, dtype=np.float32)
        indices_np = np.array(all_indices, dtype=np.uint32)
        num_tris = len(indices_np) // 3

        info.append(f"Triangles: {num_tris}")

        # Count edge usage (each edge should be shared by exactly 2 triangles for watertight mesh)
        edge_count = defaultdict(int)
        for ti in range(num_tris):
            i0, i1, i2 = indices_np[ti*3], indices_np[ti*3+1], indices_np[ti*3+2]
            # Sort edge vertex indices to create canonical edge keys
            edges = [
                tuple(sorted([i0, i1])),
                tuple(sorted([i1, i2])),
                tuple(sorted([i0, i2])),
            ]
            for e in edges:
                edge_count[e] += 1

        boundary_edges = sum(1 for cnt in edge_count.values() if cnt == 1)
        interior_edges = sum(1 for cnt in edge_count.values() if cnt == 2)
        nonmanifold_edges = sum(1 for cnt in edge_count.values() if cnt > 2)
        total_edges = len(edge_count)

        info.append(f"Total unique edges: {total_edges}")
        info.append(f"Interior edges (shared by 2 tris): {interior_edges}")
        info.append(f"Boundary edges (shared by 1 tri): {boundary_edges}")
        info.append(f"Non-manifold edges (shared by 3+ tris): {nonmanifold_edges}")

        if boundary_edges > 0:
            boundary_ratio = boundary_edges / total_edges * 100
            warnings.append(f"Mesh has {boundary_edges} boundary edges ({boundary_ratio:.1f}% of total) - these cause visible cracks!")

            # Sample some boundary edges for debugging
            sample_count = min(10, boundary_edges)
            sample_edges = [(e, cnt) for e, cnt in edge_count.items() if cnt == 1][:sample_count]
            info.append(f"\nSample boundary edges (first {sample_count}):")
            for (vi0, vi1), cnt in sample_edges:
                p0 = positions_np[vi0]
                p1 = positions_np[vi1]
                dist = np.linalg.norm(p1 - p0)
                info.append(f"  Edge ({vi0}, {vi1}): dist={dist:.6f}, "
                            f"p0=({p0[0]:.4f},{p0[1]:.4f},{p0[2]:.4f}), "
                            f"p1=({p1[0]:.4f},{p1[1]:.4f},{p1[2]:.4f})")

        if nonmanifold_edges > 0:
            warnings.append(f"Mesh has {nonmanifold_edges} non-manifold edges (shared by 3+ triangles)")

        # Check for very close but not identical vertices (potential unwelded seams)
        info.append("")
        info.append("=== Near-duplicate Vertex Analysis ===")
        from scipy.spatial import cKDTree
        tree = cKDTree(positions_np)

        # Check very close vertices (within 1e-5)
        pairs = tree.query_pairs(1e-5)
        info.append(f"Vertex pairs within 1e-5: {len(pairs)}")

        # Check if any boundary edges have near-duplicate endpoints
        if boundary_edges > 0:
            boundary_edge_list = [(e, cnt) for e, cnt in edge_count.items() if cnt == 1]
            boundary_vertices = set()
            for (vi0, vi1), _ in boundary_edge_list:
                boundary_vertices.add(vi0)
                boundary_vertices.add(vi1)

            info.append(f"Unique vertices on boundary edges: {len(boundary_vertices)}")

            # Check if boundary vertices have near-duplicates
            boundary_verts_list = sorted(boundary_vertices)
            boundary_positions = positions_np[boundary_verts_list]
            if len(boundary_positions) > 1:
                btree = cKDTree(boundary_positions)
                bpairs = btree.query_pairs(1e-4)
                info.append(f"Near-duplicate boundary vertex pairs (within 1e-4): {len(bpairs)}")

                if bpairs:
                    sample = list(bpairs)[:5]
                    for (bi0, bi1) in sample:
                        vi0 = boundary_verts_list[bi0]
                        vi1 = boundary_verts_list[bi1]
                        p0 = positions_np[vi0]
                        p1 = positions_np[vi1]
                        dist = np.linalg.norm(p1 - p0)
                        info.append(f"  Near-dup: vtx {vi0} <-> vtx {vi1}, dist={dist:.8f}")

    # === Degenerate triangle check ===
    if all_indices:
        indices_np = np.array(all_indices, dtype=np.uint32)
        num_tris = len(indices_np) // 3
        degen_count = 0
        zero_area_count = 0
        for ti in range(num_tris):
            i0, i1, i2 = indices_np[ti*3], indices_np[ti*3+1], indices_np[ti*3+2]
            if i0 == i1 or i1 == i2 or i0 == i2:
                degen_count += 1
            elif all_positions:
                p0 = np.array(all_positions[i0])
                p1 = np.array(all_positions[i1])
                p2 = np.array(all_positions[i2])
                area = np.linalg.norm(np.cross(p1 - p0, p2 - p0)) * 0.5
                if area < 1e-10:
                    zero_area_count += 1

        if degen_count > 0:
            warnings.append(f"Mesh has {degen_count} degenerate triangles (shared vertex indices)")
        if zero_area_count > 0:
            warnings.append(f"Mesh has {zero_area_count} zero-area triangles")
        info.append(f"Degenerate triangles: {degen_count}")
        info.append(f"Zero-area triangles: {zero_area_count}")

    return issues, warnings, info


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 diagnose_mdl.py <file.mdl>")
        sys.exit(1)

    filepath = sys.argv[1]
    print(f"Diagnosing MDL: {filepath}")
    print("=" * 60)

    issues, warnings, info = diagnose_mdl(filepath)

    print("\n--- INFO ---")
    for line in info:
        print(line)

    if warnings:
        print(f"\n--- WARNINGS ({len(warnings)}) ---")
        for w in warnings:
            print(f"  WARNING: {w}")

    if issues:
        print(f"\n--- ISSUES ({len(issues)}) ---")
        for i in issues:
            print(f"  ERROR: {i}")
    else:
        print("\n--- No critical issues found ---")

    print("\n" + "=" * 60)
    print(f"Summary: {len(issues)} issues, {len(warnings)} warnings")


if __name__ == '__main__':
    main()
