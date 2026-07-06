# -*- coding: utf-8 -*-
"""
overlap_check.py — ตรวจหาการทับซ้อน (Overlap) ระหว่างโพลิกอน แบบมีค่า Tolerance

จุดต่างจาก Topology Checker เดิม:
  - ทำ geometry ให้ valid ก่อน (clean_polygon)
  - นับเฉพาะ "ส่วนที่เป็นพื้นที่" ของ intersection (ขอบที่แชร์กัน = เส้น ไม่ถือเป็น overlap)
  - กรองเศษ sliver ที่บางกว่า tolerance ทิ้ง (is_significant)

ผู้พัฒนา : นายภาคภูมิ สูบกำปัง (วิศวกรรังวัดปฏิบัติการ กองเทคโนโลยีทำแผนที่)
"""

from qgis.core import QgsFeature, QgsSpatialIndex

from .geometry_utils import clean_polygon, polygonal_part, is_significant


def _canceled(feedback):
    return feedback is not None and hasattr(feedback, "isCanceled") and feedback.isCanceled()


def _set_progress(feedback, value):
    if feedback is not None and hasattr(feedback, "setProgress"):
        feedback.setProgress(value)


def find_overlaps(features, tolerance, feedback=None):
    """หาพื้นที่ทับซ้อนระหว่างโพลิกอน

    :param features: iterable ของ (fid, QgsGeometry) — ต้องอยู่ใน CRS เดียวกัน
    :param tolerance: ค่าความคลาดเคลื่อน (หน่วยแผนที่) สำหรับกรองเศษ sliver
    :param feedback: อ็อบเจ็กต์ที่มี isCanceled()/setProgress() (เช่น QgsTask) หรือ None
    :return: list ของ dict {type, geometry, fids, area, detail}
    """
    geoms = {}
    index = QgsSpatialIndex()
    for fid, geom in features:
        if _canceled(feedback):
            return []
        clean = clean_polygon(geom)
        if clean is None or clean.isEmpty():
            continue
        geoms[fid] = clean
        feat = QgsFeature(fid)
        feat.setGeometry(clean)
        index.addFeature(feat)

    results = []
    checked_pairs = set()
    total = max(len(geoms), 1)
    done = 0

    for fid_a, geom_a in geoms.items():
        if _canceled(feedback):
            break
        done += 1
        _set_progress(feedback, 100.0 * done / total)

        candidates = index.intersects(geom_a.boundingBox())
        for fid_b in candidates:
            if fid_b == fid_a:
                continue
            key = (fid_a, fid_b) if fid_a < fid_b else (fid_b, fid_a)
            if key in checked_pairs:
                continue
            checked_pairs.add(key)

            geom_b = geoms.get(fid_b)
            if geom_b is None:
                continue
            if not geom_a.intersects(geom_b):
                continue

            inter = geom_a.intersection(geom_b)
            poly = polygonal_part(inter)
            if poly is None or poly.isEmpty():
                continue
            if not is_significant(poly, tolerance):
                # เศษ sliver บางกว่า tolerance = ไม่ถือว่าทับซ้อน (แก้ false positive)
                continue

            results.append({
                "type": "overlap",
                "geometry": poly,
                "fids": key,
                "area": poly.area(),
                "detail": "แปลง FID {} ทับซ้อน FID {} (พื้นที่ {:.4f})".format(
                    key[0], key[1], poly.area()),
            })

    return results
