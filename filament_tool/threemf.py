"""Read 3MF files (Bambu Studio / OrcaSlicer): filaments used and the estimated amount per filament.

- Sliced files (slice_info.config with <filament used_g=...>) give exact values.
- Otherwise the volume of every object is computed from its mesh and roughly converted to grams using
  walls and infill.
"""
from __future__ import annotations

import io
import json
import math
import re
import zipfile
import xml.etree.ElementTree as ET
from array import array
from typing import Optional

NS_CORE = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
NS_PROD = "{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}"
MAX_UNZIPPED = 400 * 1024 * 1024


class ThreeMFError(Exception):
    pass


def _mat(t: Optional[str]) -> list:
    """3MF transform '12 numbers' -> 3x4 matrix (rows: m00 m01 m02 / ... / tx ty tz)."""
    if not t:
        return [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]
    v = [float(x) for x in t.split()]
    return v if len(v) == 12 else [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]


def _det(m: list) -> float:
    a, b, c, d, e, f, g, h, i = m[:9]
    return abs(a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g))


def _paint(code: str) -> dict:
    """Decode a painted triangle (Bambu "paint_color" / PrusaSlicer "mmu_segmentation", TriangleSelector format)
    into {state: share of the triangle}. State 0 = not painted (the object's own filament), state k = filament k.
    The string is read nibble by nibble from its end; a split node has 2 to 4 children, the area is split evenly."""
    try:
        nib = [int(c, 16) for c in reversed(code)]
    except ValueError:
        return {}
    out: dict = {}
    pos, stack = 0, [1.0]
    while stack and pos < len(nib):
        w = stack.pop()
        c = nib[pos]
        pos += 1
        split = c & 3
        if split:
            stack.extend([w / (split + 1)] * (split + 1))
            continue
        st = c >> 2
        if st == 3 and pos < len(nib):
            st = nib[pos] + 3
            pos += 1
        out[st] = out.get(st, 0.0) + w
    return out


class Cancelled(ThreeMFError):
    pass


_TAG = re.compile(rb'<(/?)(object|vertex|triangle|component|item)\b([^>]*)>')
_XYZ = re.compile(rb'x="([^"]*)"\s+y="([^"]*)"\s+z="([^"]*)"')
_ATTR = re.compile(rb'([\w:]+)="([^"]*)"')
_V123 = re.compile(rb'v1="(\d+)"\s+v2="(\d+)"\s+v3="(\d+)"')
_PAINT = re.compile(rb'(?:paint_color|mmu_segmentation)="([^"]*)"')
_ID = re.compile(rb'\bid="([^"]*)"')
CHUNK = 4 * 1024 * 1024


