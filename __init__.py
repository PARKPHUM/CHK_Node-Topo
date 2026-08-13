# -*- coding: utf-8 -*-
"""
Line Draw & Measure - QGIS Plugin
=================================
เครื่องมือวาดเส้นพร้อมแสดงระยะแต่ละช่วงเป็นเมตร ล็อกมุม/ล็อกระยะระหว่างวาด
และแสดง Node ที่จุดหักของเส้น

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
    from .plugin import LineDrawMeasurePlugin
    return LineDrawMeasurePlugin(iface)
