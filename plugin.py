# -*- coding: utf-8 -*-
"""
คลาสหลักของปลั๊กอิน: สร้างเมนู/ทูลบาร์ และเปิดหน้าต่างเครื่องมือวาดเส้น

หน้าต่างเป็น "หน้าต่างลอย" แบบ Windows (QDialog) ไม่ใช่แผงติดขอบจอ
จึงลากย้ายไปวางตรงไหนก็ได้ ย่อ/ขยายได้ และไม่บล็อกการใช้งาน QGIS

ผู้พัฒนา : นายภาคภูมิ สูบกำปัง
ตำแหน่ง  : วิศวกรรังวัดปฏิบัติการ
สังกัด    : กองเทคโนโลยีทำแผนที่
"""

import os

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .line_dock import LineToolWindow

PLUGIN_DIR = os.path.dirname(__file__)
PLUGIN_NAME = "Line Draw & Measure"
MENU_TITLE = "&วาดเส้น && วัดระยะ"


def find_plugin_icon():
    """มองหาไฟล์ไอคอนที่ผู้ใช้เตรียมไว้ จากหลายตำแหน่ง/ชื่อไฟล์ที่พบบ่อย

    รองรับกรณีผู้ใช้วางไอคอนเองไว้ที่ resources/ หรือที่ราก และตั้งชื่อได้อิสระ
    ถ้าไม่พบจะคืน QIcon() ว่าง (ปลั๊กอินยังทำงานได้ปกติ)
    """
    candidates = [
        os.path.join(PLUGIN_DIR, "resources", "icon.png"),
        os.path.join(PLUGIN_DIR, "resources", "icon.svg"),
        os.path.join(PLUGIN_DIR, "icon.png"),
        os.path.join(PLUGIN_DIR, "icon.svg"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return QIcon(path)

    # เผื่อผู้ใช้ตั้งชื่อไฟล์อื่น: หยิบไฟล์ภาพไฟล์แรกที่เจอในโฟลเดอร์ resources/
    resources_dir = os.path.join(PLUGIN_DIR, "resources")
    if os.path.isdir(resources_dir):
        for name in sorted(os.listdir(resources_dir)):
            if name.lower().endswith((".png", ".svg", ".ico", ".jpg", ".jpeg")):
                return QIcon(os.path.join(resources_dir, name))

    return QIcon()


class LineDrawMeasurePlugin:
    """จุดเชื่อมต่อของปลั๊กอินกับ QGIS"""

    def __init__(self, iface):
        self.iface = iface
        self.actions = []
        self.window = None
        self._menu_added = False

    # ------------------------------------------------------------------
    # วงจรชีวิตของปลั๊กอิน
    # ------------------------------------------------------------------
    def initGui(self):  # noqa: N802 (ชื่อกำหนดโดย QGIS)
        """สร้าง action สำหรับเปิดหน้าต่างเครื่องมือวาดเส้น"""
        icon = find_plugin_icon()

        action = QAction(icon, "เปิดเครื่องมือวาดเส้น & วัดระยะ", self.iface.mainWindow())
        action.triggered.connect(self.run)
        action.setCheckable(False)

        self.iface.addToolBarIcon(action)
        self.iface.addPluginToVectorMenu(MENU_TITLE, action)
        self.actions.append(action)
        self._menu_added = True

    def unload(self):
        """ถอดปลั๊กอิน: ลบเมนู/ทูลบาร์ และปิดหน้าต่าง"""
        for action in self.actions:
            self.iface.removePluginVectorMenu(MENU_TITLE, action)
            self.iface.removeToolBarIcon(action)
        self.actions = []

        if self.window is not None:
            try:
                self.window.cleanup()
            except Exception:  # noqa: BLE001 - ป้องกัน unload พังตอนปิด QGIS
                pass
            self.window.close()
            self.window.deleteLater()
            self.window = None

    # ------------------------------------------------------------------
    # การทำงาน
    # ------------------------------------------------------------------
    def run(self):
        """เปิด/แสดงหน้าต่างเครื่องมือวาดเส้น (หน้าต่างลอย ไม่บล็อก QGIS)"""
        if self.window is None:
            self.window = LineToolWindow(self.iface)
            self.window.destroyed.connect(self._on_window_destroyed)

        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def _on_window_destroyed(self, *args):
        self.window = None