def _mesh_stats(f, progress=None, struct=None) -> dict:
    """{object_id: (volume_mm3, (side, top, bottom) area_mm2, painted)} for all mesh objects of a .model file.
    painted is {} for an unpainted object, otherwise {state: painted area mm2} (state 0 = the object's own filament).
    The area is split by the face normal: steep faces get walls, faces looking up/down get top/bottom shells.
    f is a binary file object (or bytes); it is read in chunks with a regex instead of an XML tree, so a model of
    several hundred MB needs little memory: the points of one object are kept in a flat array of doubles.
    progress(n) is called with the number of bytes read so far and may raise Cancelled.
    struct (a dict) receives the structure of the file: "comps" {object id: [(path, component id, transform)]}
    and "items" [(object id, transform, printable)], so the main model never has to be held as an XML tree."""
    if struct is not None:
        struct.setdefault("comps", {})
        struct.setdefault("items", [])
    if isinstance(f, (bytes, bytearray)):
        f = io.BytesIO(f)
    out: dict = {}
    verts = array("d")
    vol, area, painted, cur = 0.0, [0.0, 0.0, 0.0], {}, None
    rest, done = b"", 0
    sqrt = math.sqrt
    while True:
        chunk = f.read(CHUNK)
        if not chunk and not rest:
            break
        buf = rest + chunk
        last = 0
        for mt in _TAG.finditer(buf):
            last = mt.end()
            close, tag, attrs = mt.group(1), mt.group(2), mt.group(3)
            if tag == b"vertex":
                m = _XYZ.search(attrs)
                if m:
                    verts.extend((float(m.group(1)), float(m.group(2)), float(m.group(3))))
                else:
                    d = dict(_ATTR.findall(attrs))
                    try:
                        verts.extend((float(d[b"x"]), float(d[b"y"]), float(d[b"z"])))
                    except (KeyError, ValueError):
                        verts.extend((0.0, 0.0, 0.0))
            elif tag == b"triangle":
                m = _V123.search(attrs)
                if not m:
                    continue
                i, j, k = int(m.group(1)) * 3, int(m.group(2)) * 3, int(m.group(3)) * 3
                try:
                    ax, ay, az = verts[i], verts[i + 1], verts[i + 2]
                    bx, by, bz = verts[j], verts[j + 1], verts[j + 2]
                    cx, cy, cz = verts[k], verts[k + 1], verts[k + 2]
                except IndexError:
                    continue
                vol += (ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx)) / 6.0
                ux, uy, uz = bx - ax, by - ay, bz - az
                vx, vy, vz = cx - ax, cy - ay, cz - az
                nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
                dbl = sqrt(nx * nx + ny * ny + nz * nz)
                if dbl > 0:
                    # within 45° of horizontal counts as top (normal up) or bottom (normal down)
                    area[0 if abs(nz) < 0.7071 * dbl else (1 if nz > 0 else 2)] += 0.5 * dbl
                pm = _PAINT.search(attrs) if (b"paint" in attrs or b"mmu" in attrs) else None
                if pm and pm.group(1):
                    for st, share in _paint(pm.group(1).decode("ascii", "replace")).items():
                        painted[st] = painted.get(st, 0.0) + share * 0.5 * dbl
                elif dbl > 0:
                    painted[0] = painted.get(0, 0.0) + 0.5 * dbl
            elif tag == b"component":
                if struct is not None and cur is not None:
                    d = {k.decode().rsplit(":", 1)[-1]: v.decode() for k, v in _ATTR.findall(attrs)}
                    struct["comps"].setdefault(cur, []).append((d.get("path") or "3D/3dmodel.model", d.get("objectid"), d.get("transform")))
            elif tag == b"item":
                if struct is not None and not close:
                    d = {k.decode().rsplit(":", 1)[-1]: v.decode() for k, v in _ATTR.findall(attrs)}
                    struct["items"].append((d.get("objectid"), d.get("transform"), d.get("printable")))
            elif not close:          # <object ...>
                m = _ID.search(attrs)
                cur, vol, area, painted = (m.group(1).decode() if m else None), 0.0, [0.0, 0.0, 0.0], {}
                verts = array("d")
            else:                    # </object>
                if len(verts):
                    if vol < 0:      # inverted winding: up and down are swapped
                        area[1], area[2] = area[2], area[1]
                    out[cur] = (abs(vol), tuple(area), painted if any(k for k in painted) else {})
                verts = array("d")
        # keep an unfinished tag at the end of the buffer for the next round
        lt = buf.rfind(b"<", last)
        rest = buf[lt:] if lt >= 0 and buf.find(b">", lt) < 0 else b""
        if not chunk:
            break
        done += len(chunk)
        if progress:
            progress(done)
    return out


def _mem_free_mb() -> Optional[float]:
    """Free memory in MB (Linux: MemAvailable), None where it cannot be told."""
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / 1024
    except (OSError, ValueError):
        pass
    return None


def _settings(z: zipfile.ZipFile) -> dict:
    for name in ("Metadata/project_settings.config", "Metadata/Slic3r_PE.config"):
        if name in z.namelist():
            raw = z.read(name)
            try:
                return json.loads(raw)
            except ValueError:
                # Slic3r format: "; key = value"
                d = {}
                for line in raw.decode("utf-8", "replace").splitlines():
                    m = re.match(r";\s*(\w+)\s*=\s*(.*)", line)
                    if m:
                        d[m.group(1)] = m.group(2).split(";") if ";" in m.group(2) else m.group(2)
                return d
    return {}


def _num(v, default: float) -> float:
    if isinstance(v, list):
        v = v[0] if v else None
    try:
        return float(str(v).rstrip("%"))
    except (TypeError, ValueError):
        return default


