# -*- coding: utf-8 -*-
"""
line_dock.py — หน้าต่างหลักของปลั๊กอิน (หน้าต่างลอย ย้ายไปมาได้)

เครื่องมือวาดเส้นพร้อมวัดระยะ:
  • สร้างชั้นเส้น + วาดเส้นด้วยเครื่องมือ Add Feature มาตรฐาน (snapping แบบ vertex)
  • แสดงระยะแต่ละช่วงเป็นเมตรบนแผนที่ (label ข้างเส้น ไม่ทับแนวเส้น)
  • แสดงจุด Node ที่จุดหักของเส้น
  • ล็อกระยะ / ล็อกมุม ผ่านระบบดิจิไทซ์ขั้นสูงของ QGIS โดยสั่งจากในปลั๊กอินได้เลย
    (แถบของ QGIS ถูกซ่อนไว้ตลอด ไม่โผล่มากวน)
  • แนวอ้างอิงมุมจาก Ctrl + คลิกซ้าย 2 จุด — ตีฉากจากแนวเขตจริงได้
  • Banner บอกขั้นตอนการใช้งานทีละขั้น
  • ปุ่มตรวจสอบ/อัปเดตปลั๊กอินจาก GitHub

ผู้พัฒนา : นายภาคภูมิ สูบกำปัง (วิศวกรรังวัดปฏิบัติการ กองเทคโนโลยีทำแผนที่)
"""

import os

from qgis.PyQt.QtCore import QEvent, QObject, QSettings, Qt
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
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
    QgsMapToolCapture,
)

from .line_tools import LineToolLayers
from .angle_ref import AngleReference
from . import update_checker

PLUGIN_DIR = os.path.dirname(__file__)

#: คีย์เก็บตำแหน่ง/ขนาดหน้าต่าง เพื่อเปิดมาที่เดิมทุกครั้ง
SETTINGS_GEOMETRY = "LineDrawMeasure/windowGeometry"

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
# ปุ่ม "ล้างแนวอ้างอิง" — สีเทา (Bootstrap secondary)
BTN_GRAY = _BTN_BASE.format(bg="#6c757d", hover="#828a91", pressed="#5a6268")

# สไตล์รวมของหน้าต่าง — โทน/ขนาดฟอนต์อ้างอิงตาม Filter_PATH (Bootstrap)
DOCK_QSS = """
QDialog { background-color: #f8f9fa; }

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

/* ช่องเดียวในหน้าต่างคือช่องอาซิมุท (อ่านอย่างเดียว) — ไม่ใช้ property selector
   เพราะ selector แบบนั้นต้องพึ่งจังหวะ polish ของ Qt ซึ่งไม่แน่นอน */
QLineEdit {
    font-size: 11pt;
    font-weight: bold;
    color: #6f42c1;
    background-color: #f4f0fa;
    border: 1px solid #d9cdf0;
    border-radius: 4px;
    padding: 3px 6px;
}

QFrame[frameShape="4"] { color: #e3e6ea; }
"""

# Banner บอกขั้นตอน — เขียวเมื่อสำเร็จ, ฟ้าเมื่อกำลังบอกขั้นตอนถัดไป
BANNER_INFO = (
    "font-size: 10pt; font-weight: bold; color: #0b4a8f;"
    " background-color: #eef4ff; border: 1px solid #cfe2ff;"
    " border-left: 5px solid #007bff;"
    " border-radius: 4px; padding: 8px 10px;")
BANNER_ACTIVE = (
    "font-size: 10pt; font-weight: bold; color: #155724;"
    " background-color: #eaf7ee; border: 1px solid #c3e6cb;"
    " border-left: 5px solid #28a745;"
    " border-radius: 4px; padding: 8px 10px;")


