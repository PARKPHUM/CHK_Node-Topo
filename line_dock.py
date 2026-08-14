# -*- coding: utf-8 -*-
"""
line_dock.py — หน้าต่าง (Dock) หลักของปลั๊กอิน สร้าง UI ด้วยโค้ด (ภาษาไทย)

เครื่องมือวาดเส้นพร้อมวัดระยะ:
  • สร้างชั้นเส้น + วาดเส้นด้วยเครื่องมือ Add Feature มาตรฐาน (snapping แบบ vertex)
  • แสดงระยะแต่ละช่วงเป็นเมตรบนแผนที่ (label ข้างเส้น ไม่ทับแนวเส้น)
  • แสดงจุด Node ที่จุดหักของเส้น
  • ล็อกระยะ / ล็อกมุม ผ่านระบบดิจิไทซ์ขั้นสูงของ QGIS โดยสั่งจากในปลั๊กอินได้เลย
  • ปุ่มตรวจสอบ/อัปเดตปลั๊กอินจาก GitHub

ผู้พัฒนา : นายภาคภูมิ สูบกำปัง (วิศวกรรังวัดปฏิบัติการ กองเทคโนโลยีทำแผนที่)
"""

import os

from qgis.PyQt.QtCore import QEvent, QObject, Qt
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsProject,
    QgsSnappingConfig,
    QgsTolerance,
    QgsUnitTypes,
)
from qgis.gui import (
    QgsAdvancedDigitizingDockWidget,
    QgsDockWidget,
)

from .line_tools import LineToolLayers
from . import update_checker

PLUGIN_DIR = os.path.dirname(__file__)

# ==================================================================
# ชุดสี/สไตล์ — โทน Bootstrap ให้เข้าชุดกับปลั๊กอิน Filter_PATH
#   น้ำเงิน #007bff | แดง #dc3545 | เทา #6c757d
#   พื้นอ่อน #f8f9fa | ตัวหนังสือ #333 | ขอบ #ced4da
# ==================================================================
# ขนาด/สไตล์อ้างอิงตามปุ่ม "อัปเดตปลั๊กอิน" ของ Filter_PATH:
#   font-size 10pt, ตัวหนา, padding 6px, border-radius 4px
_BTN_BASE = (
    "QPushButton {{"
    " background-color: {bg}; color: white; border: none;"
    " border-radius: 4px; padding: 6px; font-size: 10pt; font-weight: bold; }}"
    "QPushButton:hover:enabled {{ background-color: {hover}; }}"
    "QPushButton:pressed:enabled {{ background-color: {pressed}; }}"
    "QPushButton:disabled {{ background-color: #ced4da; color: #f1f3f5; }}"
)

# ปุ่ม "อัปเดตปลั๊กอิน" — สีแดง
BTN_RED = _BTN_BASE.format(bg="#dc3545", hover="#e15361", pressed="#bd2130")
# ปุ่ม "วาดเส้น" — สีฟ้า
BTN_BLUE = _BTN_BASE.format(bg="#007bff", hover="#268fff", pressed="#0062cc")
# ปุ่ม "สร้าง Layer เส้น" — สีเขียว (Bootstrap success)
BTN_GREEN = _BTN_BASE.format(bg="#28a745", hover="#34ce57", pressed="#1e7e34")

# สไตล์รวมของหน้าต่าง — โทน/ขนาดฟอนต์อ้างอิงตาม Filter_PATH (Bootstrap)
DOCK_QSS = """
#ntcContainer { background-color: #f8f9fa; }

QLabel { font-size: 10pt; font-weight: bold; color: #333; }

QGroupBox {
    font-size: 10pt;
    font-weight: bold;
    color: #2c3e50;
    background-color: #ffffff;
    border: 1px solid #e3e6ea;
    border-radius: 6px;
    margin-top: 14px;
    padding: 10px 8px 8px 8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 2px 8px;
    color: #007bff;
}

QCheckBox { font-size: 10pt; font-weight: bold; color: #333; spacing: 7px; padding: 2px 0; }

QDoubleSpinBox { font-size: 11pt; padding: 2px 4px; min-height: 22px; }

QFrame[frameShape="4"] { color: #e3e6ea; }
"""


