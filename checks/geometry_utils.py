# -*- coding: utf-8 -*-
"""
geometry_utils.py — ฟังก์ชันช่วยด้านเรขาคณิต (หัวใจของการแก้ false positive)

ปัญหาเดิมของ Topology Checker ที่มากับ QGIS คือรายงานการทับซ้อน (overlap) ทั้งที่
ผู้ใช้แก้ให้แปลงแนบสนิทแล้ว สาเหตุมาจาก:
  1) geometry ไม่ valid (self-intersection)           -> make_valid()
  2) การนับ "ขอบที่แชร์กัน" (เส้น/จุด) เป็นการทับซ้อน   -> polygonal_part()
  3) เศษพื้นที่ sliver บางมากจาก floating point/snapping -> is_significant() (negative buffer)

ผู้พัฒนา : นายภาคภูมิ สูบกำปัง
ตำแหน่ง  : วิศวกรรังวัดปฏิบัติการ
สังกัด    : กองเทคโนโลยีทำแผนที่
"""

from qgis.core import QgsGeometry, QgsWkbTypes


def make_valid(geom):
    """คืน geometry ที่ valid แล้ว (ซ่อม self-intersection ฯลฯ)

    ถ้า geometry valid อยู่แล้วจะคืนตัวเดิม เพื่อความเร็ว
    ถ้าซ่อมไม่ได้จะคืนตัวเดิมกลับไป (ให้ขั้นถัดไปตัดสินใจเอง)
    """
    if geom is None or geom.isNull():
        return geom
    try:
        if geom.isGeosValid():
            return geom
    except Exception:  # noqa: BLE001
        pass

    # วิธีที่ 1: makeValid() (แม่นยำที่สุด มีใน QGIS 3.x)
    try:
        fixed = geom.makeValid()
        if fixed is not None and not fixed.isNull() and not fixed.isEmpty():
            return fixed
    except Exception:  # noqa: BLE001
        pass

    # วิธีที่ 2 (fallback): buffer(0) มักซ่อมโพลิกอนที่ไม่ valid ได้
    try:
        fixed = geom.buffer(0.0, 1)
        if fixed is not None and not fixed.isNull() and not fixed.isEmpty():
            return fixed
    except Exception:  # noqa: BLE001
        pass

    return geom


def polygonal_part(geom):
    """ดึงเฉพาะส่วนที่เป็น "พื้นที่" (polygon) ออกจาก geometry

    ผลลัพธ์ของ intersection ระหว่างสองโพลิกอนที่แนบขอบกัน อาจได้ออกมาเป็น
    GeometryCollection ที่มีทั้งเส้น/จุด (ขอบที่แชร์กัน) และอาจมีพื้นที่เล็ก ๆ ปน
    ฟังก์ชันนี้ทิ้งส่วนที่เป็นเส้น/จุด เก็บเฉพาะพื้นที่ เพื่อไม่ให้ "ขอบที่แนบกัน"
    ถูกนับว่าเป็นการทับซ้อน

    คืน QgsGeometry (โพลิกอน) หรือ None ถ้าไม่มีส่วนที่เป็นพื้นที่เลย
    """
    if geom is None or geom.isNull() or geom.isEmpty():
        return None

    if geom.type() != QgsWkbTypes.PolygonGeometry and not _has_polygon(geom):
        return None

    polys = [
        g for g in geom.asGeometryCollection()
        if g is not None
        and not g.isEmpty()
        and g.type() == QgsWkbTypes.PolygonGeometry
    ]
    if not polys:
        return None
    if len(polys) == 1:
        return polys[0]
    return QgsGeometry.unaryUnion(polys)


def _has_polygon(geom):
    """เช็กเบื้องต้นว่ามีส่วนที่เป็น polygon อยู่ใน geometry collection หรือไม่"""
    try:
        return any(
            g.type() == QgsWkbTypes.PolygonGeometry
            for g in geom.asGeometryCollection()
        )
    except Exception:  # noqa: BLE001
        return False


def is_significant(geom, tolerance):
    """ตัดสินว่า geometry (พื้นที่ทับซ้อน/ช่องว่าง) เป็น "ของจริง" หรือแค่เศษ sliver

    หลักการ: ใช้ negative buffer หด geometry เข้าไปครึ่งหนึ่งของ tolerance
    - ถ้าเป็นแถบบาง (กว้าง < tolerance) เช่น เศษ sliver จาก snapping/floating point
      การหดเข้าไปจะทำให้พื้นที่หายไป -> ถือว่าไม่สำคัญ (คืน False)
    - ถ้าเป็นพื้นที่จริงที่กว้างกว่า tolerance การหดแล้วยังเหลือพื้นที่ -> สำคัญ (คืน True)

    นี่คือจุดที่ทำให้ปลั๊กอินนี้ไม่ฟ้อง overlap ปลอมเหมือน Topology Checker เดิม

    :param tolerance: ค่าความคลาดเคลื่อน (หน่วยแผนที่); ถ้า <= 0 จะนับทุกพื้นที่ที่ > 0
    """
    if geom is None or geom.isNull() or geom.isEmpty():
        return False

    try:
        area = geom.area()
    except Exception:  # noqa: BLE001
        return False
    if area <= 0:
        return False

    # tolerance <= 0: ไม่กรอง sliver นับทุกพื้นที่ที่มากกว่า 0
    if tolerance is None or tolerance <= 0:
        return True

    try:
        shrunk = geom.buffer(-tolerance / 2.0, 8)
    except Exception:  # noqa: BLE001
        # buffer พังกับ geometry แปลก ๆ -> ใช้เกณฑ์พื้นที่ขั้นต่ำแทน
        return area > (tolerance * tolerance)

    if shrunk is None or shrunk.isNull() or shrunk.isEmpty():
        return False
    try:
        return shrunk.area() > 0
    except Exception:  # noqa: BLE001
        return False


def clean_polygon(geom):
    """ทำให้ geometry valid แล้วเก็บเฉพาะส่วนที่เป็นพื้นที่ พร้อมใช้กับ overlap/gap"""
    fixed = make_valid(geom)
    part = polygonal_part(fixed)
    return part if part is not None else fixed
