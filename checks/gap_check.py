# -*- coding: utf-8 -*-
"""
gap_check.py — ตรวจหาช่องว่าง (Gap) ที่ถูกโพลิกอนล้อมรอบ

หลักการ:
  - รวมโพลิกอนทั้งหมดเป็นก้อนเดียว (unaryUnion)
  - ช่องว่างที่ถูกล้อมรอบ = "รู" (interior ring) ของก้อนที่รวมแล้ว
  - กรองช่องว่างที่เล็ก/บางกว่า tolerance ทิ้ง (is_significant)
  - ขอบนอกสุดของชุดข้อมูลจะไม่ถูกนับ (ถูกต้องตามหลัก topology)

ผู้พัฒนา : นายภาคภูมิ สูบกำปัง (วิศวกรรังวัดปฏิบัติการ กองเทคโนโลยีทำแผนที่)
"""

from qgis.core import QgsGeometry, QgsPolygon, QgsWkbTypes

from .geometry_utils import clean_polygon, is_significant


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

    _set_progress(feedback, 40.0)
    union = QgsGeometry.unaryUnion(geoms)
    if union is None or union.isNull() or union.isEmpty():
        return []
    _set_progress(feedback, 70.0)

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