def _lock_mode(name):
    """คืนค่า enum LockMode ตามชื่อ — รองรับตำแหน่ง enum ที่ต่างกันตามรุ่น QGIS

    QGIS บางรุ่นวาง enum ไว้ที่ CadConstraint ตรง ๆ บางรุ่นซ้อนใน LockMode อีกชั้น
    """
    constraint_cls = QgsAdvancedDigitizingDockWidget.CadConstraint
    holder = getattr(constraint_cls, "LockMode", constraint_cls)
    return getattr(holder, name, None)


class _CanvasFilter(QObject):
    """ดักอินพุตบนแผนที่: ปุ่ม Shift (ล็อกมุม) และ Ctrl + คลิกซ้าย (แนวอ้างอิง)

    ใช้ event filter แทนการเขียน map tool เอง — จึงยังได้พฤติกรรมมาตรฐานของ
    เครื่องมือ Add Feature ครบ (คลิกขวาจบเส้น, undo, snapping)

    หมายเหตุ: event ของปุ่มกดวิ่งเข้า canvas แต่ event ของเมาส์วิ่งเข้า viewport()
    จึงต้องติดตั้งตัวกรองนี้กับทั้งสองตัว
    """

    def __init__(self, dock):
        super().__init__(dock)
        self._dock = dock
        self._swallow_release = False

    def eventFilter(self, obj, event):  # noqa: N802 (ชื่อกำหนดโดย Qt)
        try:
            etype = event.type()

            if etype == QEvent.KeyPress and event.key() == Qt.Key_Shift:
                self._dock.apply_angle_lock(True)
            elif etype == QEvent.KeyRelease and event.key() == Qt.Key_Shift:
                self._dock.apply_angle_lock(False)

            elif (etype == QEvent.MouseButtonPress
                    and event.button() == Qt.LeftButton
                    and bool(event.modifiers() & Qt.ControlModifier)):
                if self._dock.handle_ctrl_click(event.pos()):
                    # กลืนทั้งคู่: เครื่องมือ Add Feature ลงจุดตอน "ปล่อย" เมาส์
                    # ถ้ากลืนแค่ตอนกด เส้นจะโดนลงจุดเกินมาหนึ่งจุด
                    self._swallow_release = True
                    return True

            elif (etype in (QEvent.MouseButtonRelease, QEvent.MouseButtonDblClick)
                    and event.button() == Qt.LeftButton
                    and self._swallow_release):
                if etype == QEvent.MouseButtonRelease:
                    self._swallow_release = False
                return True

        except Exception:  # noqa: BLE001 - ห้ามให้ event filter พังจนคลิกแผนที่ไม่ได้
            pass
        return False  # ส่ง event ต่อเสมอ ไม่กลืน


