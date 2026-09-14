from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QGroupBox, QFormLayout, QTreeWidget,
    QTreeWidgetItem, QHeaderView, QLineEdit, QComboBox, QCheckBox,
    QPushButton, QPlainTextEdit, QHBoxLayout, QMessageBox,
)

from chromapress.models import ChangeItem, ChangeKind
from chromapress.services.part5 import generate_installer_template, validate_installer_payload


class InstallerPage(QWidget):
    """Part 5 structured installer editor.

    Editing is capability-gated to positively identified native installer families.
    No credential input is accepted here: credential material is deferred to a
    later secure verified-apply step and is never stored in the staged plan.
    """

    stage_requested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.analysis: dict = {}
        self.capability: dict = {}
        layout = QVBoxLayout(self)
        title = QLabel("Installer")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        intro = QLabel(
            "Structured native installer forms. ChromaPress generates inspectable Kickstart, "
            "Subiquity Autoinstall/cloud-init or Debian Preseed templates only when the target "
            "installer family is positively verified. Credentials are never collected or stored here."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        summary_box = QGroupBox("Detected installer")
        form = QFormLayout(summary_box)
        self.family_value = QLabel("Analyze a source ISO first.")
        self.family_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.mode_value = QLabel("—"); self.mode_value.setWordWrap(True)
        self.config_value = QLabel("—"); self.config_value.setWordWrap(True)
        self.source_hash_value = QLabel("—"); self.source_hash_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.capability_value = QLabel("UNKNOWN"); self.capability_value.setWordWrap(True)
        form.addRow("Installer family:", self.family_value)
        form.addRow("Detected capability:", self.mode_value)
        form.addRow("Explicit config files:", self.config_value)
        form.addRow("Part 5 native generator:", self.capability_value)
        form.addRow("Source SHA-256:", self.source_hash_value)
        layout.addWidget(summary_box)

        evidence_box = QGroupBox("Installer evidence")
        evidence_layout = QVBoxLayout(evidence_box)
        self.evidence_tree = QTreeWidget(); self.evidence_tree.setHeaderLabels(["Evidence", "Details"])
        self.evidence_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.evidence_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        evidence_layout.addWidget(self.evidence_tree)
        layout.addWidget(evidence_box)

        editor = QGroupBox("Structured installer profile — staged only")
        ef = QFormLayout(editor)
        self.depth = QComboBox(); self.depth.addItem("Quick", "quick"); self.depth.addItem("Advanced", "advanced"); self.depth.addItem("Expert", "expert")
        self.username = QLineEdit(); self.username.setPlaceholderText("user")
        self.display_name = QLineEdit(); self.display_name.setPlaceholderText("Full name")
        self.groups = QLineEdit(); self.groups.setPlaceholderText("audio,video")
        self.admin = QCheckBox("Grant verified distro administrator group")
        self.credential_policy = QLabel("Secure password/hash material is deferred to verified apply; no secret field exists here."); self.credential_policy.setWordWrap(True)
        self.hostname = QLineEdit(); self.hostname.setPlaceholderText("chromapress-host")
        self.language = QLineEdit("en")
        self.locale = QLineEdit("en_US.UTF-8")
        self.keyboard = QLineEdit("us")
        self.timezone = QLineEdit("UTC")
        self.network_mode = QComboBox(); self.network_mode.addItem("DHCP", "dhcp"); self.network_mode.addItem("Static IPv4", "static")
        self.ipv4 = QLineEdit(); self.ipv4.setPlaceholderText("192.0.2.10/24")
        self.gateway = QLineEdit(); self.gateway.setPlaceholderText("192.0.2.1")
        self.dns = QLineEdit(); self.dns.setPlaceholderText("1.1.1.1, 9.9.9.9")
        self.packages = QLineEdit(); self.packages.setPlaceholderText("curl, vim")
        self.profile = QComboBox(); self.profile.addItem("Standard", "standard"); self.profile.addItem("Minimal", "minimal")
        self.behavior = QComboBox(); self.behavior.addItem("Interactive / reviewed", "interactive_reviewed"); self.behavior.addItem("Automatic after verified apply", "automatic_after_verified_apply")
        self.partitioning = QComboBox(); self.partitioning.addItem("Preserve installer default", "preserve_installer_default"); self.partitioning.addItem("Guided: use entire target disk (destructive)", "guided_use_entire_disk")
        self.partition_confirm = QCheckBox("I understand the guided entire-disk option is destructive to the target disk")
        ef.addRow("Control depth:", self.depth); ef.addRow("Username:", self.username); ef.addRow("Full/display name:", self.display_name)
        ef.addRow("Groups:", self.groups); ef.addRow("Administrator:", self.admin); ef.addRow("Credential policy:", self.credential_policy)
        ef.addRow("Hostname:", self.hostname); ef.addRow("Language:", self.language); ef.addRow("Locale:", self.locale)
        ef.addRow("Keyboard:", self.keyboard); ef.addRow("Timezone:", self.timezone); ef.addRow("Network:", self.network_mode)
        ef.addRow("Static IPv4:", self.ipv4); ef.addRow("Gateway:", self.gateway); ef.addRow("DNS:", self.dns)
        ef.addRow("Package selections:", self.packages); ef.addRow("Installer profile:", self.profile); ef.addRow("Installation behavior:", self.behavior)
        ef.addRow("Partitioning (Advanced/Expert):", self.partitioning); ef.addRow("Destructive confirmation:", self.partition_confirm)
        layout.addWidget(editor)

        buttons = QHBoxLayout()
        self.preview_btn = QPushButton("Validate & Preview")
        self.stage_btn = QPushButton("Stage installer profile")
        buttons.addWidget(self.preview_btn); buttons.addWidget(self.stage_btn); buttons.addStretch(1)
        layout.addLayout(buttons)
        self.preview = QPlainTextEdit(); self.preview.setReadOnly(True); self.preview.setPlaceholderText("Generated native-family template appears here. It never contains a real credential.")
        self.preview.setMinimumHeight(220); layout.addWidget(self.preview)
        self.status = QLabel("No source analyzed."); self.status.setWordWrap(True); layout.addWidget(self.status)

        self.preview_btn.clicked.connect(self._preview)
        self.stage_btn.clicked.connect(self._stage)
        self.depth.currentIndexChanged.connect(self._update_partition_visibility)
        self.network_mode.currentIndexChanged.connect(self._update_network_visibility)
        self._update_partition_visibility(); self._update_network_visibility(); self._set_editor_enabled(False)

    def _set_editor_enabled(self, enabled: bool) -> None:
        for w in (self.depth, self.username, self.display_name, self.groups, self.admin, self.hostname, self.language, self.locale,
                  self.keyboard, self.timezone, self.network_mode, self.ipv4, self.gateway, self.dns, self.packages, self.profile,
                  self.behavior, self.partitioning, self.partition_confirm, self.preview_btn, self.stage_btn):
            w.setEnabled(enabled)

    def _update_partition_visibility(self) -> None:
        deep = self.depth.currentData() in {"advanced", "expert"}
        self.partitioning.setEnabled(deep and self.stage_btn.isEnabled())
        self.partition_confirm.setEnabled(deep and self.stage_btn.isEnabled())
        if not deep:
            self.partitioning.setCurrentIndex(0); self.partition_confirm.setChecked(False)

    def _update_network_visibility(self) -> None:
        static = self.network_mode.currentData() == "static"
        for w in (self.ipv4, self.gateway, self.dns):
            w.setEnabled(static and self.stage_btn.isEnabled())

    def _payload(self) -> dict:
        cap = self.capability
        groups = [x.strip() for x in self.groups.text().split(",") if x.strip()]
        packages = [x.strip() for x in self.packages.text().split(",") if x.strip()]
        dns = [x.strip() for x in self.dns.text().split(",") if x.strip()]
        partitioning = self.partitioning.currentData() if self.depth.currentData() in {"advanced", "expert"} else "preserve_installer_default"
        return {
            "config_type": "part5_installer_profile", "part": 5, "gate_version": "part5-complete",
            "source_sha256": str(self.analysis.get("sha256") or "").strip().casefold(),
            "analysis_scope": str(cap.get("analysis_scope") or ""), "capability_status": str(cap.get("capability_status") or "UNKNOWN"),
            "installer_family": str(cap.get("installer_family") or ""), "native_generator": str(cap.get("native_generator") or ""),
            "control_depth": str(self.depth.currentData()), "username": self.username.text().strip(), "display_name": self.display_name.text().strip(),
            "groups": groups, "admin": self.admin.isChecked(), "credential_policy": "secure_hash_deferred_to_verified_apply",
            "hostname": self.hostname.text().strip(), "language": self.language.text().strip(), "locale": self.locale.text().strip(),
            "keyboard": self.keyboard.text().strip(), "timezone": self.timezone.text().strip(), "network_mode": str(self.network_mode.currentData()),
            "ipv4_address": self.ipv4.text().strip(), "gateway": self.gateway.text().strip(), "dns_servers": dns,
            "package_selections": packages, "installer_profile": str(self.profile.currentData()), "installation_behavior": str(self.behavior.currentData()),
            "partitioning": str(partitioning), "destructive_partitioning_confirmed": self.partition_confirm.isChecked(),
            "credential_secret_read": False, "credential_secret_staged": False, "native_tool_validation_performed": False,
            "require_native_tool_validation_before_apply": True, "require_secure_credential_material_before_apply": True,
            "require_source_reverification_before_apply": True, "source_read_only": True, "preserve_unrelated": True, "stage_only": True,
        }

    def _preview(self) -> None:
        payload = self._payload(); ok, message = validate_installer_payload(payload)
        if not ok:
            self.preview.clear(); self.status.setText(f"BLOCKED — {message}"); return
        text = generate_installer_template(payload); self.preview.setPlainText(text); self.status.setText(f"VALIDATED FOR STAGING — {message}")

    def _stage(self) -> None:
        payload = self._payload(); ok, message = validate_installer_payload(payload)
        if not ok:
            self.status.setText(f"BLOCKED — {message}"); QMessageBox.warning(self, "Installer profile blocked", message); return
        payload["generated_native_template"] = generate_installer_template(payload)
        payload["generated_template_contains_real_secret"] = False
        detail = f"{payload['installer_family']} / {payload['native_generator']} structured profile; secure credential and native-tool validation deferred to verified apply."
        self.stage_requested.emit(ChangeItem("Part 5 installer profile", ChangeKind.CONFIG, detail, payload))
        self.status.setText("STAGED — review in Changes. Source ISO remains read-only.")

    def set_analysis(self, data: dict) -> None:
        self.analysis = dict(data or {}); self.capability = dict(data.get("part5_installer_evidence") or {})
        family = str(data.get("installer") or "unknown"); sha = str(data.get("sha256") or "")
        evidence = list(data.get("installer_evidence") or []); configs = [str(x) for x in (data.get("installer_config_files") or []) if str(x).strip()]
        modes = [str(x) for x in (data.get("installer_modes") or []) if str(x).strip()]
        self.family_value.setText("Unknown / no explicit installer evidence" if family.casefold() == "unknown" else family)
        self.mode_value.setText("; ".join(modes) if modes else "No installer capability claimed without explicit evidence")
        self.config_value.setText("\n".join(configs) if configs else "No ISO-level installer configuration files detected")
        status = str(self.capability.get("capability_status") or "UNKNOWN")
        generator = str(self.capability.get("native_generator") or "")
        self.capability_value.setText(f"{status}" + (f" — {generator}" if generator else ""))
        self.source_hash_value.setText(sha or "—")
        self.evidence_tree.clear()
        if evidence:
            root = QTreeWidgetItem([f"Manifest packages ({len(evidence)})", "Explicit package-manifest evidence"]); self.evidence_tree.addTopLevelItem(root)
            for item in evidence:
                root.addChild(QTreeWidgetItem([str(item.get("value") or ""), f"{item.get('version','')} • {item.get('family',family)}".strip(" •")]))
            root.setExpanded(True)
        if configs:
            cfg = QTreeWidgetItem([f"ISO config paths ({len(configs)})", "Read-only source paths"]); self.evidence_tree.addTopLevelItem(cfg)
            for path in configs: cfg.addChild(QTreeWidgetItem([path, "Preserved unless an explicit reviewed apply later replaces it"]))
            cfg.setExpanded(True)
        if not evidence and not configs:
            self.evidence_tree.addTopLevelItem(QTreeWidgetItem(["No explicit installer evidence detected", "Structured installer staging remains fail-closed"]))
        enabled = status in {"SUPPORTED", "SUPPORTED_WITH_REQUIREMENTS"} and bool(generator) and bool(sha)
        self._set_editor_enabled(enabled); self._update_partition_visibility(); self._update_network_visibility()

        # Preserve the established Alpha 35 read-only installer evidence contract
        # when Part 5 capability evidence is not present. Part 5 adds editing only
        # when its own verified capability object exists; it must not regress the
        # older evidence-only view used by Parts 1-4 regression acceptance.
        if not self.capability:
            if not sha:
                reason = "Analyze a supported source ISO first."
            elif family.casefold() == "unknown":
                reason = "BLOCKED for editing — installer family is not verified from source evidence."
            else:
                reason = "READ-ONLY PASS — installer family is evidence-backed. Configuration editing remains gated to Part 5."
        else:
            reason = str(self.capability.get("reason") or "Part 5 installer capability is not verified.")
        self.status.setText(reason); self.preview.clear()
