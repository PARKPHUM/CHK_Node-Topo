# -*- coding: utf-8 -*-
"""
node_check.py — ตรวจว่า vertex (มุม/หัก) ของ POLYGON มีหมุด POINT ตรงกันหรือไม่

ทิศทางการตรวจ: หา vertex ของ POLYGON ที่ "ไม่มี" POINT อยู่ในระยะยอมรับ (node tolerance)
(ตรงตามที่ผู้ใช้เลือก — เหมาะกับงานตรวจหมุดหลักเขต)

สำคัญ: ระยะยอมรับของ Node ใช้ค่าแยกจาก Overlap/Gap เพราะหมุดกับ vertex ในงานจริง
มักห่างกันมากกว่าเศษ sliver — ผลลัพธ์จะรายงาน "ระยะถึงหมุดใกล้สุด" ด้วย เพื่อช่วยตั้งค่า

หมายเหตุ: geometry ของ POLYGON และ POINT ต้องอยู่ใน CRS เดียวกันแล้ว (transform ที่ชั้นเรียกใช้ก่อน)

ผู้พัฒนา : นายภาคภูมิ สูบกำปัง (วิศวกรรังวัดปฏิบัติการ กองเทคโนโลยีทำแผนที่)
"""

import math

from qgis.core import (
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsRectangle,
    QgsSpatialIndex,
)


def _canceled(feedback):
    return feedback is not None and hasattr(feedback, "isCanceled") and feedback.isCanceled()


def _set_progress(feedback, value):
    if feedback is not None and hasattr(feedback, "setProgress"):
        feedback.setProgress(value)


def _point_coords(geom):
    """คืน list ของ (x, y) จาก geometry ของ POINT/MultiPoint"""
    coords = []
    if geom is None or geom.isEmpty():
        return coords
    for v in geom.vertices():
        coords.append((v.x(), v.y()))
    return coords


def _nearest_distance(index, point_coords, x, y):
    """คืนระยะจาก (x, y) ถึงหมุด POINT ที่ใกล้ที่สุด (หรือ None ถ้าไม่มีหมุดเลย)"""
    try:
        ids = index.nearestNeighbor(QgsPointXY(x, y), 3)
    except Exception:  # noqa: BLE001
        ids = index.nearestNeighbor(QgsPointXY(x, y), 1)
    best = None
    for pid in ids:
        for (px, py) in point_coords.get(pid, ()):
            d = math.hypot(px - x, py - y)
            if best is None or d < best:
                best = d
    return best


def find_unmatched_vertices(polygon_features, point_features, tolerance, feedback=None):
    """หา vertex ของ POLYGON ที่ไม่มี POINT ตรงกันภายในระยะ tolerance (node tolerance)

    :param polygon_features: iterable ของ (fid, QgsGeometry) ของชั้น POLYGON
    :param point_features: iterable ของ (fid, QgsGeometry) ของชั้น POINT (CRS เดียวกัน)
    :param tolerance: ระยะยอมรับ (หน่วยแผนที่) ที่ถือว่า vertex กับ point ตรงกัน
    :param feedback: อ็อบเจ็กต์ isCanceled()/setProgress() หรือ None
    :return: list ของ dict {type, geometry(จุด), fids, area, detail, x, y, distance}
    """
    # สร้าง spatial index ของหมุด POINT พร้อมเก็บพิกัดไว้เทียบระยะจริง
    index = QgsSpatialIndex()
    point_coords = {}
    for fid, geom in point_features:
        if _canceled(feedback):
            return []
        coords = _point_coords(geom)
        if not coords:
            continue
        point_coords[fid] = coords
        feat = QgsFeature(fid)
        feat.setGeometry(geom)
        index.addFeature(feat)

    tol = float(tolerance)
    tol_sq = tol * tol
    results = []
    seen = set()  # กันรายงานพิกัดซ้ำ (เช่น มุมที่แชร์กันระหว่างสองแปลง)

    poly_list = list(polygon_features)
    total = max(len(poly_list), 1)
    step = max(1, total // 100)  # throttle: ยิง progress ~100 ครั้งพอ ไม่ยิงทุก feature

    for i, (fid, geom) in enumerate(poly_list):
        if i % step == 0:
            if _canceled(feedback):
                break
            _set_progress(feedback, 100.0 * i / total)
        if geom is None or geom.isEmpty():
            continue

        for v in geom.vertices():
            x, y = v.x(), v.y()
            key = (round(x, 6), round(y, 6))
            if key in seen:
                continue
            seen.add(key)

            # เช็กเร็ว: มีหมุดในกรอบ ±tol และระยะจริง <= tol หรือไม่
            # (vertex ส่วนใหญ่ควร match — จ่ายค่า nearestNeighbor เฉพาะตัวที่ไม่ match)
            matched = False
            for pid in index.intersects(QgsRectangle(x - tol, y - tol, x + tol, y + tol)):
                for (px, py) in point_coords.get(pid, ()):
                    dx = px - x
                    dy = py - y
                    if dx * dx + dy * dy <= tol_sq:
                        matched = True
                        break
                if matched:
                    break
            if matched:
                continue  # มีหมุดอยู่ในระยะยอมรับ = ตรงกัน

            # ไม่ match — หาระยะถึงหมุดใกล้สุดไว้รายงาน (ช่วยผู้ใช้ตั้งค่า tolerance)
            nearest = _nearest_distance(index, point_coords, x, y)

            if nearest is None:
                detail = "แปลง FID {} มี Vertex ไม่มีหมุดใกล้เคียง ที่ ({:.3f}, {:.3f})".format(
                    fid, x, y)
            else:
                detail = ("แปลง FID {} Vertex ห่างหมุดใกล้สุด {:.3f} "
                          "(เกินระยะยอมรับ {:.3f}) ที่ ({:.3f}, {:.3f})").format(
                    fid, nearest, tol, x, y)

            results.append({
                "type": "node",
                "geometry": QgsGeometry.fromPointXY(QgsPointXY(x, y)),
                "fids": (fid,),
                "area": 0.0,
                "x": x,
                "y": y,
                "distance": nearest,
                "detail": detail,
            })

    _set_progress(feedback, 100.0)
    return results