def _lock_mode(name):
    """คืนค่า enum LockMode ตามชื่อ — รองรับตำแหน่ง enum ที่ต่างกันตามรุ่น QGIS

    QGIS บางรุ่นวาง enum ไว้ที่ CadConstraint ตรง ๆ บางรุ่นซ้อนใน LockMode อีกชั้น
    """
    constraint_cls = QgsAdvancedDigitizingDockWidget.CadConstraint
    holder = getattr(constraint_cls, "LockMode", constraint_cls)
    return getattr(holder, name, None)


class _ShiftAngleFilter(QObject):
    """ดักปุ่ม Shift บนแผนที่ เพื่อเปิด/ปิดการล็อกมุมระหว่างวาดเส้น

    ใช้ event filter แทนการเขียน map tool เอง — จึงยังได้พฤติกรรมมาตรฐานของ
    เครื่องมือ Add Feature ครบ (คลิกขวาจบเส้น, undo, snapping)
    """

    def __init__(self, dock):
        super().__init__(dock)
        self._dock = dock

    def eventFilter(self, obj, event):  # noqa: N802 (ชื่อกำหนดโดย Qt)
        try:
            etype = event.type()
            if etype == QEvent.KeyPress and event.key() == Qt.Key_Shift:
                self._dock.apply_angle_lock(True)
            elif etype == QEvent.KeyRelease and event.key() == Qt.Key_Shift:
                self._dock.apply_angle_lock(False)
        except Exception:  # noqa: BLE001 - ห้ามให้ event filter พังจนคลิกแผนที่ไม่ได้
            pass
        return False  # ส่ง event ต่อเสมอ ไม่กลืน


