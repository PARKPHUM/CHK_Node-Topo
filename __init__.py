# -*- coding: utf-8 -*-
"""
Node & Topology Checker - QGIS Plugin
=====================================
ตรวจสอบ Topology (Gap/Overlap) แบบมีค่า Tolerance และตรวจสอบ Node/Vertex
ของ POLYGON ที่ไม่ตรงกับ POINT

ผู้พัฒนา : นายภาคภูมิ สูบกำปัง
ตำแหน่ง  : วิศวกรรังวัดปฏิบัติการ
สังกัด    : กองเทคโนโลยีทำแผนที่
"""


# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    """โหลดคลาสหลักของปลั๊กอิน

    :param iface: อินเทอร์เฟซของ QGIS ที่ส่งเข้ามาตอนโหลดปลั๊กอิน
    :type iface: QgsInterface
    """
    from .plugin import NodeTopologyCheckerPlugin
    return NodeTopologyCheckerPlugin(iface)