def _lst(v) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def analyze(blob: bytes, progress=None) -> dict:
    """Analyse a 3MF file: filaments with color, type and grams (exact if sliced, otherwise estimated).
    progress(fraction 0..1) is called while the models are read; it may raise Cancelled."""
    try:
        z = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile:
        raise ThreeMFError("This is not a valid 3MF file.")
    if sum(i.file_size for i in z.infolist()) > MAX_UNZIPPED:
        raise ThreeMFError("The file is too large.")
    names = set(z.namelist())
    if "3D/3dmodel.model" not in names:
        raise ThreeMFError("The 3D model is missing from the file (3D/3dmodel.model).")
    models = {i.filename: i.file_size for i in z.infolist() if i.filename.lower().endswith(".model")}
    total_bytes = sum(models.values()) or 1
    # the points of the largest object are kept in memory (about a fifth of its text); refuse kindly if that does not fit
    free = _mem_free_mb()
    need = max(models.values(), default=0) * 0.22 / 1e6 + 60
    if free is not None and free < need:
        raise ThreeMFError("Not enough free memory on this device for such a large model. "
                           "Slice it in Bambu Studio and load the .gcode.3mf instead: it is much smaller.")
    read_before = [0]

    st = _settings(z)
    colors = _lst(st.get("filament_colour"))
    types = _lst(st.get("filament_type"))
    ids = _lst(st.get("filament_ids"))
    profiles = _lst(st.get("filament_settings_id"))
    dens = _lst(st.get("filament_density"))
    costs = _lst(st.get("filament_cost"))       # price per kg as set in the slicer
    n = max(len(colors), len(types), 1)
    fil = []
    for i in range(n):
        fil.append({
            "idx": i + 1,
            "hex": (colors[i] if i < len(colors) else "#888888")[:7].upper(),
            "type": types[i] if i < len(types) else "",
            "filament_id": ids[i] if i < len(ids) else "",
            "profile": re.sub(r"\s*@.*$", "", profiles[i]) if i < len(profiles) else "",
            "density": _num(dens[i] if i < len(dens) else None, 1.24),
            "cost_kg": _num(costs[i] if i < len(costs) else None, 0) or None,
            "est_g": 0.0, "exact_g": None, "exact_m": None, "painted": False,
        })

    # --- exact values from a sliced file
    sliced = False
    if "Metadata/slice_info.config" in names:
        try:
            root = ET.fromstring(z.read("Metadata/slice_info.config"))
            for f in root.iter("filament"):
                k = int(f.get("id", "0")) - 1
                if 0 <= k < len(fil):
                    fil[k]["exact_g"] = round((fil[k]["exact_g"] or 0) + float(f.get("used_g", 0)), 1)
                    fil[k]["exact_m"] = round((fil[k]["exact_m"] or 0) + float(f.get("used_m", 0)), 2)
                    sliced = True
        except ET.ParseError:
            pass

    # --- extruder assignment from model_settings.config
    obj_ext, part_ext, obj_name = {}, {}, {}
    if "Metadata/model_settings.config" in names:
        try:
            ms = ET.fromstring(z.read("Metadata/model_settings.config"))
            for o in ms.iter("object"):
                oid = o.get("id")
                for md in o.findall("metadata"):
                    if md.get("key") == "extruder":
                        obj_ext[oid] = int(md.get("value") or 1)
                    elif md.get("key") == "name":
                        obj_name[oid] = md.get("value")
                for p in o.findall("part"):
                    for md in p.findall("metadata"):
                        if md.get("key") == "extruder":
                            part_ext[(oid, p.get("id"))] = int(md.get("value") or 1)
        except ET.ParseError:
            pass

    # --- geometry
    cache: dict = {}

    def stats(path: str) -> dict:
        path = path.lstrip("/")
        if path not in cache:
            if path not in names:
                cache[path] = {}
            else:
                base = read_before[0]
                cb = (lambda n: progress(min(1.0, (base + n) / total_bytes))) if progress else None
                with z.open(path) as fh:
                    cache[path] = _mesh_stats(fh, cb)
                read_before[0] += models.get(path, 0)
        return cache[path]

    struct: dict = {}
    with z.open("3D/3dmodel.model") as fh:
        main_stats = _mesh_stats(fh, (lambda n: progress(min(1.0, n / total_bytes))) if progress else None, struct)
    cache["3D/3dmodel.model"] = main_stats
    read_before[0] += models.get("3D/3dmodel.model", 0)

    lw = _num(st.get("inner_wall_line_width") or st.get("line_width"), 0.45)
    walls = _num(st.get("wall_loops"), 2)
    lh = _num(st.get("layer_height"), 0.2)
    top_l, bot_l = _num(st.get("top_shell_layers"), 5), _num(st.get("bottom_shell_layers"), 3)
    shells = (top_l + bot_l) / 2
    # thickness of the solid skins: walls along the sides, layers (or the minimum shell thickness) on top/bottom
    t_wall = walls * lw
    t_top = max(top_l * lh, _num(st.get("top_shell_thickness"), 0))
    t_bot = max(bot_l * lh, _num(st.get("bottom_shell_thickness"), 0))
    infill = _num(st.get("sparse_infill_density"), 15) / 100
    # an extruded line is not a full rectangle: rounded edges take away lh * (1 - pi/4) of its width
    fill = 1 - lh * (1 - 3.14159 / 4) / max(lw, 0.1)

    parts_out = []
    total_vol = 0.0
    for oid, item_tf, printable in struct["items"]:
        if printable == "0":
            continue
        comps = struct["comps"].get(oid)
        if not comps and oid not in main_stats:
            continue
        s_item = _det(_mat(item_tf))
        pieces = []
        if comps:
            for path, cid, tf in comps:
                ms = stats(path).get(cid)
                if ms:
                    pieces.append((ms, s_item * _det(_mat(tf)), part_ext.get((oid, cid), obj_ext.get(oid, 1))))
        elif oid in main_stats:
            pieces.append((main_stats[oid], s_item, obj_ext.get(oid, 1)))
        for (vol, (a_side, a_top, a_bot), painted), scale, ext in pieces:
            v = vol * scale
            f2 = scale ** (2 / 3)
            # walls and skins overlap at the edges; for small or thin parts everything is solid
            shell = min(v, (a_side * t_wall + a_top * t_top + a_bot * t_bot) * f2 * 0.92)
            k = max(1, min(ext, len(fil))) - 1
            dens_g = fil[k]["density"] / 1000.0
            g = (shell + infill * max(v - shell, 0)) * fill * dens_g
            if painted:
                # painted surface: the outer shell is split by painted area, the infill stays with the object's filament
                tot_a = sum(painted.values()) or 1.0
                g_shell = shell * fill * dens_g
                fil[k]["est_g"] += g - g_shell
                for pst, a in painted.items():
                    j = k if pst == 0 else max(1, min(pst, len(fil))) - 1
                    fil[j]["est_g"] += g_shell * a / tot_a
                    fil[j]["assigned"] = True
                    fil[j]["painted"] = fil[j]["painted"] or pst != 0
            else:
                fil[k]["est_g"] += g
            if v > 0:
                fil[k]["assigned"] = True     # tiny parts (a thin logo inlay) round to 0 g but are still printed
            total_vol += v
            parts_out.append({"name": obj_name.get(oid, f"Objekt {oid}"), "filament": k + 1,
                              "volume_cm3": round(v / 1000, 1 if v >= 1000 else 3), "est_g": round(g, 1 if g >= 1 else 3),
                              "painted": bool(painted),
                              "paint_filaments": sorted({(k if pst == 0 else max(1, min(pst, len(fil))) - 1) + 1 for pst in painted})})

    # sliced files (.gcode.3mf) usually carry no meshes: take the object names from slice_info.config
    if sliced and not parts_out:
        try:
            root = ET.fromstring(z.read("Metadata/slice_info.config"))
            for o in root.iter("object"):
                if o.get("skipped") != "true":
                    parts_out.append({"name": o.get("name") or "?", "filament": None, "volume_cm3": None, "est_g": None, "painted": False})
        except (ET.ParseError, KeyError):
            pass

    # supports: their filament is listed too (amount only known after slicing)
    support = str(st.get("enable_support", "0")) in ("1", "true")
    if support and not sliced:
        for key in ("support_filament", "support_interface_filament"):
            k = int(_num(st.get(key), 0)) - 1      # 0 = "default": the object's own filament
            if 0 <= k < len(fil):
                fil[k]["support"] = True
                fil[k]["assigned"] = True
    for f in fil:
        f["est_g"] = round(f["est_g"], 1 if f["est_g"] >= 1 else 3)
        f["used"] = (f["exact_g"] or 0) > 0 if sliced else bool(f.pop("assigned", False)) or f["est_g"] > 0
    painted_any = any(p["painted"] for p in parts_out)
    return {
        "sliced": sliced,
        "printer": st.get("printer_model") or "",
        "settings": {"layer_height": lh, "walls": walls, "infill_pct": round(infill * 100), "top_bottom": shells},
        "filaments": fil,
        "objects": parts_out,
        "total_volume_cm3": round(total_vol / 1000, 1),
        "painted": painted_any,
        "support": support,
        "multicolor": sum(1 for f in fil if (f["exact_g"] or f["est_g"]) > 0) > 1 or painted_any,   # support-only filaments do not count
    }
