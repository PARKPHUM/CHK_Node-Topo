# -*- coding: utf-8 -*-
"""
คลาสหลักของปลั๊กอิน: สร้างเมนู/ทูลบาร์ และเปิดหน้าต่าง (dock) ตรวจสอบ

ผู้พัฒนา : นายภาคภูมิ สูบกำปัง
ตำแหน่ง  : วิศวกรรังวัดปฏิบัติการ
สังกัด    : กองเทคโนโลยีทำแผนที่
"""

import os

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .topology_dock import TopologyCheckerDock

PLUGIN_DIR = os.path.dirname(__file__)
PLUGIN_NAME = "Node & Topology Checker"
MENU_TITLE = "&Node && Topology Checker"


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


class NodeTopologyCheckerPlugin:
    """จุดเชื่อมต่อของปลั๊กอินกับ QGIS"""

    def __init__(self, iface):
        self.iface = iface
        self.actions = []
        self.dock = None
        self._menu_added = False

    # ------------------------------------------------------------------
    # วงจรชีวิตของปลั๊กอิน
    # ------------------------------------------------------------------
    def initGui(self):  # noqa: N802 (ชื่อกำหนดโดย QGIS)
        """สร้าง action สำหรับเปิดหน้าต่างตรวจสอบ"""
        icon = find_plugin_icon()

        action = QAction(icon, "เปิดตัวตรวจสอบ Topology / Node", self.iface.mainWindow())
        action.triggered.connect(self.run)
        action.setCheckable(False)

        self.iface.addToolBarIcon(action)
        self.iface.addPluginToVectorMenu(MENU_TITLE, action)
        self.actions.append(action)
        self._menu_added = True

    def unload(self):
        """ถอดปลั๊กอิน: ลบเมนู/ทูลบาร์ และปิด dock"""
        for action in self.actions:
            self.iface.removePluginVectorMenu(MENU_TITLE, action)
            self.iface.removeToolBarIcon(action)
        self.actions = []

        if self.dock is not None:
            try:
                self.dock.cleanup()
            except Exception:  # noqa: BLE001 - ป้องกัน unload พังตอนปิด QGIS
                pass
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
            self.dock = None

    # ------------------------------------------------------------------
    # การทำงาน
    # ------------------------------------------------------------------
    def run(self):
        """เปิด/แสดงหน้าต่างตรวจสอบ"""
        if self.dock is None:
            self.dock = TopologyCheckerDock(self.iface)
            self.dock.destroyed.connect(self._on_dock_destroyed)
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock)

        self.dock.show()
        self.dock.raise_()

    def _on_dock_destroyed(self, *args):
        self.dock = None
