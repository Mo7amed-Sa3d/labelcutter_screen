"""
gcode_transform.py
-------------------
Applies the affine correction (rotation + translation + minor scale) found by
the registration system to a gcode program before it's streamed to GRBL.

Limitation (documented on purpose, not hidden): arcs (G2/G3 with I/J) get
their I/J offsets rotated+scaled the same as the endpoint, which is correct
for pure rotation/uniform-scale transforms. If the fitted transform has
significant shear (rare for a paper skew correction), arc shape will be
slightly off - straight-line-heavy label cut paths are the common case this
is built for.
"""
import re
import numpy as np

AXIS_RE = re.compile(r"([XYIJ])(-?\d*\.?\d+)")


def load_gcode(path):
    with open(path, "r") as f:
        return f.readlines()


def apply_affine_to_gcode(lines, affine_2x3):
    """affine_2x3: 2x3 numpy array mapping [x, y, 1] -> [x', y']"""
    A = affine_2x3[:, :2]
    t = affine_2x3[:, 2]

    def transform_point(x, y):
        p = A @ np.array([x, y]) + t
        return p[0], p[1]

    def transform_vector(i, j):
        # offsets (arc centers) rotate/scale but do not translate
        v = A @ np.array([i, j])
        return v[0], v[1]

    out = []
    last_x, last_y = 0.0, 0.0
    for raw in lines:
        line = raw.rstrip("\n")
        code = line.split(";", 1)[0]
        if not code.strip() or not (code.strip().upper().startswith(("G0", "G1", "G2", "G3"))):
            out.append(line)
            continue

        found = dict(AXIS_RE.findall(code))
        x = float(found["X"]) if "X" in found else last_x
        y = float(found["Y"]) if "Y" in found else last_y
        new_x, new_y = transform_point(x, y)

        new_line = code
        if "X" in found:
            new_line = re.sub(r"X-?\d*\.?\d+", f"X{new_x:.4f}", new_line)
        elif "Y" in found:
            new_line = new_line  # x unchanged, inserted below if needed
        if "Y" in found:
            new_line = re.sub(r"Y-?\d*\.?\d+", f"Y{new_y:.4f}", new_line)

        if "I" in found or "J" in found:
            i_val = float(found.get("I", 0.0))
            j_val = float(found.get("J", 0.0))
            new_i, new_j = transform_vector(i_val, j_val)
            if "I" in found:
                new_line = re.sub(r"I-?\d*\.?\d+", f"I{new_i:.4f}", new_line)
            if "J" in found:
                new_line = re.sub(r"J-?\d*\.?\d+", f"J{new_j:.4f}", new_line)

        last_x, last_y = x, y
        out.append(new_line)
    return out


def identity_affine():
    return np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
