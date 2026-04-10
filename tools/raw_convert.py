#!/usr/bin/env python3
"""
Minimal raw GLB -> MDL converter for debugging.
NO decimation, NO welding, NO gap-closing.
Only applies coordinate conversion (Z-flip + winding order).
Purpose: verify that the basic read/write path is correct.
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

    # Step 1: Read raw mesh data (zero processing)
    positions, normals, texcoords, joints, weights, indices = extract_mesh(gltf, bin_data)
    print(f"  Raw vertices: {len(positions)}")
    print(f"  Raw indices: {len(indices)} ({len(indices)//3} triangles)")

    # Step 2: Normalize bone weights (safe, doesn't change topology)
    weight_sums = weights.sum(axis=1, keepdims=True)
    weight_sums[weight_sums < 1e-8] = 1.0
    weights = weights / weight_sums

    # Step 3: Coordinate conversion ONLY (necessary for correct rendering)
    positions = flip_z_position(positions)
    normals = flip_z_normal(normals)
    indices = flip_winding_order(indices)

    # Step 4: Bounding box
    bb_min = positions.min(axis=0)
    bb_max = positions.max(axis=0)

    # Step 5: Skeleton
    bones, armature_scale = extract_skeleton(gltf, bin_data)

    # Step 6: Write directly — vertex count should be IDENTICAL to GLB
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
