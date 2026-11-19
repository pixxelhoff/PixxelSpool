"""Read 3MF files (Bambu Studio / OrcaSlicer): filaments used and the estimated amount per filament.

- Sliced files (slice_info.config with <filament used_g=...>) give exact values.
- Otherwise the volume of every object is computed from its mesh and roughly converted to grams using
  walls and infill.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
import xml.etree.ElementTree as ET
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


def _mesh_stats(data: bytes) -> dict:
    """{object_id: (volume_mm3, (side, top, bottom) area_mm2, painted)} for all mesh objects of a .model file.
    The area is split by the face normal: steep faces get walls, faces looking up/down get top/bottom shells."""
    out, verts, vol, area, painted, cur = {}, [], 0.0, [0.0, 0.0, 0.0], False, None
    for ev, el in ET.iterparse(io.BytesIO(data), events=("start", "end")):
        tag = el.tag.rsplit("}", 1)[-1]
        if ev == "start":
            if tag == "object":
                cur, verts, vol, area, painted = el.get("id"), [], 0.0, [0.0, 0.0, 0.0], False
            continue
        if tag == "vertex":
            verts.append((float(el.get("x")), float(el.get("y")), float(el.get("z"))))
        elif tag == "triangle":
            try:
                a, b, c = verts[int(el.get("v1"))], verts[int(el.get("v2"))], verts[int(el.get("v3"))]
            except (IndexError, TypeError, ValueError):
                el.clear()
                continue
            vol += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0])
                    + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0
            ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
            vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
            nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
            dbl = (nx * nx + ny * ny + nz * nz) ** 0.5
            if dbl > 0:
                # within 45° of horizontal counts as top (normal up) or bottom (normal down)
                k = 0 if abs(nz) < 0.7071 * dbl else (1 if nz > 0 else 2)
                area[k] += 0.5 * dbl
            if not painted and (el.get("paint_color") or el.get("{http://schemas.slic3r.org/3mf/2017/06}mmu_segmentation")):
                painted = True
        elif tag == "object":
            if verts:
                if vol < 0:          # inverted winding: up and down are swapped
                    area[1], area[2] = area[2], area[1]
                out[cur] = (abs(vol), tuple(area), painted)
            verts = []
        if tag in ("vertex", "triangle"):
            el.clear()
    return out


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


def analyze(blob: bytes) -> dict:
    """Analyse a 3MF file: filaments with color, type and grams (exact if sliced, otherwise estimated)."""
    try:
        z = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile:
        raise ThreeMFError("This is not a valid 3MF file.")
    if sum(i.file_size for i in z.infolist()) > MAX_UNZIPPED:
        raise ThreeMFError("The file is too large.")
    names = set(z.namelist())
    if "3D/3dmodel.model" not in names:
        raise ThreeMFError("The 3D model is missing from the file (3D/3dmodel.model).")

    st = _settings(z)
    colors = _lst(st.get("filament_colour"))
    types = _lst(st.get("filament_type"))
    ids = _lst(st.get("filament_ids"))
    profiles = _lst(st.get("filament_settings_id"))
    dens = _lst(st.get("filament_density"))
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
            cache[path] = _mesh_stats(z.read(path)) if path in names else {}
        return cache[path]

    main = ET.fromstring(z.read("3D/3dmodel.model"))
    res = main.find(f"{NS_CORE}resources")
    objects = {o.get("id"): o for o in (res.findall(f"{NS_CORE}object") if res is not None else [])}
    main_stats = stats("3D/3dmodel.model")

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
    build = main.find(f"{NS_CORE}build")
    for item in (build.findall(f"{NS_CORE}item") if build is not None else []):
        if item.get("printable") == "0":
            continue
        oid = item.get("objectid")
        o = objects.get(oid)
        if o is None:
            continue
        s_item = _det(_mat(item.get("transform")))
        comps = o.find(f"{NS_CORE}components")
        pieces = []
        if comps is not None:
            for c in comps.findall(f"{NS_CORE}component"):
                path = c.get(f"{NS_PROD}path") or "3D/3dmodel.model"
                cid = c.get("objectid")
                ms = stats(path).get(cid)
                if ms:
                    pieces.append((ms, s_item * _det(_mat(c.get("transform"))),
                                   part_ext.get((oid, cid), obj_ext.get(oid, 1))))
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
            fil[k]["est_g"] += g
            if v > 0:
                fil[k]["assigned"] = True     # tiny parts (a thin logo inlay) round to 0 g but are still printed
            fil[k]["painted"] = fil[k]["painted"] or painted
            total_vol += v
            parts_out.append({"name": obj_name.get(oid, f"Objekt {oid}"), "filament": k + 1,
                              "volume_cm3": round(v / 1000, 1 if v >= 1000 else 3), "est_g": round(g, 1 if g >= 1 else 3), "painted": painted})

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
