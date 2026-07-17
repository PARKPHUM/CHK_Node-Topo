# -*- coding: utf-8 -*-
"""
gap_check.py — ตรวจหาช่องว่าง (Gap) ที่ถูกโพลิกอนล้อมรอบ

หลักการ:
  - รวมโพลิกอนทั้งหมดเป็นก้อนเดียว (unaryUnion)
  - ช่องว่างที่ถูกล้อมรอบ = "รู" (interior ring) ของก้อนที่รวมแล้ว
  - กรองช่องว่างที่เล็ก/บางกว่า tolerance ทิ้ง (is_significant)
  - ขอบนอกสุดของชุดข้อมูลจะไม่ถูกนับ (ถูกต้องตามหลัก topology)

การรวมทำเป็นช่วง (chunk) แล้วค่อยรวมผลของแต่ละช่วงอีกที — ผลลัพธ์เท่าเดิม
แต่ยกเลิกกลางทางได้และรายงาน progress ระหว่างรวม ซึ่งจำเป็นเมื่อดึงแปลง
จำนวนมากจากฐานข้อมูล (PostgreSQL/PostGIS)

ผู้พัฒนา : นายภาคภูมิ สูบกำปัง (วิศวกรรังวัดปฏิบัติการ กองเทคโนโลยีทำแผนที่)
"""

from qgis.core import QgsGeometry, QgsPolygon, QgsWkbTypes

from .geometry_utils import clean_polygon, is_significant

# ขนาดช่วงของการรวม — ใหญ่พอให้ GEOS cascaded union ทำงานมีประสิทธิภาพ
# แต่เล็กพอให้เช็ก cancel/progress ได้ระหว่างทาง
_UNION_CHUNK = 256


def _canceled(feedback):
    return feedback is not None and hasattr(feedback, "isCanceled") and feedback.isCanceled()


def _set_progress(feedback, value):
    if feedback is not None and hasattr(feedback, "setProgress"):
        feedback.setProgress(value)


def _ring_to_polygon(ring):
    """สร้าง QgsGeometry (โพลิกอน) จากเส้นขอบวงใน (interior ring)"""
    if ring is None:
        return None
    poly = QgsPolygon()
    poly.setExteriorRing(ring.clone())
    geom = QgsGeometry(poly)
    if geom.isNull() or geom.isEmpty():
        return None
    return geom


def _cascaded_union(geoms, feedback, p_start, p_end):
    """unaryUnion แบบแบ่งช่วง — เช็ก cancel และรายงาน progress ระหว่างรวม

    คืน geometry ที่รวมแล้ว หรือ None ถ้าถูกยกเลิก/รวมไม่สำเร็จ
    """
    parts = geoms
    first_level = max(len(parts), 1)
    first = True
    while len(parts) > 1:
        merged = []
        for i in range(0, len(parts), _UNION_CHUNK):
            if _canceled(feedback):
                return None
            chunk = parts[i:i + _UNION_CHUNK]
            u = QgsGeometry.unaryUnion(chunk) if len(chunk) > 1 else chunk[0]
            if u is not None and not u.isNull() and not u.isEmpty():
                merged.append(u)
            if first:
                frac = min(1.0, float(i + _UNION_CHUNK) / first_level)
                _set_progress(feedback, p_start + (p_end - p_start) * frac)
        if not merged:
            return None
        parts = merged
        first = False
    return parts[0] if parts else None


def find_gaps(features, tolerance, feedback=None):
    """หาช่องว่างที่ถูกโพลิกอนล้อมรอบ

    :param features: iterable ของ (fid, QgsGeometry) — CRS เดียวกัน
    :param tolerance: ค่าความคลาดเคลื่อน (หน่วยแผนที่) สำหรับกรองช่องว่างเล็ก/บาง
    :param feedback: อ็อบเจ็กต์ isCanceled()/setProgress() หรือ None
    :return: list ของ dict {type, geometry, fids, area, detail}
    """
    geoms = []
    for fid, geom in features:
        if _canceled(feedback):
            return []
        clean = clean_polygon(geom)
        if clean is not None and not clean.isEmpty():
            geoms.append(clean)

    if len(geoms) < 2:
        return []

    _set_progress(feedback, 10.0)
    union = _cascaded_union(geoms, feedback, 10.0, 75.0)
    if union is None or union.isNull() or union.isEmpty():
        return []
    _set_progress(feedback, 80.0)

    results = []
    index = 0
    for part in union.asGeometryCollection():
        if _canceled(feedback):
            break
        if part is None or part.type() != QgsWkbTypes.PolygonGeometry:
            continue
        abstract = part.constGet()
        if abstract is None:
            continue
        try:
            n_rings = abstract.numInteriorRings()
        except Exception:  # noqa: BLE001
            continue
        for i in range(n_rings):
            ring = abstract.interiorRing(i)
            gap_geom = _ring_to_polygon(ring)
            if gap_geom is None:
                continue
            if not is_significant(gap_geom, tolerance):
                continue
            index += 1
            results.append({
                "type": "gap",
                "geometry": gap_geom,
                "fids": (),
                "area": gap_geom.area(),
                "detail": "ช่องว่าง #{} (พื้นที่ {:.4f})".format(index, gap_geom.area()),
            })

    _set_progress(feedback, 100.0)
    return results