class LineToolDock(QgsDockWidget):
    """หน้าต่างหลักของปลั๊กอิน"""

    def __init__(self, iface, parent=None):
        version = update_checker.read_local_version(PLUGIN_DIR)
        super().__init__("วาดเส้น & วัดระยะ  Version {}".format(version), parent)
        self.iface = iface
        self.setObjectName("LineDrawMeasureDock")

        self.update_task = None     # งานตรวจสอบเวอร์ชัน
        self.install_task = None    # งานติดตั้งอัปเดต
        self._warned_units = False  # เตือนเรื่องหน่วยของช่องล็อกระยะแค่ครั้งเดียว

        self.layers = LineToolLayers(iface, self)
        self.layers.layersChanged.connect(self._sync_layer_state)

        self._build_ui()

    # ==================================================================
    # สร้าง UI
    # ==================================================================
    def _build_ui(self):
        container = QWidget()
        container.setObjectName("ntcContainer")
        container.setStyleSheet(DOCK_QSS)
        root = QVBoxLayout(container)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        # ---- กลุ่ม: เครื่องมือวาดเส้น ----
        line_group = QGroupBox("เครื่องมือวาดเส้น (Line)")
        lv = QVBoxLayout(line_group)
        lv.setSpacing(8)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.btn_new_line = QPushButton("สร้าง Layer เส้น")
        self.btn_new_line.setStyleSheet(BTN_GREEN)
        self.btn_new_line.setCursor(Qt.PointingHandCursor)
        self.btn_new_line.clicked.connect(self.on_new_line_layer)
        self.btn_draw_line = QPushButton("✎ วาดเส้น")
        self.btn_draw_line.setStyleSheet(BTN_BLUE)
        self.btn_draw_line.setCursor(Qt.PointingHandCursor)
        self.btn_draw_line.clicked.connect(self.on_draw_line)
        self.btn_draw_line.setEnabled(False)
        self.btn_draw_line.setToolTip(
            "คลิกซ้ายเพื่อลงจุด, คลิกขวาเพื่อจบเส้น (วาดได้หลายเส้น)\n"
            "เปิด snapping แบบ Vertex ให้อัตโนมัติ — เคอร์เซอร์จะดูดเข้าหามุม/หมุด")
        btn_row.addWidget(self.btn_new_line, 1)
        btn_row.addWidget(self.btn_draw_line, 1)
        lv.addLayout(btn_row)

        self.chk_labels = QCheckBox("แสดงระยะบนเส้น (เมตร)")
        self.chk_labels.setChecked(True)
        self.chk_labels.setToolTip(
            "แสดงระยะของเส้น 'แต่ละช่วง' เป็นเมตร วางไว้ข้างแนวเส้น (ไม่ทับเส้น)\n"
            "คำนวณด้วย ellipsoid ของโปรเจกต์ จึงเป็นเมตรจริงแม้โปรเจกต์อยู่บน CRS หน่วยองศา")
        self.chk_labels.toggled.connect(self.on_toggle_labels)
        lv.addWidget(self.chk_labels)

        self.chk_nodes = QCheckBox("แสดง Node ที่จุดหัก")
        self.chk_nodes.setChecked(True)
        self.chk_nodes.setToolTip("แสดงจุดกลมสีแดงที่หัว/ท้ายเส้น และทุกจุดหักของเส้น")
        self.chk_nodes.toggled.connect(self.on_toggle_nodes)
        lv.addWidget(self.chk_nodes)
        root.addWidget(line_group)

        # ---- กลุ่ม: ล็อกการวาด ----
        lock_group = QGroupBox("ล็อกการวาด (ดิจิไทซ์ขั้นสูง)")
        kv = QVBoxLayout(lock_group)
        kv.setSpacing(8)

        # ล็อกระยะ — ยก Advanced Digitizing ของ QGIS มาสั่งจากในปลั๊กอิน
        dist_row = QHBoxLayout()
        dist_row.setSpacing(8)
        self.chk_dist_lock = QCheckBox("ล็อกระยะ")
        self.chk_dist_lock.setToolTip(
            "ล็อกความยาวของทุกช่วงที่วาดให้เท่ากับค่าที่กรอก\n"
            "แก้ตัวเลขระหว่างวาดได้ ช่วงถัดไปจะใช้ค่าใหม่ทันที")
        self.chk_dist_lock.toggled.connect(self.on_toggle_distance_lock)
        self.spin_distance = QDoubleSpinBox()
        self.spin_distance.setRange(0.001, 1000000.0)
        self.spin_distance.setDecimals(3)
        self.spin_distance.setSingleStep(1.0)
        self.spin_distance.setValue(10.0)
        self.spin_distance.setSuffix(" ม.")
        self.spin_distance.setFixedWidth(120)
        self.spin_distance.setToolTip("ระยะที่จะล็อก (หน่วยแผนที่ — เป็นเมตรเมื่อโปรเจกต์ใช้ CRS หน่วยเมตร)")
        self.spin_distance.valueChanged.connect(self.on_distance_value_changed)
        dist_row.addWidget(self.chk_dist_lock, 1)
        dist_row.addWidget(self.spin_distance)
        kv.addLayout(dist_row)

        # ล็อกมุมด้วยปุ่ม Shift
        angle_row = QHBoxLayout()
        angle_row.setSpacing(8)
        self.chk_shift_lock = QCheckBox("กด Shift ค้างเพื่อล็อกมุม")
        self.chk_shift_lock.setChecked(True)
        self.chk_shift_lock.setToolTip(
            "ระหว่างวาดเส้น กดปุ่ม Shift ค้างไว้ = ล็อกมุมตามองศาที่ตั้ง\n"
            "ปล่อย Shift = กลับมาลากอิสระเหมือนเดิม")
        self.spin_angle = QDoubleSpinBox()
        self.spin_angle.setRange(0.0, 360.0)
        self.spin_angle.setDecimals(1)
        self.spin_angle.setSingleStep(15.0)
        self.spin_angle.setValue(90.0)   # ค่าเริ่มต้น: ตั้งฉากกับช่วงก่อนหน้า
        self.spin_angle.setSuffix(" °")
        self.spin_angle.setFixedWidth(120)
        self.spin_angle.setToolTip("องศาที่จะล็อกเมื่อกด Shift (เทียบกับเส้นช่วงก่อนหน้า)")
        angle_row.addWidget(self.chk_shift_lock, 1)
        angle_row.addWidget(self.spin_angle)
        kv.addLayout(angle_row)

        # เปิด/ปิดแถบ "ดิจิไทซ์ขั้นสูง" ของ QGIS แบบเห็นหน้าตาแถบจริง
        self.chk_cad = QCheckBox("แสดงแถบดิจิไทซ์ขั้นสูงของ QGIS")
        self.chk_cad.setToolTip(
            "ปกติปิดไว้ได้เลย — ล็อกระยะ/มุมด้านบนทำงานได้โดยไม่ต้องมีแถบนี้บนจอ\n"
            "ติ๊กเมื่ออยากเห็นแถบจริงของ QGIS เพื่อกรอกค่าเองแบบละเอียด:\n"
            "• ช่อง a = มุม (พิมพ์เองได้ เช่น 30, 45, 90) แล้วกดแม่กุญแจเพื่อล็อก\n"
            "• ช่อง d = ระยะ (พิมพ์ความยาวเป๊ะ ๆ ได้)")
        self.chk_cad.toggled.connect(self.on_toggle_cad)
        kv.addWidget(self.chk_cad)
        root.addWidget(lock_group)

        # ดักปุ่ม Shift บน canvas (ติดตั้งครั้งเดียว ถอดตอน unload)
        self._shift_filter = _ShiftAngleFilter(self)
        try:
            self.iface.mapCanvas().installEventFilter(self._shift_filter)
        except Exception:  # noqa: BLE001
            self._shift_filter = None

        # ---- แถบสถานะ ----
        self.status_label = QLabel("ยังไม่ได้สร้าง Layer เส้น — กด 'สร้าง Layer เส้น' เพื่อเริ่ม")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            "font-size: 10pt; font-weight: bold; color: #495057;"
            " background-color: #eef4ff; border: 1px solid #cfe2ff;"
            " border-radius: 4px; padding: 7px 9px;")
        root.addWidget(self.status_label)

        root.addStretch(1)

        # ---- เส้นคั่น + ส่วนอัปเดต ----
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        root.addWidget(line)

        upd_row = QHBoxLayout()
        self.btn_update = QPushButton("อัปเดตปลั๊กอิน")
        self.btn_update.setStyleSheet(BTN_RED)
        self.btn_update.setCursor(Qt.PointingHandCursor)
        self.btn_update.clicked.connect(self.on_check_update)
        upd_row.addWidget(self.btn_update)
        upd_row.addStretch(1)
        root.addLayout(upd_row)

        self.setWidget(container)

    # ==================================================================
    # เครื่องมือวาดเส้น
    # ==================================================================
    def on_new_line_layer(self):
        """สร้างชั้นเส้น + ชั้น label ระยะ — บังคับให้มีได้ชุดเดียว"""
        had_layer = self.layers.has_layers()
        layer, error = self.layers.create_layers()
        if layer is None:
            self._warn(error or "สร้างชั้นเส้นไม่สำเร็จ")
            return

        self.iface.setActiveLayer(layer)
        self._sync_layer_state()

        if had_layer:
            self._warn("มี Layer เส้นอยู่แล้ว — วาดเส้นลงในชั้นเดิมได้เลย")
            return

        self.iface.messageBar().pushMessage(
            "สร้าง Layer เส้นแล้ว",
            "กด '✎ วาดเส้น' เพื่อเริ่มวาด (คลิกขวาเพื่อจบเส้น)",
            level=Qgis.Info, duration=5)

    def on_draw_line(self):
        """เริ่มวาดเส้นลงในชั้นเส้น: เปิด snapping + editing + เครื่องมือ Add Feature"""
        layer = self.layers.line_layer()
        if layer is None:
            self._sync_layer_state()
            self._warn("กรุณาสร้าง Layer เส้นก่อน")
            return

        # เปิด snapping ก่อน เพื่อให้เคอร์เซอร์ดูดเข้าหา vertex พร้อมตัวชี้ตำแหน่ง
        try:
            self._enable_vertex_snapping()
        except Exception:  # noqa: BLE001 - ตั้ง snapping ไม่ได้ ก็ยังวาดเส้นได้ตามปกติ
            pass
        self.iface.setActiveLayer(layer)
        if not layer.isEditable():
            layer.startEditing()
        # เครื่องมือ Add Feature มาตรฐาน: คลิกซ้ายลงจุด, คลิกขวาจบเส้น (ฟรี)
        self.iface.actionAddFeature().trigger()

        # ต้องตั้งค่า CAD หลัง trigger เสมอ เพราะ CAD ผูกกับ map tool ที่กำลังใช้งาน
        # (สลับเครื่องมือแล้ว QGIS อาจเด้งแถบขึ้นมาเอง — บังคับกลับตามที่ผู้ใช้ตั้งไว้)
        try:
            self._set_cad_visible(self.chk_cad.isChecked())
        except Exception:  # noqa: BLE001
            pass
        if self.chk_dist_lock.isChecked():
            self.apply_distance_lock(True)

        self.status_label.setText(
            "กำลังวาดเส้น — คลิกซ้ายลงจุด, คลิกขวาเพื่อจบเส้น")

    def _enable_vertex_snapping(self):
        """เปิด snapping แบบ Vertex ทุกชั้น — เคอร์เซอร์จะดูดเข้าหามุม/หมุด
        และ QGIS จะวาดตัวชี้ (snap indicator) ตรงตำแหน่ง vertex ที่จะ snap ให้เอง
        """
        project = QgsProject.instance()
        config = project.snappingConfig()
        config.setEnabled(True)
        config.setMode(QgsSnappingConfig.AllLayers)
        # QGIS ใหม่ใช้ flag enum (setTypeFlag) ส่วนรุ่นเก่าใช้ setType
        try:
            config.setTypeFlag(QgsSnappingConfig.VertexFlag)
        except (AttributeError, TypeError):
            config.setType(QgsSnappingConfig.Vertex)
        config.setTolerance(12)
        config.setUnits(QgsTolerance.Pixels)
        project.setSnappingConfig(config)

    def _sync_layer_state(self):
        """ปรับปุ่ม/ข้อความสถานะให้ตรงกับว่ามีชั้นเส้นอยู่จริงหรือไม่"""
        has_layer = self.layers.has_layers()
        self.btn_draw_line.setEnabled(has_layer)
        if has_layer:
            self.status_label.setText("พร้อมวาด — กด '✎ วาดเส้น' แล้วคลิกลงจุดบนแผนที่")
        else:
            self.status_label.setText(
                "ยังไม่ได้สร้าง Layer เส้น — กด 'สร้าง Layer เส้น' เพื่อเริ่ม")

    # ==================================================================
    # ปุ่มเช็ก: label ระยะ / จุด Node
    # ==================================================================
    def on_toggle_labels(self, checked):
        self.layers.set_labels_visible(checked)

    def on_toggle_nodes(self, checked):
        self.layers.set_nodes_visible(checked)

    # ==================================================================
    # ล็อกระยะ / ล็อกมุม (ระบบดิจิไทซ์ขั้นสูงของ QGIS)
    # ==================================================================
    # "ระบบ" ดิจิไทซ์ขั้นสูง กับ "แถบ" ที่เห็นบนจอ เป็นคนละเรื่องกัน:
    #   • cadEnabled()  = ระบบล็อกมุม/ระยะทำงานอยู่ไหม  → จำเป็นต้องเปิด ไม่งั้น constraint ไม่มีผล
    #   • setVisible()  = แถบโผล่บนจอไหม               → เรื่องหน้าตาล้วน ๆ ไม่กระทบการล็อก
    # แยกสองอย่างนี้ออกจากกัน ผู้ใช้จึงล็อกระยะ/มุมได้โดยไม่ต้องมีแถบ CAD เกะกะจอ
    def _set_cad_enabled(self, enabled):
        """เปิด/ปิด "ระบบ" ดิจิไทซ์ขั้นสูง

        ใช้ enableAction() ซึ่งเป็นปุ่มสลับ "เปิดเครื่องมือดิจิไทซ์ขั้นสูง" ของ QGIS เอง
        จึงได้พฤติกรรมตรงกับที่ผู้ใช้กดเองในโปรแกรม
        """
        cad = self.iface.cadDockWidget()
        if cad is None:
            return False
        action = cad.enableAction()
        if action is not None and action.isEnabled() and action.isChecked() != enabled:
            action.trigger()
        return cad.cadEnabled() == enabled

    def _set_cad_visible(self, visible):
        """แสดง/ซ่อน "แถบ" ดิจิไทซ์ขั้นสูงบนจอ (ไม่แตะสถานะเปิด/ปิดของระบบ)"""
        cad = self.iface.cadDockWidget()
        if cad is None:
            return False
        cad.setVisible(bool(visible))
        return True

    def _ensure_cad_enabled(self):
        """เปิดระบบ CAD ถ้ายังปิดอยู่ — constraint ไม่มีผลเลยถ้าระบบไม่เปิด

        เปิดแล้วบังคับสถานะการ "แสดงแถบ" กลับไปตามที่ผู้ใช้ตั้งไว้เสมอ
        เพราะการเปิดระบบอาจทำให้ QGIS เด้งแถบขึ้นมาเอง
        """
        cad = self.iface.cadDockWidget()
        if cad is None:
            return None
        if not cad.cadEnabled():
            self._set_cad_enabled(True)
        self._set_cad_visible(self.chk_cad.isChecked())
        return cad

    def apply_distance_lock(self, locked):
        """ล็อก/ปลดล็อกระยะของแต่ละช่วงที่วาด

        ใช้ constraint "ระยะ" ของแถบดิจิไทซ์ขั้นสูง + repeating lock เพื่อให้ค้าง
        ทุกช่วง ไม่ใช่ล็อกช่วงเดียวแล้วหลุด
        """
        cad = self.iface.cadDockWidget()
        if cad is None:
            if locked:
                self._warn("เปิดระบบดิจิไทซ์ขั้นสูงไม่สำเร็จ — ล็อกระยะไม่ได้")
            return
        constraint = cad.constraintDistance()
        if constraint is None:
            return

        if locked:
            self._ensure_cad_enabled()
            self._check_distance_units()
            constraint.setValue(float(self.spin_distance.value()), True)
            try:
                constraint.setRepeatingLock(True)
            except (AttributeError, TypeError):
                pass
            mode = _lock_mode("HardLock")
        else:
            try:
                constraint.setRepeatingLock(False)
            except (AttributeError, TypeError):
                pass
            mode = _lock_mode("NoLock")
        if mode is not None:
            constraint.setLockMode(mode)

    def on_toggle_distance_lock(self, checked):
        try:
            self.apply_distance_lock(checked)
        except Exception:  # noqa: BLE001
            self._warn("ตั้งค่าล็อกระยะไม่สำเร็จ")

    def on_distance_value_changed(self, _value):
        """แก้ตัวเลขระหว่างวาด — ช่วงถัดไปต้องใช้ค่าใหม่ทันที"""
        if self.chk_dist_lock.isChecked():
            try:
                self.apply_distance_lock(True)
            except Exception:  # noqa: BLE001
                pass

    def _check_distance_units(self):
        """เตือนครั้งเดียวถ้าโปรเจกต์ไม่ได้ใช้ CRS หน่วยเมตร

        ค่า constraint ของ QGIS เป็น "หน่วยแผนที่" ต่างจาก label ระยะ
        ที่คำนวณเป็นเมตรจริงเสมอ — ถ้าไม่บอก ผู้ใช้จะงงว่าทำไมล็อก 10 แล้วได้เส้นยาวผิด
        """
        if self._warned_units:
            return
        crs = QgsProject.instance().crs()
        if crs is not None and crs.isValid() and crs.mapUnits() != QgsUnitTypes.DistanceMeters:
            self._warned_units = True
            self._warn("โปรเจกต์นี้ไม่ได้ใช้ CRS หน่วยเมตร — ค่าในช่อง 'ล็อกระยะ' "
                       "เป็นหน่วยแผนที่ ไม่ใช่เมตร (label ระยะยังเป็นเมตรจริงตามปกติ)")

    def apply_angle_lock(self, locked):
        """ล็อก/ปลดล็อกมุมของการวาดเส้น (เรียกจากตัวดักปุ่ม Shift)

        ใช้ระบบ constraint ของแถบดิจิไทซ์ขั้นสูง: ตั้งมุมแบบ "สัมพัทธ์กับช่วงก่อนหน้า"
        แล้วสั่ง HardLock — QGIS จะบังคับแนวเส้นให้เอง พร้อมแสดงเส้นประบอกแนว
        """
        if not self.chk_shift_lock.isChecked():
            return
        # ล็อกมุมต้องมีชั้นเส้นที่กำลังแก้ไขอยู่ ไม่งั้นไปกวนการวาดชั้นอื่นของผู้ใช้
        layer = self.layers.line_layer()
        if layer is None or not layer.isEditable():
            return

        cad = self.iface.cadDockWidget()
        if cad is None:
            return
        constraint = cad.constraintAngle()
        if constraint is None:
            return

        if locked:
            self._ensure_cad_enabled()
            constraint.setRelative(True)
            constraint.setValue(float(self.spin_angle.value()), True)
            mode = _lock_mode("HardLock")
        else:
            mode = _lock_mode("NoLock")
        if mode is not None:
            constraint.setLockMode(mode)

    def on_toggle_cad(self, checked):
        """ผู้ใช้กดแสดง/ซ่อนแถบดิจิไทซ์ขั้นสูงของ QGIS

        ซ่อนแถบไม่ได้ทำให้ล็อกระยะ/มุมหยุดทำงาน — ระบบยังเปิดอยู่เบื้องหลัง
        """
        try:
            ok = self._set_cad_visible(checked)
        except Exception:  # noqa: BLE001
            ok = False
        if not ok and checked:
            self._warn("เปิดแถบดิจิไทซ์ขั้นสูงไม่สำเร็จ — เปิดเองได้ที่เมนู "
                       "มุมมอง > แผงหน้าต่าง > ดิจิไทซ์ขั้นสูง")

    # ==================================================================
    # ตรวจสอบ / อัปเดตปลั๊กอิน
    # ==================================================================
    def on_check_update(self):
        if self.update_task is not None or self.install_task is not None:
            return
        if not update_checker.is_repo_configured():
            QMessageBox.information(
                self, "ยังไม่ได้ตั้งค่า repository",
                "ระบบอัปเดตยังไม่ได้กำหนด GitHub repository\n"
                "ผู้ดูแลต้องแก้ค่า DEFAULT_REPO ในไฟล์ update_checker.py "
                "ให้เป็น owner/repository ของโครงการ")
            return

        self.btn_update.setEnabled(False)
        self.btn_update.setText("กำลังตรวจสอบ...")
        self.update_task = update_checker.UpdateCheckTask(PLUGIN_DIR)
        self.update_task.set_callback(self.on_update_checked)
        QgsApplication.taskManager().addTask(self.update_task)

    def on_update_checked(self, success, task):
        self.btn_update.setEnabled(True)
        self.btn_update.setText("อัปเดตปลั๊กอิน")
        self.update_task = None

        if not success:
            QMessageBox.warning(
                self, "ตรวจสอบอัปเดตไม่สำเร็จ",
                "ไม่สามารถเชื่อมต่อ GitHub ได้\n\nรายละเอียด: {}".format(
                    task.error_message or "ไม่ทราบสาเหตุ"))
            return

        if task.has_update():
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Information)
            box.setWindowTitle("พบเวอร์ชันใหม่")
            box.setText(
                "🎉 พบเวอร์ชันใหม่บน GitHub แล้ว!\n\n"
                "เวอร์ชันใหม่ : {}\n"
                "เวอร์ชันของคุณ : {}\n\n"
                "ต้องการดาวน์โหลดและติดตั้งเลยหรือไม่?\n"
                "(หลังติดตั้งเสร็จ ต้องปิดและเปิด QGIS ใหม่)".format(
                    task.remote_version, task.local_version))
            btn_update = box.addButton("อัปเดตเลย", QMessageBox.AcceptRole)
            box.addButton("ไว้ก่อน", QMessageBox.RejectRole)
            box.setDefaultButton(btn_update)
            box.exec_()

            if box.clickedButton() == btn_update:
                self._start_install(task.resolved_branch)
        elif (update_checker.parse_version(task.local_version)
                > update_checker.parse_version(task.remote_version)):
            # เครื่องนักพัฒนา: โค้ดในเครื่องใหม่กว่าที่ push ขึ้น GitHub
            # (แยกข้อความออกมา ไม่งั้นจะอ่านว่า "ล่าสุดแล้ว" ทั้งที่ยังไม่ได้เผยแพร่)
            QMessageBox.information(
                self, "เวอร์ชันในเครื่องใหม่กว่า GitHub",
                "ไม่มีอะไรให้อัปเดต — เครื่องคุณใหม่กว่าบน GitHub\n\n"
                "เวอร์ชันในเครื่อง : {}\n"
                "เวอร์ชันบน GitHub : {}\n\n"
                "ถ้าต้องการเผยแพร่เวอร์ชันนี้ ให้ commit + push ขึ้น GitHub ก่อน".format(
                    task.local_version, task.remote_version))
        else:
            QMessageBox.information(
                self, "ใช้เวอร์ชันล่าสุดแล้ว",
                "คุณกำลังใช้ปลั๊กอินเวอร์ชันล่าสุดแล้ว ✔\n\n"
                "เวอร์ชันในเครื่อง : {}\n"
                "เวอร์ชันบน GitHub : {}".format(
                    task.local_version, task.remote_version))

    def _start_install(self, branch):
        self.install_task = update_checker.UpdateInstallTask(PLUGIN_DIR, branch)
        self.install_task.set_callback(self.on_update_installed)
        self.btn_update.setEnabled(False)
        self.btn_update.setText("กำลังดาวน์โหลด...")
        QgsApplication.taskManager().addTask(self.install_task)

    def on_update_installed(self, success, task):
        self.btn_update.setEnabled(True)
        self.btn_update.setText("อัปเดตปลั๊กอิน")
        self.install_task = None

        if success:
            # ใช้ไอคอนเตือน (ไม่ใช่ information) เพราะถ้าไม่รีสตาร์ท
            # ปลั๊กอินจะยังรันโค้ดเดิมในหน่วยความจำ — ผู้ใช้มักพลาดจุดนี้
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle("อัปเดตเสร็จแล้ว — ต้องปิด/เปิด QGIS ใหม่")
            box.setText(
                "ดาวน์โหลดและติดตั้งเวอร์ชันใหม่เรียบร้อยแล้ว ✔\n\n"
                "⚠ กรุณา \"ปิดโปรแกรม QGIS แล้วเปิดใหม่\" ตอนนี้\n\n"
                "เวอร์ชันใหม่จะเริ่มทำงานหลังเปิด QGIS ใหม่เท่านั้น\n"
                "ถ้ายังไม่ปิด/เปิดใหม่ ปลั๊กอินจะยังทำงานด้วยโค้ดเวอร์ชันเดิมอยู่")
            box.exec_()
        else:
            QMessageBox.warning(
                self, "อัปเดตไม่สำเร็จ",
                "ไม่สามารถติดตั้งอัปเดตได้\n\nรายละเอียด: {}".format(
                    task.error_message or "ไม่ทราบสาเหตุ"))

    # ==================================================================
    # ตัวช่วย
    # ==================================================================
    def _warn(self, message):
        self.iface.messageBar().pushMessage(
            "แจ้งเตือน", message, level=Qgis.Warning, duration=5)

    # ==================================================================
    # cleanup (เรียกตอน unload ปลั๊กอิน)
    # ==================================================================
    def cleanup(self):
        # ถอดตัวดักปุ่ม Shift ออกจาก canvas ไม่งั้นค้างหลัง unload ปลั๊กอิน
        if getattr(self, "_shift_filter", None) is not None:
            try:
                self.iface.mapCanvas().removeEventFilter(self._shift_filter)
            except Exception:  # noqa: BLE001
                pass
            self._shift_filter = None

        try:
            self.layers.cleanup()
        except Exception:  # noqa: BLE001
            pass

        if self.update_task is not None:
            try:
                self.update_task.cancel()
            except Exception:  # noqa: BLE001
                pass
        if self.install_task is not None:
            try:
                self.install_task.cancel()
            except Exception:  # noqa: BLE001
                pass
