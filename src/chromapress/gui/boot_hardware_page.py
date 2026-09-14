from __future__ import annotations

import posixpath

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QGroupBox, QFormLayout, QTreeWidget,
    QTreeWidgetItem, QComboBox, QSpinBox, QLineEdit, QPushButton, QHBoxLayout, QCheckBox,
    QSplitter, QMessageBox,
)

from chromapress.models import ChangeItem, ChangeKind


class BootHardwarePage(QWidget):
    """Part 3 source inspection plus staging-only boot configuration planning.

    Alpha 34 keeps the selected ISO read-only. It can create reviewed boot,
    kernel/initramfs and manifest-backed firmware/driver plans for a later
    apply/build step; no boot file, rootfs or source-image byte is modified here.
    """

    stage_requested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        title = QLabel("Boot & Hardware")
        title.setObjectName("pageTitle")
        # Keep the safety contract available without spending permanent vertical
        # space on a second explanatory header. The footer repeats the read-only
        # state while a tooltip keeps the full wording directly on the page title.
        self.safety_text = (
            "SOURCE READ-ONLY — Alpha 34 can stage boot, boot-metadata, kernel/initramfs, manifest-backed hardware, SquashFS/rootfs, immutable-runtime, controlled-persistence and runtime-integration plans, "
            "but does not modify boot records, kernels, initramfs, firmware, drivers, rootfs layers or the selected ISO."
        )
        title.setToolTip(self.safety_text)
        layout.addWidget(title)

        settings_widget = QWidget()
        settings_layout = QVBoxLayout(settings_widget)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(6)

        boot_box = QGroupBox("Boot architecture")
        boot_form = QFormLayout(boot_box)
        self.boot_fields: dict[str, QLabel] = {}
        for key, label in [
            ("modes", "Boot modes"),
            ("el_torito", "El Torito"),
            ("hybrid", "Hybrid/system area"),
            ("loaders", "Bootloader(s)"),
            ("catalog", "Boot catalog"),
            ("volume", "Volume ID"),
        ]:
            value = QLabel("—")
            value.setWordWrap(True)
            value.setTextInteractionFlags(value.textInteractionFlags() | Qt.TextInteractionFlag.TextSelectableByMouse)
            boot_form.addRow(label + ":", value)
            self.boot_fields[key] = value
        settings_layout.addWidget(boot_box)

        config_box = QGroupBox("Boot configuration evidence")
        config_form = QFormLayout(config_box)
        self.config_fields: dict[str, QLabel] = {}
        for key, label in [
            ("defaults", "Declared default(s)"),
            ("timeouts", "Declared timeout(s)"),
        ]:
            value = QLabel("—")
            value.setWordWrap(True)
            value.setTextInteractionFlags(value.textInteractionFlags() | Qt.TextInteractionFlag.TextSelectableByMouse)
            config_form.addRow(label + ":", value)
            self.config_fields[key] = value
        settings_layout.addWidget(config_box)

        plan_box = QGroupBox("Boot configuration plan — staged only")
        plan_layout = QFormLayout(plan_box)
        plan_layout.setVerticalSpacing(5)
        plan_layout.setContentsMargins(10, 10, 10, 8)
        self.default_combo = QComboBox()
        self.default_combo.addItem("Preserve current default", None)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(-1, 600)
        self.timeout_spin.setSpecialValueText("Preserve")
        self.timeout_spin.setValue(-1)
        self.timeout_spin.setSuffix(" s")
        self.kernel_args_edit = QLineEdit()
        self.kernel_args_edit.setPlaceholderText("Optional arguments to append; existing arguments are preserved")
        plan_layout.addRow("Default boot entry:", self.default_combo)
        plan_layout.addRow("Boot timeout:", self.timeout_spin)
        plan_layout.addRow("Append kernel arguments:", self.kernel_args_edit)
        controls_widget = QWidget()
        controls = QHBoxLayout(controls_widget)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(6)
        self.stage_btn = QPushButton("Stage boot plan")
        self.reset_btn = QPushButton("Reset")
        self.stage_btn.setMinimumSize(120, 30)
        self.reset_btn.setMinimumSize(70, 30)
        self.plan_status = QLabel("Analyze a source ISO first.")
        self.plan_status.setWordWrap(False)
        controls.addWidget(self.stage_btn)
        controls.addWidget(self.reset_btn)
        controls.addSpacing(8)
        controls.addWidget(self.plan_status, 1)
        plan_layout.addRow("", controls_widget)
        self.stage_btn.clicked.connect(self._stage_plan)
        self.reset_btn.clicked.connect(self._reset_plan)
        self.stage_btn.setEnabled(False)
        settings_layout.addWidget(plan_box)

        metadata_box = QGroupBox("Boot identity / metadata plan — staged only")
        metadata_layout = QFormLayout(metadata_box)
        metadata_layout.setVerticalSpacing(5)
        metadata_layout.setContentsMargins(10, 10, 10, 8)
        self.metadata_entry_combo = QComboBox()
        self.metadata_entry_combo.addItem("Select detected boot entry", None)
        self.metadata_label_edit = QLineEdit()
        self.metadata_label_edit.setPlaceholderText("Optional replacement label for the selected boot entry")
        self.metadata_order_combo = QComboBox()
        self.metadata_order_combo.addItem("Preserve detected boot order", "preserve")
        self.metadata_order_combo.addItem("Move selected boot entry to first position", "move_selected_first")
        self.metadata_volume_edit = QLineEdit()
        self.metadata_volume_edit.setPlaceholderText("Leave blank to preserve detected Volume ID")
        self.metadata_safety_value = QLabel("Preserve El Torito/hybrid boot records and all unrelated boot entries")
        self.metadata_safety_value.setWordWrap(True)
        metadata_layout.addRow("Boot entry:", self.metadata_entry_combo)
        metadata_layout.addRow("Entry label:", self.metadata_label_edit)
        metadata_layout.addRow("Boot order:", self.metadata_order_combo)
        metadata_layout.addRow("Volume ID:", self.metadata_volume_edit)
        metadata_layout.addRow("Safety:", self.metadata_safety_value)
        metadata_controls_widget = QWidget()
        metadata_controls = QHBoxLayout(metadata_controls_widget)
        metadata_controls.setContentsMargins(0, 0, 0, 0)
        metadata_controls.setSpacing(6)
        self.stage_metadata_btn = QPushButton("Stage metadata plan")
        self.reset_metadata_btn = QPushButton("Reset")
        self.stage_metadata_btn.setMinimumSize(145, 30)
        self.reset_metadata_btn.setMinimumSize(70, 30)
        self.metadata_plan_status = QLabel("Analyze a source ISO first.")
        self.metadata_plan_status.setWordWrap(False)
        metadata_controls.addWidget(self.stage_metadata_btn)
        metadata_controls.addWidget(self.reset_metadata_btn)
        metadata_controls.addSpacing(8)
        metadata_controls.addWidget(self.metadata_plan_status, 1)
        metadata_layout.addRow("", metadata_controls_widget)
        self.stage_metadata_btn.clicked.connect(self._stage_metadata_plan)
        self.reset_metadata_btn.clicked.connect(self._reset_metadata_plan)
        self.stage_metadata_btn.setEnabled(False)
        self.reset_metadata_btn.setEnabled(False)
        settings_layout.addWidget(metadata_box)

        kernel_box = QGroupBox("Kernel / initramfs plan — staged only")
        kernel_layout = QFormLayout(kernel_box)
        kernel_layout.setVerticalSpacing(5)
        kernel_layout.setContentsMargins(10, 10, 10, 8)
        self.kernel_images_value = QLabel("—")
        self.initramfs_images_value = QLabel("—")
        self.initramfs_mechanism_value = QLabel("Not detected")
        self.kernel_safety_value = QLabel("Protect last viable kernel — mandatory")
        for value in (self.kernel_images_value, self.initramfs_images_value, self.initramfs_mechanism_value, self.kernel_safety_value):
            value.setWordWrap(True)
        kernel_layout.addRow("Detected kernel images:", self.kernel_images_value)
        kernel_layout.addRow("Detected initramfs images:", self.initramfs_images_value)
        kernel_layout.addRow("Expected native mechanism:", self.initramfs_mechanism_value)
        kernel_layout.addRow("Kernel safety:", self.kernel_safety_value)
        self.regenerate_initramfs = QCheckBox("Regenerate initramfs during a later verified apply")
        kernel_layout.addRow("Requested operation:", self.regenerate_initramfs)
        kernel_controls_widget = QWidget()
        kernel_controls = QHBoxLayout(kernel_controls_widget)
        kernel_controls.setContentsMargins(0, 0, 0, 0)
        kernel_controls.setSpacing(6)
        self.stage_kernel_btn = QPushButton("Stage kernel plan")
        self.reset_kernel_btn = QPushButton("Reset")
        self.stage_kernel_btn.setMinimumSize(130, 30)
        self.reset_kernel_btn.setMinimumSize(70, 30)
        self.kernel_plan_status = QLabel("Analyze a supported source ISO first.")
        self.kernel_plan_status.setWordWrap(False)
        kernel_controls.addWidget(self.stage_kernel_btn)
        kernel_controls.addWidget(self.reset_kernel_btn)
        kernel_controls.addSpacing(8)
        kernel_controls.addWidget(self.kernel_plan_status, 1)
        kernel_layout.addRow("", kernel_controls_widget)
        self.stage_kernel_btn.clicked.connect(self._stage_kernel_plan)
        self.reset_kernel_btn.clicked.connect(self._reset_kernel_plan)
        self.stage_kernel_btn.setEnabled(False)
        self.reset_kernel_btn.setEnabled(False)
        settings_layout.addWidget(kernel_box)

        hardware_box = QGroupBox("Firmware / driver plan — staged only")
        hardware_layout = QFormLayout(hardware_box)
        hardware_layout.setVerticalSpacing(5)
        hardware_layout.setContentsMargins(10, 10, 10, 8)
        self.hardware_evidence_value = QLabel("—")
        self.hardware_package_combo = QComboBox()
        self.hardware_package_combo.addItem("Select manifest-backed package", None)
        self.hardware_action_combo = QComboBox()
        self.hardware_action_combo.addItem("Preserve current package", None)
        self.hardware_action_combo.addItem("Re-resolve from target repositories during later verified apply", "re_resolve")
        self.hardware_initramfs_value = QLabel("—")
        hardware_layout.addRow("Manifest-backed evidence:", self.hardware_evidence_value)
        hardware_layout.addRow("Hardware package:", self.hardware_package_combo)
        hardware_layout.addRow("Requested operation:", self.hardware_action_combo)
        hardware_layout.addRow("Initramfs safety:", self.hardware_initramfs_value)
        hardware_controls_widget = QWidget()
        hardware_controls = QHBoxLayout(hardware_controls_widget)
        hardware_controls.setContentsMargins(0, 0, 0, 0)
        hardware_controls.setSpacing(6)
        self.stage_hardware_btn = QPushButton("Stage hardware plan")
        self.reset_hardware_btn = QPushButton("Reset")
        self.stage_hardware_btn.setMinimumSize(140, 30)
        self.reset_hardware_btn.setMinimumSize(70, 30)
        self.hardware_plan_status = QLabel("Analyze a supported source ISO first.")
        self.hardware_plan_status.setWordWrap(False)
        hardware_controls.addWidget(self.stage_hardware_btn)
        hardware_controls.addWidget(self.reset_hardware_btn)
        hardware_controls.addSpacing(8)
        hardware_controls.addWidget(self.hardware_plan_status, 1)
        hardware_layout.addRow("", hardware_controls_widget)
        self.stage_hardware_btn.clicked.connect(self._stage_hardware_plan)
        self.reset_hardware_btn.clicked.connect(self._reset_hardware_plan)
        self.stage_hardware_btn.setEnabled(False)
        self.reset_hardware_btn.setEnabled(False)
        settings_layout.addWidget(hardware_box)

        rootfs_box = QGroupBox("Root filesystem / SquashFS plan — staged only")
        rootfs_layout = QFormLayout(rootfs_box)
        rootfs_layout.setVerticalSpacing(5)
        rootfs_layout.setContentsMargins(10, 10, 10, 8)
        self.rootfs_evidence_value = QLabel("—")
        self.rootfs_layer_combo = QComboBox()
        self.rootfs_layer_combo.addItem("Select detected SquashFS layer", None)
        self.rootfs_current_compression_value = QLabel("—")
        self.rootfs_action_combo = QComboBox()
        self.rootfs_action_combo.addItem("Preserve source layer", None)
        self.rootfs_action_combo.addItem("Repack selected layer during later verified apply", "repack")
        self.rootfs_target_compression_combo = QComboBox()
        self.rootfs_target_compression_combo.addItem("Preserve detected compression", "preserve")
        for compression in ("xz", "zstd", "gzip", "lz4"):
            self.rootfs_target_compression_combo.addItem(compression, compression)
        rootfs_layout.addRow("Detected layers:", self.rootfs_evidence_value)
        rootfs_layout.addRow("SquashFS layer:", self.rootfs_layer_combo)
        rootfs_layout.addRow("Detected compression:", self.rootfs_current_compression_value)
        rootfs_layout.addRow("Requested operation:", self.rootfs_action_combo)
        rootfs_layout.addRow("Target compression:", self.rootfs_target_compression_combo)
        rootfs_controls_widget = QWidget()
        rootfs_controls = QHBoxLayout(rootfs_controls_widget)
        rootfs_controls.setContentsMargins(0, 0, 0, 0)
        rootfs_controls.setSpacing(6)
        self.stage_rootfs_btn = QPushButton("Stage rootfs plan")
        self.reset_rootfs_btn = QPushButton("Reset")
        self.stage_rootfs_btn.setMinimumSize(125, 30)
        self.reset_rootfs_btn.setMinimumSize(70, 30)
        self.rootfs_plan_status = QLabel("Analyze a supported source ISO first.")
        self.rootfs_plan_status.setWordWrap(False)
        rootfs_controls.addWidget(self.stage_rootfs_btn)
        rootfs_controls.addWidget(self.reset_rootfs_btn)
        rootfs_controls.addSpacing(8)
        rootfs_controls.addWidget(self.rootfs_plan_status, 1)
        rootfs_layout.addRow("", rootfs_controls_widget)
        self.rootfs_layer_combo.currentIndexChanged.connect(self._update_rootfs_selection)
        self.stage_rootfs_btn.clicked.connect(self._stage_rootfs_plan)
        self.reset_rootfs_btn.clicked.connect(self._reset_rootfs_plan)
        self.stage_rootfs_btn.setEnabled(False)
        self.reset_rootfs_btn.setEnabled(False)
        settings_layout.addWidget(rootfs_box)

        immutable_box = QGroupBox("Immutable / volatile runtime plan — staged only")
        immutable_layout = QFormLayout(immutable_box)
        immutable_layout.setVerticalSpacing(5)
        immutable_layout.setContentsMargins(10, 10, 10, 8)
        self.immutable_layer_combo = QComboBox()
        self.immutable_layer_combo.addItem("Select detected SquashFS base layer", None)
        self.immutable_mode_combo = QComboBox()
        self.immutable_mode_combo.addItem("Preserve current runtime model", None)
        self.immutable_mode_combo.addItem("Read-only rootfs + volatile OverlayFS", "volatile_overlay")
        self.immutable_writable_value = QLabel("tmpfs upper/work layer")
        self.immutable_survival_value = QLabel("Volatile — runtime changes do not survive reboot")
        self.immutable_integration_value = QLabel("—")
        immutable_layout.addRow("Base rootfs layer:", self.immutable_layer_combo)
        immutable_layout.addRow("Runtime model:", self.immutable_mode_combo)
        immutable_layout.addRow("Writable runtime:", self.immutable_writable_value)
        immutable_layout.addRow("Reboot persistence:", self.immutable_survival_value)
        immutable_layout.addRow("Required integration:", self.immutable_integration_value)
        immutable_controls_widget = QWidget()
        immutable_controls = QHBoxLayout(immutable_controls_widget)
        immutable_controls.setContentsMargins(0, 0, 0, 0)
        immutable_controls.setSpacing(6)
        self.stage_immutable_btn = QPushButton("Stage immutable plan")
        self.reset_immutable_btn = QPushButton("Reset")
        self.stage_immutable_btn.setMinimumSize(140, 30)
        self.reset_immutable_btn.setMinimumSize(70, 30)
        self.immutable_plan_status = QLabel("Analyze a supported source ISO first.")
        self.immutable_plan_status.setWordWrap(False)
        immutable_controls.addWidget(self.stage_immutable_btn)
        immutable_controls.addWidget(self.reset_immutable_btn)
        immutable_controls.addSpacing(8)
        immutable_controls.addWidget(self.immutable_plan_status, 1)
        immutable_layout.addRow("", immutable_controls_widget)
        self.stage_immutable_btn.clicked.connect(self._stage_immutable_plan)
        self.reset_immutable_btn.clicked.connect(self._reset_immutable_plan)
        self.stage_immutable_btn.setEnabled(False)
        self.reset_immutable_btn.setEnabled(False)
        settings_layout.addWidget(immutable_box)

        persistence_box = QGroupBox("Controlled persistence plan — staged only")
        persistence_layout = QFormLayout(persistence_box)
        persistence_layout.setVerticalSpacing(5)
        persistence_layout.setContentsMargins(10, 10, 10, 8)
        self.persistence_layer_combo = QComboBox()
        self.persistence_layer_combo.addItem("Select detected SquashFS base layer", None)
        self.persistence_directories_edit = QLineEdit()
        self.persistence_directories_edit.setPlaceholderText("Absolute directories separated by ';' — e.g. /var/lib/app;/home/kiosk/data")
        self.persistence_storage_combo = QComboBox()
        self.persistence_storage_combo.addItem("Select persistent backing storage", None)
        self.persistence_storage_combo.addItem("Provision dedicated target-system volume during later verified apply", "dedicated_volume")
        self.persistence_size_spin = QSpinBox()
        self.persistence_size_spin.setRange(256, 1048576)
        self.persistence_size_spin.setValue(4096)
        self.persistence_size_spin.setSuffix(" MiB")
        self.persistence_filesystem_combo = QComboBox()
        self.persistence_filesystem_combo.addItem("ext4", "ext4")
        self.persistence_label_edit = QLineEdit("CHROMAPERSIST")
        self.persistence_label_edit.setMaxLength(16)
        self.persistence_survival_value = QLabel("Only listed directories survive reboot; all other runtime changes remain volatile")
        self.persistence_integration_value = QLabel("—")
        persistence_layout.addRow("Base rootfs layer:", self.persistence_layer_combo)
        persistence_layout.addRow("Persistent directories:", self.persistence_directories_edit)
        persistence_layout.addRow("Backing storage:", self.persistence_storage_combo)
        persistence_layout.addRow("Volume size:", self.persistence_size_spin)
        persistence_layout.addRow("Filesystem:", self.persistence_filesystem_combo)
        persistence_layout.addRow("Volume label:", self.persistence_label_edit)
        persistence_layout.addRow("Reboot persistence:", self.persistence_survival_value)
        persistence_layout.addRow("Required integration:", self.persistence_integration_value)
        persistence_controls_widget = QWidget()
        persistence_controls = QHBoxLayout(persistence_controls_widget)
        persistence_controls.setContentsMargins(0, 0, 0, 0)
        persistence_controls.setSpacing(6)
        self.stage_persistence_btn = QPushButton("Stage persistence plan")
        self.reset_persistence_btn = QPushButton("Reset")
        self.stage_persistence_btn.setMinimumSize(145, 30)
        self.reset_persistence_btn.setMinimumSize(70, 30)
        self.persistence_plan_status = QLabel("Analyze a supported source ISO first.")
        self.persistence_plan_status.setWordWrap(False)
        persistence_controls.addWidget(self.stage_persistence_btn)
        persistence_controls.addWidget(self.reset_persistence_btn)
        persistence_controls.addSpacing(8)
        persistence_controls.addWidget(self.persistence_plan_status, 1)
        persistence_layout.addRow("", persistence_controls_widget)
        self.stage_persistence_btn.clicked.connect(self._stage_persistence_plan)
        self.reset_persistence_btn.clicked.connect(self._reset_persistence_plan)
        self.stage_persistence_btn.setEnabled(False)
        self.reset_persistence_btn.setEnabled(False)
        settings_layout.addWidget(persistence_box)

        integration_box = QGroupBox("Runtime integration verification — staged only")
        integration_layout = QFormLayout(integration_box)
        integration_layout.setVerticalSpacing(5)
        integration_layout.setContentsMargins(10, 10, 10, 8)
        self.integration_layer_combo = QComboBox()
        self.integration_layer_combo.addItem("Select detected SquashFS base layer", None)
        self.integration_target_combo = QComboBox()
        self.integration_target_combo.addItem("Select runtime integration target", None)
        self.integration_target_combo.addItem("Volatile OverlayFS runtime", "volatile_overlay")
        self.integration_target_combo.addItem("Controlled persistence runtime", "controlled_persistence")
        self.integration_evidence_value = QLabel("—")
        self.integration_boot_value = QLabel("Preserve detected boot structure; re-verify explicit boot configuration")
        self.integration_initramfs_value = QLabel("—")
        self.integration_mount_value = QLabel("Select an integration target")
        for value in (self.integration_evidence_value, self.integration_boot_value, self.integration_initramfs_value, self.integration_mount_value):
            value.setWordWrap(True)
        integration_layout.addRow("Base rootfs layer:", self.integration_layer_combo)
        integration_layout.addRow("Integration target:", self.integration_target_combo)
        integration_layout.addRow("Bound source evidence:", self.integration_evidence_value)
        integration_layout.addRow("Boot integration:", self.integration_boot_value)
        integration_layout.addRow("Initramfs integration:", self.integration_initramfs_value)
        integration_layout.addRow("Mount integration:", self.integration_mount_value)
        integration_controls_widget = QWidget()
        integration_controls = QHBoxLayout(integration_controls_widget)
        integration_controls.setContentsMargins(0, 0, 0, 0)
        integration_controls.setSpacing(6)
        self.stage_integration_btn = QPushButton("Stage integration plan")
        self.reset_integration_btn = QPushButton("Reset")
        self.stage_integration_btn.setMinimumSize(145, 30)
        self.reset_integration_btn.setMinimumSize(70, 30)
        self.integration_plan_status = QLabel("Analyze a supported source ISO first.")
        self.integration_plan_status.setWordWrap(False)
        integration_controls.addWidget(self.stage_integration_btn)
        integration_controls.addWidget(self.reset_integration_btn)
        integration_controls.addSpacing(8)
        integration_controls.addWidget(self.integration_plan_status, 1)
        integration_layout.addRow("", integration_controls_widget)
        self.integration_target_combo.currentIndexChanged.connect(self._update_integration_target)
        self.stage_integration_btn.clicked.connect(self._stage_integration_plan)
        self.reset_integration_btn.clicked.connect(self._reset_integration_plan)
        self.stage_integration_btn.setEnabled(False)
        self.reset_integration_btn.setEnabled(False)
        settings_layout.addWidget(integration_box)

        self.structure = QTreeWidget()
        self.structure.setHeaderLabels(["Detected source structure", "Details"])
        self.structure.setAlternatingRowColors(True)
        self.structure.setColumnWidth(0, 330)
        self.structure.setMinimumHeight(150)

        self.footer = QLabel("No source analyzed yet.")
        self.footer.setWordWrap(False)

        structure_widget = QWidget()
        structure_layout = QVBoxLayout(structure_widget)
        structure_layout.setContentsMargins(0, 0, 0, 0)
        structure_layout.setSpacing(4)
        structure_layout.addWidget(self.structure, 1)
        structure_layout.addWidget(self.footer)

        self.section_splitter = QSplitter(Qt.Orientation.Vertical)
        self.section_splitter.setChildrenCollapsible(False)
        self.section_splitter.addWidget(settings_widget)
        self.section_splitter.addWidget(structure_widget)
        self.section_splitter.setStretchFactor(0, 0)
        self.section_splitter.setStretchFactor(1, 1)
        self.section_splitter.setSizes([500, 320])
        layout.addWidget(self.section_splitter, 1)

        self._analysis: dict = {}
        self.set_analysis({})

    @staticmethod
    def _yes_no(value: object) -> str:
        return "Detected" if bool(value) else "Not detected"

    @staticmethod
    def _join(values: object, empty: str = "Not detected") -> str:
        if isinstance(values, (list, tuple)):
            cleaned = [str(x) for x in values if str(x).strip()]
            return ", ".join(cleaned) if cleaned else empty
        return str(values).strip() if values else empty

    @staticmethod
    def _parse_persistent_directories(value: str) -> list[str]:
        blocked = ("/proc", "/sys", "/dev", "/run", "/boot", "/efi")
        result: list[str] = []
        for raw in str(value or "").replace(",", ";").split(";"):
            item = raw.strip()
            if not item:
                continue
            if any(ch in item for ch in ("\r", "\n", "\x00")) or not item.startswith("/"):
                raise ValueError("Persistent directories must be absolute Linux paths without control characters.")
            parts = [part for part in item.split("/") if part]
            if ".." in parts:
                raise ValueError("Persistent directories may not contain '..' path traversal.")
            normalized = posixpath.normpath(item)
            if normalized == "/" or any(normalized == prefix or normalized.startswith(prefix + "/") for prefix in blocked):
                raise ValueError("Root, boot and pseudo-filesystem paths cannot be staged as persistent directories.")
            if normalized not in result:
                result.append(normalized)
        return result

    @staticmethod
    def _root(tree: QTreeWidget, name: str, detail: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem(tree, [name, detail])
        font = item.font(0)
        font.setBold(True)
        item.setFont(0, font)
        return item

    def _reset_plan(self) -> None:
        self.default_combo.setCurrentIndex(0)
        self.timeout_spin.setValue(-1)
        self.kernel_args_edit.clear()
        if self._analysis.get("boot_config_files"):
            self.plan_status.setText("Ready — no boot changes staged.")
        else:
            self.plan_status.setText("Analyze a source ISO first.")

    def _stage_plan(self) -> None:
        if not self._analysis.get("boot_config_files"):
            self.plan_status.setText("No explicit boot configuration file is available; staging is blocked.")
            return

        default_entry = self.default_combo.currentData()
        timeout = self.timeout_spin.value()
        timeout_value = None if timeout < 0 else timeout
        kernel_args = self.kernel_args_edit.text().strip()

        if not default_entry and timeout_value is None and not kernel_args:
            self.plan_status.setText("Choose at least one boot setting before staging.")
            return
        if any(ch in kernel_args for ch in ("\r", "\n", "\x00")) or len(kernel_args) > 512:
            self.plan_status.setText("Kernel arguments contain unsafe control characters or exceed 512 characters.")
            return

        payload = {
            "config_type": "boot",
            "source_sha256": str(self._analysis.get("sha256") or ""),
            "boot_config_files": list(self._analysis.get("boot_config_files") or []),
            "default_entry": dict(default_entry) if isinstance(default_entry, dict) else None,
            "timeout_seconds": timeout_value,
            "kernel_args_append": kernel_args,
            "preservation_policy": "preserve-unrelated",
            "stage_only": True,
        }
        selected = []
        if isinstance(default_entry, dict):
            selected.append(f"default: {default_entry.get('title') or default_entry.get('id') or 'entry'}")
        if timeout_value is not None:
            selected.append(f"timeout: {timeout_value} s")
        if kernel_args:
            selected.append(f"append args: {kernel_args}")
        detail = "; ".join(selected) + ". Source ISO remains read-only until a later verified apply/build gate."
        change = ChangeItem("Boot configuration plan", ChangeKind.CONFIG, detail, payload)
        self.stage_requested.emit(change)
        self.plan_status.setText("Staged — review/Test in Changes.")

    def _reset_metadata_plan(self) -> None:
        self.metadata_entry_combo.setCurrentIndex(0)
        self.metadata_label_edit.clear()
        self.metadata_order_combo.setCurrentIndex(0)
        self.metadata_volume_edit.clear()
        if self.stage_metadata_btn.isEnabled():
            self.metadata_plan_status.setText("Ready — no boot metadata changes staged.")
        else:
            self.metadata_plan_status.setText("Analyze a source ISO first.")

    @staticmethod
    def _safe_printable_ascii(value: str, maximum: int) -> bool:
        return bool(value) and len(value) <= maximum and all(32 <= ord(ch) <= 126 for ch in value)

    def _stage_metadata_plan(self) -> None:
        if not self.stage_metadata_btn.isEnabled():
            message = "BLOCKED — explicit boot configuration/entry evidence is incomplete. Nothing has been staged."
            self.metadata_plan_status.setText(message)
            QMessageBox.information(self, "Boot metadata plan blocked", message)
            return

        selected_entry = self.metadata_entry_combo.currentData()
        new_label = self.metadata_label_edit.text().strip()
        order_operation = str(self.metadata_order_combo.currentData() or "preserve")
        volume_id_new = self.metadata_volume_edit.text().strip()

        entry_change_requested = bool(new_label) or order_operation == "move_selected_first"
        if entry_change_requested and not isinstance(selected_entry, dict):
            message = "Select a detected boot entry before changing its label or boot order."
            self.metadata_plan_status.setText(message)
            self.metadata_entry_combo.setFocus()
            QMessageBox.information(self, "Boot metadata plan not staged", message)
            return
        if new_label and not self._safe_printable_ascii(new_label, 80):
            message = "Boot entry label must contain 1–80 printable ASCII characters."
            self.metadata_plan_status.setText(message)
            self.metadata_label_edit.setFocus()
            QMessageBox.information(self, "Boot metadata plan not staged", message)
            return
        if volume_id_new and not self._safe_printable_ascii(volume_id_new, 32):
            message = "Volume ID must contain 1–32 printable ASCII characters."
            self.metadata_plan_status.setText(message)
            self.metadata_volume_edit.setFocus()
            QMessageBox.information(self, "Boot metadata plan not staged", message)
            return
        if not entry_change_requested and not volume_id_new:
            message = "Choose an entry label/order change or enter a new Volume ID before staging."
            self.metadata_plan_status.setText(message)
            QMessageBox.information(self, "Boot metadata plan not staged", message)
            return

        entries = [dict(item) for item in list(self._analysis.get("boot_entries") or []) if isinstance(item, dict)]
        payload = {
            "config_type": "boot_metadata",
            "source_sha256": str(self._analysis.get("sha256") or ""),
            "boot_config_files": [str(x) for x in list(self._analysis.get("boot_config_files") or []) if str(x).strip()],
            "boot_entries": entries,
            "selected_entry": dict(selected_entry) if isinstance(selected_entry, dict) else None,
            "entry_label_new": new_label,
            "boot_order_operation": order_operation,
            "volume_id_current": str(self._analysis.get("volume_id") or ""),
            "volume_id_new": volume_id_new,
            "boot_catalog": str(self._analysis.get("boot_catalog") or ""),
            "el_torito_detected": bool(self._analysis.get("el_torito_boot")),
            "hybrid_detected": bool(self._analysis.get("hybrid_boot")),
            "preserve_boot_records": True,
            "preserve_unselected_entries": True,
            "require_boot_catalog_reverification": True,
            "source_read_only": True,
            "preserve_unrelated": True,
            "stage_only": True,
        }
        requested = []
        if new_label:
            requested.append(f"rename entry to '{new_label}'")
        if order_operation == "move_selected_first":
            requested.append("move selected entry first")
        if volume_id_new:
            requested.append(f"Volume ID '{volume_id_new}'")
        detail = "; ".join(requested) + ". El Torito/hybrid records and unrelated entries are preserved; source ISO remains read-only."
        change = ChangeItem("Boot identity / metadata plan", ChangeKind.CONFIG, detail, payload)
        self.stage_requested.emit(change)
        self.metadata_plan_status.setText("Staged — review/Test in Changes.")
        QMessageBox.information(
            self,
            "STAGED: Boot identity / metadata plan",
            "The boot identity/metadata plan is staging-only. Review and Test it in Changes before any later apply.",
        )

    def _reset_kernel_plan(self) -> None:
        self.regenerate_initramfs.setChecked(False)
        if self.stage_kernel_btn.isEnabled():
            self.kernel_plan_status.setText("Ready — no kernel/initramfs changes staged.")
        else:
            self.kernel_plan_status.setText("Analyze a supported source ISO first.")

    def _stage_kernel_plan(self) -> None:
        if not self.stage_kernel_btn.isEnabled():
            self.kernel_plan_status.setText("Kernel/initramfs staging is blocked because required source evidence is incomplete.")
            return
        if not self.regenerate_initramfs.isChecked():
            self.kernel_plan_status.setText("Choose at least one kernel/initramfs operation before staging.")
            return
        payload = {
            "config_type": "kernel_initramfs",
            "source_sha256": str(self._analysis.get("sha256") or ""),
            "kernel_images": list(self._analysis.get("kernel_images") or []),
            "initramfs_images": list(self._analysis.get("initramfs_images") or []),
            "rootfs": list(self._analysis.get("rootfs") or []),
            "initramfs_mechanism": str(self._analysis.get("initramfs_mechanism") or ""),
            "regenerate_initramfs": True,
            "protect_last_viable_kernel": True,
            "preservation_policy": "preserve-unrelated",
            "stage_only": True,
        }
        detail = (
            f"Regenerate initramfs later using {payload['initramfs_mechanism']} after tool/rootfs verification; "
            "last viable kernel protection is mandatory. Source ISO remains read-only."
        )
        change = ChangeItem("Kernel / initramfs plan", ChangeKind.CONFIG, detail, payload)
        self.stage_requested.emit(change)
        self.kernel_plan_status.setText("Staged — review/Test in Changes.")

    def _reset_hardware_plan(self) -> None:
        self.hardware_package_combo.setCurrentIndex(0)
        self.hardware_action_combo.setCurrentIndex(0)
        if self.stage_hardware_btn.isEnabled() and self.hardware_package_combo.count() > 1:
            self.hardware_plan_status.setText("Ready — no firmware/driver changes staged.")
        else:
            self.hardware_plan_status.setText("No manifest-backed firmware/driver package evidence available.")

    def _stage_hardware_plan(self) -> None:
        if not self.stage_hardware_btn.isEnabled():
            message = "Analyze a supported source ISO before staging a hardware plan."
            self.hardware_plan_status.setText(message)
            QMessageBox.information(self, "Hardware plan not staged", message)
            return
        if self.hardware_package_combo.count() <= 1:
            message = (
                "BLOCKED — the selected ISO contains no manifest-backed firmware/driver "
                "package evidence. Nothing has been staged."
            )
            self.hardware_plan_status.setText(message)
            QMessageBox.information(self, "Hardware plan blocked", message)
            return
        package = self.hardware_package_combo.currentData()
        action = self.hardware_action_combo.currentData()
        if not isinstance(package, dict) or not str(package.get("package") or "").strip():
            message = "Select a manifest-backed firmware/driver package first."
            self.hardware_plan_status.setText(message)
            self.hardware_package_combo.setFocus()
            QMessageBox.information(self, "Hardware plan not staged", message)
            return
        if action != "re_resolve":
            message = "Choose 'Re-resolve from target repositories' before staging."
            self.hardware_plan_status.setText(message)
            self.hardware_action_combo.setFocus()
            QMessageBox.information(self, "Hardware plan not staged", message)
            return
        payload = {
            "config_type": "hardware_package",
            "source_sha256": str(self._analysis.get("sha256") or ""),
            "package": str(package.get("package") or ""),
            "version": str(package.get("version") or ""),
            "hardware_kind": str(package.get("kind") or ""),
            "rootfs": list(self._analysis.get("rootfs") or []),
            "initramfs_mechanism": str(self._analysis.get("initramfs_mechanism") or ""),
            "operation": "re_resolve",
            "require_signed_repository_metadata": True,
            "require_dependency_resolution": True,
            "protect_last_viable_kernel": True,
            "regenerate_initramfs": True,
            "preservation_policy": "preserve-unrelated",
            "stage_only": True,
        }
        detail = (
            f"Re-resolve {payload['package']} ({payload['hardware_kind']}) later from target repositories; "
            f"signed metadata, dependency resolution and {payload['initramfs_mechanism']} verification are mandatory. "
            "Source ISO remains read-only."
        )
        change = ChangeItem("Firmware / driver plan", ChangeKind.CONFIG, detail, payload)
        self.stage_requested.emit(change)
        self.hardware_plan_status.setText("Staged — review/Test in Changes.")
        QMessageBox.information(
            self,
            "STAGED: Firmware / driver plan",
            f"{payload['package']} is staged only. Review and Test it in Changes before any later apply.",
        )

    def _reset_rootfs_plan(self) -> None:
        self.rootfs_layer_combo.setCurrentIndex(0)
        self.rootfs_action_combo.setCurrentIndex(0)
        self.rootfs_target_compression_combo.setCurrentIndex(0)
        self._update_rootfs_selection()
        if self._analysis.get("rootfs_details") or self._analysis.get("rootfs"):
            self.rootfs_plan_status.setText("Ready — no rootfs/SquashFS changes staged.")
        else:
            self.rootfs_plan_status.setText("No detected SquashFS layer evidence available.")

    def _update_rootfs_selection(self) -> None:
        layer = self.rootfs_layer_combo.currentData()
        if isinstance(layer, dict):
            compression = str(layer.get("compression") or "unknown")
            block = layer.get("block_size")
            text = compression
            if block:
                text += f"; block size {block}"
            self.rootfs_current_compression_value.setText(text)
        else:
            self.rootfs_current_compression_value.setText("—")

    def _stage_rootfs_plan(self) -> None:
        if not self.stage_rootfs_btn.isEnabled():
            message = "Analyze a supported source ISO before staging a rootfs plan."
            self.rootfs_plan_status.setText(message)
            QMessageBox.information(self, "Rootfs plan not staged", message)
            return
        if self.rootfs_layer_combo.count() <= 1:
            message = "BLOCKED — the selected ISO contains no detected SquashFS/rootfs layer evidence. Nothing has been staged."
            self.rootfs_plan_status.setText(message)
            QMessageBox.information(self, "Rootfs plan blocked", message)
            return
        layer = self.rootfs_layer_combo.currentData()
        if not isinstance(layer, dict) or not str(layer.get("path") or "").strip():
            message = "Select a detected SquashFS layer first."
            self.rootfs_plan_status.setText(message)
            self.rootfs_layer_combo.setFocus()
            QMessageBox.information(self, "Rootfs plan not staged", message)
            return
        source_compression = str(layer.get("compression") or "unknown").strip().casefold()
        if source_compression not in {"xz", "zstd", "gzip", "lz4", "lzo"}:
            message = "BLOCKED — the selected layer compression was not identified safely. Nothing has been staged."
            self.rootfs_plan_status.setText(message)
            QMessageBox.information(self, "Rootfs plan blocked", message)
            return
        if self.rootfs_action_combo.currentData() != "repack":
            message = "Choose 'Repack selected layer' before staging."
            self.rootfs_plan_status.setText(message)
            self.rootfs_action_combo.setFocus()
            QMessageBox.information(self, "Rootfs plan not staged", message)
            return
        requested = str(self.rootfs_target_compression_combo.currentData() or "preserve")
        target_compression = source_compression if requested == "preserve" else requested
        if target_compression not in {"xz", "zstd", "gzip", "lz4", "lzo"}:
            message = "Selected target compression is not supported by this staging gate."
            self.rootfs_plan_status.setText(message)
            QMessageBox.information(self, "Rootfs plan not staged", message)
            return
        try:
            source_block_size = int(layer.get("block_size") or 0)
        except (TypeError, ValueError):
            source_block_size = 0
        payload = {
            "config_type": "rootfs_squashfs",
            "source_sha256": str(self._analysis.get("sha256") or ""),
            "layer_path": str(layer.get("path") or ""),
            "source_compression": source_compression,
            "source_block_size": source_block_size,
            "operation": "repack",
            "target_compression": target_compression,
            "preserve_block_size": True,
            "require_unsquashfs_verification": True,
            "require_mksquashfs_verification": True,
            "preserve_unrelated": True,
            "source_read_only": True,
            "stage_only": True,
        }
        detail = (
            f"Repack {payload['layer_path']} later from {source_compression} to {target_compression}; "
            "unsquashfs/mksquashfs capability checks, preserved block size and unrelated-source preservation are mandatory. "
            "Source ISO remains read-only."
        )
        change = ChangeItem("Rootfs / SquashFS plan", ChangeKind.CONFIG, detail, payload)
        self.stage_requested.emit(change)
        self.rootfs_plan_status.setText("Staged — review/Test in Changes.")
        QMessageBox.information(
            self,
            "STAGED: Rootfs / SquashFS plan",
            "The rootfs plan is staged only. Review and Test it in Changes before any later apply.",
        )

    def _reset_immutable_plan(self) -> None:
        self.immutable_layer_combo.setCurrentIndex(0)
        self.immutable_mode_combo.setCurrentIndex(0)
        if self.stage_immutable_btn.isEnabled():
            self.immutable_plan_status.setText("Ready — no immutable runtime changes staged.")
        else:
            self.immutable_plan_status.setText("Required rootfs/boot/initramfs evidence is incomplete.")

    def _stage_immutable_plan(self) -> None:
        if not self.stage_immutable_btn.isEnabled():
            message = "BLOCKED — required rootfs, boot and initramfs evidence is incomplete. Nothing has been staged."
            self.immutable_plan_status.setText(message)
            QMessageBox.information(self, "Immutable runtime plan blocked", message)
            return
        layer = self.immutable_layer_combo.currentData()
        if not isinstance(layer, dict) or not str(layer.get("path") or "").strip():
            message = "Select a detected SquashFS base layer first."
            self.immutable_plan_status.setText(message)
            self.immutable_layer_combo.setFocus()
            QMessageBox.information(self, "Immutable runtime plan not staged", message)
            return
        if self.immutable_mode_combo.currentData() != "volatile_overlay":
            message = "Choose 'Read-only rootfs + volatile OverlayFS' before staging."
            self.immutable_plan_status.setText(message)
            self.immutable_mode_combo.setFocus()
            QMessageBox.information(self, "Immutable runtime plan not staged", message)
            return
        payload = {
            "config_type": "immutable_runtime",
            "source_sha256": str(self._analysis.get("sha256") or ""),
            "base_layer": str(layer.get("path") or ""),
            "runtime_mode": "volatile_overlay",
            "writable_layer": "tmpfs",
            "persistence_policy": "volatile",
            "runtime_changes_survive_reboot": False,
            "initramfs_mechanism": str(self._analysis.get("initramfs_mechanism") or ""),
            "require_initramfs_integration": True,
            "require_boot_integration": True,
            "source_read_only": True,
            "preserve_unrelated": True,
            "stage_only": True,
        }
        detail = (
            f"Use {payload['base_layer']} as a read-only rootfs with volatile OverlayFS and tmpfs upper/work layers; "
            "runtime changes do not survive reboot. Native initramfs and boot integration must be verified before apply. "
            "Source ISO remains read-only."
        )
        change = ChangeItem("Immutable / volatile runtime plan", ChangeKind.CONFIG, detail, payload)
        self.stage_requested.emit(change)
        self.immutable_plan_status.setText("Staged — review/Test in Changes.")
        QMessageBox.information(
            self,
            "STAGED: Immutable / volatile runtime plan",
            "The immutable runtime plan is staging-only. Review and Test it in Changes before any later apply.",
        )

    def _reset_persistence_plan(self) -> None:
        self.persistence_layer_combo.setCurrentIndex(0)
        self.persistence_directories_edit.clear()
        self.persistence_storage_combo.setCurrentIndex(0)
        self.persistence_size_spin.setValue(4096)
        self.persistence_filesystem_combo.setCurrentIndex(0)
        self.persistence_label_edit.setText("CHROMAPERSIST")
        if self.stage_persistence_btn.isEnabled():
            self.persistence_plan_status.setText("Ready — no controlled persistence changes staged.")
        else:
            self.persistence_plan_status.setText("Required rootfs/boot/initramfs evidence is incomplete.")

    def _stage_persistence_plan(self) -> None:
        if not self.stage_persistence_btn.isEnabled():
            message = "BLOCKED — required rootfs, boot and initramfs evidence is incomplete. Nothing has been staged."
            self.persistence_plan_status.setText(message)
            QMessageBox.information(self, "Controlled persistence plan blocked", message)
            return
        layer = self.persistence_layer_combo.currentData()
        if not isinstance(layer, dict) or not str(layer.get("path") or "").strip():
            message = "Select a detected SquashFS base layer first."
            self.persistence_plan_status.setText(message)
            self.persistence_layer_combo.setFocus()
            QMessageBox.information(self, "Controlled persistence plan not staged", message)
            return
        try:
            directories = self._parse_persistent_directories(self.persistence_directories_edit.text())
        except ValueError as exc:
            message = str(exc)
            self.persistence_plan_status.setText(message)
            self.persistence_directories_edit.setFocus()
            QMessageBox.information(self, "Controlled persistence plan not staged", message)
            return
        if not directories:
            message = "Enter at least one controlled persistent directory."
            self.persistence_plan_status.setText(message)
            self.persistence_directories_edit.setFocus()
            QMessageBox.information(self, "Controlled persistence plan not staged", message)
            return
        if self.persistence_storage_combo.currentData() != "dedicated_volume":
            message = "Choose the dedicated target-system persistent volume plan before staging."
            self.persistence_plan_status.setText(message)
            self.persistence_storage_combo.setFocus()
            QMessageBox.information(self, "Controlled persistence plan not staged", message)
            return
        label = self.persistence_label_edit.text().strip()
        if not label or len(label) > 16 or not all(ch.isalnum() or ch in "_-" for ch in label) or not label[0].isalnum():
            message = "Volume label must be 1–16 ASCII letters/digits/underscore/hyphen and start with a letter or digit."
            self.persistence_plan_status.setText(message)
            self.persistence_label_edit.setFocus()
            QMessageBox.information(self, "Controlled persistence plan not staged", message)
            return
        if any(ord(ch) > 127 for ch in label):
            message = "Volume label must use ASCII characters only."
            self.persistence_plan_status.setText(message)
            self.persistence_label_edit.setFocus()
            QMessageBox.information(self, "Controlled persistence plan not staged", message)
            return
        payload = {
            "config_type": "controlled_persistence",
            "source_sha256": str(self._analysis.get("sha256") or ""),
            "base_layer": str(layer.get("path") or ""),
            "runtime_mode": "volatile_overlay_with_controlled_persistence",
            "writable_layer": "tmpfs",
            "persistence_policy": "selected_directories",
            "persistent_directories": directories,
            "selected_directories_survive_reboot": True,
            "unlisted_runtime_changes_survive_reboot": False,
            "backing_storage": "dedicated_volume",
            "volume_scope": "target_system",
            "volume_size_mib": int(self.persistence_size_spin.value()),
            "filesystem": str(self.persistence_filesystem_combo.currentData() or ""),
            "volume_label": label,
            "initramfs_mechanism": str(self._analysis.get("initramfs_mechanism") or ""),
            "require_initramfs_integration": True,
            "require_boot_integration": True,
            "require_mount_verification": True,
            "do_not_repartition_source_iso": True,
            "source_read_only": True,
            "preserve_unrelated": True,
            "stage_only": True,
        }
        detail = (
            f"Persist only {', '.join(directories)} on a dedicated {payload['filesystem']} target-system volume "
            f"({payload['volume_size_mib']} MiB, label {label}); all other OverlayFS runtime changes remain volatile. "
            "Initramfs, boot and mount integration must be verified before apply; the source ISO is never repartitioned."
        )
        change = ChangeItem("Controlled persistence plan", ChangeKind.CONFIG, detail, payload)
        self.stage_requested.emit(change)
        self.persistence_plan_status.setText("Staged — review/Test in Changes.")
        QMessageBox.information(
            self,
            "STAGED: Controlled persistence plan",
            "The controlled persistence plan is staging-only. Review and Test it in Changes before any later apply.",
        )

    def _reset_integration_plan(self) -> None:
        self.integration_layer_combo.setCurrentIndex(0)
        self.integration_target_combo.setCurrentIndex(0)
        self._update_integration_target()
        if self.stage_integration_btn.isEnabled():
            self.integration_plan_status.setText("Ready — no runtime integration changes staged.")
        else:
            self.integration_plan_status.setText("Required boot/kernel/initramfs/rootfs evidence is incomplete.")

    def _update_integration_target(self) -> None:
        target = self.integration_target_combo.currentData()
        if target == "volatile_overlay":
            self.integration_mount_value.setText("No persistent mount; tmpfs upper/work layers are recreated each boot")
        elif target == "controlled_persistence":
            self.integration_mount_value.setText("Resolve persistent volume by label/UUID and verify mount before persistent binds")
        else:
            self.integration_mount_value.setText("Select an integration target")

    def _stage_integration_plan(self) -> None:
        if not self.stage_integration_btn.isEnabled():
            message = "BLOCKED — required boot, kernel, initramfs and SquashFS evidence is incomplete. Nothing has been staged."
            self.integration_plan_status.setText(message)
            QMessageBox.information(self, "Runtime integration plan blocked", message)
            return
        layer = self.integration_layer_combo.currentData()
        if not isinstance(layer, dict) or not str(layer.get("path") or "").strip():
            message = "Select a detected SquashFS base layer first."
            self.integration_plan_status.setText(message)
            self.integration_layer_combo.setFocus()
            QMessageBox.information(self, "Runtime integration plan not staged", message)
            return
        target = str(self.integration_target_combo.currentData() or "")
        if target not in {"volatile_overlay", "controlled_persistence"}:
            message = "Select either the volatile OverlayFS or controlled persistence integration target."
            self.integration_plan_status.setText(message)
            self.integration_target_combo.setFocus()
            QMessageBox.information(self, "Runtime integration plan not staged", message)
            return
        boot_configs = [str(x).strip() for x in list(self._analysis.get("boot_config_files") or []) if str(x).strip()]
        kernels = [str(x).strip() for x in list(self._analysis.get("kernel_images") or []) if str(x).strip()]
        initramfs = [str(x).strip() for x in list(self._analysis.get("initramfs_images") or []) if str(x).strip()]
        mechanism = str(self._analysis.get("initramfs_mechanism") or "").strip()
        payload = {
            "config_type": "runtime_integration",
            "source_sha256": str(self._analysis.get("sha256") or ""),
            "base_layer": str(layer.get("path") or ""),
            "integration_target": target,
            "boot_config_files": boot_configs,
            "kernel_images": kernels,
            "initramfs_images": initramfs,
            "initramfs_mechanism": mechanism,
            "boot_policy": "preserve_detected_boot_structure",
            "require_boot_config_reverification": True,
            "require_kernel_binding": True,
            "initramfs_policy": "verify_hook_then_regenerate",
            "require_initramfs_hook_verification": True,
            "require_initramfs_regeneration": True,
            "mount_policy": "resolve_label_or_uuid_before_persistent_binds" if target == "controlled_persistence" else "none",
            "require_mount_verification": target == "controlled_persistence",
            "runtime_changes_survive_reboot": False if target == "volatile_overlay" else None,
            "selected_persistence_only": target == "controlled_persistence",
            "source_read_only": True,
            "preserve_unrelated": True,
            "stage_only": True,
        }
        detail = (
            f"Bind {payload['base_layer']} to {target.replace('_', ' ')} using {mechanism}; "
            f"re-verify {len(boot_configs)} boot config(s), {len(kernels)} kernel image(s) and {len(initramfs)} initramfs image(s). "
            "Detected boot structure is preserved and the source ISO remains read-only."
        )
        change = ChangeItem("Runtime integration verification plan", ChangeKind.CONFIG, detail, payload)
        self.stage_requested.emit(change)
        self.integration_plan_status.setText("Staged — review/Test in Changes.")
        QMessageBox.information(
            self,
            "STAGED: Runtime integration verification plan",
            "The integration plan is staging-only. Review and Test it in Changes before any later apply.",
        )

    def set_staged_changes(self, changes: list[ChangeItem]) -> None:
        staged = next(
            (
                c for c in changes
                if c.kind == ChangeKind.CONFIG and str(c.payload.get("config_type", "")) == "boot"
            ),
            None,
        )
        if staged:
            self.plan_status.setText("Staged — review/Test in Changes.")
        elif self._analysis.get("boot_config_files"):
            self.plan_status.setText("Ready — no boot changes staged.")
        else:
            self.plan_status.setText("Analyze a source ISO first.")

        metadata_staged = next(
            (
                c for c in changes
                if c.kind == ChangeKind.CONFIG and str(c.payload.get("config_type", "")) == "boot_metadata"
            ),
            None,
        )
        if metadata_staged:
            self.metadata_plan_status.setText("Staged — review/Test in Changes.")
        elif self.stage_metadata_btn.isEnabled():
            self.metadata_plan_status.setText("Ready — no boot metadata changes staged.")
        else:
            self.metadata_plan_status.setText("Analyze a source ISO first.")

        kernel_staged = next(
            (
                c for c in changes
                if c.kind == ChangeKind.CONFIG and str(c.payload.get("config_type", "")) == "kernel_initramfs"
            ),
            None,
        )
        if kernel_staged:
            self.kernel_plan_status.setText("Staged — review/Test in Changes.")
        elif self.stage_kernel_btn.isEnabled():
            self.kernel_plan_status.setText("Ready — no kernel/initramfs changes staged.")
        else:
            self.kernel_plan_status.setText("Analyze a supported source ISO first.")

        hardware_staged = next(
            (
                c for c in changes
                if c.kind == ChangeKind.CONFIG and str(c.payload.get("config_type", "")) == "hardware_package"
            ),
            None,
        )
        if hardware_staged:
            self.hardware_plan_status.setText("Staged — review/Test in Changes.")
        elif self.stage_hardware_btn.isEnabled() and self.hardware_package_combo.count() > 1:
            self.hardware_plan_status.setText("Ready — no firmware/driver changes staged.")
        else:
            self.hardware_plan_status.setText("No manifest-backed firmware/driver package evidence available.")

        rootfs_staged = next(
            (
                c for c in changes
                if c.kind == ChangeKind.CONFIG and str(c.payload.get("config_type", "")) == "rootfs_squashfs"
            ),
            None,
        )
        if rootfs_staged:
            self.rootfs_plan_status.setText("Staged — review/Test in Changes.")
        elif self.stage_rootfs_btn.isEnabled():
            self.rootfs_plan_status.setText("Ready — no rootfs/SquashFS changes staged.")
        else:
            self.rootfs_plan_status.setText("No detected SquashFS layer evidence available.")

        immutable_staged = next(
            (
                c for c in changes
                if c.kind == ChangeKind.CONFIG and str(c.payload.get("config_type", "")) == "immutable_runtime"
            ),
            None,
        )
        if immutable_staged:
            self.immutable_plan_status.setText("Staged — review/Test in Changes.")
        elif self.stage_immutable_btn.isEnabled():
            self.immutable_plan_status.setText("Ready — no immutable runtime changes staged.")
        else:
            self.immutable_plan_status.setText("Required rootfs/boot/initramfs evidence is incomplete.")

        persistence_staged = next(
            (
                c for c in changes
                if c.kind == ChangeKind.CONFIG and str(c.payload.get("config_type", "")) == "controlled_persistence"
            ),
            None,
        )
        if persistence_staged:
            self.persistence_plan_status.setText("Staged — review/Test in Changes.")
        elif self.stage_persistence_btn.isEnabled():
            self.persistence_plan_status.setText("Ready — no controlled persistence changes staged.")
        else:
            self.persistence_plan_status.setText("Required rootfs/boot/initramfs evidence is incomplete.")

        integration_staged = next(
            (
                c for c in changes
                if c.kind == ChangeKind.CONFIG and str(c.payload.get("config_type", "")) == "runtime_integration"
            ),
            None,
        )
        if integration_staged:
            self.integration_plan_status.setText("Staged — review/Test in Changes.")
        elif self.stage_integration_btn.isEnabled():
            self.integration_plan_status.setText("Ready — no runtime integration changes staged.")
        else:
            self.integration_plan_status.setText("Required boot/kernel/initramfs/rootfs evidence is incomplete.")

    def set_analysis(self, data: dict) -> None:
        self._analysis = dict(data or {})
        bios = bool(data.get("bios_boot"))
        uefi = bool(data.get("uefi_boot"))
        modes = [name for name, enabled in (("BIOS", bios), ("UEFI", uefi)) if enabled]
        self.boot_fields["modes"].setText(", ".join(modes) if modes else "Not detected")
        self.boot_fields["el_torito"].setText(self._yes_no(data.get("el_torito_boot")))
        self.boot_fields["hybrid"].setText(self._yes_no(data.get("hybrid_boot")))
        self.boot_fields["loaders"].setText(self._join(data.get("bootloaders")))
        self.boot_fields["catalog"].setText(data.get("boot_catalog") or "Not detected")
        self.boot_fields["volume"].setText(data.get("volume_id") or "—")
        self.config_fields["defaults"].setText(self._join(data.get("boot_defaults"), "No explicit default declaration found"))
        self.config_fields["timeouts"].setText(self._join(data.get("boot_timeouts"), "No explicit timeout declaration found"))

        self.default_combo.blockSignals(True)
        self.default_combo.clear()
        self.default_combo.addItem("Preserve current default", None)
        for entry in list(data.get("boot_entries") or []):
            if not isinstance(entry, dict):
                continue
            title = str(entry.get("title") or entry.get("id") or "").strip()
            source = str(entry.get("source") or "").strip()
            if title and source:
                self.default_combo.addItem(title, {"title": title, "source": source, "id": str(entry.get("id") or "")})
        self.default_combo.blockSignals(False)
        self.timeout_spin.setValue(-1)
        self.kernel_args_edit.clear()
        has_config = bool(data.get("boot_config_files")) and bool(data.get("sha256"))
        self.stage_btn.setEnabled(has_config)
        self.reset_btn.setEnabled(bool(data.get("path")))
        self.plan_status.setText(
            "Ready — no boot changes staged." if has_config
            else "Analyze a source ISO first."
        )

        self.metadata_entry_combo.blockSignals(True)
        self.metadata_entry_combo.clear()
        self.metadata_entry_combo.addItem("Select detected boot entry", None)
        detected_entries = []
        for entry in list(data.get("boot_entries") or []):
            if not isinstance(entry, dict):
                continue
            title = str(entry.get("title") or entry.get("id") or "").strip()
            source = str(entry.get("source") or "").strip()
            if title and source:
                normalized = {"title": title, "source": source, "id": str(entry.get("id") or "")}
                detected_entries.append(normalized)
                self.metadata_entry_combo.addItem(title, normalized)
        self.metadata_entry_combo.blockSignals(False)
        self.metadata_label_edit.clear()
        self.metadata_order_combo.setCurrentIndex(0)
        self.metadata_volume_edit.clear()
        current_volume = str(data.get("volume_id") or "").strip()
        self.metadata_volume_edit.setPlaceholderText(
            f"Preserve detected: {current_volume}" if current_volume else "Leave blank to preserve detected Volume ID"
        )
        metadata_ready = bool(data.get("sha256")) and bool(data.get("boot_config_files")) and bool(detected_entries)
        self.stage_metadata_btn.setEnabled(metadata_ready)
        self.reset_metadata_btn.setEnabled(bool(data.get("path")))
        self.metadata_plan_status.setText(
            "Ready — no boot metadata changes staged." if metadata_ready
            else "Analyze a source ISO with explicit boot entries first."
        )

        kernels_for_plan = list(data.get("kernel_images") or [])
        initramfs_for_plan = list(data.get("initramfs_images") or [])
        rootfs_for_plan = list(data.get("rootfs") or [])
        mechanism = str(data.get("initramfs_mechanism") or "")
        self.kernel_images_value.setText(f"{len(kernels_for_plan)} detected" if kernels_for_plan else "None detected")
        self.initramfs_images_value.setText(f"{len(initramfs_for_plan)} detected" if initramfs_for_plan else "None detected")
        self.initramfs_mechanism_value.setText(mechanism or "Not determined")
        self.regenerate_initramfs.setChecked(False)
        kernel_ready = bool(data.get("sha256")) and bool(kernels_for_plan) and bool(rootfs_for_plan) and mechanism in {"update-initramfs", "dracut", "mkinitcpio"}
        self.stage_kernel_btn.setEnabled(kernel_ready)
        self.reset_kernel_btn.setEnabled(bool(data.get("path")))
        self.kernel_plan_status.setText(
            "Ready — no kernel/initramfs changes staged." if kernel_ready
            else "Analyze a supported source ISO first."
        )

        hardware_hints = [
            item for item in list(data.get("hardware_package_hints") or [])
            if isinstance(item, dict) and str(item.get("kind") or "") in {"Firmware / microcode", "Driver / DKMS"}
        ]
        self.hardware_evidence_value.setText(
            f"{len(hardware_hints)} manifest-backed firmware/driver package(s)"
            if hardware_hints else "No matching manifest-backed firmware/driver packages"
        )
        self.hardware_package_combo.blockSignals(True)
        self.hardware_package_combo.clear()
        self.hardware_package_combo.addItem("Select manifest-backed package", None)
        for item in hardware_hints:
            package = str(item.get("package") or "").strip()
            version = str(item.get("version") or "").strip()
            kind = str(item.get("kind") or "").strip()
            if package:
                label = f"{package} — {kind}" + (f" ({version})" if version else "")
                self.hardware_package_combo.addItem(label, dict(item))
        self.hardware_package_combo.blockSignals(False)
        self.hardware_action_combo.setCurrentIndex(0)
        hardware_ready = bool(data.get("sha256")) and bool(rootfs_for_plan) and bool(hardware_hints) and mechanism in {"update-initramfs", "dracut", "mkinitcpio"}
        # Keep the control clickable after a source ISO has been analyzed so a blocked
        # state can explain itself. The handler remains fail-closed and never stages
        # without manifest-backed package evidence plus the required safety gates.
        hardware_control_available = bool(data.get("path")) and bool(data.get("sha256"))
        self.stage_hardware_btn.setEnabled(hardware_control_available)
        self.reset_hardware_btn.setEnabled(bool(data.get("path")))
        self.hardware_initramfs_value.setText(
            f"{mechanism} re-verification + regeneration required before apply" if mechanism
            else "Native initramfs mechanism not determined"
        )
        self.hardware_plan_status.setText(
            "Select a package and choose Re-resolve, then Stage hardware plan." if hardware_ready
            else "No manifest-backed firmware/driver package evidence available."
        )

        rootfs_details_for_plan = [item for item in list(data.get("rootfs_details") or []) if isinstance(item, dict)]
        if not rootfs_details_for_plan:
            rootfs_details_for_plan = [
                {"path": str(path), "compression": "unknown"}
                for path in list(data.get("rootfs") or []) if str(path).strip()
            ]
        self.rootfs_evidence_value.setText(
            f"{len(rootfs_details_for_plan)} detected SquashFS layer(s)"
            if rootfs_details_for_plan else "No detected SquashFS layers"
        )
        self.rootfs_layer_combo.blockSignals(True)
        self.rootfs_layer_combo.clear()
        self.rootfs_layer_combo.addItem("Select detected SquashFS layer", None)
        for item in rootfs_details_for_plan:
            path = str(item.get("path") or "").strip()
            compression = str(item.get("compression") or "unknown").strip()
            if path:
                self.rootfs_layer_combo.addItem(f"{path} — {compression}", dict(item))
        self.rootfs_layer_combo.blockSignals(False)
        self.rootfs_action_combo.setCurrentIndex(0)
        self.rootfs_target_compression_combo.setCurrentIndex(0)
        self._update_rootfs_selection()
        rootfs_control_available = bool(data.get("path")) and bool(data.get("sha256"))
        self.stage_rootfs_btn.setEnabled(rootfs_control_available)
        self.reset_rootfs_btn.setEnabled(bool(data.get("path")))
        self.rootfs_plan_status.setText(
            "Select a layer and choose Repack, then Stage rootfs plan." if rootfs_details_for_plan
            else "No detected SquashFS layer evidence available."
        )

        self.immutable_layer_combo.blockSignals(True)
        self.immutable_layer_combo.clear()
        self.immutable_layer_combo.addItem("Select detected SquashFS base layer", None)
        for item in rootfs_details_for_plan:
            path = str(item.get("path") or "").strip()
            if path:
                self.immutable_layer_combo.addItem(path, dict(item))
        self.immutable_layer_combo.blockSignals(False)
        self.immutable_mode_combo.setCurrentIndex(0)
        immutable_ready = (
            bool(data.get("path"))
            and bool(data.get("sha256"))
            and bool(rootfs_details_for_plan)
            and bool(data.get("boot_config_files"))
            and mechanism in {"update-initramfs", "dracut", "mkinitcpio"}
        )
        self.stage_immutable_btn.setEnabled(immutable_ready)
        self.reset_immutable_btn.setEnabled(bool(data.get("path")))
        self.immutable_integration_value.setText(
            f"{mechanism} + boot configuration re-verification required before apply"
            if mechanism else "Native initramfs mechanism not determined"
        )
        self.immutable_plan_status.setText(
            "Select a base layer and volatile OverlayFS, then Stage immutable plan."
            if immutable_ready else "Required rootfs/boot/initramfs evidence is incomplete."
        )

        self.persistence_layer_combo.blockSignals(True)
        self.persistence_layer_combo.clear()
        self.persistence_layer_combo.addItem("Select detected SquashFS base layer", None)
        for item in rootfs_details_for_plan:
            path = str(item.get("path") or "").strip()
            if path:
                self.persistence_layer_combo.addItem(path, dict(item))
        self.persistence_layer_combo.blockSignals(False)
        self.persistence_directories_edit.clear()
        self.persistence_storage_combo.setCurrentIndex(0)
        self.persistence_size_spin.setValue(4096)
        self.persistence_filesystem_combo.setCurrentIndex(0)
        self.persistence_label_edit.setText("CHROMAPERSIST")
        persistence_ready = immutable_ready
        self.stage_persistence_btn.setEnabled(persistence_ready)
        self.reset_persistence_btn.setEnabled(bool(data.get("path")))
        self.persistence_integration_value.setText(
            f"{mechanism} + boot + mount verification required before apply"
            if mechanism else "Native initramfs mechanism not determined"
        )
        self.persistence_plan_status.setText(
            "Select a base layer, directories and target-system volume, then Stage persistence plan."
            if persistence_ready else "Required rootfs/boot/initramfs evidence is incomplete."
        )

        self.integration_layer_combo.blockSignals(True)
        self.integration_layer_combo.clear()
        self.integration_layer_combo.addItem("Select detected SquashFS base layer", None)
        for item in rootfs_details_for_plan:
            path = str(item.get("path") or "").strip()
            if path:
                self.integration_layer_combo.addItem(path, dict(item))
        self.integration_layer_combo.blockSignals(False)
        self.integration_target_combo.setCurrentIndex(0)
        integration_ready = (
            bool(data.get("path"))
            and bool(data.get("sha256"))
            and bool(rootfs_details_for_plan)
            and bool(data.get("boot_config_files"))
            and bool(kernels_for_plan)
            and bool(initramfs_for_plan)
            and mechanism in {"update-initramfs", "dracut", "mkinitcpio"}
        )
        self.stage_integration_btn.setEnabled(integration_ready)
        self.reset_integration_btn.setEnabled(bool(data.get("path")))
        self.integration_evidence_value.setText(
            f"{len(list(data.get('boot_config_files') or []))} boot config • {len(kernels_for_plan)} kernel • {len(initramfs_for_plan)} initramfs"
            if integration_ready else "Required source evidence incomplete"
        )
        self.integration_initramfs_value.setText(
            f"Verify runtime hook, then regenerate with {mechanism}" if mechanism else "Native initramfs mechanism not determined"
        )
        self._update_integration_target()
        self.integration_plan_status.setText(
            "Select a base layer and integration target, then Stage integration plan."
            if integration_ready else "Required boot/kernel/initramfs/rootfs evidence is incomplete."
        )

        self.structure.clear()

        configs = list(data.get("boot_config_files") or [])
        config_root = self._root(self.structure, "Boot configuration", f"{len(configs)} file(s) detected")
        for value in configs:
            QTreeWidgetItem(config_root, ["Configuration", str(value)])

        entries = list(data.get("boot_entries") or [])
        entries_root = self._root(self.structure, "Boot entries", f"{len(entries)} explicit entrie(s) parsed")
        for item in entries:
            if isinstance(item, dict):
                title = str(item.get("title") or item.get("id") or "Entry")
                source = str(item.get("source") or "")
                QTreeWidgetItem(entries_root, [title, source])

        kernel_args = list(data.get("kernel_arguments") or [])
        args_root = self._root(self.structure, "Kernel arguments", f"{len(kernel_args)} explicit command line(s) parsed")
        for item in kernel_args:
            if isinstance(item, dict):
                QTreeWidgetItem(args_root, [str(item.get("source") or "Kernel command"), str(item.get("args") or "")])

        efi = list(data.get("efi_images") or [])
        efi_root = self._root(self.structure, "EFI images", f"{len(efi)} item(s) detected")
        for value in efi:
            QTreeWidgetItem(efi_root, ["EFI", str(value)])

        kernels = list(data.get("kernel_images") or [])
        kernel_root = self._root(self.structure, "Kernel images", f"{len(kernels)} item(s) detected")
        for value in kernels:
            QTreeWidgetItem(kernel_root, ["Kernel", str(value)])

        initramfs = list(data.get("initramfs_images") or [])
        init_root = self._root(self.structure, "Initramfs / initrd", f"{len(initramfs)} item(s) detected")
        for value in initramfs:
            QTreeWidgetItem(init_root, ["Initramfs", str(value)])

        rootfs_details = list(data.get("rootfs_details") or [])
        if not rootfs_details:
            rootfs_details = [{"path": x, "compression": "unknown"} for x in data.get("rootfs") or []]
        rootfs_root = self._root(self.structure, "Root filesystem layers", f"{len(rootfs_details)} layer(s) detected")
        for item in rootfs_details:
            if isinstance(item, dict):
                path = str(item.get("path") or "")
                compression = str(item.get("compression") or "unknown")
                block = item.get("block_size")
                detail = f"compression: {compression}"
                if block:
                    detail += f"; block size: {block}"
                QTreeWidgetItem(rootfs_root, [path or "SquashFS", detail])
            else:
                QTreeWidgetItem(rootfs_root, [str(item), "compression: unknown"])

        firmware = list(data.get("firmware_hints") or [])
        firmware_root = self._root(
            self.structure,
            "Firmware / driver media hints",
            f"{len(firmware)} ISO-level hint(s) detected" if firmware else "No ISO-level hints detected",
        )
        for value in firmware:
            QTreeWidgetItem(firmware_root, ["Hint", str(value)])

        hardware = list(data.get("hardware_package_hints") or [])
        hardware_root = self._root(
            self.structure,
            "Manifest-backed kernel / firmware / driver packages",
            f"{len(hardware)} package hint(s) detected" if hardware else "No matching manifest package hints detected",
        )
        for item in hardware:
            if isinstance(item, dict):
                name = str(item.get("package") or "")
                version = str(item.get("version") or "")
                kind = str(item.get("kind") or "Package")
                detail = f"{kind}; version {version}" if version else kind
                QTreeWidgetItem(hardware_root, [name or kind, detail])

        for i in range(self.structure.topLevelItemCount()):
            self.structure.expandItem(self.structure.topLevelItem(i))

        path = str(data.get("path") or "")
        sha = str(data.get("sha256") or "")
        if path:
            name = path.replace("\\", "/").rsplit("/", 1)[-1] or path
            short_sha = f"{sha[:12]}…" if sha else "not available"
            self.footer.setText(f"SOURCE READ-ONLY • {name} • SHA-256 {short_sha} • staging only")
            self.footer.setToolTip(
                f"Source: {path}\nSHA-256: {sha or 'not available'}\n"
                "Source remains read-only; no source-image bytes are changed. "
                "Boot, kernel/initramfs, firmware/driver, rootfs/SquashFS, immutable-runtime and controlled-persistence changes remain staged-only."
            )
            self.footer.setWordWrap(False)
        else:
            self.footer.setText("No source analyzed yet — select and analyze an ISO on Source.")
            self.footer.setToolTip("")
            self.footer.setWordWrap(False)
