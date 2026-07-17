# -*- coding: utf-8 -*-
"""
overlap_check.py — ตรวจหาการทับซ้อน (Overlap) ระหว่างโพลิกอน แบบมีค่า Tolerance

จุดต่างจาก Topology Checker เดิม:
  - ทำ geometry ให้ valid ก่อน (clean_polygon)
  - นับเฉพาะ "ส่วนที่เป็นพื้นที่" ของ intersection (ขอบที่แชร์กัน = เส้น ไม่ถือเป็น overlap)
  - กรองเศษ sliver ที่บางกว่า tolerance ทิ้ง (is_significant)

การเร่งความเร็ว (สำคัญกับข้อมูลจากฐานข้อมูลที่มีแปลงจำนวนมาก):
  - QgsSpatialIndex กรองคู่ที่ bbox ไม่ชนกันออกก่อน
  - เทียบเฉพาะคู่ fid_a < fid_b — ไม่ต้องเก็บ set ของคู่ที่เช็กแล้ว (ลดหน่วยความจำ)
  - ใช้ prepared geometry (QgsGeometryEngine) ทดสอบ intersects กับเพื่อนบ้านหลายตัว

ผู้พัฒนา : นายภาคภูมิ สูบกำปัง (วิศวกรรังวัดปฏิบัติการ กองเทคโนโลยีทำแผนที่)
"""

from qgis.core import QgsFeature, QgsGeometry, QgsSpatialIndex

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
    total = max(len(geoms), 1)
    step = max(1, total // 100)

    for done, (fid_a, geom_a) in enumerate(geoms.items()):
        if done % step == 0:
            if _canceled(feedback):
                break
            _set_progress(feedback, 100.0 * done / total)

        # ทุกคู่ถูกพิจารณาครั้งเดียวจากฝั่ง fid ที่น้อยกว่า (bbox ชนกันเป็นสมมาตร)
        candidates = [fid_b for fid_b in index.intersects(geom_a.boundingBox())
                      if fid_b > fid_a]
        if not candidates:
            continue

        # prepared geometry: เร็วขึ้นมากเมื่อ geom_a ถูกเทียบกับเพื่อนบ้านหลายตัว
        engine = QgsGeometry.createGeometryEngine(geom_a.constGet())
        engine.prepareGeometry()

        for fid_b in candidates:
            geom_b = geoms.get(fid_b)
            if geom_b is None:
                continue
            if not engine.intersects(geom_b.constGet()):
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
                "fids": (fid_a, fid_b),
                "area": poly.area(),
                "detail": "แปลง FID {} ทับซ้อน FID {} (พื้นที่ {:.4f})".format(
                    fid_a, fid_b, poly.area()),
            })

    _set_progress(feedback, 100.0)
    return results
