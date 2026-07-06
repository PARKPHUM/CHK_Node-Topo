# -*- coding: utf-8 -*-
"""
run_checks_test.py — ทดสอบตรรกะเรขาคณิตของการตรวจสอบ (ไม่ต้องเปิด GUI)

วิธีรัน (บน Windows ที่ติดตั้ง QGIS):
    "C:\\Program Files\\QGIS 3.40.6\\bin\\python-qgis-ltr.bat" tests\\run_checks_test.py

ทดสอบ:
  1) โพลิกอนซ้อนกันชัดเจน            -> find_overlaps พบ 1
  2) โพลิกอนแนบขอบสนิท (แชร์ edge)   -> find_overlaps พบ 0  (พิสูจน์แก้ false positive)
  3) โพลิกอนซ้อนเป็น sliver บาง       -> find_overlaps พบ 0  (พิสูจน์แก้ false positive)
  4) โพลิกอน 4 แปลงล้อมช่องว่างกลาง   -> find_gaps พบ 1
  5) โพลิกอนมี vertex ไม่มี point ตรง -> find_unmatched_vertices พบ 1

ผู้พัฒนา : นายภาคภูมิ สูบกำปัง (วิศวกรรังวัดปฏิบัติการ กองเทคโนโลยีทำแผนที่)
"""

import os
import sys

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PLUGIN_ROOT)

from qgis.core import QgsApplication, QgsGeometry  # noqa: E402

from checks.overlap_check import find_overlaps       # noqa: E402
from checks.gap_check import find_gaps               # noqa: E402
from checks.node_check import find_unmatched_vertices  # noqa: E402


def wkt(fid, text):
    return (fid, QgsGeometry.fromWkt(text))


def rect_wkt(x1, y1, x2, y2):
    return "POLYGON(({x1} {y1}, {x2} {y1}, {x2} {y2}, {x1} {y2}, {x1} {y1}))".format(
        x1=x1, y1=y1, x2=x2, y2=y2)


TOL = 0.01
_passed = 0
_failed = 0


def check(name, condition):
    global _passed, _failed
    status = "PASS" if condition else "FAIL"
    if condition:
        _passed += 1
    else:
        _failed += 1
    print("  [{}] {}".format(status, name))


def run():
    print("=== ทดสอบตรรกะการตรวจสอบ (tolerance = {}) ===".format(TOL))

    # 1) ซ้อนกันชัดเจน: A(0,0-10,10) กับ B(5,0-15,10) ซ้อน 5x10
    overlaps = find_overlaps(
        [wkt(1, rect_wkt(0, 0, 10, 10)), wkt(2, rect_wkt(5, 0, 15, 10))], TOL)
    check("1) ซ้อนกันชัดเจน -> พบ 1 (ได้ {})".format(len(overlaps)), len(overlaps) == 1)

    # 2) แนบขอบสนิท: A(0,0-10,10) กับ C(10,0-20,10) แชร์เส้น x=10
    overlaps = find_overlaps(
        [wkt(1, rect_wkt(0, 0, 10, 10)), wkt(2, rect_wkt(10, 0, 20, 10))], TOL)
    check("2) แนบขอบสนิท -> พบ 0 (ได้ {})".format(len(overlaps)), len(overlaps) == 0)

    # 3) sliver บาง: ซ้อนกว้าง 0.001 < tol
    overlaps = find_overlaps(
        [wkt(1, rect_wkt(0, 0, 10, 10)), wkt(2, rect_wkt(9.999, 0, 20, 10))], TOL)
    check("3) sliver บางกว่า tol -> พบ 0 (ได้ {})".format(len(overlaps)), len(overlaps) == 0)

    # 3b) sliver ที่กว้างกว่า tol ต้องยังพบ (กันกรองแรงเกิน)
    overlaps = find_overlaps(
        [wkt(1, rect_wkt(0, 0, 10, 10)), wkt(2, rect_wkt(9.9, 0, 20, 10))], TOL)
    check("3b) ซ้อนกว้าง 0.1 > tol -> พบ 1 (ได้ {})".format(len(overlaps)), len(overlaps) == 1)

    # 4) ช่องว่างกลาง: 4 แปลงล้อมรู (10,10)-(20,20)
    frame = [
        wkt(1, rect_wkt(0, 0, 10, 30)),    # ซ้าย
        wkt(2, rect_wkt(20, 0, 30, 30)),   # ขวา
        wkt(3, rect_wkt(10, 0, 20, 10)),   # ล่าง
        wkt(4, rect_wkt(10, 20, 20, 30)),  # บน
    ]
    gaps = find_gaps(frame, TOL)
    check("4) ช่องว่างถูกล้อมรอบ -> พบ 1 (ได้ {})".format(len(gaps)), len(gaps) == 1)

    # 5) node: สี่เหลี่ยมมี 4 มุม แต่มี point แค่ 3 มุม (ขาด (0,10))
    polys = [wkt(1, rect_wkt(0, 0, 10, 10))]
    points = [
        wkt(101, "POINT(0 0)"),
        wkt(102, "POINT(10 0)"),
        wkt(103, "POINT(10 10)"),
    ]
    unmatched = find_unmatched_vertices(polys, points, TOL)
    check("5) vertex ไม่มี point ตรง -> พบ 1 (ได้ {})".format(len(unmatched)), len(unmatched) == 1)

    # 5b) เพิ่ม point ครบ 4 มุม -> ต้องไม่พบ
    points_full = points + [wkt(104, "POINT(0 10)")]
    unmatched = find_unmatched_vertices(polys, points_full, TOL)
    check("5b) point ครบทุกมุม -> พบ 0 (ได้ {})".format(len(unmatched)), len(unmatched) == 0)

    print("\nสรุป: PASS {} / FAIL {}".format(_passed, _failed))
    return _failed == 0


def main():
    QgsApplication.setPrefixPath(os.environ.get("QGIS_PREFIX_PATH", ""), True)
    qgs = QgsApplication([], False)
    qgs.initQgis()
    try:
        ok = run()
    finally:
        qgs.exitQgis()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