class LineToolWindow(QDialog):
    """หน้าต่างหลักของปลั๊กอิน — หน้าต่างลอยแบบ Windows ย้าย/ย่อ/ขยายได้"""

    def __init__(self, iface, parent=None):
        super().__init__(parent or iface.mainWindow())
        version = update_checker.read_local_version(PLUGIN_DIR)
        self.setWindowTitle("วาดเส้น & วัดระยะ  Version {}".format(version))
        self.setObjectName("LineDrawMeasureWindow")
        # หน้าต่างจริงของ Windows: มีปุ่มย่อ/ขยาย/ปิด และไม่บล็อกการใช้งาน QGIS
        self.setWindowFlags(Qt.Window)
        self.setModal(False)
        self.setSizeGripEnabled(True)

        self.iface = iface
        self.update_task = None     # งานตรวจสอบเวอร์ชัน
        self.install_task = None    # งานติดตั้งอัปเดต
        self._warned_units = False  # เตือนเรื่องหน่วยของช่องล็อกระยะแค่ครั้งเดียว
        self._cad_visible_before = None  # สถานะแถบ CAD ก่อนที่ปลั๊กอินจะไปซ่อน

        self.layers = LineToolLayers(iface, self)
        self.layers.layersChanged.connect(self._sync_layer_state)
        self.angle_ref = AngleReference(iface, self)
        self.angle_ref.referenceChanged.connect(self._sync_angle_ref)

        self._build_ui()
        self._restore_geometry()

    # ==================================================================
    # สร้าง UI
    # ==================================================================
    def _build_ui(self):
        self.setStyleSheet(DOCK_QSS)
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # ---- Banner บอกขั้นตอน ----
        self.banner = QLabel()
        self.banner.setWordWrap(True)
        self.banner.setTextFormat(Qt.RichText)
        root.addWidget(self.banner)

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
        self.spin_angle.setValue(90.0)   # ค่าเริ่มต้น: ตั้งฉาก
        self.spin_angle.setSuffix(" °")
        self.spin_angle.setFixedWidth(120)
        self.spin_angle.setToolTip(
            "องศาที่จะล็อกเมื่อกด Shift\n"
            "• ไม่มีแนวอ้างอิง = เทียบกับเส้นช่วงก่อนหน้า\n"
            "• มีแนวอ้างอิง = เทียบกับแนวที่ Ctrl+คลิกไว้ (90° = ตั้งฉากกับแนวนั้น)")
        # เปลี่ยนองศาแล้วข้อความ "จะล็อกที่อาซิมุทเท่าไหร่" ต้องอัปเดตตาม
        self.spin_angle.valueChanged.connect(lambda _v: self._sync_angle_ref())
        angle_row.addWidget(self.chk_shift_lock, 1)
        angle_row.addWidget(self.spin_angle)
        kv.addLayout(angle_row)
        root.addWidget(lock_group)

        # ---- กลุ่ม: แนวอ้างอิงมุม ----
        ref_group = QGroupBox("แนวอ้างอิงมุม (Ctrl + คลิกซ้าย 2 จุด)")
        rv = QVBoxLayout(ref_group)
        rv.setSpacing(8)

        self.chk_angle_ref = QCheckBox("เปิดใช้แนวอ้างอิงจาก Ctrl + คลิกซ้าย")
        self.chk_angle_ref.setChecked(True)
        self.chk_angle_ref.setToolTip(
            "ระหว่างวาดเส้น กด Ctrl ค้างแล้วคลิกซ้ายที่ Node ของแปลง หรือที่หมุด POINT\n"
            "2 ครั้ง → ได้แนวอ้างอิง (เส้นประม่วง) แล้วล็อกมุมจะอิงแนวนี้แทน\n"
            "Ctrl+คลิกซ้ายไม่ชนกับ shortcut ของ QGIS ในเครื่องมือวาด")
        self.chk_angle_ref.toggled.connect(self.on_toggle_angle_ref)
        rv.addWidget(self.chk_angle_ref)

        ref_row = QHBoxLayout()
        ref_row.setSpacing(8)
        ref_row.addWidget(QLabel("อาซิมุทแนว:"))
        self.edit_ref_azimuth = QLineEdit()
        self.edit_ref_azimuth.setReadOnly(True)
        self.edit_ref_azimuth.setAlignment(Qt.AlignCenter)
        self.edit_ref_azimuth.setToolTip("มุมของแนวอ้างอิง วัดตามเข็มนาฬิกาจากทิศเหนือ")
        self.btn_clear_ref = QPushButton("ล้างแนว")
        self.btn_clear_ref.setStyleSheet(BTN_GRAY)
        self.btn_clear_ref.setCursor(Qt.PointingHandCursor)
        self.btn_clear_ref.setFixedWidth(90)
        self.btn_clear_ref.clicked.connect(self.on_clear_angle_ref)
        ref_row.addWidget(self.edit_ref_azimuth, 1)
        ref_row.addWidget(self.btn_clear_ref)
        rv.addLayout(ref_row)

        self.lbl_lock_target = QLabel()
        self.lbl_lock_target.setWordWrap(True)
        self.lbl_lock_target.setStyleSheet(
            "font-size: 9pt; font-weight: normal; color: #6c757d;")
        rv.addWidget(self.lbl_lock_target)
        root.addWidget(ref_group)

        # ดักอินพุตบนแผนที่ — ปุ่มกดเข้า canvas ส่วนเมาส์เข้า viewport()
        self._canvas_filter = _CanvasFilter(self)
        self._filtered = []
        try:
            canvas = self.iface.mapCanvas()
            for target in (canvas, canvas.viewport()):
                target.installEventFilter(self._canvas_filter)
                self._filtered.append(target)
        except Exception:  # noqa: BLE001
            self._canvas_filter = None

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

        self.resize(400, 620)
        self._sync_layer_state()
        self._sync_angle_ref()

    # ==================================================================
    # Banner บอกขั้นตอน
    # ==================================================================
    def _set_banner(self, title, steps, active=False):
        """แสดงขั้นตอนการใช้งานเป็นข้อ ๆ"""
        items = "".join("<div>{}</div>".format(s) for s in steps)
        self.banner.setText("<b>{}</b>{}".format(title, items))
        self.banner.setStyleSheet(BANNER_ACTIVE if active else BANNER_INFO)

    def _banner_idle(self):
        self._set_banner("เริ่มต้นใช้งาน", [
            "1) กด <b>สร้าง Layer เส้น</b> เพื่อเตรียมชั้นข้อมูล",
            "2) กด <b>✎ วาดเส้น</b> แล้วคลิกลงจุดบนแผนที่",
        ])

    def _banner_layer_ready(self):
        self._set_banner("สร้าง Layer เส้นแล้ว ✔", [
            "เกิด 2 ชั้นบนแผนที่: <b>เส้นที่วาด (Line)</b> และ <b>ระยะเส้น (Label)</b>",
            "ขั้นถัดไป: กด <b>✎ วาดเส้น</b> เพื่อเริ่มลงจุด",
        ], active=True)

    def _banner_drawing(self):
        self._set_banner("กำลังวาดเส้น", [
            "• <b>คลิกซ้าย</b> = ลงจุด &nbsp;|&nbsp; <b>คลิกขวา</b> = จบเส้น",
            "• เคอร์เซอร์ดูดเข้าหามุม/หมุดให้อัตโนมัติ (snapping)",
            "• <b>Shift ค้าง</b> = ล็อกมุมตามองศาที่ตั้งไว้",
            "• <b>Ctrl + คลิกซ้าย 2 จุด</b> = จับแนวอ้างอิงมุม",
            "• ระยะแต่ละช่วงขึ้นเป็น label ให้เองหลังจบเส้น",
        ], active=True)

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
        self.btn_draw_line.setEnabled(True)

        if had_layer:
            self._warn("มี Layer เส้นอยู่แล้ว — วาดเส้นลงในชั้นเดิมได้เลย")
            self._banner_layer_ready()
            return

        self._banner_layer_ready()
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

        # ต้องซ่อนแถบ CAD หลัง trigger เสมอ เพราะ CAD ผูกกับ map tool ที่กำลังใช้งาน
        # — สลับเครื่องมือทีไร QGIS เด้งแถบขึ้นมาเองทุกที
        try:
            self._hide_cad_bar()
        except Exception:  # noqa: BLE001
            pass
        if self.chk_dist_lock.isChecked():
            self.apply_distance_lock(True)

        self._banner_drawing()

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
        """ปรับปุ่ม/Banner ให้ตรงกับว่ามีชั้นเส้นอยู่จริงหรือไม่"""
        has_layer = self.layers.has_layers()
        self.btn_draw_line.setEnabled(has_layer)
        if has_layer:
            self._banner_layer_ready()
        else:
            self._banner_idle()

    # ==================================================================
    # ปุ่มเช็ก: label ระยะ / จุด Node
    # ==================================================================
    def on_toggle_labels(self, checked):
        self.layers.set_labels_visible(checked)

    def on_toggle_nodes(self, checked):
        self.layers.set_nodes_visible(checked)

    # ==================================================================
    # แนวอ้างอิงมุม (Ctrl + คลิกซ้าย)
    # ==================================================================
    def handle_ctrl_click(self, screen_pos):
        """รับ Ctrl + คลิกซ้ายจากแผนที่ — คืน True ถ้ารับไว้แล้ว (ให้กลืน event)

        ดักเฉพาะตอนที่เครื่องมือปัจจุบันเป็นเครื่องมือ "วาด" (QgsMapToolCapture)
        เท่านั้น เพื่อไม่ไปแย่ง Ctrl+คลิก ของ Vertex Tool / Rotate / Offset Curve
        ซึ่ง QGIS จองไว้ใช้งานอยู่แล้ว
        """
        if not self.chk_angle_ref.isChecked():
            return False
        try:
            tool = self.iface.mapCanvas().mapTool()
        except Exception:  # noqa: BLE001
            return False
        if not isinstance(tool, QgsMapToolCapture):
            return False
        return self.angle_ref.handle_click(screen_pos)

    def on_toggle_angle_ref(self, checked):
        if not checked:
            self.angle_ref.clear()
        self._sync_angle_ref()

    def on_clear_angle_ref(self):
        self.angle_ref.clear()

    def _sync_angle_ref(self):
        """อัปเดตช่องอาซิมุท + คำอธิบายว่าการล็อกมุมจะอิงอะไร"""
        azimuth = self.angle_ref.azimuth()
        count = self.angle_ref.point_count()

        if azimuth is not None:
            self.edit_ref_azimuth.setText("{:.3f} °".format(azimuth))
            target = (azimuth + float(self.spin_angle.value())) % 360.0
            self.lbl_lock_target.setText(
                "กด Shift → ล็อกแนวที่อาซิมุท {:.3f}° "
                "(แนวอ้างอิง {:.3f}° + {:.1f}°)".format(
                    target, azimuth, self.spin_angle.value()))
        elif count == 1:
            self.edit_ref_azimuth.setText("รออีก 1 จุด")
            self.lbl_lock_target.setText(
                "Ctrl + คลิกซ้ายอีกครั้งเพื่อกำหนดจุดที่ 2 ของแนว")
        else:
            self.edit_ref_azimuth.setText("—")
            self.lbl_lock_target.setText(
                "ยังไม่มีแนวอ้างอิง — กด Shift จะล็อกมุมเทียบกับเส้นช่วงก่อนหน้าแทน")

    # ==================================================================
    # ล็อกระยะ / ล็อกมุม (ระบบดิจิไทซ์ขั้นสูงของ QGIS)
    # ==================================================================
    # "ระบบ" ดิจิไทซ์ขั้นสูง กับ "แถบ" ที่เห็นบนจอ เป็นคนละเรื่องกัน:
    #   • cadEnabled()  = ระบบล็อกมุม/ระยะทำงานอยู่ไหม  → จำเป็นต้องเปิด ไม่งั้น constraint ไม่มีผล
    #   • setVisible()  = แถบโผล่บนจอไหม               → เรื่องหน้าตาล้วน ๆ ไม่กระทบการล็อก
    # ปลั๊กอินนี้มีช่องล็อกของตัวเองแล้ว จึงเปิดแต่ระบบ และซ่อนแถบไว้ตลอด
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

    def _hide_cad_bar(self):
        """ซ่อน "แถบ" ดิจิไทซ์ขั้นสูงบนจอ (ไม่แตะสถานะเปิด/ปิดของระบบ)

        จำสถานะเดิมไว้คืนให้ตอน unload ปลั๊กอิน
        """
        cad = self.iface.cadDockWidget()
        if cad is None:
            return False
        if self._cad_visible_before is None:
            self._cad_visible_before = cad.isVisible()
        cad.setVisible(False)
        return True

    def _restore_cad_bar(self):
        """คืนสถานะแถบ CAD ให้เหมือนก่อนเปิดปลั๊กอิน (เรียกตอน unload)"""
        if self._cad_visible_before is None:
            return
        cad = self.iface.cadDockWidget()
        if cad is not None:
            cad.setVisible(self._cad_visible_before)
        self._cad_visible_before = None

    def _ensure_cad_enabled(self):
        """เปิดระบบ CAD ถ้ายังปิดอยู่ — constraint ไม่มีผลเลยถ้าระบบไม่เปิด

        เปิดแล้วซ่อนแถบทันที เพราะการเปิดระบบทำให้ QGIS เด้งแถบขึ้นมาเอง
        """
        cad = self.iface.cadDockWidget()
        if cad is None:
            return None
        if not cad.cadEnabled():
            self._set_cad_enabled(True)
        self._hide_cad_bar()
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

        • มีแนวอ้างอิง (Ctrl+คลิก 2 จุด) → ล็อกเป็นมุม "สัมบูรณ์"
          = อาซิมุทของแนวอ้างอิง + องศาที่ตั้งไว้
        • ไม่มีแนวอ้างอิง → ล็อกเป็นมุม "สัมพัทธ์" กับเส้นช่วงก่อนหน้า (พฤติกรรมเดิม)
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
            azimuth = self.angle_ref.azimuth() if self.chk_angle_ref.isChecked() else None
            if azimuth is None:
                constraint.setRelative(True)
                constraint.setValue(float(self.spin_angle.value()), True)
            else:
                # แปลงอาซิมุท (ตามเข็ม จากทิศเหนือ) → มุมของ CAD ที่ QGIS ใช้
                # ซึ่งวัดทวนเข็มจากแกน +X (ทิศตะวันออก)
                target = (azimuth + float(self.spin_angle.value())) % 360.0
                constraint.setRelative(False)
                constraint.setValue((90.0 - target) % 360.0, True)
            mode = _lock_mode("HardLock")
        else:
            mode = _lock_mode("NoLock")
        if mode is not None:
            constraint.setLockMode(mode)

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
    # จำตำแหน่ง/ขนาดหน้าต่าง
    # ==================================================================
    def _restore_geometry(self):
        try:
            saved = QSettings().value(SETTINGS_GEOMETRY)
            if saved:
                self.restoreGeometry(saved)
        except Exception:  # noqa: BLE001 - ค่าที่เก็บไว้เสีย ก็เปิดขนาดเริ่มต้นไป
            pass

    def _save_geometry(self):
        try:
            QSettings().setValue(SETTINGS_GEOMETRY, self.saveGeometry())
        except Exception:  # noqa: BLE001
            pass

    def closeEvent(self, event):  # noqa: N802 (ชื่อกำหนดโดย Qt)
        self._save_geometry()
        super().closeEvent(event)

    # ==================================================================
    # cleanup (เรียกตอน unload ปลั๊กอิน)
    # ==================================================================
    def cleanup(self):
        self._save_geometry()

        # ถอดตัวดักอินพุตออกจาก canvas ไม่งั้นค้างหลัง unload ปลั๊กอิน
        if getattr(self, "_canvas_filter", None) is not None:
            for target in getattr(self, "_filtered", []):
                try:
                    target.removeEventFilter(self._canvas_filter)
                except Exception:  # noqa: BLE001
                    pass
            self._filtered = []
            self._canvas_filter = None

        # คืนแถบ CAD ให้เหมือนเดิม — ปลั๊กอินไปซ่อนไว้ ไม่ควรทิ้งค้างไว้แบบนั้น
        try:
            self._restore_cad_bar()
        except Exception:  # noqa: BLE001
            pass

        for helper in (getattr(self, "angle_ref", None), getattr(self, "layers", None)):
            if helper is not None:
                try:
                    helper.cleanup()
                except Exception:  # noqa: BLE001
                    pass

        for task in (self.update_task, self.install_task):
            if task is not None:
                try:
                    task.cancel()
                except Exception:  # noqa: BLE001
                    pass
