from __future__ import annotations
from chromapress.i18n import tr
import ipaddress
import re
from collections import defaultdict
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QGroupBox, QFormLayout, QTreeWidget, QTreeWidgetItem, QHeaderView, QComboBox, QLineEdit, QPushButton, QHBoxLayout, QMessageBox
from chromapress.models import ChangeItem, ChangeKind

class SystemPage(QWidget):
    """Part 4 System Configuration with narrow read-only evidence/staging gates."""
    stage_requested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._analysis: dict = {}
        layout = QVBoxLayout(self)
        title = QLabel(tr('System'))
        title.setObjectName('pageTitle')
        layout.addWidget(title)
        intro = QLabel(tr('System configuration is preservation-first. Alpha 68 preserves all verified Alpha 37–64 gates and completes the planned Part 4 authenticator/security sequence with security-key, YubiKey-class, platform-authenticator and TPM-backed key-protection gates. Every capability remains evidence-driven and fail-closed; no physical authenticator, biometric sensor or TPM hardware is inferred from package metadata.'))
        intro.setWordWrap(True)
        layout.addWidget(intro)
        banner = QLabel(tr('SOURCE READ-ONLY — Part 4 completion gates use target ISO/rootfs/package evidence only. Security-key and YubiKey-class gates never claim physical device presence; the platform-authenticator gate remains UNKNOWN without runtime hardware verification; TPM policy never equates TPM with biometrics and never claims TPM hardware from package metadata. The selected ISO is never mutated during analysis/staging.'))
        banner.setStyleSheet('QLabel { background: #eef4fa; border: 1px solid #c9d7e5; border-radius: 5px; padding: 8px; }')
        banner.setWordWrap(True)
        layout.addWidget(banner)
        summary_box = QGroupBox(tr('System configuration evidence'))
        form = QFormLayout(summary_box)
        self.package_format_value = QLabel(tr('Analyze a source ISO first.'))
        self.areas_value = QLabel(tr('—'))
        self.areas_value.setWordWrap(True)
        self.rootfs_value = QLabel(tr('—'))
        self.rootfs_value.setWordWrap(True)
        self.source_hash_value = QLabel(tr('—'))
        self.source_hash_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow(tr('Package family:'), self.package_format_value)
        form.addRow(tr('Evidence-backed areas:'), self.areas_value)
        form.addRow(tr('Remaining rootfs gates:'), self.rootfs_value)
        form.addRow(tr('Source SHA-256:'), self.source_hash_value)
        layout.addWidget(summary_box)
        identity_evidence_box = QGroupBox(tr('Identity / accounts rootfs evidence'))
        identity_evidence_form = QFormLayout(identity_evidence_box)
        self.identity_status_value = QLabel(tr('Analyze a source ISO first.'))
        self.identity_status_value.setWordWrap(True)
        self.identity_layers_value = QLabel(tr('—'))
        self.identity_layers_value.setWordWrap(True)
        self.identity_users_value = QLabel(tr('—'))
        self.identity_users_value.setWordWrap(True)
        self.identity_admin_groups_value = QLabel(tr('—'))
        self.identity_admin_groups_value.setWordWrap(True)
        self.identity_uid_min_value = QLabel(tr('—'))
        self.identity_capability_value = QLabel(tr('UNKNOWN'))
        self.identity_capability_value.setWordWrap(True)
        self.identity_default_user_value = QLabel(tr('—'))
        self.identity_password_policy_value = QLabel(tr('—'))
        self.identity_password_policy_value.setWordWrap(True)
        identity_evidence_form.addRow(tr('Verification:'), self.identity_status_value)
        identity_evidence_form.addRow(tr('Capability:'), self.identity_capability_value)
        identity_evidence_form.addRow(tr('Account database layer(s):'), self.identity_layers_value)
        identity_evidence_form.addRow(tr('Detected regular users:'), self.identity_users_value)
        identity_evidence_form.addRow(tr('Default-user candidate:'), self.identity_default_user_value)
        identity_evidence_form.addRow(tr('Admin-group candidates:'), self.identity_admin_groups_value)
        identity_evidence_form.addRow(tr('UID_MIN:'), self.identity_uid_min_value)
        identity_evidence_form.addRow(tr('Password-aging defaults:'), self.identity_password_policy_value)
        layout.addWidget(identity_evidence_box)
        plan_box = QGroupBox(tr('Users / Groups / Password Policy plan — staged only'))
        plan_form = QFormLayout(plan_box)
        plan_form.setVerticalSpacing(5)
        self.identity_depth = QComboBox()
        self.identity_depth.addItem(tr('Quick — safe normal user settings'), 'quick')
        self.identity_depth.addItem(tr('Advanced — UID/GID, groups and password aging'), 'advanced')
        self.identity_depth.addItem(tr('Expert — explicit low-level account planning'), 'expert')
        self.identity_operation = QComboBox()
        self.identity_operation.addItem(tr('Preserve existing users/groups/password policy'), 'preserve')
        self.identity_operation.addItem(tr('Configure target-system default user'), 'configure_default_user')
        self.identity_operation.addItem(tr('Create target-system user'), 'create_user')
        self.identity_operation.addItem(tr('Modify existing target-system user'), 'modify_user')
        self.identity_username = QLineEdit()
        self.identity_username.setPlaceholderText(tr('lowercase Linux username, e.g. chromatest'))
        self.identity_display_name = QLineEdit()
        self.identity_display_name.setPlaceholderText(tr('Optional display/full name; blank preserves existing value when modifying'))
        self.identity_role = QComboBox()
        self.identity_role.addItem(tr('Preserve existing role/group membership'), 'preserve')
        self.identity_role.addItem(tr('Standard user'), 'standard')
        self.identity_role.addItem(tr('Administrator via verified distro admin group'), 'administrator')
        self.identity_admin_group = QComboBox()
        self.identity_admin_group.addItem(tr('No verified admin group'), '')
        self.identity_advanced_box = QGroupBox(tr('Advanced / Expert account options'))
        identity_advanced_form = QFormLayout(self.identity_advanced_box)
        self.identity_uid = QLineEdit()
        self.identity_uid.setPlaceholderText(tr('Optional numeric UID; blank = preserve/automatic'))
        self.identity_gid = QLineEdit()
        self.identity_gid.setPlaceholderText(tr('Optional numeric primary GID; blank = preserve/automatic'))
        self.identity_supplementary_groups = QLineEdit()
        self.identity_supplementary_groups.setPlaceholderText(tr('Existing groups only, comma-separated; blank = preserve/none for new user'))
        self.identity_group_name = QLineEdit()
        self.identity_group_name.setPlaceholderText(tr('New group name (Create group operation only)'))
        self.identity_group_gid = QLineEdit()
        self.identity_group_gid.setPlaceholderText(tr('Optional numeric GID; blank = automatic'))
        self.identity_password_min_days = QLineEdit()
        self.identity_password_min_days.setPlaceholderText(tr('PASS_MIN_DAYS; blank = preserve'))
        self.identity_password_max_days = QLineEdit()
        self.identity_password_max_days.setPlaceholderText(tr('PASS_MAX_DAYS; blank = preserve'))
        self.identity_password_warn_days = QLineEdit()
        self.identity_password_warn_days.setPlaceholderText(tr('PASS_WARN_AGE; blank = preserve'))
        identity_advanced_form.addRow(tr('Target UID:'), self.identity_uid)
        identity_advanced_form.addRow(tr('Target primary GID:'), self.identity_gid)
        identity_advanced_form.addRow(tr('Supplementary groups:'), self.identity_supplementary_groups)
        identity_advanced_form.addRow(tr('New group name:'), self.identity_group_name)
        identity_advanced_form.addRow(tr('New group GID:'), self.identity_group_gid)
        identity_advanced_form.addRow(tr('Password min days:'), self.identity_password_min_days)
        identity_advanced_form.addRow(tr('Password max days:'), self.identity_password_max_days)
        identity_advanced_form.addRow(tr('Password warning days:'), self.identity_password_warn_days)
        self.credential_policy_value = QLabel(tr('No password, hash, token or recovery secret is entered, read or stored here; credential assignment remains a separate secure apply-time requirement.'))
        self.credential_policy_value.setWordWrap(True)
        plan_form.addRow(tr('Control depth:'), self.identity_depth)
        plan_form.addRow(tr('Requested operation:'), self.identity_operation)
        plan_form.addRow(tr('Username:'), self.identity_username)
        plan_form.addRow(tr('Display/full name:'), self.identity_display_name)
        plan_form.addRow(tr('Account role:'), self.identity_role)
        plan_form.addRow(tr('Admin group:'), self.identity_admin_group)
        plan_form.addRow(self.identity_advanced_box)
        plan_form.addRow(tr('Credential safety:'), self.credential_policy_value)
        controls = QHBoxLayout()
        self.stage_identity_btn = QPushButton(tr('Stage users/groups/password-policy plan'))
        self.reset_identity_btn = QPushButton(tr('Reset'))
        self.identity_plan_status = QLabel(tr('Ready — no users/groups/password-policy changes staged.'))
        self.identity_plan_status.setWordWrap(True)
        controls.addWidget(self.stage_identity_btn)
        controls.addWidget(self.reset_identity_btn)
        controls.addWidget(self.identity_plan_status, 1)
        plan_form.addRow(tr(''), controls)
        layout.addWidget(plan_box)
        machine_evidence_box = QGroupBox(tr('Hostname / machine identity rootfs evidence'))
        machine_evidence_form = QFormLayout(machine_evidence_box)
        self.machine_status_value = QLabel(tr('Analyze a source ISO first.'))
        self.machine_status_value.setWordWrap(True)
        self.machine_hostname_value = QLabel(tr('—'))
        self.machine_hostname_layer_value = QLabel(tr('—'))
        self.machine_hostname_layer_value.setWordWrap(True)
        self.machine_id_state_value = QLabel(tr('—'))
        self.machine_id_layer_value = QLabel(tr('—'))
        self.machine_id_layer_value.setWordWrap(True)
        machine_evidence_form.addRow(tr('Verification:'), self.machine_status_value)
        machine_evidence_form.addRow(tr('Detected hostname:'), self.machine_hostname_value)
        machine_evidence_form.addRow(tr('Hostname layer:'), self.machine_hostname_layer_value)
        machine_evidence_form.addRow(tr('Machine-id state:'), self.machine_id_state_value)
        machine_evidence_form.addRow(tr('Machine-id layer:'), self.machine_id_layer_value)
        layout.addWidget(machine_evidence_box)
        machine_plan_box = QGroupBox(tr('Hostname / machine identity plan — staged only'))
        machine_plan_form = QFormLayout(machine_plan_box)
        machine_plan_form.setVerticalSpacing(5)
        self.machine_operation = QComboBox()
        self.machine_operation.addItem(tr('Preserve existing hostname / machine identity'), 'preserve')
        self.machine_operation.addItem(tr('Configure target-system hostname'), 'configure_hostname')
        self.machine_hostname = QLineEdit()
        self.machine_hostname.setPlaceholderText(tr('lowercase hostname, e.g. chromalinux'))
        self.machine_id_policy = QComboBox()
        self.machine_id_policy.addItem(tr('Preserve current machine-id boot behavior'), 'preserve')
        self.machine_id_policy.addItem(tr('Regenerate machine-id on first boot'), 'regenerate_on_first_boot')
        self.machine_id_safety_value = QLabel(tr('The current machine-id value is never displayed or stored in this staged plan.'))
        self.machine_id_safety_value.setWordWrap(True)
        machine_plan_form.addRow(tr('Requested operation:'), self.machine_operation)
        machine_plan_form.addRow(tr('Target hostname:'), self.machine_hostname)
        machine_plan_form.addRow(tr('Machine-id policy:'), self.machine_id_policy)
        machine_plan_form.addRow(tr('Machine-id safety:'), self.machine_id_safety_value)
        machine_controls = QHBoxLayout()
        self.stage_machine_btn = QPushButton(tr('Stage machine identity plan'))
        self.reset_machine_btn = QPushButton(tr('Reset'))
        self.machine_plan_status = QLabel(tr('Ready — no hostname/machine identity changes staged.'))
        self.machine_plan_status.setWordWrap(True)
        machine_controls.addWidget(self.stage_machine_btn)
        machine_controls.addWidget(self.reset_machine_btn)
        machine_controls.addWidget(self.machine_plan_status, 1)
        machine_plan_form.addRow(tr(''), machine_controls)
        layout.addWidget(machine_plan_box)
        autologin_evidence_box = QGroupBox(tr('Autologin / display manager rootfs evidence'))
        autologin_evidence_form = QFormLayout(autologin_evidence_box)
        self.autologin_status_value = QLabel(tr('Analyze a source ISO first.'))
        self.autologin_status_value.setWordWrap(True)
        self.autologin_dm_value = QLabel(tr('—'))
        self.autologin_dm_layer_value = QLabel(tr('—'))
        self.autologin_dm_layer_value.setWordWrap(True)
        self.autologin_state_value = QLabel(tr('—'))
        self.autologin_user_value = QLabel(tr('—'))
        autologin_evidence_form.addRow(tr('Verification:'), self.autologin_status_value)
        autologin_evidence_form.addRow(tr('Display manager:'), self.autologin_dm_value)
        autologin_evidence_form.addRow(tr('Evidence layer:'), self.autologin_dm_layer_value)
        autologin_evidence_form.addRow(tr('Explicit autologin state:'), self.autologin_state_value)
        autologin_evidence_form.addRow(tr('Explicit autologin user:'), self.autologin_user_value)
        layout.addWidget(autologin_evidence_box)
        autologin_plan_box = QGroupBox(tr('Autologin plan — staged only'))
        autologin_plan_form = QFormLayout(autologin_plan_box)
        autologin_plan_form.setVerticalSpacing(5)
        self.autologin_operation = QComboBox()
        self.autologin_operation.addItem(tr('Preserve existing autologin policy'), 'preserve')
        self.autologin_operation.addItem(tr('Enable autologin for target user'), 'enable_autologin')
        self.autologin_operation.addItem(tr('Disable autologin'), 'disable_autologin')
        self.autologin_target_user = QLineEdit()
        self.autologin_target_user.setPlaceholderText(tr('lowercase Linux username, e.g. chromatest'))
        self.autologin_session_policy_value = QLabel(tr("Preserve the display manager's current/default session; verify the target user again before apply."))
        self.autologin_session_policy_value.setWordWrap(True)
        self.autologin_safety_value = QLabel(tr('Autologin bypasses interactive login for the selected user. No password, hash, token or credential secret is read or staged.'))
        self.autologin_safety_value.setWordWrap(True)
        autologin_plan_form.addRow(tr('Requested operation:'), self.autologin_operation)
        autologin_plan_form.addRow(tr('Target user:'), self.autologin_target_user)
        autologin_plan_form.addRow(tr('Session policy:'), self.autologin_session_policy_value)
        autologin_plan_form.addRow(tr('Security:'), self.autologin_safety_value)
        autologin_controls = QHBoxLayout()
        self.stage_autologin_btn = QPushButton(tr('Stage autologin plan'))
        self.reset_autologin_btn = QPushButton(tr('Reset'))
        self.autologin_plan_status = QLabel(tr('Ready — no autologin changes staged.'))
        self.autologin_plan_status.setWordWrap(True)
        autologin_controls.addWidget(self.stage_autologin_btn)
        autologin_controls.addWidget(self.reset_autologin_btn)
        autologin_controls.addWidget(self.autologin_plan_status, 1)
        autologin_plan_form.addRow(tr(''), autologin_controls)
        layout.addWidget(autologin_plan_box)
        locale_evidence_box = QGroupBox(tr('Locale / language rootfs evidence'))
        locale_evidence_form = QFormLayout(locale_evidence_box)
        self.locale_status_value = QLabel(tr('Analyze a source ISO first.'))
        self.locale_status_value.setWordWrap(True)
        self.locale_path_value = QLabel(tr('—'))
        self.locale_layer_value = QLabel(tr('—'))
        self.locale_layer_value.setWordWrap(True)
        self.locale_lang_value = QLabel(tr('—'))
        self.locale_language_value = QLabel(tr('—'))
        locale_evidence_form.addRow(tr('Verification:'), self.locale_status_value)
        locale_evidence_form.addRow(tr('Configuration evidence:'), self.locale_path_value)
        locale_evidence_form.addRow(tr('Evidence layer:'), self.locale_layer_value)
        locale_evidence_form.addRow(tr('Current LANG:'), self.locale_lang_value)
        locale_evidence_form.addRow(tr('Current LANGUAGE:'), self.locale_language_value)
        layout.addWidget(locale_evidence_box)
        locale_plan_box = QGroupBox(tr('Locale / language plan — staged only'))
        locale_plan_form = QFormLayout(locale_plan_box)
        locale_plan_form.setVerticalSpacing(5)
        self.locale_operation = QComboBox()
        self.locale_operation.addItem(tr('Preserve existing locale/language'), 'preserve')
        self.locale_operation.addItem(tr('Configure target-system LANG'), 'configure_lang')
        self.locale_target = QLineEdit()
        self.locale_target.setPlaceholderText(tr('locale identifier, e.g. da_DK.UTF-8'))
        self.locale_policy_value = QLabel(tr('Set LANG only. Preserve existing LANGUAGE and LC_* overrides unless a later explicit gate changes them.'))
        self.locale_policy_value.setWordWrap(True)
        self.locale_safety_value = QLabel(tr('Target locale availability must be verified again before apply. No credential secret is read or staged.'))
        self.locale_safety_value.setWordWrap(True)
        locale_plan_form.addRow(tr('Requested operation:'), self.locale_operation)
        locale_plan_form.addRow(tr('Target LANG:'), self.locale_target)
        locale_plan_form.addRow(tr('Override policy:'), self.locale_policy_value)
        locale_plan_form.addRow(tr('Safety:'), self.locale_safety_value)
        locale_controls = QHBoxLayout()
        self.stage_locale_btn = QPushButton(tr('Stage locale plan'))
        self.reset_locale_btn = QPushButton(tr('Reset'))
        self.locale_plan_status = QLabel(tr('Ready — no locale/language changes staged.'))
        self.locale_plan_status.setWordWrap(True)
        locale_controls.addWidget(self.stage_locale_btn)
        locale_controls.addWidget(self.reset_locale_btn)
        locale_controls.addWidget(self.locale_plan_status, 1)
        locale_plan_form.addRow(tr(''), locale_controls)
        layout.addWidget(locale_plan_box)
        keyboard_evidence_box = QGroupBox(tr('Keyboard layout rootfs evidence'))
        keyboard_evidence_form = QFormLayout(keyboard_evidence_box)
        self.keyboard_status_value = QLabel(tr('Analyze a source ISO first.'))
        self.keyboard_status_value.setWordWrap(True)
        self.keyboard_path_value = QLabel(tr('—'))
        self.keyboard_layer_value = QLabel(tr('—'))
        self.keyboard_layer_value.setWordWrap(True)
        self.keyboard_layout_value = QLabel(tr('—'))
        self.keyboard_model_value = QLabel(tr('—'))
        self.keyboard_variant_value = QLabel(tr('—'))
        keyboard_evidence_form.addRow(tr('Verification:'), self.keyboard_status_value)
        keyboard_evidence_form.addRow(tr('Configuration evidence:'), self.keyboard_path_value)
        keyboard_evidence_form.addRow(tr('Evidence layer:'), self.keyboard_layer_value)
        keyboard_evidence_form.addRow(tr('Current layout:'), self.keyboard_layout_value)
        keyboard_evidence_form.addRow(tr('Current model:'), self.keyboard_model_value)
        keyboard_evidence_form.addRow(tr('Current variant:'), self.keyboard_variant_value)
        layout.addWidget(keyboard_evidence_box)
        keyboard_plan_box = QGroupBox(tr('Keyboard layout plan — staged only'))
        keyboard_plan_form = QFormLayout(keyboard_plan_box)
        keyboard_plan_form.setVerticalSpacing(5)
        self.keyboard_operation = QComboBox()
        self.keyboard_operation.addItem(tr('Preserve existing keyboard configuration'), 'preserve')
        self.keyboard_operation.addItem(tr('Configure target-system keyboard layout'), 'configure_layout')
        self.keyboard_target = QLineEdit()
        self.keyboard_target.setPlaceholderText(tr('XKB layout identifier, e.g. dk'))
        self.keyboard_policy_value = QLabel(tr('Set the primary layout only. Preserve existing model, variant and options unless a later explicit gate changes them.'))
        self.keyboard_policy_value.setWordWrap(True)
        self.keyboard_safety_value = QLabel(tr('Target layout availability must be verified again before apply. No credential secret is read or staged.'))
        self.keyboard_safety_value.setWordWrap(True)
        keyboard_plan_form.addRow(tr('Requested operation:'), self.keyboard_operation)
        keyboard_plan_form.addRow(tr('Target layout:'), self.keyboard_target)
        keyboard_plan_form.addRow(tr('Preservation policy:'), self.keyboard_policy_value)
        keyboard_plan_form.addRow(tr('Safety:'), self.keyboard_safety_value)
        keyboard_controls = QHBoxLayout()
        self.stage_keyboard_btn = QPushButton(tr('Stage keyboard plan'))
        self.reset_keyboard_btn = QPushButton(tr('Reset'))
        self.keyboard_plan_status = QLabel(tr('Ready — no keyboard-layout changes staged.'))
        self.keyboard_plan_status.setWordWrap(True)
        keyboard_controls.addWidget(self.stage_keyboard_btn)
        keyboard_controls.addWidget(self.reset_keyboard_btn)
        keyboard_controls.addWidget(self.keyboard_plan_status, 1)
        keyboard_plan_form.addRow(tr(''), keyboard_controls)
        layout.addWidget(keyboard_plan_box)
        timezone_evidence_box = QGroupBox(tr('Timezone rootfs evidence'))
        timezone_evidence_form = QFormLayout(timezone_evidence_box)
        self.timezone_status_value = QLabel(tr('Analyze a source ISO first.'))
        self.timezone_status_value.setWordWrap(True)
        self.timezone_path_value = QLabel(tr('—'))
        self.timezone_layer_value = QLabel(tr('—'))
        self.timezone_layer_value.setWordWrap(True)
        self.timezone_current_value = QLabel(tr('—'))
        timezone_evidence_form.addRow(tr('Verification:'), self.timezone_status_value)
        timezone_evidence_form.addRow(tr('Configuration evidence:'), self.timezone_path_value)
        timezone_evidence_form.addRow(tr('Evidence layer:'), self.timezone_layer_value)
        timezone_evidence_form.addRow(tr('Current timezone:'), self.timezone_current_value)
        layout.addWidget(timezone_evidence_box)
        timezone_plan_box = QGroupBox(tr('Timezone plan — staged only'))
        timezone_plan_form = QFormLayout(timezone_plan_box)
        timezone_plan_form.setVerticalSpacing(5)
        self.timezone_operation = QComboBox()
        self.timezone_operation.addItem(tr('Preserve existing timezone'), 'preserve')
        self.timezone_operation.addItem(tr('Configure target-system timezone'), 'configure_timezone')
        self.timezone_target = QLineEdit()
        self.timezone_target.setPlaceholderText(tr('IANA timezone, e.g. Europe/Copenhagen'))
        self.timezone_policy_value = QLabel(tr('Set the target timezone only. Preserve hardware-clock/RTC policy and unrelated regional settings.'))
        self.timezone_policy_value.setWordWrap(True)
        self.timezone_safety_value = QLabel(tr('Target zoneinfo availability must be verified again before apply. No credential secret is read or staged.'))
        self.timezone_safety_value.setWordWrap(True)
        timezone_plan_form.addRow(tr('Requested operation:'), self.timezone_operation)
        timezone_plan_form.addRow(tr('Target timezone:'), self.timezone_target)
        timezone_plan_form.addRow(tr('Preservation policy:'), self.timezone_policy_value)
        timezone_plan_form.addRow(tr('Safety:'), self.timezone_safety_value)
        timezone_controls = QHBoxLayout()
        self.stage_timezone_btn = QPushButton(tr('Stage timezone plan'))
        self.reset_timezone_btn = QPushButton(tr('Reset'))
        self.timezone_plan_status = QLabel(tr('Ready — no timezone changes staged.'))
        self.timezone_plan_status.setWordWrap(True)
        timezone_controls.addWidget(self.stage_timezone_btn)
        timezone_controls.addWidget(self.reset_timezone_btn)
        timezone_controls.addWidget(self.timezone_plan_status, 1)
        timezone_plan_form.addRow(tr(''), timezone_controls)
        layout.addWidget(timezone_plan_box)
        network_evidence_box = QGroupBox(tr('Networking / NetworkManager / DNS rootfs evidence'))
        network_evidence_form = QFormLayout(network_evidence_box)
        self.network_status_value = QLabel(tr('Analyze a source ISO first.'))
        self.network_status_value.setWordWrap(True)
        self.network_capability_value = QLabel(tr('UNKNOWN'))
        self.network_capability_value.setWordWrap(True)
        self.network_backend_value = QLabel(tr('—'))
        self.network_backend_path_value = QLabel(tr('—'))
        self.network_backend_layer_value = QLabel(tr('—'))
        self.network_backend_layer_value.setWordWrap(True)
        self.network_managed_path_value = QLabel(tr('—'))
        self.network_resolver_path_value = QLabel(tr('—'))
        self.network_resolver_layer_value = QLabel(tr('—'))
        self.network_resolver_layer_value.setWordWrap(True)
        self.network_profiles_value = QLabel(tr('—'))
        self.network_profiles_value.setWordWrap(True)
        network_evidence_form.addRow(tr('Verification:'), self.network_status_value)
        network_evidence_form.addRow(tr('Capability:'), self.network_capability_value)
        network_evidence_form.addRow(tr('Network backend:'), self.network_backend_value)
        network_evidence_form.addRow(tr('Backend evidence:'), self.network_backend_path_value)
        network_evidence_form.addRow(tr('Backend layer:'), self.network_backend_layer_value)
        network_evidence_form.addRow(tr('Managed target path:'), self.network_managed_path_value)
        network_evidence_form.addRow(tr('Resolver evidence:'), self.network_resolver_path_value)
        network_evidence_form.addRow(tr('Resolver layer:'), self.network_resolver_layer_value)
        network_evidence_form.addRow(tr('NetworkManager profiles (metadata only):'), self.network_profiles_value)
        layout.addWidget(network_evidence_box)
        network_plan_box = QGroupBox(tr('Networking / NetworkManager / DNS plan — staged only'))
        network_plan_form = QFormLayout(network_plan_box)
        network_plan_form.setVerticalSpacing(5)
        self.network_depth = QComboBox()
        self.network_depth.addItem(tr('Quick — DHCP and DNS'), 'quick')
        self.network_depth.addItem(tr('Advanced — static IPv4 and NetworkManager profiles'), 'advanced')
        self.network_depth.addItem(tr('Expert — explicit verified target/profile planning'), 'expert')
        self.network_operation = QComboBox()
        self.network_profile_name = QLineEdit()
        self.network_profile_name.setPlaceholderText(tr('Managed profile name, e.g. ChromaPress Ethernet'))
        self.network_profile_name.setText(tr('ChromaPress Ethernet'))
        self.network_existing_profile = QComboBox()
        self.network_existing_profile.addItem(tr('No verified existing NetworkManager profile'), '')
        self.network_interface = QLineEdit()
        self.network_interface.setPlaceholderText(tr('Optional target interface, e.g. enp1s0'))
        self.network_ipv4_address = QLineEdit()
        self.network_ipv4_address.setPlaceholderText(tr('Static IPv4/prefix, e.g. 192.168.1.50/24'))
        self.network_gateway = QLineEdit()
        self.network_gateway.setPlaceholderText(tr('IPv4 gateway, e.g. 192.168.1.1'))
        self.network_dns_target = QLineEdit()
        self.network_dns_target.setPlaceholderText(tr('IPv4 DNS only, e.g. 1.1.1.1, 1.0.0.1'))
        self.network_autoconnect = QComboBox()
        self.network_autoconnect.addItem(tr('Enable autoconnect'), True)
        self.network_autoconnect.addItem(tr('Disable autoconnect'), False)
        self.network_policy_value = QLabel(tr('Preserve existing profiles/routes/addressing unless explicitly targeted. Alpha 51 creates a dedicated managed fragment/keyfile for new DHCP/static configuration rather than overwriting unknown custom network content.'))
        self.network_policy_value.setWordWrap(True)
        self.network_safety_value = QLabel(tr('IPv6 is intentionally not exposed in Alpha 51. Existing NetworkManager profile contents, netplan YAML and Wi-Fi/VPN credentials are never read. Host networking is never used as a fallback.'))
        self.network_safety_value.setWordWrap(True)
        self.network_hostname_note = QLabel(tr('Hostname remains controlled by the existing Hostname / machine identity gate and is preserved by this networking plan.'))
        self.network_hostname_note.setWordWrap(True)
        network_plan_form.addRow(tr('Control depth:'), self.network_depth)
        network_plan_form.addRow(tr('Requested operation:'), self.network_operation)
        network_plan_form.addRow(tr('Managed profile name:'), self.network_profile_name)
        network_plan_form.addRow(tr('Existing NM profile:'), self.network_existing_profile)
        network_plan_form.addRow(tr('Target interface:'), self.network_interface)
        network_plan_form.addRow(tr('Static IPv4/prefix:'), self.network_ipv4_address)
        network_plan_form.addRow(tr('Gateway:'), self.network_gateway)
        network_plan_form.addRow(tr('DNS servers:'), self.network_dns_target)
        network_plan_form.addRow(tr('Profile autoconnect:'), self.network_autoconnect)
        network_plan_form.addRow(tr('Hostname:'), self.network_hostname_note)
        network_plan_form.addRow(tr('Preservation policy:'), self.network_policy_value)
        network_plan_form.addRow(tr('Safety:'), self.network_safety_value)
        network_controls = QHBoxLayout()
        self.stage_network_btn = QPushButton(tr('Stage networking plan'))
        self.reset_network_btn = QPushButton(tr('Reset'))
        self.network_plan_status = QLabel(tr('Ready — no networking changes staged.'))
        self.network_plan_status.setWordWrap(True)
        network_controls.addWidget(self.stage_network_btn)
        network_controls.addWidget(self.reset_network_btn)
        network_controls.addWidget(self.network_plan_status, 1)
        network_plan_form.addRow(tr(''), network_controls)
        layout.addWidget(network_plan_box)
        services_evidence_box = QGroupBox(tr('Services / systemd rootfs evidence'))
        services_evidence_form = QFormLayout(services_evidence_box)
        self.services_status_value = QLabel(tr('Analyze a source ISO first.'))
        self.services_status_value.setWordWrap(True)
        self.services_init_value = QLabel(tr('—'))
        self.services_vendor_path_value = QLabel(tr('—'))
        self.services_vendor_layer_value = QLabel(tr('—'))
        self.services_vendor_layer_value.setWordWrap(True)
        self.services_local_path_value = QLabel(tr('—'))
        services_evidence_form.addRow(tr('Verification:'), self.services_status_value)
        services_evidence_form.addRow(tr('Init/service manager:'), self.services_init_value)
        services_evidence_form.addRow(tr('Vendor unit directory:'), self.services_vendor_path_value)
        services_evidence_form.addRow(tr('Evidence layer:'), self.services_vendor_layer_value)
        services_evidence_form.addRow(tr('Local unit directory:'), self.services_local_path_value)
        layout.addWidget(services_evidence_box)
        services_plan_box = QGroupBox(tr('Services / systemd plan — staged only'))
        services_plan_form = QFormLayout(services_plan_box)
        services_plan_form.setVerticalSpacing(5)
        self.services_operation = QComboBox()
        self.services_operation.addItem(tr('Preserve existing service startup policy'), 'preserve')
        self.services_operation.addItem(tr('Enable target service at startup'), 'enable_service')
        self.services_operation.addItem(tr('Disable target service at startup'), 'disable_service')
        self.services_target = QLineEdit()
        self.services_target.setPlaceholderText(tr('systemd service unit, e.g. NetworkManager.service'))
        self.services_policy_value = QLabel(tr('Stage only one service enable/disable intent; preserve unit file contents, timers, targets and unrelated startup policy.'))
        self.services_policy_value.setWordWrap(True)
        self.services_safety_value = QLabel(tr('Unit contents, enablement symlink targets, environment files and service credentials are not read. Target-unit existence must be re-verified before apply.'))
        self.services_safety_value.setWordWrap(True)
        services_plan_form.addRow(tr('Requested operation:'), self.services_operation)
        services_plan_form.addRow(tr('Target service unit:'), self.services_target)
        services_plan_form.addRow(tr('Preservation policy:'), self.services_policy_value)
        services_plan_form.addRow(tr('Safety:'), self.services_safety_value)
        services_controls = QHBoxLayout()
        self.stage_services_btn = QPushButton(tr('Stage services/systemd plan'))
        self.reset_services_btn = QPushButton(tr('Reset'))
        self.services_plan_status = QLabel(tr('Ready — no services/systemd changes staged.'))
        self.services_plan_status.setWordWrap(True)
        services_controls.addWidget(self.stage_services_btn)
        services_controls.addWidget(self.reset_services_btn)
        services_controls.addWidget(self.services_plan_status, 1)
        services_plan_form.addRow(tr(''), services_controls)
        layout.addWidget(services_plan_box)
        timers_evidence_box = QGroupBox(tr('Timers / systemd rootfs evidence'))
        timers_evidence_form = QFormLayout(timers_evidence_box)
        self.timers_status_value = QLabel(tr('Analyze a source ISO first.'))
        self.timers_status_value.setWordWrap(True)
        self.timers_init_value = QLabel(tr('—'))
        self.timers_vendor_path_value = QLabel(tr('—'))
        self.timers_vendor_layer_value = QLabel(tr('—'))
        self.timers_vendor_layer_value.setWordWrap(True)
        timers_evidence_form.addRow(tr('Verification:'), self.timers_status_value)
        timers_evidence_form.addRow(tr('Init/service manager:'), self.timers_init_value)
        timers_evidence_form.addRow(tr('Timer unit directory:'), self.timers_vendor_path_value)
        timers_evidence_form.addRow(tr('Evidence layer:'), self.timers_vendor_layer_value)
        layout.addWidget(timers_evidence_box)
        timers_plan_box = QGroupBox(tr('Timers / systemd plan — staged only'))
        timers_plan_form = QFormLayout(timers_plan_box)
        timers_plan_form.setVerticalSpacing(5)
        self.timers_operation = QComboBox()
        self.timers_operation.addItem(tr('Preserve existing timer startup policy'), 'preserve')
        self.timers_operation.addItem(tr('Enable target timer'), 'enable_timer')
        self.timers_operation.addItem(tr('Disable target timer'), 'disable_timer')
        self.timers_target = QLineEdit()
        self.timers_target.setPlaceholderText(tr('systemd timer unit, e.g. apt-daily.timer'))
        self.timers_policy_value = QLabel(tr('Stage only one timer enable/disable intent; preserve timer file contents, services, targets and unrelated startup policy.'))
        self.timers_policy_value.setWordWrap(True)
        self.timers_safety_value = QLabel(tr('Timer contents, enablement symlink targets, environment files and service credentials are not read. Target-timer existence must be re-verified before apply.'))
        self.timers_safety_value.setWordWrap(True)
        timers_plan_form.addRow(tr('Requested operation:'), self.timers_operation)
        timers_plan_form.addRow(tr('Target timer unit:'), self.timers_target)
        timers_plan_form.addRow(tr('Preservation policy:'), self.timers_policy_value)
        timers_plan_form.addRow(tr('Safety:'), self.timers_safety_value)
        timers_controls = QHBoxLayout()
        self.stage_timers_btn = QPushButton(tr('Stage timers/systemd plan'))
        self.reset_timers_btn = QPushButton(tr('Reset'))
        self.timers_plan_status = QLabel(tr('Ready — no timers/systemd changes staged.'))
        self.timers_plan_status.setWordWrap(True)
        timers_controls.addWidget(self.stage_timers_btn)
        timers_controls.addWidget(self.reset_timers_btn)
        timers_controls.addWidget(self.timers_plan_status, 1)
        timers_plan_form.addRow(tr(''), timers_controls)
        layout.addWidget(timers_plan_box)
        targets_evidence_box = QGroupBox(tr('Targets / startup rootfs evidence'))
        targets_evidence_form = QFormLayout(targets_evidence_box)
        self.targets_status_value = QLabel(tr('Analyze a source ISO first.'))
        self.targets_status_value.setWordWrap(True)
        self.targets_init_value = QLabel(tr('—'))
        self.targets_vendor_path_value = QLabel(tr('—'))
        self.targets_vendor_layer_value = QLabel(tr('—'))
        self.targets_vendor_layer_value.setWordWrap(True)
        targets_evidence_form.addRow(tr('Verification:'), self.targets_status_value)
        targets_evidence_form.addRow(tr('Init/service manager:'), self.targets_init_value)
        targets_evidence_form.addRow(tr('Target unit directory:'), self.targets_vendor_path_value)
        targets_evidence_form.addRow(tr('Evidence layer:'), self.targets_vendor_layer_value)
        layout.addWidget(targets_evidence_box)
        targets_plan_box = QGroupBox(tr('Targets / startup plan — staged only'))
        targets_plan_form = QFormLayout(targets_plan_box)
        targets_plan_form.setVerticalSpacing(5)
        self.targets_operation = QComboBox()
        self.targets_operation.addItem(tr('Preserve existing default startup target'), 'preserve')
        self.targets_operation.addItem(tr('Set target-system default startup target'), 'set_default_target')
        self.targets_target = QLineEdit()
        self.targets_target.setPlaceholderText(tr('systemd target unit, e.g. graphical.target'))
        self.targets_policy_value = QLabel(tr('Stage only one default-target intent; preserve services, timers, unit contents and unrelated startup policy.'))
        self.targets_policy_value.setWordWrap(True)
        self.targets_safety_value = QLabel(tr('Target unit contents and the current default.target symlink target are not read. Target-unit existence must be re-verified before apply.'))
        self.targets_safety_value.setWordWrap(True)
        targets_plan_form.addRow(tr('Requested operation:'), self.targets_operation)
        targets_plan_form.addRow(tr('Target .target unit:'), self.targets_target)
        targets_plan_form.addRow(tr('Preservation policy:'), self.targets_policy_value)
        targets_plan_form.addRow(tr('Safety:'), self.targets_safety_value)
        targets_controls = QHBoxLayout()
        self.stage_targets_btn = QPushButton(tr('Stage targets/startup plan'))
        self.reset_targets_btn = QPushButton(tr('Reset'))
        self.targets_plan_status = QLabel(tr('Ready — no targets/startup changes staged.'))
        self.targets_plan_status.setWordWrap(True)
        targets_controls.addWidget(self.stage_targets_btn)
        targets_controls.addWidget(self.reset_targets_btn)
        targets_controls.addWidget(self.targets_plan_status, 1)
        targets_plan_form.addRow(tr(''), targets_controls)
        layout.addWidget(targets_plan_box)
        firewall_evidence_box = QGroupBox(tr('Firewall rootfs evidence'))
        firewall_evidence_form = QFormLayout(firewall_evidence_box)
        self.firewall_status_value = QLabel(tr('Analyze a source ISO first.'))
        self.firewall_status_value.setWordWrap(True)
        self.firewall_backend_value = QLabel(tr('—'))
        self.firewall_path_value = QLabel(tr('—'))
        self.firewall_layer_value = QLabel(tr('—'))
        self.firewall_layer_value.setWordWrap(True)
        firewall_evidence_form.addRow(tr('Verification:'), self.firewall_status_value)
        firewall_evidence_form.addRow(tr('Detected backend:'), self.firewall_backend_value)
        firewall_evidence_form.addRow(tr('Backend evidence path:'), self.firewall_path_value)
        firewall_evidence_form.addRow(tr('Evidence layer:'), self.firewall_layer_value)
        layout.addWidget(firewall_evidence_box)
        firewall_plan_box = QGroupBox(tr('Firewall plan — staged only'))
        firewall_plan_form = QFormLayout(firewall_plan_box)
        firewall_plan_form.setVerticalSpacing(5)
        self.firewall_operation = QComboBox()
        self.firewall_operation.addItem(tr('Preserve existing firewall state'), 'preserve')
        self.firewall_operation.addItem(tr('Enable target-system firewall'), 'enable_firewall')
        self.firewall_operation.addItem(tr('Disable target-system firewall'), 'disable_firewall')
        self.firewall_policy_value = QLabel(tr('Stage only firewall enable/disable intent; preserve existing rule contents, ports/services policy, application profiles and unrelated network configuration.'))
        self.firewall_policy_value.setWordWrap(True)
        self.firewall_safety_value = QLabel(tr('Firewall rule contents and policy details are not read. Backend/apply semantics must be re-verified before apply.'))
        self.firewall_safety_value.setWordWrap(True)
        firewall_plan_form.addRow(tr('Requested operation:'), self.firewall_operation)
        firewall_plan_form.addRow(tr('Preservation policy:'), self.firewall_policy_value)
        firewall_plan_form.addRow(tr('Safety:'), self.firewall_safety_value)
        firewall_controls = QHBoxLayout()
        self.stage_firewall_btn = QPushButton(tr('Stage firewall plan'))
        self.reset_firewall_btn = QPushButton(tr('Reset'))
        self.firewall_plan_status = QLabel(tr('Ready — no firewall changes staged.'))
        self.firewall_plan_status.setWordWrap(True)
        firewall_controls.addWidget(self.stage_firewall_btn)
        firewall_controls.addWidget(self.reset_firewall_btn)
        firewall_controls.addWidget(self.firewall_plan_status, 1)
        firewall_plan_form.addRow(tr(''), firewall_controls)
        layout.addWidget(firewall_plan_box)
        apparmor_evidence_box = QGroupBox(tr('AppArmor rootfs evidence'))
        apparmor_evidence_form = QFormLayout(apparmor_evidence_box)
        self.apparmor_status_value = QLabel(tr('Analyze a source ISO first.'))
        self.apparmor_status_value.setWordWrap(True)
        self.apparmor_backend_value = QLabel(tr('—'))
        self.apparmor_path_value = QLabel(tr('—'))
        self.apparmor_layer_value = QLabel(tr('—'))
        self.apparmor_layer_value.setWordWrap(True)
        apparmor_evidence_form.addRow(tr('Verification:'), self.apparmor_status_value)
        apparmor_evidence_form.addRow(tr('Detected backend:'), self.apparmor_backend_value)
        apparmor_evidence_form.addRow(tr('Component evidence path:'), self.apparmor_path_value)
        apparmor_evidence_form.addRow(tr('Evidence layer:'), self.apparmor_layer_value)
        layout.addWidget(apparmor_evidence_box)
        apparmor_plan_box = QGroupBox(tr('AppArmor plan — staged only'))
        apparmor_plan_form = QFormLayout(apparmor_plan_box)
        apparmor_plan_form.setVerticalSpacing(5)
        self.apparmor_operation = QComboBox()
        self.apparmor_operation.addItem(tr('Preserve existing AppArmor state'), 'preserve')
        self.apparmor_operation.addItem(tr('Enable target-system AppArmor'), 'enable_apparmor')
        self.apparmor_operation.addItem(tr('Disable target-system AppArmor'), 'disable_apparmor')
        self.apparmor_policy_value = QLabel(tr('Stage only AppArmor enable/disable intent; preserve all existing profiles, parser configuration, abstractions/tunables and unrelated security configuration.'))
        self.apparmor_policy_value.setWordWrap(True)
        self.apparmor_safety_value = QLabel(tr('AppArmor profile contents and parser configuration contents are not read. Boot/apply semantics must be re-verified before apply.'))
        self.apparmor_safety_value.setWordWrap(True)
        apparmor_plan_form.addRow(tr('Requested operation:'), self.apparmor_operation)
        apparmor_plan_form.addRow(tr('Preservation policy:'), self.apparmor_policy_value)
        apparmor_plan_form.addRow(tr('Safety:'), self.apparmor_safety_value)
        apparmor_controls = QHBoxLayout()
        self.stage_apparmor_btn = QPushButton(tr('Stage AppArmor plan'))
        self.reset_apparmor_btn = QPushButton(tr('Reset'))
        self.apparmor_plan_status = QLabel(tr('Ready — no AppArmor changes staged.'))
        self.apparmor_plan_status.setWordWrap(True)
        apparmor_controls.addWidget(self.stage_apparmor_btn)
        apparmor_controls.addWidget(self.reset_apparmor_btn)
        apparmor_controls.addWidget(self.apparmor_plan_status, 1)
        apparmor_plan_form.addRow(tr(''), apparmor_controls)
        layout.addWidget(apparmor_plan_box)
        selinux_evidence_box = QGroupBox(tr('SELinux capability evidence — Alpha 52'))
        selinux_evidence_form = QFormLayout(selinux_evidence_box)
        self.selinux_status_value = QLabel(tr('Analyze a source ISO first.'))
        self.selinux_status_value.setWordWrap(True)
        self.selinux_capability_value = QLabel(tr('UNKNOWN'))
        self.selinux_mode_value = QLabel(tr('—'))
        self.selinux_policy_value = QLabel(tr('—'))
        self.selinux_config_value = QLabel(tr('—'))
        self.selinux_packages_value = QLabel(tr('—'))
        self.selinux_packages_value.setWordWrap(True)
        self.selinux_kernel_value = QLabel(tr('—'))
        self.selinux_kernel_value.setWordWrap(True)
        self.selinux_requirements_value = QLabel(tr('—'))
        self.selinux_requirements_value.setWordWrap(True)
        selinux_evidence_form.addRow(tr('Detection:'), self.selinux_status_value)
        selinux_evidence_form.addRow(tr('Capability:'), self.selinux_capability_value)
        selinux_evidence_form.addRow(tr('Configured mode:'), self.selinux_mode_value)
        selinux_evidence_form.addRow(tr('Policy type:'), self.selinux_policy_value)
        selinux_evidence_form.addRow(tr('Configuration path:'), self.selinux_config_value)
        selinux_evidence_form.addRow(tr('Package evidence/requirements:'), self.selinux_packages_value)
        selinux_evidence_form.addRow(tr('Kernel / Part 3:'), self.selinux_kernel_value)
        selinux_evidence_form.addRow(tr('Activation requirements:'), self.selinux_requirements_value)
        layout.addWidget(selinux_evidence_box)
        selinux_plan_box = QGroupBox(tr('SELinux plan — staged only'))
        selinux_plan_form = QFormLayout(selinux_plan_box)
        selinux_plan_form.setVerticalSpacing(5)
        self.selinux_mode = QComboBox()
        self.selinux_mode.addItem(tr('Preserve existing SELinux state'), 'preserve')
        self.selinux_dependency_value = QLabel(tr('Dependencies are populated from verified target capability. Package requirements stay in the package model; boot/kernel/initramfs requirements are delegated to the existing Part 3 model.'))
        self.selinux_dependency_value.setWordWrap(True)
        self.selinux_safety_value = QLabel(tr('Existing SELinux policy trees are preserved. Policy contents are not read. ChromaPress never writes boot arguments directly from this Part 4 gate and never consults host SELinux state.'))
        self.selinux_safety_value.setWordWrap(True)
        selinux_plan_form.addRow(tr('Requested mode:'), self.selinux_mode)
        selinux_plan_form.addRow(tr('Dependency routing:'), self.selinux_dependency_value)
        selinux_plan_form.addRow(tr('Preservation / safety:'), self.selinux_safety_value)
        selinux_controls = QHBoxLayout()
        self.stage_selinux_btn = QPushButton(tr('Stage SELinux plan'))
        self.reset_selinux_btn = QPushButton(tr('Reset'))
        self.selinux_plan_status = QLabel(tr('Ready — no SELinux changes staged.'))
        self.selinux_plan_status.setWordWrap(True)
        selinux_controls.addWidget(self.stage_selinux_btn)
        selinux_controls.addWidget(self.reset_selinux_btn)
        selinux_controls.addWidget(self.selinux_plan_status, 1)
        selinux_plan_form.addRow(tr(''), selinux_controls)
        layout.addWidget(selinux_plan_box)
        sysctl_evidence_box = QGroupBox(tr('sysctl rootfs evidence'))
        sysctl_evidence_form = QFormLayout(sysctl_evidence_box)
        self.sysctl_status_value = QLabel(tr('Analyze a source ISO first.'))
        self.sysctl_status_value.setWordWrap(True)
        self.sysctl_backend_value = QLabel(tr('—'))
        self.sysctl_path_value = QLabel(tr('—'))
        self.sysctl_layer_value = QLabel(tr('—'))
        self.sysctl_layer_value.setWordWrap(True)
        sysctl_evidence_form.addRow(tr('Verification:'), self.sysctl_status_value)
        sysctl_evidence_form.addRow(tr('Detected backend:'), self.sysctl_backend_value)
        sysctl_evidence_form.addRow(tr('Infrastructure evidence path:'), self.sysctl_path_value)
        sysctl_evidence_form.addRow(tr('Evidence layer:'), self.sysctl_layer_value)
        layout.addWidget(sysctl_evidence_box)
        sysctl_plan_box = QGroupBox(tr('sysctl plan — staged only'))
        sysctl_plan_form = QFormLayout(sysctl_plan_box)
        sysctl_plan_form.setVerticalSpacing(5)
        self.sysctl_operation = QComboBox()
        self.sysctl_operation.addItem(tr('Preserve existing sysctl configuration'), 'preserve')
        self.sysctl_operation.addItem(tr('Set target-system integer sysctl value'), 'set_integer_sysctl')
        self.sysctl_key = QLineEdit()
        self.sysctl_key.setPlaceholderText(tr('e.g. vm.swappiness'))
        self.sysctl_value = QLineEdit()
        self.sysctl_value.setPlaceholderText(tr('integer value, e.g. 10'))
        self.sysctl_policy_value = QLabel(tr('Stage one integer key/value only. Preserve all existing sysctl files and runtime values; a later apply must use a managed drop-in and re-verify the target key.'))
        self.sysctl_policy_value.setWordWrap(True)
        self.sysctl_safety_value = QLabel(tr('Existing sysctl configuration contents and effective runtime values are not read at this gate.'))
        self.sysctl_safety_value.setWordWrap(True)
        sysctl_plan_form.addRow(tr('Requested operation:'), self.sysctl_operation)
        sysctl_plan_form.addRow(tr('sysctl key:'), self.sysctl_key)
        sysctl_plan_form.addRow(tr('Integer value:'), self.sysctl_value)
        sysctl_plan_form.addRow(tr('Preservation policy:'), self.sysctl_policy_value)
        sysctl_plan_form.addRow(tr('Safety:'), self.sysctl_safety_value)
        sysctl_controls = QHBoxLayout()
        self.stage_sysctl_btn = QPushButton(tr('Stage sysctl plan'))
        self.reset_sysctl_btn = QPushButton(tr('Reset'))
        self.sysctl_plan_status = QLabel(tr('Ready — no sysctl changes staged.'))
        self.sysctl_plan_status.setWordWrap(True)
        sysctl_controls.addWidget(self.stage_sysctl_btn)
        sysctl_controls.addWidget(self.reset_sysctl_btn)
        sysctl_controls.addWidget(self.sysctl_plan_status, 1)
        sysctl_plan_form.addRow(tr(''), sysctl_controls)
        layout.addWidget(sysctl_plan_box)
        security_evidence_box = QGroupBox(tr('Security defaults capability evidence — Alpha 53'))
        security_evidence_form = QFormLayout(security_evidence_box)
        self.security_defaults_status_value = QLabel(tr('Analyze a source ISO first.'))
        self.security_defaults_status_value.setWordWrap(True)
        self.security_defaults_capability_value = QLabel(tr('UNKNOWN'))
        self.security_defaults_backend_value = QLabel(tr('—'))
        self.security_defaults_path_value = QLabel(tr('—'))
        self.security_defaults_layer_value = QLabel(tr('—'))
        self.security_defaults_layer_value.setWordWrap(True)
        self.security_defaults_umask_value = QLabel(tr('—'))
        self.security_defaults_usergroups_value = QLabel(tr('—'))
        security_evidence_form.addRow(tr('Detection:'), self.security_defaults_status_value)
        security_evidence_form.addRow(tr('Capability:'), self.security_defaults_capability_value)
        security_evidence_form.addRow(tr('Backend:'), self.security_defaults_backend_value)
        security_evidence_form.addRow(tr('Configuration path:'), self.security_defaults_path_value)
        security_evidence_form.addRow(tr('Evidence layer:'), self.security_defaults_layer_value)
        security_evidence_form.addRow(tr('Current default UMASK:'), self.security_defaults_umask_value)
        security_evidence_form.addRow(tr('USERGROUPS_ENAB:'), self.security_defaults_usergroups_value)
        layout.addWidget(security_evidence_box)
        security_plan_box = QGroupBox(tr('Security defaults plan — staged only'))
        security_plan_form = QFormLayout(security_plan_box)
        security_plan_form.setVerticalSpacing(5)
        self.security_defaults_operation = QComboBox()
        self.security_defaults_operation.addItem(tr('Preserve existing login security defaults'), 'preserve')
        self.security_defaults_operation.addItem(tr('Set target-system default login UMASK'), 'set_default_umask')
        self.security_defaults_umask = QComboBox()
        self.security_defaults_umask.addItem(tr('022 — standard'), '022')
        self.security_defaults_umask.addItem(tr('027 — restrict other users'), '027')
        self.security_defaults_umask.addItem(tr('077 — private'), '077')
        self.security_defaults_policy_value = QLabel(tr('Only the default login UMASK intent is staged. Existing /etc/login.defs content, PAM configuration, account policy and unrelated security settings are preserved.'))
        self.security_defaults_policy_value.setWordWrap(True)
        self.security_defaults_safety_value = QLabel(tr('Only UMASK/USERGROUPS_ENAB metadata is exposed. Effective login/session semantics must be re-verified before any later apply.'))
        self.security_defaults_safety_value.setWordWrap(True)
        security_plan_form.addRow(tr('Requested operation:'), self.security_defaults_operation)
        security_plan_form.addRow(tr('Default login UMASK:'), self.security_defaults_umask)
        security_plan_form.addRow(tr('Preservation policy:'), self.security_defaults_policy_value)
        security_plan_form.addRow(tr('Safety:'), self.security_defaults_safety_value)
        security_controls = QHBoxLayout()
        self.stage_security_defaults_btn = QPushButton(tr('Stage security defaults plan'))
        self.reset_security_defaults_btn = QPushButton(tr('Reset'))
        self.security_defaults_plan_status = QLabel(tr('Ready — no security-default changes staged.'))
        self.security_defaults_plan_status.setWordWrap(True)
        security_controls.addWidget(self.stage_security_defaults_btn)
        security_controls.addWidget(self.reset_security_defaults_btn)
        security_controls.addWidget(self.security_defaults_plan_status, 1)
        security_plan_form.addRow(tr(''), security_controls)
        layout.addWidget(security_plan_box)
        overlay_evidence_box = QGroupBox(tr('System configuration overlay evidence — Alpha 54'))
        overlay_evidence_form = QFormLayout(overlay_evidence_box)
        self.config_overlay_status_value = QLabel(tr('Analyze a source ISO first.'))
        self.config_overlay_status_value.setWordWrap(True)
        self.config_overlay_capability_value = QLabel(tr('UNKNOWN'))
        self.config_overlay_backend_value = QLabel(tr('—'))
        self.config_overlay_profile_value = QLabel(tr('—'))
        self.config_overlay_profile_layer_value = QLabel(tr('—'))
        self.config_overlay_profile_layer_value.setWordWrap(True)
        self.config_overlay_directory_value = QLabel(tr('—'))
        self.config_overlay_directory_layer_value = QLabel(tr('—'))
        self.config_overlay_directory_layer_value.setWordWrap(True)
        self.config_overlay_existing_value = QLabel(tr('—'))
        self.config_overlay_existing_value.setWordWrap(True)
        overlay_evidence_form.addRow(tr('Detection:'), self.config_overlay_status_value)
        overlay_evidence_form.addRow(tr('Capability:'), self.config_overlay_capability_value)
        overlay_evidence_form.addRow(tr('Backend:'), self.config_overlay_backend_value)
        overlay_evidence_form.addRow(tr('Profile path:'), self.config_overlay_profile_value)
        overlay_evidence_form.addRow(tr('Profile evidence layer:'), self.config_overlay_profile_layer_value)
        overlay_evidence_form.addRow(tr('Managed target directory:'), self.config_overlay_directory_value)
        overlay_evidence_form.addRow(tr('Directory evidence layer:'), self.config_overlay_directory_layer_value)
        overlay_evidence_form.addRow(tr('Existing entry names:'), self.config_overlay_existing_value)
        layout.addWidget(overlay_evidence_box)
        overlay_plan_box = QGroupBox(tr('System configuration overlay plan — staged only'))
        overlay_plan_form = QFormLayout(overlay_plan_box)
        overlay_plan_form.setVerticalSpacing(5)
        self.config_overlay_operation = QComboBox()
        self.config_overlay_operation.addItem(tr('Preserve existing system configuration overlays'), 'preserve')
        self.config_overlay_operation.addItem(tr('Add managed non-secret login environment overlay'), 'add_managed_environment_overlay')
        self.config_overlay_name = QLineEdit()
        self.config_overlay_name.setPlaceholderText(tr('managed name, e.g. chromatest54'))
        self.config_overlay_variable = QLineEdit()
        self.config_overlay_variable.setPlaceholderText(tr('non-secret variable, e.g. CHROMAPRESS_TEST'))
        self.config_overlay_value = QLineEdit()
        self.config_overlay_value.setPlaceholderText(tr('non-secret value, e.g. 1'))
        self.config_overlay_policy_value = QLabel(tr('Creates only a new 99-chromapress-<name>.sh drop-in after re-verifying that the target filename is absent. Existing /etc/profile, profile.d files and unrelated configuration are preserved.'))
        self.config_overlay_policy_value.setWordWrap(True)
        self.config_overlay_safety_value = QLabel(tr('No arbitrary shell script is accepted. Variable name/value are narrowly validated and secret-like variable names are blocked; do not use this gate for credentials or secrets.'))
        self.config_overlay_safety_value.setWordWrap(True)
        overlay_plan_form.addRow(tr('Requested operation:'), self.config_overlay_operation)
        overlay_plan_form.addRow(tr('Overlay name:'), self.config_overlay_name)
        overlay_plan_form.addRow(tr('Environment variable:'), self.config_overlay_variable)
        overlay_plan_form.addRow(tr('Public non-secret value:'), self.config_overlay_value)
        overlay_plan_form.addRow(tr('Preservation policy:'), self.config_overlay_policy_value)
        overlay_plan_form.addRow(tr('Safety:'), self.config_overlay_safety_value)
        overlay_controls = QHBoxLayout()
        self.stage_config_overlay_btn = QPushButton(tr('Stage system configuration overlay plan'))
        self.reset_config_overlay_btn = QPushButton(tr('Reset'))
        self.config_overlay_plan_status = QLabel(tr('Ready — no system-configuration overlay staged.'))
        self.config_overlay_plan_status.setWordWrap(True)
        overlay_controls.addWidget(self.stage_config_overlay_btn)
        overlay_controls.addWidget(self.reset_config_overlay_btn)
        overlay_controls.addWidget(self.config_overlay_plan_status, 1)
        overlay_plan_form.addRow(tr(''), overlay_controls)
        layout.addWidget(overlay_plan_box)
        kiosk_evidence_box = QGroupBox(tr('Dedicated non-admin kiosk user capability — Alpha 55'))
        kiosk_evidence_form = QFormLayout(kiosk_evidence_box)
        self.kiosk_user_status_value = QLabel(tr('Analyze a source ISO first.'))
        self.kiosk_user_status_value.setWordWrap(True)
        self.kiosk_user_capability_value = QLabel(tr('UNKNOWN'))
        self.kiosk_user_layers_value = QLabel(tr('—'))
        self.kiosk_user_layers_value.setWordWrap(True)
        self.kiosk_user_existing_value = QLabel(tr('—'))
        self.kiosk_user_existing_value.setWordWrap(True)
        self.kiosk_user_admin_groups_value = QLabel(tr('—'))
        self.kiosk_user_safety_value = QLabel(tr('No credential, restricted-login, session, autologin or desktop policy is read or changed by this gate.'))
        self.kiosk_user_safety_value.setWordWrap(True)
        kiosk_evidence_form.addRow(tr('Detection:'), self.kiosk_user_status_value)
        kiosk_evidence_form.addRow(tr('Capability:'), self.kiosk_user_capability_value)
        kiosk_evidence_form.addRow(tr('Account evidence layer(s):'), self.kiosk_user_layers_value)
        kiosk_evidence_form.addRow(tr('Existing regular users:'), self.kiosk_user_existing_value)
        kiosk_evidence_form.addRow(tr('Verified admin groups:'), self.kiosk_user_admin_groups_value)
        kiosk_evidence_form.addRow(tr('Scope:'), self.kiosk_user_safety_value)
        layout.addWidget(kiosk_evidence_box)
        kiosk_plan_box = QGroupBox(tr('Dedicated non-admin kiosk user plan — staged only'))
        kiosk_plan_form = QFormLayout(kiosk_plan_box)
        kiosk_plan_form.setVerticalSpacing(5)
        self.kiosk_user_operation = QComboBox()
        self.kiosk_user_operation.addItem(tr('Preserve existing accounts'), 'preserve')
        self.kiosk_user_operation.addItem(tr('Create dedicated non-admin kiosk user'), 'create_dedicated_non_admin_kiosk_user')
        self.kiosk_username = QLineEdit()
        self.kiosk_username.setPlaceholderText(tr('e.g. chromakiosk55'))
        self.kiosk_display_name = QLineEdit()
        self.kiosk_display_name.setPlaceholderText(tr('e.g. Chroma Kiosk'))
        self.kiosk_role_value = QLabel(tr('Dedicated non-admin user; automatic UID/GID; no administrative group membership. Login/session restrictions remain unchanged.'))
        self.kiosk_role_value.setWordWrap(True)
        kiosk_plan_form.addRow(tr('Requested operation:'), self.kiosk_user_operation)
        kiosk_plan_form.addRow(tr('Username:'), self.kiosk_username)
        kiosk_plan_form.addRow(tr('Display name:'), self.kiosk_display_name)
        kiosk_plan_form.addRow(tr('Account policy:'), self.kiosk_role_value)
        kiosk_controls = QHBoxLayout()
        self.stage_kiosk_user_btn = QPushButton(tr('Stage dedicated kiosk user plan'))
        self.reset_kiosk_user_btn = QPushButton(tr('Reset'))
        self.kiosk_user_plan_status = QLabel(tr('Ready — no dedicated kiosk-user change staged.'))
        self.kiosk_user_plan_status.setWordWrap(True)
        kiosk_controls.addWidget(self.stage_kiosk_user_btn)
        kiosk_controls.addWidget(self.reset_kiosk_user_btn)
        kiosk_controls.addWidget(self.kiosk_user_plan_status, 1)
        kiosk_plan_form.addRow(tr(''), kiosk_controls)
        layout.addWidget(kiosk_plan_box)
        restricted_login_evidence_box = QGroupBox(tr('Restricted login capability — Alpha 56'))
        restricted_login_evidence_form = QFormLayout(restricted_login_evidence_box)
        self.restricted_login_status_value = QLabel(tr('Analyze a source ISO first.'))
        self.restricted_login_status_value.setWordWrap(True)
        self.restricted_login_capability_value = QLabel(tr('UNKNOWN'))
        self.restricted_login_backend_value = QLabel(tr('—'))
        self.restricted_login_tool_value = QLabel(tr('—'))
        self.restricted_login_tool_layer_value = QLabel(tr('—'))
        self.restricted_login_tool_layer_value.setWordWrap(True)
        self.restricted_login_users_value = QLabel(tr('—'))
        self.restricted_login_users_value.setWordWrap(True)
        self.restricted_login_admin_users_value = QLabel(tr('—'))
        self.restricted_login_admin_users_value.setWordWrap(True)
        self.restricted_login_scope_value = QLabel(tr('Password authentication only; autologin, desktop/session policy, SSH configuration and PAM configuration are preserved.'))
        self.restricted_login_scope_value.setWordWrap(True)
        restricted_login_evidence_form.addRow(tr('Detection:'), self.restricted_login_status_value)
        restricted_login_evidence_form.addRow(tr('Capability:'), self.restricted_login_capability_value)
        restricted_login_evidence_form.addRow(tr('Backend:'), self.restricted_login_backend_value)
        restricted_login_evidence_form.addRow(tr('Verified target tool:'), self.restricted_login_tool_value)
        restricted_login_evidence_form.addRow(tr('Tool evidence layer:'), self.restricted_login_tool_layer_value)
        restricted_login_evidence_form.addRow(tr('Existing regular users:'), self.restricted_login_users_value)
        restricted_login_evidence_form.addRow(tr('Verified admin users:'), self.restricted_login_admin_users_value)
        restricted_login_evidence_form.addRow(tr('Scope:'), self.restricted_login_scope_value)
        layout.addWidget(restricted_login_evidence_box)
        restricted_login_plan_box = QGroupBox(tr('Restricted login plan — staged only'))
        restricted_login_plan_form = QFormLayout(restricted_login_plan_box)
        restricted_login_plan_form.setVerticalSpacing(5)
        self.restricted_login_operation = QComboBox()
        self.restricted_login_operation.addItem(tr('Preserve existing login policy'), 'preserve')
        self.restricted_login_operation.addItem(tr('Lock password authentication for kiosk account'), 'lock_password_authentication')
        self.restricted_login_username = QLineEdit()
        self.restricted_login_username.setPlaceholderText(tr('e.g. chromakiosk56'))
        self.restricted_login_dependency_value = QLabel(tr('Existing verified user, or an explicit dependency on the Alpha 55 dedicated non-admin kiosk-user creation gate when the username is not yet present.'))
        self.restricted_login_dependency_value.setWordWrap(True)
        self.restricted_login_safety_value = QLabel(tr('No password is requested or stored. This gate stages only a target-rootfs password-lock intent and preserves autologin/session/SSH/PAM configuration.'))
        self.restricted_login_safety_value.setWordWrap(True)
        restricted_login_plan_form.addRow(tr('Requested operation:'), self.restricted_login_operation)
        restricted_login_plan_form.addRow(tr('Kiosk username:'), self.restricted_login_username)
        restricted_login_plan_form.addRow(tr('Account requirement:'), self.restricted_login_dependency_value)
        restricted_login_plan_form.addRow(tr('Safety:'), self.restricted_login_safety_value)
        restricted_login_controls = QHBoxLayout()
        self.stage_restricted_login_btn = QPushButton(tr('Stage restricted login plan'))
        self.reset_restricted_login_btn = QPushButton(tr('Reset'))
        self.restricted_login_plan_status = QLabel(tr('Ready — no restricted-login change staged.'))
        self.restricted_login_plan_status.setWordWrap(True)
        restricted_login_controls.addWidget(self.stage_restricted_login_btn)
        restricted_login_controls.addWidget(self.reset_restricted_login_btn)
        restricted_login_controls.addWidget(self.restricted_login_plan_status, 1)
        restricted_login_plan_form.addRow(tr(''), restricted_login_controls)
        layout.addWidget(restricted_login_plan_box)
        restricted_session_evidence_box = QGroupBox(tr('Restricted session capability — Alpha 57'))
        restricted_session_evidence_form = QFormLayout(restricted_session_evidence_box)
        self.restricted_session_status_value = QLabel(tr('Analyze a source ISO first.'))
        self.restricted_session_status_value.setWordWrap(True)
        self.restricted_session_capability_value = QLabel(tr('UNKNOWN'))
        self.restricted_session_backend_value = QLabel(tr('—'))
        self.restricted_session_dm_value = QLabel(tr('—'))
        self.restricted_session_sessions_value = QLabel(tr('—'))
        self.restricted_session_sessions_value.setWordWrap(True)
        self.restricted_session_target_value = QLabel(tr('—'))
        self.restricted_session_target_value.setWordWrap(True)
        self.restricted_session_requirements_value = QLabel(tr('Alpha 39 autologin for the same kiosk user + Alpha 56 restricted login; both are re-verified before apply.'))
        self.restricted_session_requirements_value.setWordWrap(True)
        self.restricted_session_scope_value = QLabel(tr('Fixed SDDM autologin-session selection only; this does not claim complete desktop/service lockdown.'))
        self.restricted_session_scope_value.setWordWrap(True)
        restricted_session_evidence_form.addRow(tr('Detection:'), self.restricted_session_status_value)
        restricted_session_evidence_form.addRow(tr('Capability:'), self.restricted_session_capability_value)
        restricted_session_evidence_form.addRow(tr('Backend:'), self.restricted_session_backend_value)
        restricted_session_evidence_form.addRow(tr('Display manager:'), self.restricted_session_dm_value)
        restricted_session_evidence_form.addRow(tr('Verified target sessions:'), self.restricted_session_sessions_value)
        restricted_session_evidence_form.addRow(tr('Managed target:'), self.restricted_session_target_value)
        restricted_session_evidence_form.addRow(tr('Required dependencies:'), self.restricted_session_requirements_value)
        restricted_session_evidence_form.addRow(tr('Scope:'), self.restricted_session_scope_value)
        layout.addWidget(restricted_session_evidence_box)
        restricted_session_plan_box = QGroupBox(tr('Restricted session plan — staged only'))
        restricted_session_plan_form = QFormLayout(restricted_session_plan_box)
        restricted_session_plan_form.setVerticalSpacing(5)
        self.restricted_session_operation = QComboBox()
        self.restricted_session_operation.addItem(tr('Preserve existing session policy'), 'preserve')
        self.restricted_session_operation.addItem(tr('Bind kiosk account to verified SDDM autologin session'), 'bind_kiosk_autologin_session')
        self.restricted_session_username = QLineEdit()
        self.restricted_session_username.setPlaceholderText(tr('e.g. chromakiosk57'))
        self.restricted_session_choice = QComboBox()
        self.restricted_session_choice.addItem(tr('No verified target session'), '')
        self.restricted_session_dependency_value = QLabel(tr('Requires the same kiosk account to be covered by Alpha 56 restricted login and Alpha 39 autologin. Missing account may depend on Alpha 55 kiosk-user creation.'))
        self.restricted_session_dependency_value.setWordWrap(True)
        self.restricted_session_safety_value = QLabel(tr('Creates only the structured SDDM Autologin/Session intent for a collision-free managed drop-in. Existing session descriptors and display-manager configuration are preserved.'))
        self.restricted_session_safety_value.setWordWrap(True)
        restricted_session_plan_form.addRow(tr('Requested operation:'), self.restricted_session_operation)
        restricted_session_plan_form.addRow(tr('Kiosk username:'), self.restricted_session_username)
        restricted_session_plan_form.addRow(tr('Verified session:'), self.restricted_session_choice)
        restricted_session_plan_form.addRow(tr('Dependencies:'), self.restricted_session_dependency_value)
        restricted_session_plan_form.addRow(tr('Safety:'), self.restricted_session_safety_value)
        restricted_session_controls = QHBoxLayout()
        self.stage_restricted_session_btn = QPushButton(tr('Stage restricted session plan'))
        self.reset_restricted_session_btn = QPushButton(tr('Reset'))
        self.restricted_session_plan_status = QLabel(tr('Ready — no restricted-session change staged.'))
        self.restricted_session_plan_status.setWordWrap(True)
        restricted_session_controls.addWidget(self.stage_restricted_session_btn)
        restricted_session_controls.addWidget(self.reset_restricted_session_btn)
        restricted_session_controls.addWidget(self.restricted_session_plan_status, 1)
        restricted_session_plan_form.addRow(tr(''), restricted_session_controls)
        layout.addWidget(restricted_session_plan_box)
        service_lockdown_evidence_box = QGroupBox(tr('Service lockdown capability — Alpha 58'))
        service_lockdown_evidence_form = QFormLayout(service_lockdown_evidence_box)
        self.service_lockdown_status_value = QLabel(tr('Analyze a source ISO first.'))
        self.service_lockdown_status_value.setWordWrap(True)
        self.service_lockdown_capability_value = QLabel(tr('UNKNOWN'))
        self.service_lockdown_backend_value = QLabel(tr('—'))
        self.service_lockdown_units_value = QLabel(tr('—'))
        self.service_lockdown_units_value.setWordWrap(True)
        self.service_lockdown_protected_value = QLabel(tr('—'))
        self.service_lockdown_protected_value.setWordWrap(True)
        self.service_lockdown_scope_value = QLabel(tr('One verified non-critical target systemd service at a time; no wildcard/bulk lockdown.'))
        self.service_lockdown_scope_value.setWordWrap(True)
        service_lockdown_evidence_form.addRow(tr('Detection:'), self.service_lockdown_status_value)
        service_lockdown_evidence_form.addRow(tr('Capability:'), self.service_lockdown_capability_value)
        service_lockdown_evidence_form.addRow(tr('Backend:'), self.service_lockdown_backend_value)
        service_lockdown_evidence_form.addRow(tr('Selectable verified services:'), self.service_lockdown_units_value)
        service_lockdown_evidence_form.addRow(tr('Protected services:'), self.service_lockdown_protected_value)
        service_lockdown_evidence_form.addRow(tr('Scope:'), self.service_lockdown_scope_value)
        layout.addWidget(service_lockdown_evidence_box)
        service_lockdown_plan_box = QGroupBox(tr('Service lockdown plan — staged only'))
        service_lockdown_plan_form = QFormLayout(service_lockdown_plan_box)
        service_lockdown_plan_form.setVerticalSpacing(5)
        self.service_lockdown_operation = QComboBox()
        self.service_lockdown_operation.addItem(tr('Preserve existing service policy'), 'preserve')
        self.service_lockdown_operation.addItem(tr('Disable + mask one verified non-critical service'), 'disable_and_mask_verified_service')
        self.service_lockdown_choice = QComboBox()
        self.service_lockdown_choice.addItem(tr('No verified non-protected service'), '')
        self.service_lockdown_safety_value = QLabel(tr('Only a verified target .service filename may be selected. Core/display/network-management units are safety-protected; unit files, timers/sockets and unrelated service policy are preserved.'))
        self.service_lockdown_safety_value.setWordWrap(True)
        service_lockdown_plan_form.addRow(tr('Requested operation:'), self.service_lockdown_operation)
        service_lockdown_plan_form.addRow(tr('Verified service:'), self.service_lockdown_choice)
        service_lockdown_plan_form.addRow(tr('Safety:'), self.service_lockdown_safety_value)
        service_lockdown_controls = QHBoxLayout()
        self.stage_service_lockdown_btn = QPushButton(tr('Stage service lockdown plan'))
        self.reset_service_lockdown_btn = QPushButton(tr('Reset'))
        self.service_lockdown_plan_status = QLabel(tr('Ready — no service-lockdown change staged.'))
        self.service_lockdown_plan_status.setWordWrap(True)
        service_lockdown_controls.addWidget(self.stage_service_lockdown_btn)
        service_lockdown_controls.addWidget(self.reset_service_lockdown_btn)
        service_lockdown_controls.addWidget(self.service_lockdown_plan_status, 1)
        service_lockdown_plan_form.addRow(tr(''), service_lockdown_controls)
        layout.addWidget(service_lockdown_plan_box)
        network_restriction_evidence_box = QGroupBox(tr('Network restrictions capability — Alpha 59'))
        network_restriction_evidence_form = QFormLayout(network_restriction_evidence_box)
        self.network_restriction_status_value = QLabel(tr('Analyze a source ISO first.'))
        self.network_restriction_status_value.setWordWrap(True)
        self.network_restriction_capability_value = QLabel(tr('UNKNOWN'))
        self.network_restriction_backend_value = QLabel(tr('—'))
        self.network_restriction_target_value = QLabel(tr('—'))
        self.network_restriction_target_value.setWordWrap(True)
        self.network_restriction_scope_value = QLabel(tr('Kiosk account NetworkManager control only; this gate does not claim or stage traffic blocking.'))
        self.network_restriction_scope_value.setWordWrap(True)
        network_restriction_evidence_form.addRow(tr('Detection:'), self.network_restriction_status_value)
        network_restriction_evidence_form.addRow(tr('Capability:'), self.network_restriction_capability_value)
        network_restriction_evidence_form.addRow(tr('Backend:'), self.network_restriction_backend_value)
        network_restriction_evidence_form.addRow(tr('Managed rule target:'), self.network_restriction_target_value)
        network_restriction_evidence_form.addRow(tr('Scope:'), self.network_restriction_scope_value)
        layout.addWidget(network_restriction_evidence_box)
        network_restriction_plan_box = QGroupBox(tr('Network restrictions plan — staged only'))
        network_restriction_plan_form = QFormLayout(network_restriction_plan_box)
        network_restriction_plan_form.setVerticalSpacing(5)
        self.network_restriction_operation = QComboBox()
        self.network_restriction_operation.addItem(tr('Preserve existing network-control policy'), 'preserve')
        self.network_restriction_operation.addItem(tr('Restrict kiosk account from changing NetworkManager configuration'), 'restrict_kiosk_networkmanager_control')
        self.network_restriction_username = QLineEdit()
        self.network_restriction_username.setPlaceholderText(tr('kiosk username, e.g. chromakiosk59'))
        self.network_restriction_dependency_value = QLabel(tr('Requires the same dedicated non-admin kiosk account planned by Alpha 55 before apply.'))
        self.network_restriction_dependency_value.setWordWrap(True)
        self.network_restriction_safety_value = QLabel(tr('This restricts NetworkManager control actions only. It does not block network traffic and does not create firewall rules; the firewall-rules gate remains separate.'))
        self.network_restriction_safety_value.setWordWrap(True)
        network_restriction_plan_form.addRow(tr('Requested operation:'), self.network_restriction_operation)
        network_restriction_plan_form.addRow(tr('Kiosk username:'), self.network_restriction_username)
        network_restriction_plan_form.addRow(tr('Dependency:'), self.network_restriction_dependency_value)
        network_restriction_plan_form.addRow(tr('Safety:'), self.network_restriction_safety_value)
        network_restriction_controls = QHBoxLayout()
        self.stage_network_restriction_btn = QPushButton(tr('Stage network restrictions plan'))
        self.reset_network_restriction_btn = QPushButton(tr('Reset'))
        self.network_restriction_plan_status = QLabel(tr('Ready — no network-restriction change staged.'))
        self.network_restriction_plan_status.setWordWrap(True)
        network_restriction_controls.addWidget(self.stage_network_restriction_btn)
        network_restriction_controls.addWidget(self.reset_network_restriction_btn)
        network_restriction_controls.addWidget(self.network_restriction_plan_status, 1)
        network_restriction_plan_form.addRow(tr(''), network_restriction_controls)
        layout.addWidget(network_restriction_plan_box)
        firewall_rules_evidence_box = QGroupBox(tr('Firewall rules capability — Alpha 60'))
        firewall_rules_evidence_form = QFormLayout(firewall_rules_evidence_box)
        self.firewall_rules_status_value = QLabel(tr('Analyze a source ISO first.'))
        self.firewall_rules_status_value.setWordWrap(True)
        self.firewall_rules_capability_value = QLabel(tr('UNKNOWN'))
        self.firewall_rules_backend_value = QLabel(tr('—'))
        self.firewall_rules_adapter_value = QLabel(tr('—'))
        self.firewall_rules_command_value = QLabel(tr('—'))
        self.firewall_rules_command_value.setWordWrap(True)
        self.firewall_rules_scope_value = QLabel(tr('One explicit inbound TCP-port deny rule only; existing/default/unrelated firewall policy is preserved.'))
        self.firewall_rules_scope_value.setWordWrap(True)
        firewall_rules_evidence_form.addRow(tr('Detection:'), self.firewall_rules_status_value)
        firewall_rules_evidence_form.addRow(tr('Capability:'), self.firewall_rules_capability_value)
        firewall_rules_evidence_form.addRow(tr('Target backend:'), self.firewall_rules_backend_value)
        firewall_rules_evidence_form.addRow(tr('Verified adapter:'), self.firewall_rules_adapter_value)
        firewall_rules_evidence_form.addRow(tr('Command evidence:'), self.firewall_rules_command_value)
        firewall_rules_evidence_form.addRow(tr('Scope:'), self.firewall_rules_scope_value)
        layout.addWidget(firewall_rules_evidence_box)
        firewall_rules_plan_box = QGroupBox(tr('Firewall rules plan — staged only'))
        firewall_rules_plan_form = QFormLayout(firewall_rules_plan_box)
        firewall_rules_plan_form.setVerticalSpacing(5)
        self.firewall_rules_operation = QComboBox()
        self.firewall_rules_operation.addItem(tr('Preserve existing firewall rules'), 'preserve')
        self.firewall_rules_operation.addItem(tr('Deny one inbound TCP port'), 'deny_inbound_tcp_port')
        self.firewall_rules_port = QLineEdit()
        self.firewall_rules_port.setPlaceholderText(tr('TCP port 1–65535, e.g. 65060'))
        self.firewall_rules_safety_value = QLabel(tr('Existing rules are not read during analysis. Duplicate/conflicting rules and backend state must be re-verified before apply; no default policy or unrelated rule is changed.'))
        self.firewall_rules_safety_value.setWordWrap(True)
        firewall_rules_plan_form.addRow(tr('Requested operation:'), self.firewall_rules_operation)
        firewall_rules_plan_form.addRow(tr('Inbound TCP port:'), self.firewall_rules_port)
        firewall_rules_plan_form.addRow(tr('Safety:'), self.firewall_rules_safety_value)
        firewall_rules_controls = QHBoxLayout()
        self.stage_firewall_rules_btn = QPushButton(tr('Stage firewall rules plan'))
        self.reset_firewall_rules_btn = QPushButton(tr('Reset'))
        self.firewall_rules_plan_status = QLabel(tr('Ready — no firewall-rule change staged.'))
        self.firewall_rules_plan_status.setWordWrap(True)
        firewall_rules_controls.addWidget(self.stage_firewall_rules_btn)
        firewall_rules_controls.addWidget(self.reset_firewall_rules_btn)
        firewall_rules_controls.addWidget(self.firewall_rules_plan_status, 1)
        firewall_rules_plan_form.addRow(tr(''), firewall_rules_controls)
        layout.addWidget(firewall_rules_plan_box)
        persistence_policy_evidence_box = QGroupBox(tr('Persistence policy capability — Alpha 61'))
        persistence_policy_evidence_form = QFormLayout(persistence_policy_evidence_box)
        self.persistence_policy_status_value = QLabel(tr('Analyze a source ISO first.'))
        self.persistence_policy_status_value.setWordWrap(True)
        self.persistence_policy_capability_value = QLabel(tr('UNKNOWN'))
        self.persistence_policy_part3_value = QLabel(tr('—'))
        self.persistence_policy_part3_value.setWordWrap(True)
        self.persistence_policy_scope_value = QLabel(tr('Kiosk session runtime only; filesystem/OverlayFS/mount mechanics remain a Part 3 responsibility.'))
        self.persistence_policy_scope_value.setWordWrap(True)
        persistence_policy_evidence_form.addRow(tr('Detection:'), self.persistence_policy_status_value)
        persistence_policy_evidence_form.addRow(tr('Capability:'), self.persistence_policy_capability_value)
        persistence_policy_evidence_form.addRow(tr('Part 3 dependency evidence:'), self.persistence_policy_part3_value)
        persistence_policy_evidence_form.addRow(tr('Scope:'), self.persistence_policy_scope_value)
        layout.addWidget(persistence_policy_evidence_box)
        persistence_policy_plan_box = QGroupBox(tr('Persistence policy plan — staged only'))
        persistence_policy_plan_form = QFormLayout(persistence_policy_plan_box)
        persistence_policy_plan_form.setVerticalSpacing(5)
        self.persistence_policy_operation = QComboBox()
        self.persistence_policy_operation.addItem(tr('Preserve existing persistence policy'), 'preserve')
        self.persistence_policy_operation.addItem(tr('Require volatile kiosk runtime'), 'require_volatile_kiosk_runtime')
        self.persistence_policy_operation.addItem(tr('Require controlled persistence for selected kiosk directories'), 'require_controlled_kiosk_persistence')
        self.persistence_policy_username = QLineEdit()
        self.persistence_policy_username.setPlaceholderText(tr('Dedicated kiosk username, e.g. chromakiosk61'))
        self.persistence_policy_directories = QLineEdit()
        self.persistence_policy_directories.setPlaceholderText(tr('Controlled mode only: /home/<user>/data;/home/<user>/.config/app'))
        self.persistence_policy_dependency_value = QLabel(tr('Volatile policy requires Part 3 immutable_runtime; controlled policy requires Part 3 controlled_persistence before apply.'))
        self.persistence_policy_dependency_value.setWordWrap(True)
        self.persistence_policy_safety_value = QLabel(tr('Policy only: no mount/volume/initramfs edits are staged here. Existing persistence and persistent data remain untouched; dependencies are re-verified before apply.'))
        self.persistence_policy_safety_value.setWordWrap(True)
        persistence_policy_plan_form.addRow(tr('Requested policy:'), self.persistence_policy_operation)
        persistence_policy_plan_form.addRow(tr('Kiosk username:'), self.persistence_policy_username)
        persistence_policy_plan_form.addRow(tr('Persistent directories:'), self.persistence_policy_directories)
        persistence_policy_plan_form.addRow(tr('Dependency routing:'), self.persistence_policy_dependency_value)
        persistence_policy_plan_form.addRow(tr('Safety:'), self.persistence_policy_safety_value)
        persistence_policy_controls = QHBoxLayout()
        self.stage_persistence_policy_btn = QPushButton(tr('Stage persistence policy plan'))
        self.reset_persistence_policy_btn = QPushButton(tr('Reset'))
        self.persistence_policy_plan_status = QLabel(tr('Ready — no persistence-policy change staged.'))
        self.persistence_policy_plan_status.setWordWrap(True)
        persistence_policy_controls.addWidget(self.stage_persistence_policy_btn)
        persistence_policy_controls.addWidget(self.reset_persistence_policy_btn)
        persistence_policy_controls.addWidget(self.persistence_policy_plan_status, 1)
        persistence_policy_plan_form.addRow(tr(''), persistence_policy_controls)
        layout.addWidget(persistence_policy_plan_box)
        admin_recovery_evidence_box = QGroupBox(tr('Administrator/recovery policy capability — Alpha 62'))
        admin_recovery_evidence_form = QFormLayout(admin_recovery_evidence_box)
        self.admin_recovery_status_value = QLabel(tr('Analyze a source ISO first.'))
        self.admin_recovery_status_value.setWordWrap(True)
        self.admin_recovery_capability_value = QLabel(tr('UNKNOWN'))
        self.admin_recovery_admin_groups_value = QLabel(tr('—'))
        self.admin_recovery_admin_users_value = QLabel(tr('—'))
        self.admin_recovery_admin_users_value.setWordWrap(True)
        self.admin_recovery_autologin_value = QLabel(tr('—'))
        self.admin_recovery_scope_value = QLabel(tr('One separate non-root, non-autologin recovery administrator; credentials and stronger authenticators are deferred.'))
        self.admin_recovery_scope_value.setWordWrap(True)
        admin_recovery_evidence_form.addRow(tr('Detection:'), self.admin_recovery_status_value)
        admin_recovery_evidence_form.addRow(tr('Capability:'), self.admin_recovery_capability_value)
        admin_recovery_evidence_form.addRow(tr('Verified admin groups:'), self.admin_recovery_admin_groups_value)
        admin_recovery_evidence_form.addRow(tr('Existing admin users:'), self.admin_recovery_admin_users_value)
        admin_recovery_evidence_form.addRow(tr('Explicit autologin user:'), self.admin_recovery_autologin_value)
        admin_recovery_evidence_form.addRow(tr('Scope:'), self.admin_recovery_scope_value)
        layout.addWidget(admin_recovery_evidence_box)
        admin_recovery_plan_box = QGroupBox(tr('Administrator/recovery policy plan — staged only'))
        admin_recovery_plan_form = QFormLayout(admin_recovery_plan_box)
        admin_recovery_plan_form.setVerticalSpacing(5)
        self.admin_recovery_operation = QComboBox()
        self.admin_recovery_operation.addItem(tr('Preserve existing administrator/recovery policy'), 'preserve')
        self.admin_recovery_operation.addItem(tr('Require dedicated recovery administrator'), 'require_dedicated_recovery_administrator')
        self.admin_recovery_username = QLineEdit()
        self.admin_recovery_username.setPlaceholderText(tr('Recovery administrator username, e.g. chromarecovery62'))
        self.admin_recovery_admin_group = QComboBox()
        self.admin_recovery_dependency_value = QLabel(tr('Existing verified admin may be designated directly; a new name explicitly depends on the Alpha 50 administrator-account gate before apply.'))
        self.admin_recovery_dependency_value.setWordWrap(True)
        self.admin_recovery_safety_value = QLabel(tr('No password/recovery secret/authenticator, root-policy, rescue-boot, PAM or SSH change is staged. Recovery account must remain distinct from kiosk and explicit autologin roles.'))
        self.admin_recovery_safety_value.setWordWrap(True)
        admin_recovery_plan_form.addRow(tr('Requested policy:'), self.admin_recovery_operation)
        admin_recovery_plan_form.addRow(tr('Recovery username:'), self.admin_recovery_username)
        admin_recovery_plan_form.addRow(tr('Administrator group:'), self.admin_recovery_admin_group)
        admin_recovery_plan_form.addRow(tr('Dependency routing:'), self.admin_recovery_dependency_value)
        admin_recovery_plan_form.addRow(tr('Safety:'), self.admin_recovery_safety_value)
        admin_recovery_controls = QHBoxLayout()
        self.stage_admin_recovery_btn = QPushButton(tr('Stage administrator/recovery policy'))
        self.reset_admin_recovery_btn = QPushButton(tr('Reset'))
        self.admin_recovery_plan_status = QLabel(tr('Ready — no administrator/recovery policy change staged.'))
        self.admin_recovery_plan_status.setWordWrap(True)
        admin_recovery_controls.addWidget(self.stage_admin_recovery_btn)
        admin_recovery_controls.addWidget(self.reset_admin_recovery_btn)
        admin_recovery_controls.addWidget(self.admin_recovery_plan_status, 1)
        admin_recovery_plan_form.addRow(tr(''), admin_recovery_controls)
        layout.addWidget(admin_recovery_plan_box)
        fido2_evidence_box = QGroupBox(tr('FIDO2 policy capability — Alpha 63'))
        fido2_evidence_form = QFormLayout(fido2_evidence_box)
        self.fido2_status_value = QLabel(tr('Analyze a source ISO first.'))
        self.fido2_status_value.setWordWrap(True)
        self.fido2_capability_value = QLabel(tr('UNKNOWN'))
        self.fido2_pam_packages_value = QLabel(tr('—'))
        self.fido2_pam_packages_value.setWordWrap(True)
        self.fido2_lib_packages_value = QLabel(tr('—'))
        self.fido2_lib_packages_value.setWordWrap(True)
        self.fido2_scope_value = QLabel(tr('FIDO2 second-factor policy intent for the Alpha 62 recovery administrator only; no authenticator enrollment or WebAuthn/security-key/YubiKey/platform/TPM claim.'))
        self.fido2_scope_value.setWordWrap(True)
        fido2_evidence_form.addRow(tr('Detection:'), self.fido2_status_value)
        fido2_evidence_form.addRow(tr('Capability:'), self.fido2_capability_value)
        fido2_evidence_form.addRow(tr('PAM FIDO2/U2F packages:'), self.fido2_pam_packages_value)
        fido2_evidence_form.addRow(tr('libfido2 packages:'), self.fido2_lib_packages_value)
        fido2_evidence_form.addRow(tr('Scope:'), self.fido2_scope_value)
        layout.addWidget(fido2_evidence_box)
        fido2_plan_box = QGroupBox(tr('FIDO2 policy plan — staged only'))
        fido2_plan_form = QFormLayout(fido2_plan_box)
        fido2_plan_form.setVerticalSpacing(5)
        self.fido2_operation = QComboBox()
        self.fido2_operation.addItem(tr('Preserve existing authentication policy'), 'preserve')
        self.fido2_operation.addItem(tr('Require FIDO2 second factor for recovery administrator'), 'require_fido2_second_factor_for_recovery_admin')
        self.fido2_username = QLineEdit()
        self.fido2_username.setPlaceholderText(tr('Recovery administrator username, e.g. chromarecovery62'))
        self.fido2_dependency_value = QLabel(tr('Requires the verified Alpha 62 administrator/recovery-policy role before apply. The recovery username is re-verified at apply time.'))
        self.fido2_dependency_value.setWordWrap(True)
        self.fido2_safety_value = QLabel(tr('No PAM contents, authenticator device, USB/HID state, credential ID/secret or enrollment is read/staged. Existing primary authentication remains unchanged by this gate.'))
        self.fido2_safety_value.setWordWrap(True)
        fido2_plan_form.addRow(tr('Requested policy:'), self.fido2_operation)
        fido2_plan_form.addRow(tr('Recovery username:'), self.fido2_username)
        fido2_plan_form.addRow(tr('Dependency:'), self.fido2_dependency_value)
        fido2_plan_form.addRow(tr('Safety:'), self.fido2_safety_value)
        fido2_controls = QHBoxLayout()
        self.stage_fido2_btn = QPushButton(tr('Stage FIDO2 policy'))
        self.reset_fido2_btn = QPushButton(tr('Reset'))
        self.fido2_plan_status = QLabel(tr('Ready — no FIDO2 policy change staged.'))
        self.fido2_plan_status.setWordWrap(True)
        fido2_controls.addWidget(self.stage_fido2_btn)
        fido2_controls.addWidget(self.reset_fido2_btn)
        fido2_controls.addWidget(self.fido2_plan_status, 1)
        fido2_plan_form.addRow(tr(''), fido2_controls)
        layout.addWidget(fido2_plan_box)
        webauthn_evidence_box = QGroupBox(tr('WebAuthn policy capability — Alpha 64'))
        webauthn_evidence_form = QFormLayout(webauthn_evidence_box)
        self.webauthn_status_value = QLabel(tr('Analyze a source ISO first.'))
        self.webauthn_status_value.setWordWrap(True)
        self.webauthn_capability_value = QLabel(tr('UNKNOWN'))
        self.webauthn_browser_packages_value = QLabel(tr('—'))
        self.webauthn_browser_packages_value.setWordWrap(True)
        self.webauthn_scope_value = QLabel(tr('Browser-mediated WebAuthn recovery-policy intent only; no runtime/RP/origin/authenticator/security-key/YubiKey/platform/TPM claim.'))
        self.webauthn_scope_value.setWordWrap(True)
        webauthn_evidence_form.addRow(tr('Detection:'), self.webauthn_status_value)
        webauthn_evidence_form.addRow(tr('Capability:'), self.webauthn_capability_value)
        webauthn_evidence_form.addRow(tr('Verified browser packages:'), self.webauthn_browser_packages_value)
        webauthn_evidence_form.addRow(tr('Scope:'), self.webauthn_scope_value)
        layout.addWidget(webauthn_evidence_box)
        webauthn_plan_box = QGroupBox(tr('WebAuthn policy plan — staged only'))
        webauthn_plan_form = QFormLayout(webauthn_plan_box)
        webauthn_plan_form.setVerticalSpacing(5)
        self.webauthn_operation = QComboBox()
        self.webauthn_operation.addItem(tr('Preserve existing browser authentication policy'), 'preserve')
        self.webauthn_operation.addItem(tr('Allow WebAuthn for recovery web workflows'), 'allow_webauthn_for_recovery_web_workflows')
        self.webauthn_username = QLineEdit()
        self.webauthn_username.setPlaceholderText(tr('Recovery administrator username, e.g. chromarecovery62'))
        self.webauthn_browser = QComboBox()
        self.webauthn_dependency_value = QLabel(tr('Requires the verified Alpha 62 recovery role. Browser runtime, relying party, origin and authenticator are re-verified before actual use.'))
        self.webauthn_dependency_value.setWordWrap(True)
        self.webauthn_safety_value = QLabel(tr('No browser/RP/origin configuration, authenticator device, USB/HID state, credential ID/secret or enrollment is read/staged. This gate does not replace primary authentication.'))
        self.webauthn_safety_value.setWordWrap(True)
        webauthn_plan_form.addRow(tr('Requested policy:'), self.webauthn_operation)
        webauthn_plan_form.addRow(tr('Recovery username:'), self.webauthn_username)
        webauthn_plan_form.addRow(tr('Verified browser:'), self.webauthn_browser)
        webauthn_plan_form.addRow(tr('Dependency:'), self.webauthn_dependency_value)
        webauthn_plan_form.addRow(tr('Safety:'), self.webauthn_safety_value)
        webauthn_controls = QHBoxLayout()
        self.stage_webauthn_btn = QPushButton(tr('Stage WebAuthn policy'))
        self.reset_webauthn_btn = QPushButton(tr('Reset'))
        self.webauthn_plan_status = QLabel(tr('Ready — no WebAuthn policy change staged.'))
        self.webauthn_plan_status.setWordWrap(True)
        webauthn_controls.addWidget(self.stage_webauthn_btn)
        webauthn_controls.addWidget(self.reset_webauthn_btn)
        webauthn_controls.addWidget(self.webauthn_plan_status, 1)
        webauthn_plan_form.addRow(tr(''), webauthn_controls)
        layout.addWidget(webauthn_plan_box)
        security_key_evidence_box = QGroupBox(tr('Security-key policy capability — Alpha 65'))
        security_key_evidence_form = QFormLayout(security_key_evidence_box)
        self.security_key_status_value = QLabel(tr('Analyze a source ISO first.'))
        self.security_key_status_value.setWordWrap(True)
        self.security_key_capability_value = QLabel(tr('UNKNOWN'))
        self.security_key_packages_value = QLabel(tr('—'))
        self.security_key_packages_value.setWordWrap(True)
        self.security_key_scope_value = QLabel(tr('Generic external/roaming FIDO2/U2F security-key class for recovery administration; no physical key presence or enrollment claim.'))
        self.security_key_scope_value.setWordWrap(True)
        security_key_evidence_form.addRow(tr('Detection:'), self.security_key_status_value)
        security_key_evidence_form.addRow(tr('Capability:'), self.security_key_capability_value)
        security_key_evidence_form.addRow(tr('Verified target tooling:'), self.security_key_packages_value)
        security_key_evidence_form.addRow(tr('Scope:'), self.security_key_scope_value)
        layout.addWidget(security_key_evidence_box)
        security_key_plan_box = QGroupBox(tr('Security-key policy plan — staged only'))
        security_key_plan_form = QFormLayout(security_key_plan_box)
        self.security_key_operation = QComboBox()
        self.security_key_operation.addItem(tr('Preserve existing security-key policy'), 'preserve')
        self.security_key_operation.addItem(tr('Allow external FIDO2 security key for recovery administrator'), 'allow_external_fido2_security_key_for_recovery_admin')
        self.security_key_username = QLineEdit()
        self.security_key_username.setPlaceholderText(tr('Recovery administrator username, e.g. chromarecovery62'))
        self.security_key_safety_value = QLabel(tr('Requires verified Alpha 62 + Alpha 63 dependencies. Device presence, compatibility, enrollment, credential IDs/secrets and host USB/HID state are deferred to verified apply/runtime.'))
        self.security_key_safety_value.setWordWrap(True)
        security_key_plan_form.addRow(tr('Requested policy:'), self.security_key_operation)
        security_key_plan_form.addRow(tr('Recovery username:'), self.security_key_username)
        security_key_plan_form.addRow(tr('Safety:'), self.security_key_safety_value)
        security_key_controls = QHBoxLayout()
        self.stage_security_key_btn = QPushButton(tr('Stage security-key policy'))
        self.reset_security_key_btn = QPushButton(tr('Reset'))
        self.security_key_plan_status = QLabel(tr('Ready — no security-key policy change staged.'))
        self.security_key_plan_status.setWordWrap(True)
        security_key_controls.addWidget(self.stage_security_key_btn)
        security_key_controls.addWidget(self.reset_security_key_btn)
        security_key_controls.addWidget(self.security_key_plan_status, 1)
        security_key_plan_form.addRow(tr(''), security_key_controls)
        layout.addWidget(security_key_plan_box)
        yubikey_evidence_box = QGroupBox(tr('YubiKey-class policy capability — Alpha 66'))
        yubikey_evidence_form = QFormLayout(yubikey_evidence_box)
        self.yubikey_status_value = QLabel(tr('Analyze a source ISO first.'))
        self.yubikey_status_value.setWordWrap(True)
        self.yubikey_capability_value = QLabel(tr('UNKNOWN'))
        self.yubikey_packages_value = QLabel(tr('—'))
        self.yubikey_packages_value.setWordWrap(True)
        self.yubikey_scope_value = QLabel(tr('Vendor-class policy only; no physical YubiKey, serial number, PIN/OTP secret or enrollment is claimed.'))
        self.yubikey_scope_value.setWordWrap(True)
        yubikey_evidence_form.addRow(tr('Detection:'), self.yubikey_status_value)
        yubikey_evidence_form.addRow(tr('Capability:'), self.yubikey_capability_value)
        yubikey_evidence_form.addRow(tr('YubiKey-class packages:'), self.yubikey_packages_value)
        yubikey_evidence_form.addRow(tr('Scope:'), self.yubikey_scope_value)
        layout.addWidget(yubikey_evidence_box)
        yubikey_plan_box = QGroupBox(tr('YubiKey-class policy plan — staged only'))
        yubikey_plan_form = QFormLayout(yubikey_plan_box)
        self.yubikey_operation = QComboBox()
        self.yubikey_operation.addItem(tr('Preserve existing YubiKey-class policy'), 'preserve')
        self.yubikey_operation.addItem(tr('Allow YubiKey-class authenticator for recovery administrator'), 'allow_yubikey_class_authenticator_for_recovery_admin')
        self.yubikey_username = QLineEdit()
        self.yubikey_username.setPlaceholderText(tr('Recovery administrator username, e.g. chromarecovery62'))
        self.yubikey_safety_value = QLabel(tr('Target package metadata must positively identify YubiKey-class tooling. Physical device presence, serial/PIN/OTP data and enrollment remain outside analysis/staging.'))
        self.yubikey_safety_value.setWordWrap(True)
        yubikey_plan_form.addRow(tr('Requested policy:'), self.yubikey_operation)
        yubikey_plan_form.addRow(tr('Recovery username:'), self.yubikey_username)
        yubikey_plan_form.addRow(tr('Safety:'), self.yubikey_safety_value)
        yubikey_controls = QHBoxLayout()
        self.stage_yubikey_btn = QPushButton(tr('Stage YubiKey-class policy'))
        self.reset_yubikey_btn = QPushButton(tr('Reset'))
        self.yubikey_plan_status = QLabel(tr('Ready — no YubiKey-class policy change staged.'))
        self.yubikey_plan_status.setWordWrap(True)
        yubikey_controls.addWidget(self.stage_yubikey_btn)
        yubikey_controls.addWidget(self.reset_yubikey_btn)
        yubikey_controls.addWidget(self.yubikey_plan_status, 1)
        yubikey_plan_form.addRow(tr(''), yubikey_controls)
        layout.addWidget(yubikey_plan_box)
        platform_auth_evidence_box = QGroupBox(tr('Platform-authenticator capability — Alpha 67'))
        platform_auth_evidence_form = QFormLayout(platform_auth_evidence_box)
        self.platform_auth_status_value = QLabel(tr('Analyze a source ISO first.'))
        self.platform_auth_status_value.setWordWrap(True)
        self.platform_auth_capability_value = QLabel(tr('UNKNOWN'))
        self.platform_auth_runtime_value = QLabel(tr('Runtime/hardware verification required'))
        self.platform_auth_scope_value = QLabel(tr('Built-in WebAuthn platform authenticator only. Biometrics and TPM are never inferred or treated as equivalent.'))
        self.platform_auth_scope_value.setWordWrap(True)
        platform_auth_evidence_form.addRow(tr('Detection:'), self.platform_auth_status_value)
        platform_auth_evidence_form.addRow(tr('Capability:'), self.platform_auth_capability_value)
        platform_auth_evidence_form.addRow(tr('Verification:'), self.platform_auth_runtime_value)
        platform_auth_evidence_form.addRow(tr('Scope:'), self.platform_auth_scope_value)
        layout.addWidget(platform_auth_evidence_box)
        platform_auth_plan_box = QGroupBox(tr('Platform-authenticator policy — fail-closed'))
        platform_auth_plan_form = QFormLayout(platform_auth_plan_box)
        self.platform_auth_operation = QComboBox()
        self.platform_auth_operation.addItem(tr('Preserve existing platform-authenticator policy'), 'preserve')
        self.platform_auth_operation.addItem(tr('Allow verified platform authenticator for recovery workflows'), 'allow_verified_platform_authenticator_for_recovery_workflows')
        self.platform_auth_username = QLineEdit()
        self.platform_auth_username.setPlaceholderText(tr('Recovery administrator username'))
        self.platform_auth_safety_value = QLabel(tr('Current static ISO analysis cannot prove runtime platform-authenticator hardware/integration, so staging remains blocked unless future verified runtime evidence is available.'))
        self.platform_auth_safety_value.setWordWrap(True)
        platform_auth_plan_form.addRow(tr('Requested policy:'), self.platform_auth_operation)
        platform_auth_plan_form.addRow(tr('Recovery username:'), self.platform_auth_username)
        platform_auth_plan_form.addRow(tr('Safety:'), self.platform_auth_safety_value)
        platform_auth_controls = QHBoxLayout()
        self.stage_platform_auth_btn = QPushButton(tr('Stage platform-authenticator policy'))
        self.reset_platform_auth_btn = QPushButton(tr('Reset'))
        self.platform_auth_plan_status = QLabel(tr('Ready — platform-authenticator changes are fail-closed until runtime evidence exists.'))
        self.platform_auth_plan_status.setWordWrap(True)
        platform_auth_controls.addWidget(self.stage_platform_auth_btn)
        platform_auth_controls.addWidget(self.reset_platform_auth_btn)
        platform_auth_controls.addWidget(self.platform_auth_plan_status, 1)
        platform_auth_plan_form.addRow(tr(''), platform_auth_controls)
        layout.addWidget(platform_auth_plan_box)
        tpm_evidence_box = QGroupBox(tr('TPM-backed key protection capability — Alpha 68'))
        tpm_evidence_form = QFormLayout(tpm_evidence_box)
        self.tpm_status_value = QLabel(tr('Analyze a source ISO first.'))
        self.tpm_status_value.setWordWrap(True)
        self.tpm_capability_value = QLabel(tr('UNKNOWN'))
        self.tpm_packages_value = QLabel(tr('—'))
        self.tpm_packages_value.setWordWrap(True)
        self.tpm_scope_value = QLabel(tr('Recovery credential/key protection policy only. Package support does not prove TPM hardware, ownership or PCR state, and TPM is not a biometric authenticator.'))
        self.tpm_scope_value.setWordWrap(True)
        tpm_evidence_form.addRow(tr('Detection:'), self.tpm_status_value)
        tpm_evidence_form.addRow(tr('Capability:'), self.tpm_capability_value)
        tpm_evidence_form.addRow(tr('TPM2/TSS2 packages:'), self.tpm_packages_value)
        tpm_evidence_form.addRow(tr('Scope:'), self.tpm_scope_value)
        layout.addWidget(tpm_evidence_box)
        tpm_plan_box = QGroupBox(tr('TPM-backed key-protection plan — staged only'))
        tpm_plan_form = QFormLayout(tpm_plan_box)
        self.tpm_operation = QComboBox()
        self.tpm_operation.addItem(tr('Preserve existing key-protection policy'), 'preserve')
        self.tpm_operation.addItem(tr('Require TPM-backed recovery key protection'), 'require_tpm_backed_recovery_key_protection')
        self.tpm_username = QLineEdit()
        self.tpm_username.setPlaceholderText(tr('Recovery administrator username, e.g. chromarecovery62'))
        self.tpm_safety_value = QLabel(tr('Actual TPM presence/ownership/PCR policy and key generation/sealing are mandatory apply-time checks. No credential or key material is read, generated, staged or sealed here.'))
        self.tpm_safety_value.setWordWrap(True)
        tpm_plan_form.addRow(tr('Requested policy:'), self.tpm_operation)
        tpm_plan_form.addRow(tr('Recovery username:'), self.tpm_username)
        tpm_plan_form.addRow(tr('Safety:'), self.tpm_safety_value)
        tpm_controls = QHBoxLayout()
        self.stage_tpm_btn = QPushButton(tr('Stage TPM key-protection policy'))
        self.reset_tpm_btn = QPushButton(tr('Reset'))
        self.tpm_plan_status = QLabel(tr('Ready — no TPM key-protection policy change staged.'))
        self.tpm_plan_status.setWordWrap(True)
        tpm_controls.addWidget(self.stage_tpm_btn)
        tpm_controls.addWidget(self.reset_tpm_btn)
        tpm_controls.addWidget(self.tpm_plan_status, 1)
        tpm_plan_form.addRow(tr(''), tpm_controls)
        layout.addWidget(tpm_plan_box)
        evidence_box = QGroupBox(tr('Detected system packages'))
        evidence_layout = QVBoxLayout(evidence_box)
        self.evidence_tree = QTreeWidget()
        self.evidence_tree.setHeaderLabels([tr('Area / package'), tr('Version / evidence')])
        self.evidence_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.evidence_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        evidence_layout.addWidget(self.evidence_tree)
        layout.addWidget(evidence_box, 1)
        self.status = QLabel(tr('No source analyzed.'))
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.stage_identity_btn.clicked.connect(self._stage_identity_plan)
        self.reset_identity_btn.clicked.connect(self._reset_identity_plan)
        self.identity_role.currentIndexChanged.connect(self._refresh_identity_controls)
        self.identity_operation.currentIndexChanged.connect(self._refresh_identity_controls)
        self.identity_depth.currentIndexChanged.connect(self._identity_depth_changed)
        self.stage_machine_btn.clicked.connect(self._stage_machine_identity_plan)
        self.reset_machine_btn.clicked.connect(self._reset_machine_identity_plan)
        self.machine_operation.currentIndexChanged.connect(self._refresh_machine_controls)
        self.stage_autologin_btn.clicked.connect(self._stage_autologin_plan)
        self.reset_autologin_btn.clicked.connect(self._reset_autologin_plan)
        self.autologin_operation.currentIndexChanged.connect(self._refresh_autologin_controls)
        self.stage_locale_btn.clicked.connect(self._stage_locale_plan)
        self.reset_locale_btn.clicked.connect(self._reset_locale_plan)
        self.locale_operation.currentIndexChanged.connect(self._refresh_locale_controls)
        self.stage_keyboard_btn.clicked.connect(self._stage_keyboard_plan)
        self.reset_keyboard_btn.clicked.connect(self._reset_keyboard_plan)
        self.keyboard_operation.currentIndexChanged.connect(self._refresh_keyboard_controls)
        self.stage_timezone_btn.clicked.connect(self._stage_timezone_plan)
        self.reset_timezone_btn.clicked.connect(self._reset_timezone_plan)
        self.timezone_operation.currentIndexChanged.connect(self._refresh_timezone_controls)
        self.stage_network_btn.clicked.connect(self._stage_network_dns_plan)
        self.reset_network_btn.clicked.connect(self._reset_network_dns_plan)
        self.network_operation.currentIndexChanged.connect(self._refresh_network_controls)
        self.network_depth.currentIndexChanged.connect(self._network_depth_changed)
        self.stage_services_btn.clicked.connect(self._stage_services_plan)
        self.reset_services_btn.clicked.connect(self._reset_services_plan)
        self.services_operation.currentIndexChanged.connect(self._refresh_services_controls)
        self.stage_timers_btn.clicked.connect(self._stage_timers_plan)
        self.reset_timers_btn.clicked.connect(self._reset_timers_plan)
        self.timers_operation.currentIndexChanged.connect(self._refresh_timers_controls)
        self.stage_targets_btn.clicked.connect(self._stage_targets_plan)
        self.reset_targets_btn.clicked.connect(self._reset_targets_plan)
        self.targets_operation.currentIndexChanged.connect(self._refresh_targets_controls)
        self.stage_firewall_btn.clicked.connect(self._stage_firewall_plan)
        self.reset_firewall_btn.clicked.connect(self._reset_firewall_plan)
        self.stage_apparmor_btn.clicked.connect(self._stage_apparmor_plan)
        self.reset_apparmor_btn.clicked.connect(self._reset_apparmor_plan)
        self.stage_selinux_btn.clicked.connect(self._stage_selinux_plan)
        self.reset_selinux_btn.clicked.connect(self._reset_selinux_plan)
        self.stage_sysctl_btn.clicked.connect(self._stage_sysctl_plan)
        self.reset_sysctl_btn.clicked.connect(self._reset_sysctl_plan)
        self.sysctl_operation.currentIndexChanged.connect(self._refresh_sysctl_controls)
        self.stage_security_defaults_btn.clicked.connect(self._stage_security_defaults_plan)
        self.reset_security_defaults_btn.clicked.connect(self._reset_security_defaults_plan)
        self.security_defaults_operation.currentIndexChanged.connect(self._refresh_security_defaults_controls)
        self.stage_config_overlay_btn.clicked.connect(self._stage_config_overlay_plan)
        self.reset_config_overlay_btn.clicked.connect(self._reset_config_overlay_plan)
        self.config_overlay_operation.currentIndexChanged.connect(self._refresh_config_overlay_controls)
        self.stage_kiosk_user_btn.clicked.connect(self._stage_kiosk_user_plan)
        self.reset_kiosk_user_btn.clicked.connect(self._reset_kiosk_user_plan)
        self.kiosk_user_operation.currentIndexChanged.connect(self._refresh_kiosk_user_controls)
        self.stage_restricted_login_btn.clicked.connect(self._stage_restricted_login_plan)
        self.reset_restricted_login_btn.clicked.connect(self._reset_restricted_login_plan)
        self.restricted_login_operation.currentIndexChanged.connect(self._refresh_restricted_login_controls)
        self.stage_restricted_session_btn.clicked.connect(self._stage_restricted_session_plan)
        self.reset_restricted_session_btn.clicked.connect(self._reset_restricted_session_plan)
        self.restricted_session_operation.currentIndexChanged.connect(self._refresh_restricted_session_controls)
        self.stage_service_lockdown_btn.clicked.connect(self._stage_service_lockdown_plan)
        self.reset_service_lockdown_btn.clicked.connect(self._reset_service_lockdown_plan)
        self.service_lockdown_operation.currentIndexChanged.connect(self._refresh_service_lockdown_controls)
        self.stage_network_restriction_btn.clicked.connect(self._stage_network_restriction_plan)
        self.reset_network_restriction_btn.clicked.connect(self._reset_network_restriction_plan)
        self.network_restriction_operation.currentIndexChanged.connect(self._refresh_network_restriction_controls)
        self.stage_firewall_rules_btn.clicked.connect(self._stage_firewall_rules_plan)
        self.reset_firewall_rules_btn.clicked.connect(self._reset_firewall_rules_plan)
        self.firewall_rules_operation.currentIndexChanged.connect(self._refresh_firewall_rules_controls)
        self.stage_persistence_policy_btn.clicked.connect(self._stage_persistence_policy_plan)
        self.reset_persistence_policy_btn.clicked.connect(self._reset_persistence_policy_plan)
        self.persistence_policy_operation.currentIndexChanged.connect(self._refresh_persistence_policy_controls)
        self.stage_admin_recovery_btn.clicked.connect(self._stage_admin_recovery_policy_plan)
        self.reset_admin_recovery_btn.clicked.connect(self._reset_admin_recovery_policy_plan)
        self.admin_recovery_operation.currentIndexChanged.connect(self._refresh_admin_recovery_controls)
        self.stage_fido2_btn.clicked.connect(self._stage_fido2_policy_plan)
        self.reset_fido2_btn.clicked.connect(self._reset_fido2_policy_plan)
        self.fido2_operation.currentIndexChanged.connect(self._refresh_fido2_controls)
        self.stage_webauthn_btn.clicked.connect(self._stage_webauthn_policy_plan)
        self.reset_webauthn_btn.clicked.connect(self._reset_webauthn_policy_plan)
        self.webauthn_operation.currentIndexChanged.connect(self._refresh_webauthn_controls)
        self.stage_security_key_btn.clicked.connect(self._stage_security_key_policy_plan)
        self.reset_security_key_btn.clicked.connect(self._reset_security_key_policy_plan)
        self.security_key_operation.currentIndexChanged.connect(self._refresh_security_key_controls)
        self.stage_yubikey_btn.clicked.connect(self._stage_yubikey_policy_plan)
        self.reset_yubikey_btn.clicked.connect(self._reset_yubikey_policy_plan)
        self.yubikey_operation.currentIndexChanged.connect(self._refresh_yubikey_controls)
        self.stage_platform_auth_btn.clicked.connect(self._stage_platform_authenticator_policy_plan)
        self.reset_platform_auth_btn.clicked.connect(self._reset_platform_authenticator_policy_plan)
        self.platform_auth_operation.currentIndexChanged.connect(self._refresh_platform_authenticator_controls)
        self.stage_tpm_btn.clicked.connect(self._stage_tpm_key_protection_plan)
        self.reset_tpm_btn.clicked.connect(self._reset_tpm_key_protection_plan)
        self.tpm_operation.currentIndexChanged.connect(self._refresh_tpm_controls)
        self._refresh_identity_controls()
        self._refresh_machine_controls()
        self._refresh_autologin_controls()
        self._refresh_locale_controls()
        self._refresh_keyboard_controls()
        self._refresh_timezone_controls()
        self._refresh_network_controls()
        self._refresh_services_controls()
        self._refresh_timers_controls()
        self._refresh_targets_controls()
        self._refresh_sysctl_controls()
        self._refresh_kiosk_user_controls()
        self._refresh_restricted_login_controls()
        self._refresh_restricted_session_controls()
        self._refresh_service_lockdown_controls()
        self._refresh_network_restriction_controls()
        self._refresh_firewall_rules_controls()
        self._refresh_persistence_policy_controls()
        self._refresh_admin_recovery_controls()
        self._refresh_fido2_controls()
        self._refresh_webauthn_controls()
        self._refresh_security_key_controls()
        self._refresh_yubikey_controls()
        self._refresh_platform_authenticator_controls()
        self._refresh_tpm_controls()

    def _populate_identity_operations(self) -> None:
        current = str(self.identity_operation.currentData() or 'preserve')
        items = [('Preserve existing users/groups/password policy', 'preserve'), ('Configure target-system default user', 'configure_default_user'), ('Create target-system user', 'create_user'), ('Modify existing target-system user', 'modify_user')]
        if self.identity_depth.currentData() in {'advanced', 'expert'}:
            items.append(('Create target-system group', 'create_group'))
        self.identity_operation.blockSignals(True)
        self.identity_operation.clear()
        for label, value in items:
            self.identity_operation.addItem(tr(label), value)
        idx = self.identity_operation.findData(current)
        self.identity_operation.setCurrentIndex(idx if idx >= 0 else 0)
        self.identity_operation.blockSignals(False)

    def _identity_depth_changed(self) -> None:
        self._populate_identity_operations()
        self._refresh_identity_controls()

    def _refresh_identity_controls(self) -> None:
        operation = str(self.identity_operation.currentData() or 'preserve')
        user_operation = operation in {'configure_default_user', 'create_user', 'modify_user'}
        group_operation = operation == 'create_group'
        advanced = self.identity_depth.currentData() in {'advanced', 'expert'}
        for widget in (self.identity_username, self.identity_display_name, self.identity_role):
            widget.setEnabled(user_operation)
        admin = user_operation and self.identity_role.currentData() == 'administrator'
        self.identity_admin_group.setEnabled(admin)
        self.identity_advanced_box.setVisible(advanced)
        for widget in (self.identity_uid, self.identity_gid, self.identity_supplementary_groups, self.identity_password_min_days, self.identity_password_max_days, self.identity_password_warn_days):
            widget.setEnabled(user_operation and advanced)
        self.identity_group_name.setEnabled(group_operation and advanced)
        self.identity_group_gid.setEnabled(group_operation and advanced)

    def _reset_identity_plan(self) -> None:
        self._populate_identity_operations()
        self.identity_operation.setCurrentIndex(0)
        self.identity_username.clear()
        self.identity_display_name.clear()
        self.identity_role.setCurrentIndex(0)
        if self.identity_admin_group.count():
            self.identity_admin_group.setCurrentIndex(0)
        for widget in (self.identity_uid, self.identity_gid, self.identity_supplementary_groups, self.identity_group_name, self.identity_group_gid, self.identity_password_min_days, self.identity_password_max_days, self.identity_password_warn_days):
            widget.clear()
        self.identity_plan_status.setText(tr('Ready — no users/groups/password-policy changes staged.'))
        self._refresh_identity_controls()

    def _refresh_machine_controls(self) -> None:
        configure = self.machine_operation.currentData() == 'configure_hostname'
        self.machine_hostname.setEnabled(configure)
        self.machine_id_policy.setEnabled(configure)

    def _reset_machine_identity_plan(self) -> None:
        self.machine_operation.setCurrentIndex(0)
        self.machine_hostname.clear()
        self.machine_id_policy.setCurrentIndex(0)
        self.machine_plan_status.setText(tr('Ready — no hostname/machine identity changes staged.'))
        self._refresh_machine_controls()

    def _refresh_autologin_controls(self) -> None:
        enable = self.autologin_operation.currentData() == 'enable_autologin'
        self.autologin_target_user.setEnabled(enable)

    def _reset_autologin_plan(self) -> None:
        self.autologin_operation.setCurrentIndex(0)
        self.autologin_target_user.clear()
        self.autologin_plan_status.setText(tr('Ready — no autologin changes staged.'))
        self._refresh_autologin_controls()

    def _refresh_locale_controls(self) -> None:
        configure = self.locale_operation.currentData() == 'configure_lang'
        self.locale_target.setEnabled(configure)

    def _reset_locale_plan(self) -> None:
        self.locale_operation.setCurrentIndex(0)
        self.locale_target.clear()
        self.locale_plan_status.setText(tr('Ready — no locale/language changes staged.'))
        self._refresh_locale_controls()

    def _refresh_keyboard_controls(self) -> None:
        configure = self.keyboard_operation.currentData() == 'configure_layout'
        self.keyboard_target.setEnabled(configure)

    def _reset_keyboard_plan(self) -> None:
        self.keyboard_operation.setCurrentIndex(0)
        self.keyboard_target.clear()
        self.keyboard_plan_status.setText(tr('Ready — no keyboard-layout changes staged.'))
        self._refresh_keyboard_controls()

    def _refresh_timezone_controls(self) -> None:
        configure = self.timezone_operation.currentData() == 'configure_timezone'
        self.timezone_target.setEnabled(configure)

    def _reset_timezone_plan(self) -> None:
        self.timezone_operation.setCurrentIndex(0)
        self.timezone_target.clear()
        self.timezone_plan_status.setText(tr('Ready — no timezone changes staged.'))
        self._refresh_timezone_controls()

    def _network_supported_operations(self) -> list[str]:
        evidence = dict(self._analysis.get('system_network_dns_evidence') or {})
        operations = [str(x) for x in evidence.get('supported_operations') or [] if str(x).strip()]
        if not operations and evidence.get('verified') is True:
            operations = ['configure_dns_servers']
        return operations

    def _populate_network_operations(self) -> None:
        current = str(self.network_operation.currentData() or '')
        depth = str(self.network_depth.currentData() or 'quick')
        supported = set(self._network_supported_operations())
        choices = [('Preserve existing networking', 'preserve')]
        if 'configure_dns_servers' in supported:
            choices.append(('Configure target-system DNS servers', 'configure_dns_servers'))
        if 'configure_dhcp_ipv4' in supported:
            choices.append(('Configure DHCP / automatic IPv4', 'configure_dhcp_ipv4'))
        if depth in {'advanced', 'expert'}:
            if 'configure_static_ipv4' in supported:
                choices.append(('Configure static IPv4 + gateway', 'configure_static_ipv4'))
            if 'create_networkmanager_profile' in supported:
                choices.append(('Create managed NetworkManager Ethernet profile', 'create_networkmanager_profile'))
            if 'set_networkmanager_autoconnect' in supported:
                choices.append(('Set existing NetworkManager profile autoconnect', 'set_networkmanager_autoconnect'))
        self.network_operation.blockSignals(True)
        self.network_operation.clear()
        for label, value in choices:
            self.network_operation.addItem(tr(label), value)
        idx = self.network_operation.findData(current)
        self.network_operation.setCurrentIndex(idx if idx >= 0 else 0)
        self.network_operation.blockSignals(False)
        self._refresh_network_controls()

    def _network_depth_changed(self) -> None:
        self._populate_network_operations()

    def _refresh_network_controls(self) -> None:
        operation = str(self.network_operation.currentData() or 'preserve')
        backend = str((self._analysis.get('system_network_dns_evidence') or {}).get('backend') or '')
        nm_managed = backend == 'NetworkManager' and operation in {'configure_dhcp_ipv4', 'configure_static_ipv4', 'configure_dns_servers', 'create_networkmanager_profile'}
        self.network_profile_name.setEnabled(nm_managed)
        self.network_existing_profile.setEnabled(operation == 'set_networkmanager_autoconnect')
        self.network_interface.setEnabled(operation in {'configure_dhcp_ipv4', 'configure_static_ipv4', 'create_networkmanager_profile'})
        self.network_ipv4_address.setEnabled(operation == 'configure_static_ipv4')
        self.network_gateway.setEnabled(operation == 'configure_static_ipv4')
        self.network_dns_target.setEnabled(operation in {'configure_dns_servers', 'configure_static_ipv4', 'create_networkmanager_profile'})
        self.network_autoconnect.setEnabled(operation in {'create_networkmanager_profile', 'set_networkmanager_autoconnect'})

    def _reset_network_dns_plan(self) -> None:
        self.network_depth.setCurrentIndex(0)
        self.network_profile_name.setText(tr('ChromaPress Ethernet'))
        self.network_interface.clear()
        self.network_ipv4_address.clear()
        self.network_gateway.clear()
        self.network_dns_target.clear()
        self.network_autoconnect.setCurrentIndex(0)
        self.network_existing_profile.clear()
        profiles = [str(x) for x in (self._analysis.get('system_network_dns_evidence') or {}).get('networkmanager_profile_names') or [] if str(x).strip()]
        if profiles:
            for name in profiles:
                self.network_existing_profile.addItem(name, name)
        else:
            self.network_existing_profile.addItem(tr('No verified existing NetworkManager profile'), '')
        self._populate_network_operations()
        self.network_plan_status.setText(tr('Ready — no networking changes staged.'))
        self._refresh_network_controls()

    def _refresh_services_controls(self) -> None:
        configure = self.services_operation.currentData() in {'enable_service', 'disable_service'}
        self.services_target.setEnabled(configure)

    def _reset_services_plan(self) -> None:
        self.services_operation.setCurrentIndex(0)
        self.services_target.clear()
        self.services_plan_status.setText(tr('Ready — no services/systemd changes staged.'))
        self._refresh_services_controls()

    def _refresh_timers_controls(self) -> None:
        configure = self.timers_operation.currentData() in {'enable_timer', 'disable_timer'}
        self.timers_target.setEnabled(configure)

    def _reset_timers_plan(self) -> None:
        self.timers_operation.setCurrentIndex(0)
        self.timers_target.clear()
        self.timers_plan_status.setText(tr('Ready — no timers/systemd changes staged.'))
        self._refresh_timers_controls()

    @staticmethod
    def _safe_timezone_name(value: str) -> bool:
        value = value.strip()
        if not value or len(value) > 128 or value.startswith('/') or ('\x00' in value):
            return False
        if not re.fullmatch('[A-Za-z0-9._+\\-/]+', value):
            return False
        return all((part not in {'', '.', '..'} for part in value.split('/')))

    def _refresh_targets_controls(self) -> None:
        configure = self.targets_operation.currentData() == 'set_default_target'
        self.targets_target.setEnabled(configure)

    def _reset_targets_plan(self) -> None:
        self.targets_operation.setCurrentIndex(0)
        self.targets_target.clear()
        self.targets_plan_status.setText(tr('Ready — no targets/startup changes staged.'))
        self._refresh_targets_controls()

    def _reset_firewall_plan(self) -> None:
        self.firewall_operation.setCurrentIndex(0)
        self.firewall_plan_status.setText(tr('Ready — no firewall changes staged.'))

    def _reset_apparmor_plan(self) -> None:
        self.apparmor_operation.setCurrentIndex(0)
        self.apparmor_plan_status.setText(tr('Ready — no AppArmor changes staged.'))

    def _populate_selinux_modes(self) -> None:
        evidence = dict(self._analysis.get('system_selinux_evidence') or {})
        supported = {str(x) for x in evidence.get('supported_modes') or []}
        current = str(self.selinux_mode.currentData() or 'preserve')
        self.selinux_mode.blockSignals(True)
        self.selinux_mode.clear()
        self.selinux_mode.addItem(tr('Preserve existing SELinux state'), 'preserve')
        labels = {'enforcing': 'Enable / configure SELinux enforcing', 'permissive': 'Enable / configure SELinux permissive', 'disabled': 'Configure SELinux disabled'}
        if str(evidence.get('capability_status') or 'UNKNOWN') in {'SUPPORTED', 'SUPPORTED_WITH_REQUIREMENTS'}:
            for mode in ('enforcing', 'permissive', 'disabled'):
                if mode in supported:
                    self.selinux_mode.addItem(tr(labels[mode]), mode)
        idx = self.selinux_mode.findData(current)
        self.selinux_mode.setCurrentIndex(idx if idx >= 0 else 0)
        self.selinux_mode.blockSignals(False)

    def _reset_selinux_plan(self) -> None:
        self._populate_selinux_modes()
        self.selinux_mode.setCurrentIndex(0)
        self.selinux_plan_status.setText(tr('Ready — no SELinux changes staged.'))

    def _refresh_sysctl_controls(self) -> None:
        configure = self.sysctl_operation.currentData() == 'set_integer_sysctl'
        self.sysctl_key.setEnabled(configure)
        self.sysctl_value.setEnabled(configure)

    def _reset_sysctl_plan(self) -> None:
        self.sysctl_operation.setCurrentIndex(0)
        self.sysctl_key.clear()
        self.sysctl_value.clear()
        self.sysctl_plan_status.setText(tr('Ready — no sysctl changes staged.'))
        self._refresh_sysctl_controls()

    def _refresh_security_defaults_controls(self) -> None:
        configure = self.security_defaults_operation.currentData() == 'set_default_umask'
        self.security_defaults_umask.setEnabled(configure)

    def _reset_security_defaults_plan(self) -> None:
        self.security_defaults_operation.setCurrentIndex(0)
        self.security_defaults_umask.setCurrentIndex(1)
        self.security_defaults_plan_status.setText(tr('Ready — no security-default changes staged.'))
        self._refresh_security_defaults_controls()

    def _refresh_config_overlay_controls(self) -> None:
        configure = self.config_overlay_operation.currentData() == 'add_managed_environment_overlay'
        self.config_overlay_name.setEnabled(configure)
        self.config_overlay_variable.setEnabled(configure)
        self.config_overlay_value.setEnabled(configure)

    def _reset_config_overlay_plan(self) -> None:
        self.config_overlay_operation.setCurrentIndex(0)
        self.config_overlay_name.clear()
        self.config_overlay_variable.clear()
        self.config_overlay_value.clear()
        self.config_overlay_plan_status.setText(tr('Ready — no system-configuration overlay staged.'))
        self._refresh_config_overlay_controls()

    def _refresh_kiosk_user_controls(self) -> None:
        configure = self.kiosk_user_operation.currentData() == 'create_dedicated_non_admin_kiosk_user'
        self.kiosk_username.setEnabled(configure)
        self.kiosk_display_name.setEnabled(configure)

    def _reset_kiosk_user_plan(self) -> None:
        self.kiosk_user_operation.setCurrentIndex(0)
        self.kiosk_username.clear()
        self.kiosk_display_name.clear()
        self.kiosk_user_plan_status.setText(tr('Ready — no dedicated kiosk-user change staged.'))
        self._refresh_kiosk_user_controls()

    def _refresh_restricted_login_controls(self) -> None:
        configure = self.restricted_login_operation.currentData() == 'lock_password_authentication'
        self.restricted_login_username.setEnabled(configure)

    def _reset_restricted_login_plan(self) -> None:
        self.restricted_login_operation.setCurrentIndex(0)
        self.restricted_login_username.clear()
        self.restricted_login_plan_status.setText(tr('Ready — no restricted-login change staged.'))
        self._refresh_restricted_login_controls()

    def _refresh_restricted_session_controls(self) -> None:
        configure = self.restricted_session_operation.currentData() == 'bind_kiosk_autologin_session'
        self.restricted_session_username.setEnabled(configure)
        self.restricted_session_choice.setEnabled(configure)

    def _reset_restricted_session_plan(self) -> None:
        self.restricted_session_operation.setCurrentIndex(0)
        self.restricted_session_username.clear()
        self.restricted_session_plan_status.setText(tr('Ready — no restricted-session change staged.'))
        self._refresh_restricted_session_controls()

    def _refresh_service_lockdown_controls(self) -> None:
        configure = self.service_lockdown_operation.currentData() == 'disable_and_mask_verified_service'
        self.service_lockdown_choice.setEnabled(configure)

    def _reset_service_lockdown_plan(self) -> None:
        self.service_lockdown_operation.setCurrentIndex(0)
        self.service_lockdown_plan_status.setText(tr('Ready — no service-lockdown change staged.'))
        self._refresh_service_lockdown_controls()

    def _refresh_network_restriction_controls(self) -> None:
        configure = self.network_restriction_operation.currentData() == 'restrict_kiosk_networkmanager_control'
        self.network_restriction_username.setEnabled(configure)

    def _reset_network_restriction_plan(self) -> None:
        self.network_restriction_operation.setCurrentIndex(0)
        self.network_restriction_username.clear()
        self.network_restriction_plan_status.setText(tr('Ready — no network-restriction change staged.'))
        self._refresh_network_restriction_controls()

    def _refresh_firewall_rules_controls(self) -> None:
        configure = self.firewall_rules_operation.currentData() == 'deny_inbound_tcp_port'
        self.firewall_rules_port.setEnabled(configure)

    def _reset_firewall_rules_plan(self) -> None:
        self.firewall_rules_operation.setCurrentIndex(0)
        self.firewall_rules_port.clear()
        self.firewall_rules_plan_status.setText(tr('Ready — no firewall-rule change staged.'))
        self._refresh_firewall_rules_controls()

    def _refresh_persistence_policy_controls(self) -> None:
        operation = str(self.persistence_policy_operation.currentData() or 'preserve')
        configure = operation in {'require_volatile_kiosk_runtime', 'require_controlled_kiosk_persistence'}
        self.persistence_policy_username.setEnabled(configure)
        self.persistence_policy_directories.setEnabled(operation == 'require_controlled_kiosk_persistence')

    def _reset_persistence_policy_plan(self) -> None:
        self.persistence_policy_operation.setCurrentIndex(0)
        self.persistence_policy_username.clear()
        self.persistence_policy_directories.clear()
        self.persistence_policy_plan_status.setText(tr('Ready — no persistence-policy change staged.'))
        self._refresh_persistence_policy_controls()

    def _refresh_admin_recovery_controls(self) -> None:
        configure = str(self.admin_recovery_operation.currentData() or 'preserve') == 'require_dedicated_recovery_administrator'
        self.admin_recovery_username.setEnabled(configure)
        self.admin_recovery_admin_group.setEnabled(configure)

    def _reset_admin_recovery_policy_plan(self) -> None:
        self.admin_recovery_operation.setCurrentIndex(0)
        self.admin_recovery_username.clear()
        self.admin_recovery_plan_status.setText(tr('Ready — no administrator/recovery policy change staged.'))
        self._refresh_admin_recovery_controls()

    def _refresh_fido2_controls(self) -> None:
        configure = str(self.fido2_operation.currentData() or 'preserve') == 'require_fido2_second_factor_for_recovery_admin'
        self.fido2_username.setEnabled(configure)

    def _reset_fido2_policy_plan(self) -> None:
        self.fido2_operation.setCurrentIndex(0)
        self.fido2_username.clear()
        self.fido2_plan_status.setText(tr('Ready — no FIDO2 policy change staged.'))
        self._refresh_fido2_controls()

    def _refresh_webauthn_controls(self) -> None:
        configure = str(self.webauthn_operation.currentData() or 'preserve') == 'allow_webauthn_for_recovery_web_workflows'
        self.webauthn_username.setEnabled(configure)
        self.webauthn_browser.setEnabled(configure)

    def _reset_webauthn_policy_plan(self) -> None:
        self.webauthn_operation.setCurrentIndex(0)
        self.webauthn_username.clear()
        self.webauthn_plan_status.setText(tr('Ready — no WebAuthn policy change staged.'))
        self._refresh_webauthn_controls()

    def _refresh_security_key_controls(self) -> None:
        configure = str(self.security_key_operation.currentData() or 'preserve') == 'allow_external_fido2_security_key_for_recovery_admin'
        self.security_key_username.setEnabled(configure)

    def _reset_security_key_policy_plan(self) -> None:
        self.security_key_operation.setCurrentIndex(0)
        self.security_key_username.clear()
        self.security_key_plan_status.setText(tr('Ready — no security-key policy change staged.'))
        self._refresh_security_key_controls()

    def _refresh_yubikey_controls(self) -> None:
        configure = str(self.yubikey_operation.currentData() or 'preserve') == 'allow_yubikey_class_authenticator_for_recovery_admin'
        self.yubikey_username.setEnabled(configure)

    def _reset_yubikey_policy_plan(self) -> None:
        self.yubikey_operation.setCurrentIndex(0)
        self.yubikey_username.clear()
        self.yubikey_plan_status.setText(tr('Ready — no YubiKey-class policy change staged.'))
        self._refresh_yubikey_controls()

    def _refresh_platform_authenticator_controls(self) -> None:
        configure = str(self.platform_auth_operation.currentData() or 'preserve') == 'allow_verified_platform_authenticator_for_recovery_workflows'
        self.platform_auth_username.setEnabled(configure)

    def _reset_platform_authenticator_policy_plan(self) -> None:
        self.platform_auth_operation.setCurrentIndex(0)
        self.platform_auth_username.clear()
        self.platform_auth_plan_status.setText(tr('Ready — platform-authenticator changes are fail-closed until runtime evidence exists.'))
        self._refresh_platform_authenticator_controls()

    def _refresh_tpm_controls(self) -> None:
        configure = str(self.tpm_operation.currentData() or 'preserve') == 'require_tpm_backed_recovery_key_protection'
        self.tpm_username.setEnabled(configure)

    def _reset_tpm_key_protection_plan(self) -> None:
        self.tpm_operation.setCurrentIndex(0)
        self.tpm_username.clear()
        self.tpm_plan_status.setText(tr('Ready — no TPM key-protection policy change staged.'))
        self._refresh_tpm_controls()

    @staticmethod
    def _parse_kiosk_persistence_directories(username: str, raw: str) -> list[str]:
        parts = [x.strip() for x in str(raw or '').split(';') if x.strip()]
        if not parts:
            raise ValueError('Controlled persistence requires at least one kiosk-home subdirectory.')
        if len(parts) > 8:
            raise ValueError('Controlled persistence is limited to at most 8 explicit kiosk-home directories per staged policy.')
        prefix = f'/home/{username}/'
        result: list[str] = []
        for path in parts:
            if '\x00' in path or '\n' in path or '\r' in path or ('..' in path.split('/')):
                raise ValueError('Persistent directory contains unsafe path data.')
            if not path.startswith(prefix) or path == prefix.rstrip('/'):
                raise ValueError(f'Persistent directories must be explicit subdirectories below /home/{username}/.')
            if not re.fullmatch('/[A-Za-z0-9._+@/-]{1,240}', path):
                raise ValueError('Persistent directory contains unsupported characters.')
            normalized = path.rstrip('/')
            if normalized not in result:
                result.append(normalized)
        return result

    def set_analysis(self, data: dict) -> None:
        self._analysis = dict(data or {})
        sha = str(data.get('sha256') or '')
        package_format = str(data.get('package_format') or 'unknown')
        evidence = list(data.get('system_package_evidence') or [])
        gates = [str(x) for x in data.get('system_rootfs_verification') or [] if str(x).strip()]
        identity = dict(data.get('system_identity_evidence') or {})
        machine = dict(data.get('system_machine_identity_evidence') or {})
        autologin = dict(data.get('system_autologin_evidence') or {})
        locale = dict(data.get('system_locale_evidence') or {})
        keyboard = dict(data.get('system_keyboard_evidence') or {})
        timezone = dict(data.get('system_timezone_evidence') or {})
        network = dict(data.get('system_network_dns_evidence') or {})
        services = dict(data.get('system_services_evidence') or {})
        timers = dict(data.get('system_timers_evidence') or {})
        targets = dict(data.get('system_targets_evidence') or {})
        firewall = dict(data.get('system_firewall_evidence') or {})
        apparmor = dict(data.get('system_apparmor_evidence') or {})
        selinux = dict(data.get('system_selinux_evidence') or {})
        sysctl = dict(data.get('system_sysctl_evidence') or {})
        security_defaults = dict(data.get('system_security_defaults_evidence') or {})
        config_overlay = dict(data.get('system_config_overlay_evidence') or {})
        kiosk_user = dict(data.get('system_kiosk_user_evidence') or {})
        restricted_login = dict(data.get('system_restricted_login_evidence') or {})
        restricted_session = dict(data.get('system_restricted_session_evidence') or {})
        service_lockdown = dict(data.get('system_service_lockdown_evidence') or {})
        network_restriction = dict(data.get('system_network_restriction_evidence') or {})
        firewall_rules = dict(data.get('system_firewall_rules_evidence') or {})
        persistence_policy = dict(data.get('system_persistence_policy_evidence') or {})
        admin_recovery = dict(data.get('system_admin_recovery_policy_evidence') or {})
        fido2_policy = dict(data.get('system_fido2_policy_evidence') or {})
        webauthn_policy = dict(data.get('system_webauthn_policy_evidence') or {})
        security_key_policy = dict(data.get('system_security_key_policy_evidence') or {})
        yubikey_policy = dict(data.get('system_yubikey_policy_evidence') or {})
        platform_auth_policy = dict(data.get('system_platform_authenticator_policy_evidence') or {})
        tpm_policy = dict(data.get('system_tpm_key_protection_evidence') or {})
        self.package_format_value.setText(package_format or tr('unknown'))
        areas = []
        for item in evidence:
            area = str(item.get('area') or 'Other')
            if area not in areas:
                areas.append(area)
        self.areas_value.setText('; '.join(areas) if areas else tr('No matching manifest-backed system capability packages'))
        self.rootfs_value.setText('; '.join(gates) if gates else tr('No rootfs verification list available'))
        self.source_hash_value.setText(sha or tr('—'))
        verified = identity.get('verified') is True
        reason = str(identity.get('reason') or 'UNKNOWN — target-rootfs account capability has not been verified.')
        self.identity_status_value.setText(tr(reason))
        capability = str(identity.get('capability_status') or 'UNKNOWN')
        pw_capability = str(identity.get('password_policy_status') or 'UNKNOWN')
        self.identity_capability_value.setText(tr(f"Users/groups: {capability} | UID/GID: {identity.get('uid_gid_status', 'UNKNOWN')} | Group membership: {identity.get('group_membership_status', 'UNKNOWN')} | Password policy: {pw_capability}"))
        layers = []
        for key in ('passwd_layer', 'group_layer', 'login_defs_layer'):
            value = str(identity.get(key) or '').strip()
            if value and value not in layers:
                layers.append(value)
        self.identity_layers_value.setText('; '.join(layers) if layers else tr('Not verified'))
        regular_users = [str(x) for x in identity.get('regular_users') or [] if str(x).strip()]
        self.identity_users_value.setText(', '.join(regular_users) if regular_users else tr('None detected') if verified else tr('Not verified'))
        self.identity_default_user_value.setText(str(identity.get('default_user_candidate') or (tr('Not uniquely detectable') if verified else tr('Not verified'))))
        admin_groups = [str(x) for x in identity.get('admin_groups') or [] if str(x).strip()]
        self.identity_admin_groups_value.setText(', '.join(admin_groups) if admin_groups else tr('None detected') if verified else tr('Not verified'))
        self.identity_uid_min_value.setText(str(identity.get('uid_min', '—')) if verified else tr('—'))
        policy = dict(identity.get('password_policy') or {})
        if policy:
            policy_bits = []
            for label, key in (('min', 'min_days'), ('max', 'max_days'), ('warn', 'warn_days')):
                if key in policy:
                    policy_bits.append(f'{label}={policy[key]}d')
            if policy.get('encrypt_method'):
                policy_bits.append(f"method={policy['encrypt_method']}")
            self.identity_password_policy_value.setText(', '.join(policy_bits) if policy_bits else tr('Detected, no supported aging values parsed'))
        else:
            self.identity_password_policy_value.setText(tr('Preserve / UNKNOWN') if verified else tr('Not verified'))
        self.identity_admin_group.clear()
        if admin_groups:
            for group in admin_groups:
                self.identity_admin_group.addItem(group, group)
        else:
            self.identity_admin_group.addItem(tr('No verified admin group'), '')
        self._reset_identity_plan()
        machine_verified = machine.get('verified') is True
        self.machine_status_value.setText(str(machine.get('reason') or tr('Rootfs hostname/machine identity evidence is not available.')))
        self.machine_hostname_value.setText(str(machine.get('hostname') or (tr('Not verified') if not machine_verified else tr('—'))))
        self.machine_hostname_layer_value.setText(str(machine.get('hostname_layer') or tr('Not verified')))
        machine_state = str(machine.get('machine_id_state') or 'unknown')
        self.machine_id_state_value.setText(machine_state if machine_verified else tr('Not verified'))
        self.machine_id_layer_value.setText(str(machine.get('machine_id_layer') or (tr('Not present in selected rootfs') if machine_verified else tr('Not verified'))))
        self._reset_machine_identity_plan()
        autologin_verified = autologin.get('verified') is True
        self.autologin_status_value.setText(str(autologin.get('reason') or tr('Rootfs display-manager/autologin evidence is not available.')))
        self.autologin_dm_value.setText(str(autologin.get('display_manager') or (tr('Not verified') if not autologin_verified else tr('—'))))
        self.autologin_dm_layer_value.setText(str(autologin.get('display_manager_layer') or tr('Not verified')))
        self.autologin_state_value.setText(str(autologin.get('autologin_state') or (tr('Not verified') if not autologin_verified else tr('—'))))
        self.autologin_user_value.setText(str(autologin.get('autologin_user') or (tr('None explicitly configured') if autologin_verified else tr('Not verified'))))
        self._reset_autologin_plan()
        locale_verified = locale.get('verified') is True
        self.locale_status_value.setText(str(locale.get('reason') or tr('Rootfs locale/language evidence is not available.')))
        self.locale_path_value.setText(str(locale.get('config_path') or (tr('Not verified') if not locale_verified else tr('—'))))
        self.locale_layer_value.setText(str(locale.get('config_layer') or tr('Not verified')))
        self.locale_lang_value.setText(str(locale.get('current_lang') or (tr('Not explicitly configured') if locale_verified else tr('Not verified'))))
        self.locale_language_value.setText(str(locale.get('current_language') or (tr('Not explicitly configured') if locale_verified else tr('Not verified'))))
        self._reset_locale_plan()
        keyboard_verified = keyboard.get('verified') is True
        self.keyboard_status_value.setText(str(keyboard.get('reason') or tr('Rootfs keyboard configuration evidence is not available.')))
        self.keyboard_path_value.setText(str(keyboard.get('config_path') or (tr('Not verified') if not keyboard_verified else tr('—'))))
        self.keyboard_layer_value.setText(str(keyboard.get('config_layer') or tr('Not verified')))
        self.keyboard_layout_value.setText(str(keyboard.get('current_layout') or (tr('Not explicitly configured') if keyboard_verified else tr('Not verified'))))
        self.keyboard_model_value.setText(str(keyboard.get('current_model') or (tr('Default / unspecified') if keyboard_verified else tr('Not verified'))))
        self.keyboard_variant_value.setText(str(keyboard.get('current_variant') or (tr('None / unspecified') if keyboard_verified else tr('Not verified'))))
        self._reset_keyboard_plan()
        timezone_verified = timezone.get('verified') is True
        self.timezone_status_value.setText(str(timezone.get('reason') or tr('Rootfs timezone configuration evidence is not available.')))
        self.timezone_path_value.setText(str(timezone.get('config_path') or (tr('Not verified') if not timezone_verified else tr('—'))))
        self.timezone_layer_value.setText(str(timezone.get('config_layer') or tr('Not verified')))
        self.timezone_current_value.setText(str(timezone.get('current_timezone') or (tr('Not explicitly named') if timezone_verified else tr('Not verified'))))
        self._reset_timezone_plan()
        network_verified = network.get('verified') is True
        self.network_status_value.setText(str(network.get('reason') or tr('UNKNOWN — target-rootfs networking capability is not available.')))
        self.network_capability_value.setText(tr(f"Overall: {network.get('capability_status', 'UNKNOWN')} | IPv4 addressing: {network.get('addressing_status', 'UNKNOWN')} | DNS: {network.get('dns_status', 'UNKNOWN')} | NetworkManager profiles: {network.get('networkmanager_profile_status', 'UNKNOWN')} | IPv6: {network.get('ipv6_status', 'BLOCKED')}"))
        self.network_backend_value.setText(str(network.get('backend') or (tr('Not verified') if not network_verified else tr('—'))))
        self.network_backend_path_value.setText(str(network.get('backend_config_path') or (tr('Not verified') if not network_verified else tr('—'))))
        self.network_backend_layer_value.setText(str(network.get('backend_config_layer') or tr('Not verified')))
        self.network_managed_path_value.setText(str(network.get('managed_config_path') or (tr('Not verified') if not network_verified else tr('—'))))
        self.network_resolver_path_value.setText(str(network.get('resolver_path') or (tr('Not verified / profile-specific DNS only') if network_verified else tr('Not verified'))))
        self.network_resolver_layer_value.setText(str(network.get('resolver_layer') or (tr('Not present') if network_verified else tr('Not verified'))))
        profiles = [str(x) for x in network.get('networkmanager_profile_names') or [] if str(x).strip()]
        self.network_profiles_value.setText(', '.join(profiles) if profiles else tr('None detected from metadata') if network_verified and network.get('backend') == 'NetworkManager' else tr('Not applicable / not verified'))
        self._reset_network_dns_plan()
        services_verified = services.get('verified') is True
        self.services_status_value.setText(str(services.get('reason') or tr('Rootfs services/systemd evidence is not available.')))
        self.services_init_value.setText(str(services.get('init_system') or (tr('Not verified') if not services_verified else tr('—'))))
        self.services_vendor_path_value.setText(str(services.get('vendor_unit_path') or (tr('Not verified') if not services_verified else tr('—'))))
        self.services_vendor_layer_value.setText(str(services.get('vendor_unit_layer') or tr('Not verified')))
        self.services_local_path_value.setText(str(services.get('local_unit_path') or (tr('Not present / not required') if services_verified else tr('Not verified'))))
        self._reset_services_plan()
        timers_verified = timers.get('verified') is True
        self.timers_status_value.setText(str(timers.get('reason') or tr('Rootfs timers/systemd evidence is not available.')))
        self.timers_init_value.setText(str(timers.get('init_system') or (tr('Not verified') if not timers_verified else tr('—'))))
        self.timers_vendor_path_value.setText(str(timers.get('vendor_unit_path') or (tr('Not verified') if not timers_verified else tr('—'))))
        self.timers_vendor_layer_value.setText(str(timers.get('vendor_unit_layer') or tr('Not verified')))
        self._reset_timers_plan()
        targets_verified = targets.get('verified') is True
        self.targets_status_value.setText(str(targets.get('reason') or tr('Rootfs targets/systemd evidence is not available.')))
        self.targets_init_value.setText(str(targets.get('init_system') or (tr('Not verified') if not targets_verified else tr('—'))))
        self.targets_vendor_path_value.setText(str(targets.get('vendor_unit_path') or (tr('Not verified') if not targets_verified else tr('—'))))
        self.targets_vendor_layer_value.setText(str(targets.get('vendor_unit_layer') or tr('Not verified')))
        self._reset_targets_plan()
        firewall_verified = firewall.get('verified') is True
        self.firewall_status_value.setText(str(firewall.get('reason') or tr('Rootfs firewall evidence is not available.')))
        self.firewall_backend_value.setText(str(firewall.get('backend') or (tr('Not verified') if not firewall_verified else tr('—'))))
        self.firewall_path_value.setText(str(firewall.get('backend_path') or (tr('Not verified') if not firewall_verified else tr('—'))))
        self.firewall_layer_value.setText(str(firewall.get('backend_layer') or tr('Not verified')))
        self._reset_firewall_plan()
        apparmor_verified = apparmor.get('verified') is True
        self.apparmor_status_value.setText(str(apparmor.get('reason') or tr('Rootfs AppArmor evidence is not available.')))
        self.apparmor_backend_value.setText(str(apparmor.get('backend') or (tr('Not verified') if not apparmor_verified else tr('—'))))
        self.apparmor_path_value.setText(str(apparmor.get('evidence_path') or (tr('Not verified') if not apparmor_verified else tr('—'))))
        self.apparmor_layer_value.setText(str(apparmor.get('evidence_layer') or tr('Not verified')))
        self._reset_apparmor_plan()
        selinux_capability = str(selinux.get('capability_status') or 'UNKNOWN')
        self.selinux_status_value.setText(str(selinux.get('reason') or tr('UNKNOWN — SELinux capability is not verified.')))
        self.selinux_capability_value.setText(tr(selinux_capability))
        self.selinux_mode_value.setText(str(selinux.get('configured_mode') or tr('unknown')))
        self.selinux_policy_value.setText(str(selinux.get('policy_type') or (tr('Present / preserved') if selinux.get('policy_tree_present') else tr('Not verified'))))
        cfg = str(selinux.get('config_path') or '/etc/selinux/config')
        layer = str(selinux.get('config_layer') or 'not present / not verified')
        self.selinux_config_value.setText(tr(f'{cfg} — {layer}'))
        installed_packages = [str(x) for x in selinux.get('installed_selinux_packages') or []]
        required_packages = [str(x) for x in selinux.get('required_packages') or []]
        package_bits = []
        if installed_packages:
            package_bits.append('installed: ' + ', '.join(installed_packages))
        if required_packages:
            package_bits.append('requires: ' + ', '.join(required_packages))
        if selinux.get('package_manager'):
            package_bits.append('manager: ' + str(selinux.get('package_manager')))
        self.selinux_packages_value.setText('; '.join(package_bits) if package_bits else tr('No verified SELinux package requirement'))
        kernel_bits = [f"kernel capability: {selinux.get('kernel_support_status', 'UNKNOWN')}"]
        if selinux.get('initramfs_mechanism'):
            kernel_bits.append('initramfs: ' + str(selinux.get('initramfs_mechanism')))
        if selinux.get('part3_dependency_required'):
            kernel_bits.append('Part 3 dependency required')
        self.selinux_kernel_value.setText('; '.join(kernel_bits))
        requirement_bits = []
        if selinux.get('relabel_required_on_enable'):
            requirement_bits.append('filesystem relabel required when enabling')
        if selinux.get('reboot_required'):
            requirement_bits.append('reboot required')
        if selinux_capability in {'UNKNOWN', 'BLOCKED', 'UNSUPPORTED'}:
            requirement_bits.append('staging blocked')
        self.selinux_requirements_value.setText('; '.join(requirement_bits) if requirement_bits else tr('No additional verified activation requirement'))
        self._reset_selinux_plan()
        sysctl_verified = sysctl.get('verified') is True
        self.sysctl_status_value.setText(str(sysctl.get('reason') or tr('Rootfs sysctl evidence is not available.')))
        self.sysctl_backend_value.setText(str(sysctl.get('backend') or (tr('Not verified') if not sysctl_verified else tr('—'))))
        self.sysctl_path_value.setText(str(sysctl.get('evidence_path') or (tr('Not verified') if not sysctl_verified else tr('—'))))
        self.sysctl_layer_value.setText(str(sysctl.get('evidence_layer') or tr('Not verified')))
        self._reset_sysctl_plan()
        security_capability = str(security_defaults.get('capability_status') or 'UNKNOWN')
        security_verified = security_defaults.get('verified') is True
        self.security_defaults_status_value.setText(str(security_defaults.get('reason') or tr('UNKNOWN — login security defaults are not verified.')))
        self.security_defaults_capability_value.setText(tr(security_capability))
        self.security_defaults_backend_value.setText(str(security_defaults.get('backend') or (tr('Not verified') if not security_verified else tr('—'))))
        self.security_defaults_path_value.setText(str(security_defaults.get('config_path') or tr('/etc/login.defs')))
        self.security_defaults_layer_value.setText(str(security_defaults.get('config_layer') or tr('Not verified')))
        self.security_defaults_umask_value.setText(str(security_defaults.get('current_umask') or (tr('Not explicitly configured') if security_verified else tr('Not verified'))))
        self.security_defaults_usergroups_value.setText(str(security_defaults.get('usergroups_enab') or (tr('Not explicitly configured') if security_verified else tr('Not verified'))))
        self._reset_security_defaults_plan()
        overlay_capability = str(config_overlay.get('capability_status') or 'UNKNOWN')
        overlay_verified = config_overlay.get('verified') is True
        self.config_overlay_status_value.setText(str(config_overlay.get('reason') or tr('UNKNOWN — system configuration overlay mechanism is not verified.')))
        self.config_overlay_capability_value.setText(tr(overlay_capability))
        self.config_overlay_backend_value.setText(str(config_overlay.get('backend') or tr('profile.d')))
        self.config_overlay_profile_value.setText(str(config_overlay.get('profile_path') or tr('/etc/profile')))
        self.config_overlay_profile_layer_value.setText(str(config_overlay.get('profile_layer') or tr('Not verified')))
        self.config_overlay_directory_value.setText(str(config_overlay.get('target_directory') or tr('/etc/profile.d')))
        self.config_overlay_directory_layer_value.setText(str(config_overlay.get('target_directory_layer') or tr('Not verified')))
        existing_names = [str(x) for x in config_overlay.get('existing_entry_names') or []]
        self.config_overlay_existing_value.setText(', '.join(existing_names) if existing_names else tr('None detected') if overlay_verified else tr('Not verified'))
        self._reset_config_overlay_plan()
        kiosk_capability = str(kiosk_user.get('capability_status') or 'UNKNOWN')
        kiosk_verified = kiosk_user.get('verified') is True
        self.kiosk_user_status_value.setText(str(kiosk_user.get('reason') or tr('UNKNOWN — dedicated kiosk-account capability is not verified.')))
        self.kiosk_user_capability_value.setText(tr(kiosk_capability))
        kiosk_layers = []
        for key in ('passwd_layer', 'group_layer'):
            value = str(kiosk_user.get(key) or '').strip()
            if value and value not in kiosk_layers:
                kiosk_layers.append(value)
        self.kiosk_user_layers_value.setText('; '.join(kiosk_layers) if kiosk_layers else tr('Not verified'))
        kiosk_existing = [str(x) for x in kiosk_user.get('existing_regular_users') or []]
        self.kiosk_user_existing_value.setText(', '.join(kiosk_existing) if kiosk_existing else tr('None detected') if kiosk_verified else tr('Not verified'))
        kiosk_admin = [str(x) for x in kiosk_user.get('admin_groups') or []]
        self.kiosk_user_admin_groups_value.setText(', '.join(kiosk_admin) if kiosk_admin else tr('None detected') if kiosk_verified else tr('Not verified'))
        self._reset_kiosk_user_plan()
        restricted_login_capability = str(restricted_login.get('capability_status') or 'UNKNOWN')
        restricted_login_verified = restricted_login.get('verified') is True
        self.restricted_login_status_value.setText(str(restricted_login.get('reason') or tr('UNKNOWN — restricted-login capability is not verified.')))
        self.restricted_login_capability_value.setText(tr(restricted_login_capability))
        self.restricted_login_backend_value.setText(str(restricted_login.get('backend') or (tr('Not verified') if not restricted_login_verified else tr('—'))))
        self.restricted_login_tool_value.setText(str(restricted_login.get('management_tool_path') or tr('Not verified')))
        self.restricted_login_tool_layer_value.setText(str(restricted_login.get('management_tool_layer') or tr('Not verified')))
        restricted_users = [str(x) for x in restricted_login.get('existing_regular_users') or []]
        self.restricted_login_users_value.setText(', '.join(restricted_users) if restricted_users else tr('None detected') if restricted_login_verified else tr('Not verified'))
        restricted_admin = [str(x) for x in restricted_login.get('admin_users') or []]
        self.restricted_login_admin_users_value.setText(', '.join(restricted_admin) if restricted_admin else tr('None detected') if restricted_login_verified else tr('Not verified'))
        self._reset_restricted_login_plan()
        restricted_session_capability = str(restricted_session.get('capability_status') or 'UNKNOWN')
        restricted_session_verified = restricted_session.get('verified') is True
        self.restricted_session_status_value.setText(str(restricted_session.get('reason') or tr('UNKNOWN — restricted-session capability is not verified.')))
        self.restricted_session_capability_value.setText(tr(restricted_session_capability))
        self.restricted_session_backend_value.setText(str(restricted_session.get('backend') or (tr('Not verified') if not restricted_session_verified else tr('—'))))
        self.restricted_session_dm_value.setText(str(restricted_session.get('display_manager') or tr('Not verified')))
        verified_sessions = [x for x in restricted_session.get('verified_sessions') or [] if isinstance(x, dict)]
        session_labels = [f"{str(x.get('name') or '')} ({str(x.get('kind') or '')})" for x in verified_sessions if str(x.get('name') or '')]
        self.restricted_session_sessions_value.setText(', '.join(session_labels) if session_labels else tr('None detected') if restricted_session_verified else tr('Not verified'))
        target_path = str(restricted_session.get('managed_target_path') or '/etc/sddm.conf.d/99-chromapress-kiosk-session.conf')
        target_state = 'collision — BLOCKED' if restricted_session.get('managed_target_present') is True else 'absent / collision-safe' if restricted_session_verified else 'not verified'
        self.restricted_session_target_value.setText(tr(f'{target_path} — {target_state}'))
        self.restricted_session_choice.blockSignals(True)
        self.restricted_session_choice.clear()
        if verified_sessions:
            for row in verified_sessions:
                name = str(row.get('name') or '')
                kind = str(row.get('kind') or '')
                if name:
                    self.restricted_session_choice.addItem(tr(f'{name} ({kind})'), name)
        else:
            self.restricted_session_choice.addItem(tr('No verified target session'), '')
        self.restricted_session_choice.blockSignals(False)
        self._reset_restricted_session_plan()
        service_lockdown_capability = str(service_lockdown.get('capability_status') or 'UNKNOWN')
        service_lockdown_verified = service_lockdown.get('verified') is True
        self.service_lockdown_status_value.setText(str(service_lockdown.get('reason') or tr('UNKNOWN — service-lockdown capability is not verified.')))
        self.service_lockdown_capability_value.setText(tr(service_lockdown_capability))
        self.service_lockdown_backend_value.setText(str(service_lockdown.get('backend') or (tr('Not verified') if not service_lockdown_verified else tr('—'))))
        available_lockdown = [x for x in service_lockdown.get('available_lockdown_units') or [] if isinstance(x, dict)]
        available_names = [str(x.get('name') or '') for x in available_lockdown if str(x.get('name') or '')]
        protected_names = [str(x) for x in service_lockdown.get('protected_service_units') or [] if str(x)]
        self.service_lockdown_units_value.setText(', '.join(available_names[:20]) + (tr(f' … +{len(available_names) - 20} more') if len(available_names) > 20 else tr('')) if available_names else tr('None detected') if service_lockdown_verified else tr('Not verified'))
        self.service_lockdown_protected_value.setText(', '.join(protected_names[:20]) + (tr(f' … +{len(protected_names) - 20} more') if len(protected_names) > 20 else tr('')) if protected_names else tr('None in verified set'))
        self.service_lockdown_choice.blockSignals(True)
        self.service_lockdown_choice.clear()
        if available_lockdown:
            for row in available_lockdown:
                name = str(row.get('name') or '')
                if name:
                    self.service_lockdown_choice.addItem(name, name)
        else:
            self.service_lockdown_choice.addItem(tr('No verified non-protected service'), '')
        self.service_lockdown_choice.blockSignals(False)
        self._reset_service_lockdown_plan()
        network_restriction_capability = str(network_restriction.get('capability_status') or 'UNKNOWN')
        network_restriction_verified = network_restriction.get('verified') is True
        self.network_restriction_status_value.setText(str(network_restriction.get('reason') or tr('UNKNOWN — network-restriction capability is not verified.')))
        self.network_restriction_capability_value.setText(tr(network_restriction_capability))
        self.network_restriction_backend_value.setText(str(network_restriction.get('backend') or (tr('Not verified') if not network_restriction_verified else tr('—'))))
        managed_path = str(network_restriction.get('managed_rule_path') or '/etc/polkit-1/rules.d/49-chromapress-kiosk-network.rules')
        managed_state = 'collision — BLOCKED' if network_restriction.get('managed_target_present') is True else 'absent / collision-safe' if network_restriction_verified else 'not verified'
        self.network_restriction_target_value.setText(tr(f'{managed_path} — {managed_state}'))
        self._reset_network_restriction_plan()
        firewall_rules_capability = str(firewall_rules.get('capability_status') or 'UNKNOWN')
        self.firewall_rules_status_value.setText(str(firewall_rules.get('reason') or tr('UNKNOWN — firewall-rule capability is not verified.')))
        self.firewall_rules_capability_value.setText(tr(firewall_rules_capability))
        self.firewall_rules_backend_value.setText(str(firewall_rules.get('firewall_backend') or tr('Not verified')))
        self.firewall_rules_adapter_value.setText(str(firewall_rules.get('rule_adapter') or tr('Not verified')))
        command = str(firewall_rules.get('rule_command_path') or 'Not verified')
        command_layer = str(firewall_rules.get('rule_command_layer') or '')
        self.firewall_rules_command_value.setText(command + (tr(' — ') + command_layer if command_layer else tr('')))
        self._reset_firewall_rules_plan()
        persistence_policy_capability = str(persistence_policy.get('capability_status') or 'UNKNOWN')
        self.persistence_policy_status_value.setText(str(persistence_policy.get('reason') or tr('UNKNOWN — persistence-policy capability is not verified.')))
        self.persistence_policy_capability_value.setText(tr(persistence_policy_capability))
        rootfs_count = len(list(persistence_policy.get('rootfs_layers') or []))
        boot_count = len(list(persistence_policy.get('boot_config_files') or []))
        mechanism = str(persistence_policy.get('initramfs_mechanism') or 'Not verified')
        self.persistence_policy_part3_value.setText(tr(f'rootfs={rootfs_count} • boot-config={boot_count} • initramfs={mechanism} • Part 3 dependency required'))
        self._reset_persistence_policy_plan()
        admin_recovery_capability = str(admin_recovery.get('capability_status') or 'UNKNOWN')
        self.admin_recovery_status_value.setText(str(admin_recovery.get('reason') or tr('UNKNOWN — administrator/recovery policy capability is not verified.')))
        self.admin_recovery_capability_value.setText(tr(admin_recovery_capability))
        admin_groups = [str(x) for x in admin_recovery.get('admin_groups') or []]
        admin_users = [str(x) for x in admin_recovery.get('existing_admin_users') or []]
        self.admin_recovery_admin_groups_value.setText(', '.join(admin_groups) if admin_groups else tr('Not verified'))
        self.admin_recovery_admin_users_value.setText(', '.join(admin_users) if admin_users else tr('None detected'))
        explicit_autologin = str(admin_recovery.get('autologin_user') or '')
        self.admin_recovery_autologin_value.setText(explicit_autologin or tr('None explicitly configured'))
        self.admin_recovery_admin_group.clear()
        for group in admin_groups:
            self.admin_recovery_admin_group.addItem(group, group)
        self._reset_admin_recovery_policy_plan()
        fido2_capability = str(fido2_policy.get('capability_status') or 'UNKNOWN')
        self.fido2_status_value.setText(str(fido2_policy.get('reason') or tr('UNKNOWN — FIDO2 policy capability is not verified.')))
        self.fido2_capability_value.setText(tr(fido2_capability))
        pam_fido2 = [str(x) for x in fido2_policy.get('pam_fido2_packages') or []]
        libfido2 = [str(x) for x in fido2_policy.get('libfido2_packages') or []]
        self.fido2_pam_packages_value.setText(', '.join(pam_fido2) if pam_fido2 else tr('Not verified'))
        self.fido2_lib_packages_value.setText(', '.join(libfido2) if libfido2 else tr('Not verified'))
        self._reset_fido2_policy_plan()
        webauthn_capability = str(webauthn_policy.get('capability_status') or 'UNKNOWN')
        self.webauthn_status_value.setText(str(webauthn_policy.get('reason') or tr('UNKNOWN — WebAuthn policy capability is not verified.')))
        self.webauthn_capability_value.setText(tr(webauthn_capability))
        browser_packages = [str(x) for x in webauthn_policy.get('browser_packages') or []]
        self.webauthn_browser_packages_value.setText(', '.join(browser_packages) if browser_packages else tr('Not verified'))
        self.webauthn_browser.clear()
        for package in browser_packages:
            self.webauthn_browser.addItem(package, package)
        self._reset_webauthn_policy_plan()
        security_key_capability = str(security_key_policy.get('capability_status') or 'UNKNOWN')
        self.security_key_status_value.setText(str(security_key_policy.get('reason') or tr('UNKNOWN — security-key policy capability is not verified.')))
        self.security_key_capability_value.setText(tr(security_key_capability))
        security_tools = [str(x) for x in security_key_policy.get('security_key_tool_packages') or []]
        security_libs = [str(x) for x in security_key_policy.get('libfido2_packages') or []]
        self.security_key_packages_value.setText(', '.join(security_tools + security_libs) if security_tools or security_libs else tr('Not verified'))
        self._reset_security_key_policy_plan()
        yubikey_capability = str(yubikey_policy.get('capability_status') or 'UNKNOWN')
        self.yubikey_status_value.setText(str(yubikey_policy.get('reason') or tr('UNKNOWN — YubiKey-class policy capability is not verified.')))
        self.yubikey_capability_value.setText(tr(yubikey_capability))
        yubi_packages = [str(x) for x in yubikey_policy.get('yubikey_packages') or []]
        self.yubikey_packages_value.setText(', '.join(yubi_packages) if yubi_packages else tr('Not verified'))
        self._reset_yubikey_policy_plan()
        platform_capability = str(platform_auth_policy.get('capability_status') or 'UNKNOWN')
        self.platform_auth_status_value.setText(str(platform_auth_policy.get('reason') or tr('UNKNOWN — platform-authenticator capability is not verified.')))
        self.platform_auth_capability_value.setText(tr(platform_capability))
        runtime_ok = platform_auth_policy.get('platform_authenticator_runtime_verified') is True
        hardware_ok = platform_auth_policy.get('platform_authenticator_hardware_verified') is True
        self.platform_auth_runtime_value.setText(tr(f'runtime={runtime_ok} • hardware={hardware_ok}'))
        self._reset_platform_authenticator_policy_plan()
        tpm_capability = str(tpm_policy.get('capability_status') or 'UNKNOWN')
        self.tpm_status_value.setText(str(tpm_policy.get('reason') or tr('UNKNOWN — TPM-backed key-protection capability is not verified.')))
        self.tpm_capability_value.setText(tr(tpm_capability))
        tpm_packages = [str(x) for x in tpm_policy.get('tpm_tool_packages') or []] + [str(x) for x in tpm_policy.get('tss_packages') or []]
        self.tpm_packages_value.setText(', '.join(tpm_packages) if tpm_packages else tr('Not verified'))
        self._reset_tpm_key_protection_plan()
        self.evidence_tree.clear()
        grouped: dict[str, list[dict]] = defaultdict(list)
        for item in evidence:
            grouped[str(item.get('area') or 'Other')].append(item)
        for area, items in grouped.items():
            root = QTreeWidgetItem([area, tr(f'{len(items)} manifest package(s)')])
            self.evidence_tree.addTopLevelItem(root)
            for item in items:
                package = str(item.get('package') or '')
                version = str(item.get('version') or '')
                root.addChild(QTreeWidgetItem([package, version or 'manifest-backed']))
            root.setExpanded(True)
        if not evidence:
            self.evidence_tree.addTopLevelItem(QTreeWidgetItem([tr('No matching system package evidence'), tr('Do not infer configuration from distribution name; rootfs verification is still required')]))
        selinux_schema_ok = selinux.get('gate_version') == 'alpha52' and selinux.get('analysis_scope') == 'target_iso_rootfs' and (selinux_capability in {'SUPPORTED', 'SUPPORTED_WITH_REQUIREMENTS', 'UNSUPPORTED', 'BLOCKED', 'UNKNOWN'}) and (selinux.get('host_selinux_accessed') is False) and (selinux.get('source_read_only') is True)
        security_schema_ok = security_defaults.get('gate_version') == 'alpha53' and security_defaults.get('analysis_scope') == 'target_iso_rootfs' and (security_capability in {'SUPPORTED', 'SUPPORTED_WITH_REQUIREMENTS', 'UNSUPPORTED', 'BLOCKED', 'UNKNOWN'}) and (security_defaults.get('host_security_state_accessed') is False) and (security_defaults.get('source_read_only') is True)
        kiosk_schema_ok = kiosk_user.get('gate_version') == 'alpha55' and kiosk_user.get('analysis_scope') == 'target_iso_rootfs' and (kiosk_capability in {'SUPPORTED', 'SUPPORTED_WITH_REQUIREMENTS', 'UNSUPPORTED', 'BLOCKED', 'UNKNOWN'}) and (kiosk_user.get('shadow_read') is False) and (kiosk_user.get('credential_secret_read') is False) and (kiosk_user.get('host_accounts_touched') is False) and (kiosk_user.get('source_read_only') is True)
        restricted_login_schema_ok = restricted_login.get('gate_version') == 'alpha56' and restricted_login.get('analysis_scope') == 'target_iso_rootfs' and (restricted_login_capability in {'SUPPORTED', 'SUPPORTED_WITH_REQUIREMENTS', 'UNSUPPORTED', 'BLOCKED', 'UNKNOWN'}) and (restricted_login.get('shadow_read') is False) and (restricted_login.get('credential_secret_read') is False) and (restricted_login.get('host_login_state_accessed') is False) and (restricted_login.get('pam_contents_read') is False) and (restricted_login.get('ssh_config_read') is False) and (restricted_login.get('source_read_only') is True)
        restricted_session_schema_ok = restricted_session.get('gate_version') == 'alpha57' and restricted_session.get('analysis_scope') == 'target_iso_rootfs' and (restricted_session_capability in {'SUPPORTED', 'SUPPORTED_WITH_REQUIREMENTS', 'UNSUPPORTED', 'BLOCKED', 'UNKNOWN'}) and (restricted_session.get('session_file_contents_read') is False) and (restricted_session.get('display_manager_config_contents_read') is False) and (restricted_session.get('credential_secret_read') is False) and (restricted_session.get('host_session_state_accessed') is False) and (restricted_session.get('pam_contents_read') is False) and (restricted_session.get('ssh_config_read') is False) and (restricted_session.get('source_read_only') is True)
        service_lockdown_schema_ok = service_lockdown.get('gate_version') == 'alpha58' and service_lockdown.get('analysis_scope') == 'target_iso_rootfs' and (service_lockdown_capability in {'SUPPORTED', 'SUPPORTED_WITH_REQUIREMENTS', 'UNSUPPORTED', 'BLOCKED', 'UNKNOWN'}) and (service_lockdown.get('unit_contents_read') is False) and (service_lockdown.get('enablement_link_targets_read') is False) and (service_lockdown.get('environment_files_read') is False) and (service_lockdown.get('service_secrets_read') is False) and (service_lockdown.get('host_service_state_accessed') is False) and (service_lockdown.get('source_read_only') is True)
        network_restriction_schema_ok = network_restriction.get('gate_version') == 'alpha59' and network_restriction.get('analysis_scope') == 'target_iso_rootfs' and (network_restriction_capability in {'SUPPORTED', 'SUPPORTED_WITH_REQUIREMENTS', 'UNSUPPORTED', 'BLOCKED', 'UNKNOWN'}) and (network_restriction.get('traffic_blocking_claimed') is False) and (network_restriction.get('firewall_rules_read') is False) and (network_restriction.get('firewall_rules_staged') is False) and (network_restriction.get('networkmanager_profile_contents_read') is False) and (network_restriction.get('polkit_policy_contents_read') is False) and (network_restriction.get('existing_rule_contents_read') is False) and (network_restriction.get('credential_secret_read') is False) and (network_restriction.get('host_network_accessed') is False) and (network_restriction.get('source_read_only') is True)
        firewall_rules_schema_ok = firewall_rules.get('gate_version') == 'alpha60' and firewall_rules.get('analysis_scope') == 'target_iso_rootfs' and (firewall_rules_capability in {'SUPPORTED', 'SUPPORTED_WITH_REQUIREMENTS', 'UNSUPPORTED', 'BLOCKED', 'UNKNOWN'}) and (firewall_rules.get('existing_rule_contents_read') is False) and (firewall_rules.get('ports_services_policy_read') is False) and (firewall_rules.get('application_profiles_read') is False) and (firewall_rules.get('firewall_secrets_read') is False) and (firewall_rules.get('host_firewall_accessed') is False) and (firewall_rules.get('source_read_only') is True)
        persistence_policy_schema_ok = persistence_policy.get('gate_version') == 'alpha61' and persistence_policy.get('analysis_scope') == 'target_iso_metadata' and (persistence_policy_capability in {'SUPPORTED', 'SUPPORTED_WITH_REQUIREMENTS', 'UNSUPPORTED', 'BLOCKED', 'UNKNOWN'}) and (persistence_policy.get('existing_persistence_policy_read') is False) and (persistence_policy.get('persistent_data_contents_read') is False) and (persistence_policy.get('mount_configuration_contents_read') is False) and (persistence_policy.get('host_storage_accessed') is False) and (persistence_policy.get('host_mount_state_accessed') is False) and (persistence_policy.get('source_read_only') is True)
        admin_recovery_schema_ok = admin_recovery.get('gate_version') == 'alpha62' and admin_recovery.get('analysis_scope') == 'target_iso_rootfs' and (admin_recovery_capability in {'SUPPORTED', 'SUPPORTED_WITH_REQUIREMENTS', 'UNSUPPORTED', 'BLOCKED', 'UNKNOWN'}) and (admin_recovery.get('shadow_read') is False) and (admin_recovery.get('credential_secret_read') is False) and (admin_recovery.get('recovery_secret_read') is False) and (admin_recovery.get('pam_contents_read') is False) and (admin_recovery.get('ssh_config_read') is False) and (admin_recovery.get('rescue_boot_config_read') is False) and (admin_recovery.get('root_account_policy_read') is False) and (admin_recovery.get('host_accounts_touched') is False) and (admin_recovery.get('host_login_state_accessed') is False) and (admin_recovery.get('source_read_only') is True)
        if not sha:
            self.status.setText(tr('Analyze a supported source ISO first.'))
        elif verified and machine_verified and autologin_verified and locale_verified and keyboard_verified and timezone_verified and network_verified and services_verified and timers_verified and targets_verified and firewall_verified and apparmor_verified and sysctl_verified and selinux_schema_ok and security_schema_ok and kiosk_schema_ok and restricted_login_schema_ok and restricted_session_schema_ok and service_lockdown_schema_ok and network_restriction_schema_ok and firewall_rules_schema_ok and persistence_policy_schema_ok and admin_recovery_schema_ok:
            self.status.setText(tr(f'ROOTFS PART 4 PASS — previous Part 4 gates remain verified and Alpha 62 administrator/recovery policy capability completed fail-closed. Administrator/recovery capability: {admin_recovery_capability}.'))
        elif verified and machine_verified and autologin_verified and locale_verified and keyboard_verified and timezone_verified and network_verified and services_verified and timers_verified and targets_verified and firewall_verified and apparmor_verified and sysctl_verified and selinux_schema_ok and security_schema_ok and kiosk_schema_ok and restricted_login_schema_ok and restricted_session_schema_ok and service_lockdown_schema_ok and network_restriction_schema_ok and firewall_rules_schema_ok and persistence_policy_schema_ok:
            self.status.setText(tr(f'ROOTFS PART 4 PASS — previous Part 4 gates remain verified and Alpha 61 persistence-policy capability completed fail-closed. Persistence-policy capability: {persistence_policy_capability}.'))
        elif verified and machine_verified and autologin_verified and locale_verified and keyboard_verified and timezone_verified and network_verified and services_verified and timers_verified and targets_verified and firewall_verified and apparmor_verified and sysctl_verified and selinux_schema_ok and security_schema_ok and kiosk_schema_ok and restricted_login_schema_ok and restricted_session_schema_ok and service_lockdown_schema_ok and network_restriction_schema_ok and firewall_rules_schema_ok:
            self.status.setText(tr(f'ROOTFS PART 4 PASS — previous Part 4 gates remain verified and Alpha 60 firewall-rules capability completed fail-closed. Firewall-rules capability: {firewall_rules_capability}.'))
        elif verified and machine_verified and autologin_verified and locale_verified and keyboard_verified and timezone_verified and network_verified and services_verified and timers_verified and targets_verified and firewall_verified and apparmor_verified and sysctl_verified and selinux_schema_ok and security_schema_ok and kiosk_schema_ok and restricted_login_schema_ok and restricted_session_schema_ok and service_lockdown_schema_ok and network_restriction_schema_ok:
            self.status.setText(tr(f'ROOTFS PART 4 PASS — previous Part 4 gates remain verified and Alpha 59 network-control restriction capability completed fail-closed. Network-restriction capability: {network_restriction_capability}.'))
        elif verified and machine_verified and autologin_verified and locale_verified and keyboard_verified and timezone_verified and network_verified and services_verified and timers_verified and targets_verified and firewall_verified and apparmor_verified and sysctl_verified and selinux_schema_ok and security_schema_ok and kiosk_schema_ok and restricted_login_schema_ok and restricted_session_schema_ok and service_lockdown_schema_ok:
            self.status.setText(tr(f'ROOTFS PART 4 PASS — previous Part 4 gates remain verified and Alpha 58 service-lockdown capability completed fail-closed. Service-lockdown capability: {service_lockdown_capability}.'))
        elif verified and machine_verified and autologin_verified and locale_verified and keyboard_verified and timezone_verified and network_verified and services_verified and timers_verified and targets_verified and firewall_verified and apparmor_verified and sysctl_verified and selinux_schema_ok and security_schema_ok and kiosk_schema_ok and restricted_login_schema_ok and restricted_session_schema_ok:
            self.status.setText(tr(f'ROOTFS PART 4 PASS — previous Part 4 gates remain verified and Alpha 57 restricted-session capability completed fail-closed. Restricted-session capability: {restricted_session_capability}.'))
        elif verified and machine_verified and autologin_verified and locale_verified and keyboard_verified and timezone_verified and network_verified and services_verified and timers_verified and targets_verified and firewall_verified and apparmor_verified and sysctl_verified and selinux_schema_ok and security_schema_ok and kiosk_schema_ok and restricted_login_schema_ok:
            self.status.setText(tr(f'ROOTFS PART 4 PASS — previous Part 4 gates remain verified and Alpha 56 restricted-login capability completed fail-closed. Restricted-login capability: {restricted_login_capability}.'))
        elif verified and machine_verified and autologin_verified and locale_verified and keyboard_verified and timezone_verified and network_verified and services_verified and timers_verified and targets_verified and firewall_verified and apparmor_verified and sysctl_verified and selinux_schema_ok and security_schema_ok and kiosk_schema_ok:
            self.status.setText(tr(f'ROOTFS PART 4 PASS — previous Part 4 gates remain verified and Alpha 55 dedicated non-admin kiosk-user capability completed fail-closed. Kiosk-user capability: {kiosk_capability}.'))
        elif verified and machine_verified and autologin_verified and locale_verified and keyboard_verified and timezone_verified and network_verified and services_verified and timers_verified and targets_verified and firewall_verified and apparmor_verified and sysctl_verified and selinux_schema_ok and security_schema_ok:
            self.status.setText(tr(f'ROOTFS PART 4 PASS — previous Part 4 gates remain verified and Alpha 53 login security-default capability completed fail-closed. Security-default capability: {security_capability}.'))
        elif verified and machine_verified and autologin_verified and locale_verified and keyboard_verified and timezone_verified and network_verified and services_verified and timers_verified and targets_verified and firewall_verified and apparmor_verified and sysctl_verified and selinux_schema_ok:
            self.status.setText(tr(f'ROOTFS PART 4 PASS — previous Part 4 gates remain verified and Alpha 52 SELinux capability detection completed fail-closed. SELinux capability: {selinux_capability}. UNKNOWN/BLOCKED/UNSUPPORTED states expose no configuration action.'))
        elif verified and machine_verified and autologin_verified and locale_verified and keyboard_verified and timezone_verified and network_verified and services_verified and timers_verified and targets_verified and firewall_verified and apparmor_verified:
            self.status.setText(tr('ROOTFS PART 4 PASS — account, hostname/machine-identity, display-manager/autologin, locale/language, keyboard-layout, timezone, networking/DNS, services/systemd, timers/systemd, targets/startup, firewall and AppArmor evidence are verified read-only; sysctl remains gated.'))
        elif verified and machine_verified and autologin_verified and locale_verified and keyboard_verified and timezone_verified and network_verified and services_verified and timers_verified and targets_verified and firewall_verified:
            self.status.setText(tr('ROOTFS PART 4 PASS — account, hostname/machine-identity, display-manager/autologin, locale/language, keyboard-layout, timezone, networking/DNS, services/systemd, timers/systemd, targets/startup and firewall evidence are verified read-only; AppArmor remains gated.'))
        elif verified and machine_verified and autologin_verified and locale_verified and keyboard_verified and timezone_verified and network_verified and services_verified and timers_verified and targets_verified:
            self.status.setText(tr('ROOTFS PART 4 PASS — account, hostname/machine-identity, display-manager/autologin, locale/language, keyboard-layout, timezone, networking/DNS, services/systemd, timers/systemd and targets/startup evidence are verified read-only; firewall remains gated.'))
        elif verified and machine_verified and autologin_verified and locale_verified and keyboard_verified and timezone_verified and network_verified and services_verified and timers_verified:
            self.status.setText(tr('ROOTFS PART 4 PASS — account, hostname/machine-identity, display-manager/autologin, locale/language, keyboard-layout, timezone, networking/DNS, services/systemd and timers/systemd evidence are verified read-only; targets/startup remains gated.'))
        elif verified and machine_verified and autologin_verified and locale_verified and keyboard_verified and timezone_verified and network_verified and services_verified:
            self.status.setText(tr('ROOTFS PART 4 PASS — account, hostname/machine-identity, display-manager/autologin, locale/language, keyboard-layout, timezone, networking/DNS and services/systemd evidence are verified read-only; timers/systemd remains gated.'))
        elif verified and machine_verified and autologin_verified and locale_verified and keyboard_verified and timezone_verified and network_verified:
            self.status.setText(tr('ROOTFS PART 4 PASS — account, hostname/machine-identity, display-manager/autologin, locale/language, keyboard-layout, timezone and networking/DNS evidence are verified read-only; services/systemd remains gated.'))
        elif verified and machine_verified and autologin_verified and locale_verified and keyboard_verified and timezone_verified:
            self.status.setText(tr('ROOTFS PART 4 PASS — account, hostname/machine-identity, display-manager/autologin, locale/language, keyboard-layout and timezone evidence are verified read-only; networking/DNS remains gated.'))
        elif verified and machine_verified and autologin_verified and locale_verified and keyboard_verified:
            self.status.setText(tr('ROOTFS PART 4 PASS — account, hostname/machine-identity, display-manager/autologin, locale/language and keyboard-layout evidence are verified read-only; timezone remains gated.'))
        elif verified and machine_verified and autologin_verified and locale_verified:
            self.status.setText(tr('ROOTFS PART 4 PASS — account, hostname/machine-identity, display-manager/autologin and locale/language evidence are verified read-only; keyboard layout remains gated.'))
        elif verified and machine_verified and autologin_verified:
            self.status.setText(tr('ROOTFS PART 4 PASS — account, hostname/machine-identity and display-manager/autologin evidence are verified read-only; locale/language remains gated.'))
        elif verified and machine_verified:
            self.status.setText(tr('ROOTFS IDENTITY + MACHINE ID PASS — account and hostname/machine-identity evidence are verified read-only; autologin remains gated.'))
        elif verified:
            self.status.setText(tr('ROOTFS IDENTITY PASS — account database evidence is verified read-only; hostname/machine identity remains gated.'))
        else:
            self.status.setText(tr('READ-ONLY PASS — manifest evidence is shown, but identity/account staging remains fail-closed until rootfs verification succeeds.'))

    def _stage_identity_plan(self) -> None:
        sha = str(self._analysis.get('sha256') or '').strip().casefold()
        identity = dict(self._analysis.get('system_identity_evidence') or {})
        supported = {'SUPPORTED', 'SUPPORTED_WITH_REQUIREMENTS'}
        if not re.fullmatch('[0-9a-f]{64}', sha):
            QMessageBox.information(self, tr('Users/groups plan blocked'), tr('BLOCKED — analyze a source ISO before staging users/groups/password-policy changes.'))
            return
        capability = str(identity.get('capability_status') or 'UNKNOWN')
        if identity.get('verified') is not True or capability not in supported:
            QMessageBox.information(self, tr('Users/groups plan blocked'), tr(f'BLOCKED — target-rootfs users/groups capability is {capability}. Verified /etc/passwd and /etc/group evidence is required; host accounts are never used as a substitute.'))
            self.identity_plan_status.setText(tr(f'Blocked — target-rootfs users/groups capability is {capability}.'))
            return
        operation = str(self.identity_operation.currentData() or 'preserve')
        if operation == 'preserve':
            QMessageBox.information(self, tr('Users/groups plan'), tr('No users/groups/password-policy change is selected. Existing target-image configuration remains preserved.'))
            return
        depth = str(self.identity_depth.currentData() or 'quick')
        existing_users = [str(x) for x in identity.get('regular_users') or [] if str(x).strip()]
        user_records = [dict(x) for x in identity.get('user_records') or [] if isinstance(x, dict)]
        group_records = [dict(x) for x in identity.get('group_records') or [] if isinstance(x, dict)]
        available_groups = [str(x) for x in identity.get('groups') or [] if str(x).strip()]
        existing_uids = {int(x.get('uid')) for x in user_records if isinstance(x.get('uid'), int) and (not isinstance(x.get('uid'), bool))}
        existing_gids = {int(x.get('gid')) for x in group_records if isinstance(x.get('gid'), int) and (not isinstance(x.get('gid'), bool))}
        admin_groups = [str(x) for x in identity.get('admin_groups') or [] if str(x).strip()]
        common = {'config_type': 'system_identity', 'gate_version': 'alpha50', 'source_sha256': sha, 'capability_status': capability, 'users_groups_status': str(identity.get('users_groups_status') or 'UNKNOWN'), 'uid_gid_status': str(identity.get('uid_gid_status') or 'UNKNOWN'), 'group_membership_status': str(identity.get('group_membership_status') or 'UNKNOWN'), 'password_policy_status': str(identity.get('password_policy_status') or 'UNKNOWN'), 'control_depth': depth, 'uid_min': int(identity.get('uid_min') or 1000), 'passwd_layer': str(identity.get('passwd_layer') or ''), 'group_layer': str(identity.get('group_layer') or ''), 'login_defs_layer': str(identity.get('login_defs_layer') or ''), 'rootfs_identity_verified': True, 'analysis_scope': 'target_iso_rootfs', 'host_accounts_touched': False, 'shadow_read': False, 'credential_secret_read': False, 'credential_secret_staged': False, 'secret_read': False, 'secret_staged': False, 'credential_policy': 'deferred_secure_verified_apply', 'source_read_only': True, 'preserve_unrelated': True, 'preserve_autologin': True, 'stage_only': True, 'existing_regular_users': existing_users, 'available_groups': available_groups, 'existing_user_uids': sorted(existing_uids), 'existing_group_gids': sorted(existing_gids)}
        if operation == 'create_group':
            if depth not in {'advanced', 'expert'}:
                QMessageBox.information(self, tr('Users/groups plan blocked'), tr('BLOCKED — group creation is available only in Advanced/Expert control depth.'))
                return
            group_name = self.identity_group_name.text().strip()
            if not re.fullmatch('[a-z_][a-z0-9_-]{0,31}', group_name):
                QMessageBox.warning(self, tr('Users/groups plan blocked'), tr('Group name must be 1–32 characters: lowercase letters/digits plus _ or -, and may not start with a digit.'))
                return
            if group_name in available_groups:
                QMessageBox.information(self, tr('Users/groups plan blocked'), tr('BLOCKED — that group already exists in the selected target rootfs.'))
                return
            gid_text = self.identity_group_gid.text().strip()
            group_gid = None
            if gid_text:
                if not gid_text.isdigit() or not 1 <= int(gid_text) <= 60000:
                    QMessageBox.warning(self, tr('Users/groups plan blocked'), tr('Explicit group GID must be an integer from 1 to 60000.'))
                    return
                group_gid = int(gid_text)
                if group_gid in existing_gids:
                    QMessageBox.information(self, tr('Users/groups plan blocked'), tr('BLOCKED — that GID already exists in the selected target rootfs.'))
                    return
            payload = common | {'operation': 'create_group', 'plan_slot': f'group:{group_name}', 'target_group': group_name, 'group_gid': group_gid, 'password_policy': {'mode': 'preserve'}, 'group_membership_mode': 'preserve'}
            detail = f"Create target-system group '{group_name}'" + (f' with GID {group_gid}' if group_gid is not None else ' with automatic GID') + '; preserve all unrelated users/groups and autologin policy.'
            change = ChangeItem('Users / Groups / Password Policy plan', ChangeKind.CONFIG, detail, payload)
            self.stage_requested.emit(change)
            self.identity_plan_status.setText(tr('Staged — review/Test in Changes.'))
            QMessageBox.information(self, tr('STAGED: Users / Groups / Password Policy plan'), tr('Target-group intent is source-hash locked and staging-only. Host accounts and source-ISO bytes remain untouched; no credential secret is present.'))
            return
        if operation not in {'configure_default_user', 'create_user', 'modify_user'}:
            QMessageBox.information(self, tr('Users/groups plan blocked'), tr('BLOCKED — unsupported account operation.'))
            return
        username = self.identity_username.text().strip()
        display_name = self.identity_display_name.text().strip()
        if not re.fullmatch('[a-z_][a-z0-9_-]{0,31}', username):
            QMessageBox.warning(self, tr('Users/groups plan blocked'), tr('Username must be 1–32 characters: lowercase letters/digits plus _ or -, and may not start with a digit.'))
            return
        if any((ch in display_name for ch in ('\r', '\n', '\x00', ':'))) or len(display_name) > 128:
            QMessageBox.warning(self, tr('Users/groups plan blocked'), tr('Display/full name contains unsupported characters or is too long.'))
            return
        target_exists = username in existing_users
        if operation == 'create_user' and target_exists:
            QMessageBox.information(self, tr('Users/groups plan blocked'), tr('BLOCKED — that user already exists in the selected target rootfs. Choose Modify existing user instead.'))
            return
        if operation == 'modify_user' and (not target_exists):
            QMessageBox.information(self, tr('Users/groups plan blocked'), tr('BLOCKED — that user was not verified in the selected target rootfs. Choose Create user if appropriate.'))
            return
        role = str(self.identity_role.currentData() or 'preserve')
        if role == 'preserve' and (not target_exists):
            QMessageBox.information(self, tr('Users/groups plan blocked'), tr('BLOCKED — a new target user requires an explicit Standard user or Administrator role.'))
            return
        admin_group = str(self.identity_admin_group.currentData() or '') if role == 'administrator' else ''
        if role == 'administrator' and (not admin_group or admin_group not in admin_groups):
            QMessageBox.information(self, tr('Users/groups plan blocked'), tr('BLOCKED — no verified target-rootfs administrative group is selected.'))
            return
        uid = gid = None
        supplementary_groups: list[str] = []
        group_membership_mode = 'preserve' if target_exists else 'set'
        password_policy: dict[str, object] = {'mode': 'preserve'}
        if depth in {'advanced', 'expert'}:
            uid_text = self.identity_uid.text().strip()
            gid_text = self.identity_gid.text().strip()
            if uid_text:
                if not uid_text.isdigit() or not int(identity.get('uid_min') or 1000) <= int(uid_text) <= 60000:
                    QMessageBox.warning(self, tr('Users/groups plan blocked'), tr('Explicit UID must be a regular-user UID between target UID_MIN and 60000.'))
                    return
                uid = int(uid_text)
                if operation == 'create_user' and uid in existing_uids:
                    QMessageBox.information(self, tr('Users/groups plan blocked'), tr('BLOCKED — that UID already exists in the selected target rootfs.'))
                    return
            if gid_text:
                if not gid_text.isdigit() or not 1 <= int(gid_text) <= 60000:
                    QMessageBox.warning(self, tr('Users/groups plan blocked'), tr('Explicit primary GID must be an integer from 1 to 60000.'))
                    return
                gid = int(gid_text)
                if gid not in existing_gids:
                    QMessageBox.information(self, tr('Users/groups plan blocked'), tr('BLOCKED — explicit primary GID must identify an existing verified target-rootfs group.'))
                    return
            groups_text = self.identity_supplementary_groups.text().strip()
            if groups_text:
                tokens = [x.strip() for x in re.split('[,;\\s]+', groups_text) if x.strip()]
                if any((not re.fullmatch('[a-z_][a-z0-9_-]{0,31}', x) for x in tokens)):
                    QMessageBox.warning(self, tr('Users/groups plan blocked'), tr('Supplementary group list contains an invalid group name.'))
                    return
                missing = sorted(set(tokens) - set(available_groups))
                if missing:
                    QMessageBox.information(self, tr('Users/groups plan blocked'), tr('BLOCKED — group(s) not verified in target rootfs: ' + ', '.join(missing)))
                    return
                supplementary_groups = sorted(set(tokens))
                group_membership_mode = 'set'
            policy_fields = [self.identity_password_min_days.text().strip(), self.identity_password_max_days.text().strip(), self.identity_password_warn_days.text().strip()]
            if any(policy_fields):
                if not all(policy_fields):
                    QMessageBox.warning(self, tr('Users/groups plan blocked'), tr('Set all three password-aging values (min/max/warn days), or leave all blank to preserve the existing policy.'))
                    return
                if str(identity.get('password_policy_status') or 'UNKNOWN') not in supported:
                    QMessageBox.information(self, tr('Users/groups plan blocked'), tr('BLOCKED — password-policy capability is not verified for this target image.'))
                    return
                try:
                    min_days, max_days, warn_days = [int(x) for x in policy_fields]
                except ValueError:
                    QMessageBox.warning(self, tr('Users/groups plan blocked'), tr('Password-aging values must be integers.'))
                    return
                if not (0 <= min_days <= 99999 and 1 <= max_days <= 99999 and (0 <= warn_days <= 99999) and (min_days <= max_days)):
                    QMessageBox.warning(self, tr('Users/groups plan blocked'), tr('Password-aging values are outside the supported range or min days exceeds max days.'))
                    return
                password_policy = {'mode': 'configure', 'min_days': min_days, 'max_days': max_days, 'warn_days': warn_days}
        payload = common | {'operation': operation, 'plan_slot': f'user:{username}', 'username': username, 'display_name': display_name, 'display_name_mode': 'preserve' if target_exists and (not display_name) else 'set', 'target_exists': target_exists, 'account_role': role, 'admin_group': admin_group, 'uid': uid, 'uid_mode': 'preserve' if target_exists and uid is None else 'automatic' if uid is None else 'set', 'primary_gid': gid, 'primary_gid_mode': 'preserve' if target_exists and gid is None else 'automatic' if gid is None else 'set', 'supplementary_groups': supplementary_groups, 'group_membership_mode': group_membership_mode, 'password_policy': password_policy, 'require_uid_gid_conflict_check_before_apply': True, 'require_group_reverification_before_apply': True, 'require_password_policy_reverification_before_apply': password_policy.get('mode') == 'configure'}
        role_text = 'administrator' if role == 'administrator' else 'standard user' if role == 'standard' else 'preserved role'
        detail = f"{operation.replace('_', ' ')} '{username}' as {role_text}; preserve unrelated users/groups, separate autologin policy and all credential secrets."
        change = ChangeItem('Users / Groups / Password Policy plan', ChangeKind.CONFIG, detail, payload)
        self.stage_requested.emit(change)
        self.identity_plan_status.setText(tr('Staged — review/Test in Changes.'))
        QMessageBox.information(self, tr('STAGED: Users / Groups / Password Policy plan'), tr('Target-account intent is source-hash locked and staging-only. Windows/WSL host accounts, password secrets and source-ISO bytes remain untouched.'))

    def _stage_machine_identity_plan(self) -> None:
        sha = str(self._analysis.get('sha256') or '').strip().casefold()
        machine = dict(self._analysis.get('system_machine_identity_evidence') or {})
        if not re.fullmatch('[0-9a-f]{64}', sha):
            QMessageBox.information(self, tr('Machine identity plan blocked'), tr('BLOCKED — analyze a source ISO before staging hostname/machine identity changes.'))
            return
        if machine.get('verified') is not True:
            QMessageBox.information(self, tr('Machine identity plan blocked'), tr('BLOCKED — /etc/hostname has not been verified read-only inside the selected rootfs. Nothing has been staged.'))
            self.machine_plan_status.setText(tr('Blocked — rootfs hostname/machine identity evidence is not verified.'))
            return
        if self.machine_operation.currentData() != 'configure_hostname':
            QMessageBox.information(self, tr('Machine identity plan'), tr('No hostname/machine identity change is selected. Existing configuration remains preserved.'))
            return
        hostname = self.machine_hostname.text().strip().casefold()
        labels = hostname.split('.') if hostname else []
        hostname_ok = bool(hostname) and len(hostname) <= 253 and all((re.fullmatch('[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in labels))
        if not hostname_ok:
            QMessageBox.warning(self, tr('Machine identity plan blocked'), tr('Hostname must use lowercase letters, digits, hyphens and optional dots; each label must start/end with a letter or digit.'))
            return
        machine_policy = str(self.machine_id_policy.currentData() or 'preserve')
        payload = {'config_type': 'system_machine_identity', 'source_sha256': sha, 'operation': 'configure_hostname', 'target_hostname': hostname, 'current_hostname': str(machine.get('hostname') or ''), 'hostname_layer': str(machine.get('hostname_layer') or ''), 'machine_id_policy': machine_policy, 'machine_id_state': str(machine.get('machine_id_state') or 'unknown'), 'machine_id_layer': str(machine.get('machine_id_layer') or ''), 'rootfs_machine_identity_verified': True, 'machine_id_value_staged': False, 'source_read_only': True, 'preserve_unrelated': True, 'stage_only': True}
        machine_text = 'preserve current machine-id boot behavior' if machine_policy == 'preserve' else 'regenerate machine-id on first boot'
        detail = f"Configure target-system hostname '{hostname}'; {machine_text}; no machine-id value staged."
        change = ChangeItem('Hostname / machine identity plan', ChangeKind.CONFIG, detail, payload)
        self.stage_requested.emit(change)
        self.machine_plan_status.setText(tr('Staged — review/Test in Changes.'))
        QMessageBox.information(self, tr('STAGED: Hostname / machine identity plan'), tr('Hostname/machine identity intent is source-hash locked and staging-only. No machine-id value or source-ISO byte has been written.'))

    def _stage_autologin_plan(self) -> None:
        sha = str(self._analysis.get('sha256') or '').strip().casefold()
        evidence = dict(self._analysis.get('system_autologin_evidence') or {})
        if not re.fullmatch('[0-9a-f]{64}', sha):
            QMessageBox.information(self, tr('Autologin plan blocked'), tr('BLOCKED — analyze a source ISO before staging autologin changes.'))
            return
        if evidence.get('verified') is not True:
            QMessageBox.information(self, tr('Autologin plan blocked'), tr('BLOCKED — no supported default display manager has been verified read-only inside the selected rootfs. Nothing has been staged.'))
            self.autologin_plan_status.setText(tr('Blocked — rootfs display-manager/autologin evidence is not verified.'))
            return
        operation = str(self.autologin_operation.currentData() or 'preserve')
        if operation == 'preserve':
            QMessageBox.information(self, tr('Autologin plan'), tr('No autologin change is selected. Existing login policy remains preserved.'))
            return
        target_user = ''
        if operation == 'enable_autologin':
            target_user = self.autologin_target_user.text().strip()
            if not re.fullmatch('[a-z_][a-z0-9_-]{0,31}', target_user):
                QMessageBox.warning(self, tr('Autologin plan blocked'), tr('Target user must be a safe lowercase Linux account name (1–32 characters).'))
                return
        display_manager = str(evidence.get('display_manager') or '').casefold()
        payload = {'config_type': 'system_autologin', 'source_sha256': sha, 'operation': operation, 'target_user': target_user, 'display_manager': display_manager, 'display_manager_layer': str(evidence.get('display_manager_layer') or ''), 'current_autologin_state': str(evidence.get('autologin_state') or 'unknown'), 'current_autologin_user': str(evidence.get('autologin_user') or ''), 'rootfs_autologin_verified': True, 'credential_secret_read': False, 'credential_secret_staged': False, 'require_target_user_verification_before_apply': operation == 'enable_autologin', 'session_policy': 'preserve_current_or_default_session', 'source_read_only': True, 'preserve_unrelated': True, 'stage_only': True}
        if operation == 'enable_autologin':
            detail = f"Enable {display_manager} autologin for target user '{target_user}'; target user must be re-verified before apply; no credential secret staged."
        else:
            detail = f'Disable {display_manager} autologin; preserve unrelated display-manager/session configuration; no credential secret staged.'
        change = ChangeItem('Autologin / display manager plan', ChangeKind.CONFIG, detail, payload)
        self.stage_requested.emit(change)
        self.autologin_plan_status.setText(tr('Staged — review/Test in Changes.'))
        QMessageBox.information(self, tr('STAGED: Autologin / display manager plan'), tr('Autologin intent is source-hash locked and staging-only. No password, token, credential secret or source-ISO byte has been written.'))

    def _stage_locale_plan(self) -> None:
        sha = str(self._analysis.get('sha256') or '').strip().casefold()
        evidence = dict(self._analysis.get('system_locale_evidence') or {})
        if not re.fullmatch('[0-9a-f]{64}', sha):
            QMessageBox.information(self, tr('Locale plan blocked'), tr('BLOCKED — analyze a source ISO before staging locale/language changes.'))
            return
        if evidence.get('verified') is not True:
            QMessageBox.information(self, tr('Locale plan blocked'), tr('BLOCKED — supported locale configuration evidence has not been verified read-only inside the selected rootfs. Nothing has been staged.'))
            self.locale_plan_status.setText(tr('Blocked — rootfs locale/language evidence is not verified.'))
            return
        if self.locale_operation.currentData() != 'configure_lang':
            QMessageBox.information(self, tr('Locale plan'), tr('No locale/language change is selected. Existing regional configuration remains preserved.'))
            return
        target = self.locale_target.text().strip()
        locale_re = '(?:C|POSIX|C\\.UTF-8|[A-Za-z]{2,3}_[A-Za-z]{2}(?:\\.[A-Za-z0-9_-]+)?(?:@[A-Za-z0-9_-]+)?)'
        if not re.fullmatch(locale_re, target):
            QMessageBox.warning(self, tr('Locale plan blocked'), tr('Target LANG must be a safe locale identifier, for example da_DK.UTF-8.'))
            return
        payload = {'config_type': 'system_locale', 'source_sha256': sha, 'operation': 'configure_lang', 'target_lang': target, 'locale_config_path': str(evidence.get('config_path') or ''), 'locale_config_layer': str(evidence.get('config_layer') or ''), 'locale_config_style': str(evidence.get('config_style') or ''), 'current_lang': str(evidence.get('current_lang') or ''), 'rootfs_locale_verified': True, 'require_locale_availability_verification_before_apply': True, 'preserve_language_and_lc_overrides': True, 'secret_read': False, 'secret_staged': False, 'source_read_only': True, 'preserve_unrelated': True, 'stage_only': True}
        detail = f"Configure target-system LANG='{target}'; preserve LANGUAGE/LC_* overrides and re-verify locale availability before apply."
        change = ChangeItem('Locale / language plan', ChangeKind.CONFIG, detail, payload)
        self.stage_requested.emit(change)
        self.locale_plan_status.setText(tr('Staged — review/Test in Changes.'))
        QMessageBox.information(self, tr('STAGED: Locale / language plan'), tr('Locale/language intent is source-hash locked and staging-only. Existing LANGUAGE/LC_* overrides and source-ISO bytes remain untouched.'))

    def _stage_keyboard_plan(self) -> None:
        sha = str(self._analysis.get('sha256') or '').strip().casefold()
        evidence = dict(self._analysis.get('system_keyboard_evidence') or {})
        if not re.fullmatch('[0-9a-f]{64}', sha):
            QMessageBox.information(self, tr('Keyboard plan blocked'), tr('BLOCKED — analyze a source ISO before staging keyboard-layout changes.'))
            return
        if evidence.get('verified') is not True:
            QMessageBox.information(self, tr('Keyboard plan blocked'), tr('BLOCKED — supported keyboard configuration evidence has not been verified read-only inside the selected rootfs. Nothing has been staged.'))
            self.keyboard_plan_status.setText(tr('Blocked — rootfs keyboard-layout evidence is not verified.'))
            return
        if self.keyboard_operation.currentData() != 'configure_layout':
            QMessageBox.information(self, tr('Keyboard plan'), tr('No keyboard-layout change is selected. Existing keyboard configuration remains preserved.'))
            return
        target = self.keyboard_target.text().strip().casefold()
        if not re.fullmatch('[a-z0-9][a-z0-9_-]{0,31}', target):
            QMessageBox.warning(self, tr('Keyboard plan blocked'), tr('Target layout must be a safe XKB layout identifier, for example dk.'))
            return
        payload = {'config_type': 'system_keyboard', 'source_sha256': sha, 'operation': 'configure_layout', 'target_layout': target, 'keyboard_config_path': str(evidence.get('config_path') or ''), 'keyboard_config_layer': str(evidence.get('config_layer') or ''), 'keyboard_config_style': str(evidence.get('config_style') or ''), 'current_layout': str(evidence.get('current_layout') or ''), 'rootfs_keyboard_verified': True, 'require_layout_availability_verification_before_apply': True, 'preserve_model_variant_options': True, 'secret_read': False, 'secret_staged': False, 'source_read_only': True, 'preserve_unrelated': True, 'stage_only': True}
        detail = f"Configure target-system keyboard layout '{target}'; preserve model/variant/options and re-verify layout availability before apply."
        change = ChangeItem('Keyboard layout plan', ChangeKind.CONFIG, detail, payload)
        self.stage_requested.emit(change)
        self.keyboard_plan_status.setText(tr('Staged — review/Test in Changes.'))
        QMessageBox.information(self, tr('STAGED: Keyboard layout plan'), tr('Keyboard-layout intent is source-hash locked and staging-only. Existing model/variant/options and source-ISO bytes remain untouched.'))

    def _stage_timezone_plan(self) -> None:
        sha = str(self._analysis.get('sha256') or '').strip().casefold()
        evidence = dict(self._analysis.get('system_timezone_evidence') or {})
        if not re.fullmatch('[0-9a-f]{64}', sha):
            QMessageBox.information(self, tr('Timezone plan blocked'), tr('BLOCKED — analyze a source ISO before staging timezone changes.'))
            return
        if evidence.get('verified') is not True:
            QMessageBox.information(self, tr('Timezone plan blocked'), tr('BLOCKED — supported timezone evidence has not been verified read-only inside the selected rootfs. Nothing has been staged.'))
            self.timezone_plan_status.setText(tr('Blocked — rootfs timezone evidence is not verified.'))
            return
        if self.timezone_operation.currentData() != 'configure_timezone':
            QMessageBox.information(self, tr('Timezone plan'), tr('No timezone change is selected. Existing timezone configuration remains preserved.'))
            return
        target = self.timezone_target.text().strip()
        if not self._safe_timezone_name(target):
            QMessageBox.warning(self, tr('Timezone plan blocked'), tr('Target timezone must be a safe IANA-style identifier, for example Europe/Copenhagen.'))
            return
        payload = {'config_type': 'system_timezone', 'source_sha256': sha, 'operation': 'configure_timezone', 'target_timezone': target, 'timezone_config_path': str(evidence.get('config_path') or ''), 'timezone_config_layer': str(evidence.get('config_layer') or ''), 'timezone_config_style': str(evidence.get('config_style') or ''), 'current_timezone': str(evidence.get('current_timezone') or ''), 'rootfs_timezone_verified': True, 'require_zoneinfo_verification_before_apply': True, 'preserve_hwclock_rtc_policy': True, 'secret_read': False, 'secret_staged': False, 'source_read_only': True, 'preserve_unrelated': True, 'stage_only': True}
        detail = f"Configure target-system timezone '{target}'; preserve RTC/hardware-clock policy and re-verify zoneinfo before apply."
        change = ChangeItem('Timezone plan', ChangeKind.CONFIG, detail, payload)
        self.stage_requested.emit(change)
        self.timezone_plan_status.setText(tr('Staged — review/Test in Changes.'))
        QMessageBox.information(self, tr('STAGED: Timezone plan'), tr('Timezone intent is source-hash locked and staging-only. RTC/hardware-clock policy and source-ISO bytes remain untouched.'))

    @staticmethod
    def _safe_network_profile_name(value: str) -> bool:
        return bool(value) and len(value) <= 64 and (not any((ch in value for ch in ('/', '\\', '\r', '\n', '\x00', ':'))))

    @staticmethod
    def _safe_interface_name(value: str) -> bool:
        return not value or bool(re.fullmatch('[A-Za-z0-9_.:-]{1,15}', value))

    @staticmethod
    def _parse_ipv4_dns(raw: str, *, allow_empty: bool=False) -> list[str] | None:
        parts = [x for x in re.split('[\\s,;]+', raw.strip()) if x]
        if not parts and allow_empty:
            return []
        if not parts or len(parts) > 4:
            return None
        result: list[str] = []
        try:
            for value in parts:
                address = ipaddress.ip_address(value)
                if address.version != 4:
                    return None
                normalized = str(address)
                if normalized not in result:
                    result.append(normalized)
        except ValueError:
            return None
        return result if len(result) == len(parts) else None

    def _stage_network_dns_plan(self) -> None:
        sha = str(self._analysis.get('sha256') or '').strip().casefold()
        evidence = dict(self._analysis.get('system_network_dns_evidence') or {})
        supported_states = {'SUPPORTED', 'SUPPORTED_WITH_REQUIREMENTS'}
        if not re.fullmatch('[0-9a-f]{64}', sha):
            QMessageBox.information(self, tr('Networking plan blocked'), tr('BLOCKED — analyze a source ISO before staging networking changes.'))
            return
        capability = str(evidence.get('capability_status') or ('SUPPORTED_WITH_REQUIREMENTS' if evidence.get('verified') is True else 'UNKNOWN'))
        if evidence.get('verified') is not True or capability not in supported_states:
            QMessageBox.information(self, tr('Networking plan blocked'), tr(f'{capability} — target-rootfs network backend/capability is not verified for safe staged configuration. Host networking is never used as a fallback.'))
            self.network_plan_status.setText(tr(f'{capability} — networking staging blocked fail-closed.'))
            return
        operation = str(self.network_operation.currentData() or 'preserve')
        if operation == 'preserve':
            QMessageBox.information(self, tr('Networking plan'), tr('No networking change is selected. Existing target networking remains preserved.'))
            return
        supported_ops = set(self._network_supported_operations())
        if operation not in supported_ops:
            QMessageBox.information(self, tr('Networking plan blocked'), tr('BLOCKED — requested operation is not verified for this target-image backend.'))
            return
        depth = str(self.network_depth.currentData() or 'quick')
        if depth == 'quick' and operation not in {'configure_dns_servers', 'configure_dhcp_ipv4'}:
            QMessageBox.information(self, tr('Networking plan blocked'), tr('BLOCKED — static/profile operations require Advanced or Expert control depth.'))
            return
        backend = str(evidence.get('backend') or '')
        if str(evidence.get('gate_version') or '') != 'alpha51' and operation == 'configure_dns_servers':
            servers = self._parse_ipv4_dns(self.network_dns_target.text(), allow_empty=False)
            if servers is None:
                QMessageBox.warning(self, tr('Networking plan blocked'), tr('DNS must contain 1–4 unique literal IPv4 addresses.'))
                return
            payload = {'config_type': 'system_network_dns', 'source_sha256': sha, 'operation': operation, 'target_dns_servers': servers, 'network_backend': backend, 'backend_config_path': str(evidence.get('backend_config_path') or ''), 'backend_config_layer': str(evidence.get('backend_config_layer') or ''), 'resolver_path': str(evidence.get('resolver_path') or ''), 'resolver_layer': str(evidence.get('resolver_layer') or ''), 'rootfs_network_dns_verified': True, 'require_backend_specific_apply_verification': True, 'preserve_connection_profiles': True, 'preserve_ip_dhcp_routes': True, 'connection_profiles_inspected': False, 'wifi_vpn_secrets_read': False, 'secret_read': False, 'secret_staged': False, 'source_read_only': True, 'preserve_unrelated': True, 'stage_only': True}
            change = ChangeItem('Networking / DNS plan', ChangeKind.CONFIG, f"Configure target-system DNS servers {', '.join(servers)}; preserve interfaces, addressing, routes and connection profiles.", payload)
            self.stage_requested.emit(change)
            self.network_plan_status.setText(tr('Staged — review/Test in Changes.'))
            QMessageBox.information(self, tr('STAGED: Networking / DNS plan'), tr('Legacy DNS intent remains source-hash locked and staging-only.'))
            return
        backend_path = str(evidence.get('backend_config_path') or '')
        backend_layer = str(evidence.get('backend_config_layer') or '')
        managed_path = str(evidence.get('managed_config_path') or '')
        if backend not in {'NetworkManager', 'netplan', 'ifupdown', 'systemd-networkd'} or not backend_path or (not backend_layer.startswith('/')) or (not managed_path.startswith('/')):
            QMessageBox.information(self, tr('Networking plan blocked'), tr('UNKNOWN — backend or safe managed target path could not be verified; nothing has been staged.'))
            return
        interface = self.network_interface.text().strip()
        if not self._safe_interface_name(interface):
            QMessageBox.warning(self, tr('Networking plan blocked'), tr('Target interface name is invalid; use at most 15 safe Linux interface-name characters.'))
            return
        profile_name = self.network_profile_name.text().strip()
        if backend == 'NetworkManager' and operation in {'configure_dns_servers', 'configure_dhcp_ipv4', 'configure_static_ipv4', 'create_networkmanager_profile'}:
            if not self._safe_network_profile_name(profile_name):
                QMessageBox.warning(self, tr('Networking plan blocked'), tr('A safe managed NetworkManager profile name is required for this operation.'))
                return
        dns_servers: list[str] = []
        if operation in {'configure_dns_servers', 'configure_static_ipv4', 'create_networkmanager_profile'}:
            dns_servers = self._parse_ipv4_dns(self.network_dns_target.text(), allow_empty=operation != 'configure_dns_servers')
            if dns_servers is None:
                QMessageBox.warning(self, tr('Networking plan blocked'), tr('DNS must contain 1–4 unique literal IPv4 addresses. IPv6 is intentionally not exposed in Alpha 51.'))
                return
        ipv4_address = ''
        gateway = ''
        if operation == 'configure_static_ipv4':
            try:
                interface_value = ipaddress.ip_interface(self.network_ipv4_address.text().strip())
            except ValueError:
                QMessageBox.warning(self, tr('Networking plan blocked'), tr('Static address must be a valid IPv4 address with prefix, for example 192.168.1.50/24.'))
                return
            if interface_value.version != 4:
                QMessageBox.warning(self, tr('Networking plan blocked'), tr('IPv6 is intentionally not exposed in Alpha 51.'))
                return
            ipv4_address = str(interface_value)
            try:
                gateway_value = ipaddress.ip_address(self.network_gateway.text().strip())
            except ValueError:
                QMessageBox.warning(self, tr('Networking plan blocked'), tr('Gateway must be a literal IPv4 address.'))
                return
            if gateway_value.version != 4:
                QMessageBox.warning(self, tr('Networking plan blocked'), tr('IPv6 is intentionally not exposed in Alpha 51.'))
                return
            gateway = str(gateway_value)
        existing_profile = ''
        autoconnect_enabled = True
        profile_candidates = [str(x) for x in evidence.get('networkmanager_profile_names') or [] if str(x).strip()]
        if operation == 'set_networkmanager_autoconnect':
            if backend != 'NetworkManager' or str(evidence.get('networkmanager_profile_status') or 'UNKNOWN') not in supported_states:
                QMessageBox.information(self, tr('Networking plan blocked'), tr('BLOCKED — NetworkManager profile capability is not verified for this target image.'))
                return
            existing_profile = str(self.network_existing_profile.currentData() or '')
            if not existing_profile or existing_profile not in profile_candidates or (not existing_profile.endswith('.nmconnection')):
                QMessageBox.information(self, tr('Networking plan blocked'), tr('BLOCKED — select an existing NetworkManager profile verified from target-rootfs metadata.'))
                return
            autoconnect_enabled = bool(self.network_autoconnect.currentData())
        payload = {'config_type': 'system_network_dns', 'gate_version': 'alpha51', 'source_sha256': sha, 'analysis_scope': 'target_iso_rootfs', 'capability_status': capability, 'addressing_status': str(evidence.get('addressing_status') or 'UNKNOWN'), 'dns_status': str(evidence.get('dns_status') or 'UNKNOWN'), 'networkmanager_profile_status': str(evidence.get('networkmanager_profile_status') or 'UNKNOWN'), 'control_depth': depth, 'operation': operation, 'network_backend': backend, 'backend_config_path': backend_path, 'backend_config_layer': backend_layer, 'managed_config_path': managed_path, 'managed_config_style': str(evidence.get('managed_config_style') or ''), 'resolver_path': str(evidence.get('resolver_path') or ''), 'resolver_layer': str(evidence.get('resolver_layer') or ''), 'rootfs_network_dns_verified': True, 'supported_operations': sorted(supported_ops), 'target_profile_name': profile_name if backend == 'NetworkManager' and operation != 'set_networkmanager_autoconnect' else '', 'existing_profile_filename': existing_profile, 'target_interface': interface, 'ipv4_method': 'auto' if operation in {'configure_dhcp_ipv4', 'create_networkmanager_profile'} else 'manual' if operation == 'configure_static_ipv4' else 'preserve', 'target_ipv4_address': ipv4_address, 'target_gateway': gateway, 'target_dns_servers': dns_servers, 'autoconnect_enabled': autoconnect_enabled if operation in {'create_networkmanager_profile', 'set_networkmanager_autoconnect'} else None, 'profile_connection_type': '802-3-ethernet' if operation == 'create_networkmanager_profile' else 'preserve', 'require_backend_specific_apply_verification': True, 'require_target_path_reverification_before_apply': True, 'require_syntax_validation_before_apply': True, 'require_profile_reverification_before_apply': operation == 'set_networkmanager_autoconnect', 'preserve_existing_profiles': True, 'preserve_unrelated_routes': True, 'preserve_hostname': True, 'connection_profiles_inspected': False, 'connection_profile_contents_read': False, 'profile_names_from_metadata_only': True, 'wifi_vpn_secrets_read': False, 'credential_secret_read': False, 'credential_secret_staged': False, 'secret_read': False, 'secret_staged': False, 'host_network_accessed': False, 'ipv6_exposed': False, 'ipv6_supported_by_gate': False, 'source_read_only': True, 'preserve_unrelated': True, 'stage_only': True}
        operation_text = operation.replace('_', ' ')
        detail = f'{operation_text} via verified target backend {backend}; preserve unrelated profiles/routes/hostname; IPv6 and credential secrets remain untouched.'
        change = ChangeItem('Networking / NetworkManager / DNS plan', ChangeKind.CONFIG, detail, payload)
        self.stage_requested.emit(change)
        self.network_plan_status.setText(tr('Staged — review/Test in Changes.'))
        QMessageBox.information(self, tr('STAGED: Networking / NetworkManager / DNS plan'), tr('Networking intent is source-hash locked, target-rootfs-only and staging-only. Host networking, existing profile contents, Wi-Fi/VPN credentials and source-ISO bytes remain untouched.'))

    def _stage_services_plan(self) -> None:
        sha = str(self._analysis.get('sha256') or '').strip().casefold()
        evidence = dict(self._analysis.get('system_services_evidence') or {})
        if not re.fullmatch('[0-9a-f]{64}', sha):
            QMessageBox.information(self, tr('Services/systemd plan blocked'), tr('BLOCKED — analyze a source ISO before staging service startup changes.'))
            return
        if evidence.get('verified') is not True:
            QMessageBox.information(self, tr('Services/systemd plan blocked'), tr('BLOCKED — supported systemd unit-directory evidence has not been verified read-only inside the selected rootfs. Nothing has been staged.'))
            self.services_plan_status.setText(tr('Blocked — rootfs services/systemd evidence is not verified.'))
            return
        operation = str(self.services_operation.currentData() or '')
        if operation not in {'enable_service', 'disable_service'}:
            QMessageBox.information(self, tr('Services/systemd plan'), tr('No service startup change is selected. Existing startup policy remains preserved.'))
            return
        unit = self.services_target.text().strip()
        if not re.fullmatch('[A-Za-z0-9_.@:-]{1,120}\\.service', unit) or '/' in unit:
            QMessageBox.warning(self, tr('Services/systemd plan blocked'), tr('Target must be a safe systemd .service unit name, for example NetworkManager.service.'))
            return
        payload = {'config_type': 'system_services', 'source_sha256': sha, 'operation': operation, 'service_unit': unit, 'init_system': str(evidence.get('init_system') or ''), 'vendor_unit_path': str(evidence.get('vendor_unit_path') or ''), 'vendor_unit_layer': str(evidence.get('vendor_unit_layer') or ''), 'local_unit_path': str(evidence.get('local_unit_path') or ''), 'local_unit_layer': str(evidence.get('local_unit_layer') or ''), 'rootfs_services_verified': True, 'require_target_unit_verification_before_apply': True, 'preserve_unit_file_contents': True, 'preserve_timers_targets': True, 'unit_contents_read': False, 'enablement_links_read': False, 'service_secrets_read': False, 'secret_read': False, 'secret_staged': False, 'source_read_only': True, 'preserve_unrelated': True, 'stage_only': True}
        verb = 'Enable' if operation == 'enable_service' else 'Disable'
        detail = f"{verb} target-system service '{unit}' at startup; preserve unit contents, timers, targets and unrelated service policy; target unit must be re-verified before apply."
        change = ChangeItem('Services / systemd plan', ChangeKind.CONFIG, detail, payload)
        self.stage_requested.emit(change)
        self.services_plan_status.setText(tr('Staged — review/Test in Changes.'))
        QMessageBox.information(self, tr('STAGED: Services / systemd plan'), tr('Service startup intent is source-hash locked and staging-only. Unit contents, service credentials and source-ISO bytes remain untouched.'))

    def _stage_timers_plan(self) -> None:
        sha = str(self._analysis.get('sha256') or '').strip().casefold()
        evidence = dict(self._analysis.get('system_timers_evidence') or {})
        if not re.fullmatch('[0-9a-f]{64}', sha):
            QMessageBox.information(self, tr('Timers/systemd plan blocked'), tr('BLOCKED — analyze a source ISO before staging timer startup changes.'))
            return
        if evidence.get('verified') is not True:
            QMessageBox.information(self, tr('Timers/systemd plan blocked'), tr('BLOCKED — supported systemd timer staging evidence has not been verified read-only inside the selected rootfs. Nothing has been staged.'))
            self.timers_plan_status.setText(tr('Blocked — rootfs timers/systemd evidence is not verified.'))
            return
        operation = str(self.timers_operation.currentData() or '')
        if operation not in {'enable_timer', 'disable_timer'}:
            QMessageBox.information(self, tr('Timers/systemd plan'), tr('No timer startup change is selected. Existing timer policy remains preserved.'))
            return
        unit = self.timers_target.text().strip()
        if not re.fullmatch('[A-Za-z0-9_.@:-]{1,120}\\.timer', unit) or '/' in unit:
            QMessageBox.warning(self, tr('Timers/systemd plan blocked'), tr('Target must be a safe systemd .timer unit name, for example apt-daily.timer.'))
            return
        payload = {'config_type': 'system_timers', 'source_sha256': sha, 'operation': operation, 'timer_unit': unit, 'init_system': str(evidence.get('init_system') or ''), 'vendor_unit_path': str(evidence.get('vendor_unit_path') or ''), 'vendor_unit_layer': str(evidence.get('vendor_unit_layer') or ''), 'local_unit_path': str(evidence.get('local_unit_path') or ''), 'local_unit_layer': str(evidence.get('local_unit_layer') or ''), 'rootfs_timers_verified': True, 'require_target_timer_verification_before_apply': True, 'preserve_timer_file_contents': True, 'preserve_services_targets': True, 'timer_contents_read': False, 'enablement_links_read': False, 'service_secrets_read': False, 'secret_read': False, 'secret_staged': False, 'source_read_only': True, 'preserve_unrelated': True, 'stage_only': True}
        verb = 'Enable' if operation == 'enable_timer' else 'Disable'
        detail = f"{verb} target-system timer '{unit}'; preserve timer contents, services, targets and unrelated startup policy; target timer must be re-verified before apply."
        change = ChangeItem('Timers / systemd plan', ChangeKind.CONFIG, detail, payload)
        self.stage_requested.emit(change)
        self.timers_plan_status.setText(tr('Staged — review/Test in Changes.'))
        QMessageBox.information(self, tr('STAGED: Timers / systemd plan'), tr('Timer startup intent is source-hash locked and staging-only. Timer contents, service credentials and source-ISO bytes remain untouched.'))

    def _stage_firewall_plan(self) -> None:
        sha = str(self._analysis.get('sha256') or '').strip().casefold()
        evidence = dict(self._analysis.get('system_firewall_evidence') or {})
        if not re.fullmatch('[0-9a-f]{64}', sha):
            QMessageBox.information(self, tr('Firewall plan blocked'), tr('BLOCKED — analyze a source ISO before staging firewall changes.'))
            return
        if evidence.get('verified') is not True:
            QMessageBox.information(self, tr('Firewall plan blocked'), tr('BLOCKED — supported firewall backend evidence has not been verified read-only inside the selected rootfs. Nothing has been staged.'))
            self.firewall_plan_status.setText(tr('Blocked — rootfs firewall evidence is not verified.'))
            return
        operation = str(self.firewall_operation.currentData() or '')
        if operation not in {'enable_firewall', 'disable_firewall'}:
            QMessageBox.information(self, tr('Firewall plan'), tr('No firewall state change is selected. Existing firewall policy remains preserved.'))
            return
        backend = str(evidence.get('backend') or '').strip().casefold()
        payload = {'config_type': 'system_firewall', 'source_sha256': sha, 'operation': operation, 'backend': backend, 'backend_path': str(evidence.get('backend_path') or ''), 'backend_layer': str(evidence.get('backend_layer') or ''), 'rootfs_firewall_verified': True, 'require_backend_apply_verification_before_apply': True, 'preserve_rule_contents': True, 'preserve_ports_services_profiles': True, 'rule_contents_read': False, 'ports_services_policy_read': False, 'application_profiles_read': False, 'firewall_secrets_read': False, 'secret_read': False, 'secret_staged': False, 'source_read_only': True, 'preserve_unrelated': True, 'stage_only': True}
        verb = 'Enable' if operation == 'enable_firewall' else 'Disable'
        detail = f'{verb} target-system firewall via verified {backend} backend; preserve rule contents, ports/services policy, application profiles and unrelated networking; backend/apply semantics must be re-verified before apply.'
        change = ChangeItem('Firewall plan', ChangeKind.CONFIG, detail, payload)
        self.stage_requested.emit(change)
        self.firewall_plan_status.setText(tr('Staged — review/Test in Changes.'))
        QMessageBox.information(self, tr('STAGED: Firewall plan'), tr('Firewall state intent is source-hash locked and staging-only. Firewall rules, policy details, secrets and source-ISO bytes remain untouched.'))

    def _stage_apparmor_plan(self) -> None:
        sha = str(self._analysis.get('sha256') or '').strip().casefold()
        evidence = dict(self._analysis.get('system_apparmor_evidence') or {})
        if not re.fullmatch('[0-9a-f]{64}', sha):
            QMessageBox.information(self, tr('AppArmor plan blocked'), tr('BLOCKED — analyze a source ISO before staging AppArmor changes.'))
            return
        if evidence.get('verified') is not True:
            QMessageBox.information(self, tr('AppArmor plan blocked'), tr('BLOCKED — AppArmor component evidence has not been verified read-only inside the selected rootfs. Nothing has been staged.'))
            self.apparmor_plan_status.setText(tr('Blocked — rootfs AppArmor evidence is not verified.'))
            return
        operation = str(self.apparmor_operation.currentData() or '')
        if operation not in {'enable_apparmor', 'disable_apparmor'}:
            QMessageBox.information(self, tr('AppArmor plan'), tr('No AppArmor state change is selected. Existing AppArmor policy remains preserved.'))
            return
        payload = {'config_type': 'system_apparmor', 'source_sha256': sha, 'operation': operation, 'backend': str(evidence.get('backend') or '').strip().casefold(), 'evidence_path': str(evidence.get('evidence_path') or ''), 'evidence_layer': str(evidence.get('evidence_layer') or ''), 'rootfs_apparmor_verified': True, 'require_backend_apply_verification_before_apply': True, 'preserve_profiles': True, 'preserve_parser_config': True, 'profile_contents_read': False, 'parser_config_read': False, 'abstractions_tunables_read': False, 'apparmor_secrets_read': False, 'secret_read': False, 'secret_staged': False, 'source_read_only': True, 'preserve_unrelated': True, 'stage_only': True}
        verb = 'Enable' if operation == 'enable_apparmor' else 'Disable'
        detail = f'{verb} target-system AppArmor using verified component evidence; preserve profiles, parser configuration, abstractions/tunables and unrelated security configuration; boot/apply semantics must be re-verified before apply.'
        change = ChangeItem('AppArmor plan', ChangeKind.CONFIG, detail, payload)
        self.stage_requested.emit(change)
        self.apparmor_plan_status.setText(tr('Staged — review/Test in Changes.'))
        QMessageBox.information(self, tr('STAGED: AppArmor plan'), tr('AppArmor state intent is source-hash locked and staging-only. Profiles, parser configuration, policy secrets and source-ISO bytes remain untouched.'))

    def _stage_selinux_plan(self) -> None:
        sha = str(self._analysis.get('sha256') or '').strip().casefold()
        evidence = dict(self._analysis.get('system_selinux_evidence') or {})
        capability = str(evidence.get('capability_status') or 'UNKNOWN')
        if not re.fullmatch('[0-9a-f]{64}', sha):
            QMessageBox.information(self, tr('SELinux plan blocked'), tr('BLOCKED — analyze a source ISO before staging SELinux changes.'))
            return
        if capability not in {'SUPPORTED', 'SUPPORTED_WITH_REQUIREMENTS'} or evidence.get('verified') is not True:
            QMessageBox.information(self, tr('SELinux plan blocked'), tr(f'BLOCKED — target SELinux capability is {capability}. ChromaPress does not guess when the mechanism is not verified.'))
            self.selinux_plan_status.setText(tr(f'Blocked — SELinux capability is {capability}.'))
            return
        target_mode = str(self.selinux_mode.currentData() or 'preserve')
        if target_mode == 'preserve':
            QMessageBox.information(self, tr('SELinux plan'), tr('No SELinux state change is selected. Existing SELinux configuration and policy remain preserved.'))
            return
        supported_modes = {str(x) for x in evidence.get('supported_modes') or []}
        if target_mode not in supported_modes:
            QMessageBox.information(self, tr('SELinux plan blocked'), tr('BLOCKED — the selected SELinux mode is not supported by verified target capability.'))
            self.selinux_plan_status.setText(tr('Blocked — selected SELinux mode is not verified for this target.'))
            return
        configured_mode = str(evidence.get('configured_mode') or 'unknown')
        enabling = target_mode in {'enforcing', 'permissive'}
        relabel_required = bool(enabling and evidence.get('relabel_required_on_enable'))
        reboot_required = bool(evidence.get('reboot_required'))
        required_packages = [str(x) for x in evidence.get('required_packages') or [] if str(x).strip()]
        part3_requirements = list(evidence.get('part3_requirements') or [])
        payload = {'config_type': 'system_selinux', 'gate_version': 'alpha52', 'source_sha256': sha, 'analysis_scope': 'target_iso_rootfs', 'operation': 'set_selinux_mode', 'target_mode': target_mode, 'configured_mode': configured_mode, 'capability_status': capability, 'rootfs_selinux_verified': True, 'config_path': str(evidence.get('config_path') or '/etc/selinux/config'), 'config_layer': str(evidence.get('config_layer') or ''), 'config_metadata_read': bool(evidence.get('config_metadata_read')), 'config_creation_required': bool(evidence.get('config_creation_required')), 'policy_type': str(evidence.get('policy_type') or ''), 'policy_tree_present': bool(evidence.get('policy_tree_present')), 'policy_entries': [str(x) for x in evidence.get('policy_entries') or []], 'policy_contents_read': False, 'preserve_existing_policies': True, 'custom_policy_preserved': True, 'package_manager': str(evidence.get('package_manager') or ''), 'package_manager_path': str(evidence.get('package_manager_path') or ''), 'repository_metadata_path': str(evidence.get('repository_metadata_path') or ''), 'package_install_required': bool(evidence.get('package_install_required')), 'required_packages': required_packages, 'require_signed_repository_metadata': True, 'require_dependency_resolution': True, 'package_requirements_staged': bool(required_packages), 'kernel_support_status': str(evidence.get('kernel_support_status') or 'UNKNOWN'), 'kernel_config_path': str(evidence.get('kernel_config_path') or ''), 'kernel_images': [str(x) for x in evidence.get('kernel_images') or []], 'boot_config_files': [str(x) for x in evidence.get('boot_config_files') or []], 'initramfs_mechanism': str(evidence.get('initramfs_mechanism') or ''), 'part3_dependency_required': bool(evidence.get('part3_dependency_required')), 'part3_requirements': part3_requirements, 'dependencies_visible': True, 'dependencies_staged': True, 'delegate_boot_kernel_to_part3': True, 'direct_boot_mutation': False, 'direct_kernel_mutation': False, 'direct_initramfs_mutation': False, 'relabel_required': relabel_required, 'relabel_before_enforcing': bool(target_mode == 'enforcing' and relabel_required), 'reboot_required': reboot_required, 'require_post_boot_verification': True, 'host_selinux_accessed': False, 'host_security_state_accessed': False, 'secret_read': False, 'secret_staged': False, 'source_read_only': True, 'preserve_unrelated': True, 'stage_only': True}
        requirements = []
        if required_packages:
            requirements.append('packages: ' + ', '.join(required_packages))
        if part3_requirements:
            requirements.append(f'{len(part3_requirements)} Part 3 requirement(s)')
        if relabel_required:
            requirements.append('filesystem relabel')
        if reboot_required:
            requirements.append('reboot')
        req_text = '; '.join(requirements) if requirements else 'no additional requirement'
        detail = f'Set target-system SELinux mode to {target_mode}; capability={capability}; {req_text}. Preserve existing/custom SELinux policy. Package dependencies remain explicit and all boot/kernel/initramfs requirements are delegated to the existing Part 3 model; no direct boot mutation.'
        change = ChangeItem('SELinux plan', ChangeKind.CONFIG, detail, payload)
        self.stage_requested.emit(change)
        self.selinux_plan_status.setText(tr('Staged — review dependencies/Test/Undo in Changes.'))
        QMessageBox.information(self, tr('STAGED: SELinux plan'), tr('SELinux intent is source-hash locked and staging-only. Existing policy is preserved. Package and Part 3 requirements are explicit; source-ISO bytes remain untouched.'))

    def _stage_sysctl_plan(self) -> None:
        sha = str(self._analysis.get('sha256') or '').strip().casefold()
        evidence = dict(self._analysis.get('system_sysctl_evidence') or {})
        if not re.fullmatch('[0-9a-f]{64}', sha):
            QMessageBox.information(self, tr('sysctl plan blocked'), tr('BLOCKED — analyze a source ISO before staging sysctl changes.'))
            return
        if evidence.get('verified') is not True:
            QMessageBox.information(self, tr('sysctl plan blocked'), tr('BLOCKED — sysctl infrastructure evidence has not been verified read-only inside the selected rootfs. Nothing has been staged.'))
            self.sysctl_plan_status.setText(tr('Blocked — rootfs sysctl evidence is not verified.'))
            return
        operation = str(self.sysctl_operation.currentData() or '')
        if operation != 'set_integer_sysctl':
            QMessageBox.information(self, tr('sysctl plan'), tr('No sysctl value change is selected. Existing sysctl configuration remains preserved.'))
            return
        key = self.sysctl_key.text().strip()
        value = self.sysctl_value.text().strip()
        if not re.fullmatch('[A-Za-z0-9_.-]{1,128}', key) or '.' not in key:
            QMessageBox.warning(self, tr('sysctl plan blocked'), tr('BLOCKED — enter a safe dotted sysctl key such as vm.swappiness.'))
            self.sysctl_plan_status.setText(tr('Blocked — invalid sysctl key.'))
            return
        if not re.fullmatch('-?[0-9]{1,10}', value):
            QMessageBox.warning(self, tr('sysctl plan blocked'), tr('BLOCKED — Alpha 49 accepts one integer sysctl value only.'))
            self.sysctl_plan_status.setText(tr('Blocked — sysctl value must be an integer.'))
            return
        payload = {'config_type': 'system_sysctl', 'source_sha256': sha, 'operation': operation, 'sysctl_key': key, 'sysctl_value': value, 'backend': str(evidence.get('backend') or '').strip().casefold(), 'evidence_path': str(evidence.get('evidence_path') or ''), 'evidence_layer': str(evidence.get('evidence_layer') or ''), 'rootfs_sysctl_verified': True, 'require_target_key_apply_verification_before_apply': True, 'preserve_existing_sysctl_config': True, 'use_managed_dropin_on_apply': True, 'config_contents_read': False, 'runtime_values_read': False, 'sysctl_secrets_read': False, 'secret_read': False, 'secret_staged': False, 'source_read_only': True, 'preserve_unrelated': True, 'stage_only': True}
        detail = f'Set target-system sysctl {key}={value}; preserve existing sysctl files and effective runtime values; target key/apply semantics must be re-verified before apply and later apply must use a managed drop-in.'
        change = ChangeItem('sysctl plan', ChangeKind.CONFIG, detail, payload)
        self.stage_requested.emit(change)
        self.sysctl_plan_status.setText(tr('Staged — review/Test in Changes.'))
        QMessageBox.information(self, tr('STAGED: sysctl plan'), tr('sysctl intent is source-hash locked and staging-only. Existing sysctl configuration/runtime values and source-ISO bytes remain untouched.'))

    def _stage_security_defaults_plan(self) -> None:
        sha = str(self._analysis.get('sha256') or '').strip().casefold()
        evidence = dict(self._analysis.get('system_security_defaults_evidence') or {})
        allowed = {'SUPPORTED', 'SUPPORTED_WITH_REQUIREMENTS'}
        if not re.fullmatch('[0-9a-f]{64}', sha):
            QMessageBox.information(self, tr('Security defaults plan blocked'), tr('BLOCKED — analyze a source ISO before staging security-default changes.'))
            return
        capability = str(evidence.get('capability_status') or 'UNKNOWN')
        if evidence.get('verified') is not True or capability not in allowed:
            QMessageBox.information(self, tr('Security defaults plan blocked'), tr(f'{capability} — target login security-default capability is not verified. Nothing has been staged.'))
            self.security_defaults_plan_status.setText(tr(f'{capability} — security-default staging blocked fail-closed.'))
            return
        operation = str(self.security_defaults_operation.currentData() or 'preserve')
        if operation != 'set_default_umask':
            QMessageBox.information(self, tr('Security defaults plan'), tr('No login security-default change is selected. Existing configuration remains preserved.'))
            return
        target_umask = str(self.security_defaults_umask.currentData() or '')
        supported_umasks = [str(x) for x in evidence.get('supported_umasks') or []]
        if target_umask not in {'022', '027', '077'} or target_umask not in supported_umasks:
            QMessageBox.warning(self, tr('Security defaults plan blocked'), tr('BLOCKED — select a verified allowlisted default UMASK (022, 027 or 077).'))
            return
        payload = {'config_type': 'system_security_defaults', 'gate_version': 'alpha53', 'source_sha256': sha, 'analysis_scope': 'target_iso_rootfs', 'capability_status': capability, 'rootfs_security_defaults_verified': True, 'operation': operation, 'target_umask': target_umask, 'supported_umasks': supported_umasks, 'backend': str(evidence.get('backend') or ''), 'config_path': str(evidence.get('config_path') or ''), 'config_layer': str(evidence.get('config_layer') or ''), 'current_umask': str(evidence.get('current_umask') or ''), 'umask_directive_present': bool(evidence.get('umask_directive_present')), 'usergroups_enab': str(evidence.get('usergroups_enab') or ''), 'metadata_keys_read': [str(x) for x in evidence.get('metadata_keys_read') or []], 'require_target_directive_reverification_before_apply': True, 'require_effective_session_semantics_verification_before_apply': True, 'preserve_login_defs_unrelated': True, 'preserve_pam_configuration': True, 'preserve_account_policy': True, 'full_config_exposed': False, 'credential_secret_read': False, 'credential_secret_staged': False, 'host_security_state_accessed': False, 'secret_read': False, 'secret_staged': False, 'source_read_only': True, 'preserve_unrelated': True, 'stage_only': True}
        detail = f'Set target-system default login UMASK to {target_umask}; preserve unrelated /etc/login.defs directives, PAM/account policy and all credentials. Exact target directive and effective login/session semantics must be re-verified before apply.'
        change = ChangeItem('Security defaults plan', ChangeKind.CONFIG, detail, payload)
        self.stage_requested.emit(change)
        self.security_defaults_plan_status.setText(tr('Staged — review/Test/Undo in Changes.'))
        QMessageBox.information(self, tr('STAGED: Security defaults plan'), tr('Login security-default intent is source-hash locked, target-rootfs-evidence bound and staging-only; source-ISO bytes remain untouched.'))

    def _stage_config_overlay_plan(self) -> None:
        sha = str(self._analysis.get('sha256') or '').strip().casefold()
        evidence = dict(self._analysis.get('system_config_overlay_evidence') or {})
        allowed = {'SUPPORTED', 'SUPPORTED_WITH_REQUIREMENTS'}
        if not re.fullmatch('[0-9a-f]{64}', sha):
            QMessageBox.information(self, tr('System configuration overlay blocked'), tr('BLOCKED — analyze a source ISO before staging system-configuration overlays.'))
            return
        capability = str(evidence.get('capability_status') or 'UNKNOWN')
        if evidence.get('verified') is not True or capability not in allowed:
            QMessageBox.information(self, tr('System configuration overlay blocked'), tr(f'{capability} — target overlay mechanism is not verified. Nothing has been staged.'))
            self.config_overlay_plan_status.setText(tr(f'{capability} — system-configuration overlay staging blocked fail-closed.'))
            return
        operation = str(self.config_overlay_operation.currentData() or 'preserve')
        if operation != 'add_managed_environment_overlay':
            QMessageBox.information(self, tr('System configuration overlay'), tr('No overlay change is selected. Existing target configuration remains preserved.'))
            return
        overlay_name = self.config_overlay_name.text().strip().casefold()
        variable = self.config_overlay_variable.text().strip().upper()
        value = self.config_overlay_value.text().strip()
        if not re.fullmatch('[a-z0-9][a-z0-9-]{0,31}', overlay_name):
            QMessageBox.warning(self, tr('System configuration overlay blocked'), tr('BLOCKED — overlay name must use lowercase letters, numbers or hyphens (max 32 characters).'))
            return
        if not re.fullmatch('[A-Z][A-Z0-9_]{0,63}', variable):
            QMessageBox.warning(self, tr('System configuration overlay blocked'), tr('BLOCKED — environment variable must be a safe uppercase identifier.'))
            return
        if any((word in variable for word in ('SECRET', 'TOKEN', 'PASSWORD', 'PASSWD', 'CREDENTIAL', 'AUTH', 'PRIVATE_KEY', 'API_KEY'))):
            QMessageBox.warning(self, tr('System configuration overlay blocked'), tr('BLOCKED — secret/credential-like variable names are not allowed in this public configuration gate.'))
            return
        if not re.fullmatch('[A-Za-z0-9._:/@%+,-]{1,128}', value):
            QMessageBox.warning(self, tr('System configuration overlay blocked'), tr('BLOCKED — value must be a short non-secret literal without whitespace or shell metacharacters.'))
            return
        target_filename = f'99-chromapress-{overlay_name}.sh'
        existing = [str(x) for x in evidence.get('existing_entry_names') or []]
        if target_filename in existing:
            QMessageBox.warning(self, tr('System configuration overlay blocked'), tr(f'BLOCKED — {target_filename} already exists in the target. Existing custom configuration will not be overwritten.'))
            return
        payload = {'config_type': 'system_config_overlay', 'gate_version': 'alpha54', 'source_sha256': sha, 'analysis_scope': 'target_iso_rootfs', 'capability_status': capability, 'rootfs_overlay_verified': True, 'operation': operation, 'backend': str(evidence.get('backend') or ''), 'profile_path': str(evidence.get('profile_path') or ''), 'profile_layer': str(evidence.get('profile_layer') or ''), 'target_directory': str(evidence.get('target_directory') or ''), 'target_directory_layer': str(evidence.get('target_directory_layer') or ''), 'profile_d_sourcing_verified': evidence.get('profile_d_sourcing_verified') is True, 'existing_entry_names': existing, 'overlay_name': overlay_name, 'target_filename': target_filename, 'environment_variable': variable, 'public_nonsecret_value': value, 'content_classification': 'public_nonsecret', 'generated_content_only': True, 'arbitrary_shell_content_allowed': False, 'require_target_file_absence_reverification_before_apply': True, 'preserve_existing_profile': True, 'preserve_existing_dropins': True, 'existing_dropin_contents_read': False, 'host_configuration_accessed': False, 'secret_read': False, 'secret_staged': False, 'source_read_only': True, 'preserve_unrelated': True, 'stage_only': True}
        detail = f'Add managed non-secret profile.d overlay {target_filename} for {variable}; preserve /etc/profile and every existing profile.d entry; re-verify filename absence before apply.'
        change = ChangeItem('System configuration overlay plan', ChangeKind.CONFIG, detail, payload)
        self.stage_requested.emit(change)
        self.config_overlay_plan_status.setText(tr('Staged — review/Test/Undo in Changes.'))
        QMessageBox.information(self, tr('STAGED: System configuration overlay plan'), tr('Managed overlay intent is source-hash locked, target-rootfs-evidence bound, collision-checked and staging-only; source-ISO bytes remain untouched.'))

    def _stage_kiosk_user_plan(self) -> None:
        sha = str(self._analysis.get('sha256') or '').strip().casefold()
        evidence = dict(self._analysis.get('system_kiosk_user_evidence') or {})
        if not re.fullmatch('[0-9a-f]{64}', sha):
            QMessageBox.information(self, tr('Dedicated kiosk user blocked'), tr('BLOCKED — analyze a source ISO before staging a dedicated kiosk account.'))
            return
        capability = str(evidence.get('capability_status') or 'UNKNOWN')
        if evidence.get('verified') is not True or capability not in {'SUPPORTED', 'SUPPORTED_WITH_REQUIREMENTS'}:
            QMessageBox.information(self, tr('Dedicated kiosk user blocked'), tr(f'{capability} — target account capability is not verified for dedicated kiosk-user staging. Nothing has been staged.'))
            self.kiosk_user_plan_status.setText(tr(f'{capability} — dedicated kiosk-user staging blocked fail-closed.'))
            return
        operation = str(self.kiosk_user_operation.currentData() or 'preserve')
        if operation != 'create_dedicated_non_admin_kiosk_user':
            QMessageBox.information(self, tr('Dedicated kiosk user'), tr('No kiosk-account change is selected. Existing accounts remain preserved.'))
            return
        username = self.kiosk_username.text().strip().casefold()
        display_name = self.kiosk_display_name.text().strip()
        if not re.fullmatch('[a-z_][a-z0-9_-]{0,31}', username):
            QMessageBox.warning(self, tr('Dedicated kiosk user blocked'), tr('BLOCKED — username is not a safe Linux account name.'))
            return
        existing = [str(x) for x in evidence.get('existing_regular_users') or []]
        if username in existing:
            QMessageBox.warning(self, tr('Dedicated kiosk user blocked'), tr('BLOCKED — that username already exists in the target image; existing accounts are preserved.'))
            return
        if not display_name or len(display_name) > 128 or any((ch in display_name for ch in ('\r', '\n', '\x00', ':'))):
            QMessageBox.warning(self, tr('Dedicated kiosk user blocked'), tr('BLOCKED — display name is empty or contains unsupported data.'))
            return
        payload = {'config_type': 'dedicated_kiosk_user', 'gate_version': 'alpha55', 'source_sha256': sha, 'analysis_scope': 'target_iso_rootfs', 'capability_status': capability, 'rootfs_account_verified': True, 'operation': operation, 'backend': str(evidence.get('backend') or 'passwd-group'), 'passwd_layer': str(evidence.get('passwd_layer') or ''), 'group_layer': str(evidence.get('group_layer') or ''), 'uid_min': int(evidence.get('uid_min') or 1000), 'existing_regular_users': existing, 'existing_user_uids': list(evidence.get('existing_user_uids') or []), 'available_groups': list(evidence.get('available_groups') or []), 'verified_admin_groups': list(evidence.get('admin_groups') or []), 'username': username, 'display_name': display_name, 'account_role': 'dedicated_non_admin_kiosk', 'uid_mode': 'automatic', 'primary_gid_mode': 'automatic', 'supplementary_groups': [], 'administrative_groups': [], 'create_home': True, 'credential_policy': 'deferred_to_later_verified_gate', 'credential_secret_read': False, 'credential_secret_staged': False, 'shadow_read': False, 'host_accounts_touched': False, 'login_policy_deferred_to_later_gate': True, 'session_policy_deferred_to_later_gate': True, 'autologin_policy_preserved': True, 'require_user_absence_reverification_before_apply': True, 'preserve_existing_users_groups': True, 'source_read_only': True, 'preserve_unrelated': True, 'stage_only': True}
        detail = f"Create dedicated non-admin kiosk user '{username}' with automatic UID/GID and home directory; stage no credentials/admin groups and preserve login/session/autologin policy for later gates."
        change = ChangeItem('Dedicated non-admin kiosk user plan', ChangeKind.CONFIG, detail, payload)
        self.stage_requested.emit(change)
        self.kiosk_user_plan_status.setText(tr('Staged — review/Test/Undo in Changes.'))
        QMessageBox.information(self, tr('STAGED: Dedicated non-admin kiosk user plan'), tr('Kiosk-account intent is source-hash locked, target-rootfs-evidence bound, non-admin and staging-only; source-ISO bytes remain untouched.'))

    def _stage_restricted_login_plan(self) -> None:
        sha = str(self._analysis.get('sha256') or '').strip().casefold()
        evidence = dict(self._analysis.get('system_restricted_login_evidence') or {})
        if not re.fullmatch('[0-9a-f]{64}', sha):
            QMessageBox.information(self, tr('Restricted login blocked'), tr('BLOCKED — analyze a source ISO before staging restricted login.'))
            return
        capability = str(evidence.get('capability_status') or 'UNKNOWN')
        if evidence.get('verified') is not True or capability not in {'SUPPORTED', 'SUPPORTED_WITH_REQUIREMENTS'}:
            QMessageBox.information(self, tr('Restricted login blocked'), tr(f'{capability} — target restricted-login capability is not verified. Nothing has been staged.'))
            self.restricted_login_plan_status.setText(tr(f'{capability} — restricted-login staging blocked fail-closed.'))
            return
        operation = str(self.restricted_login_operation.currentData() or 'preserve')
        if operation != 'lock_password_authentication':
            QMessageBox.information(self, tr('Restricted login'), tr('No restricted-login change is selected. Existing login policy remains preserved.'))
            return
        username = self.restricted_login_username.text().strip().casefold()
        if not re.fullmatch('[a-z_][a-z0-9_-]{0,31}', username):
            QMessageBox.warning(self, tr('Restricted login blocked'), tr('BLOCKED — kiosk username is not a safe Linux account name.'))
            return
        existing = [str(x) for x in evidence.get('existing_regular_users') or []]
        admin_users = [str(x) for x in evidence.get('admin_users') or []]
        if username == 'root' or username in admin_users:
            QMessageBox.warning(self, tr('Restricted login blocked'), tr('BLOCKED — root or a verified administrative user cannot be used by this kiosk restricted-login gate.'))
            return
        dependency = 'verified_existing_target_user' if username in existing else 'alpha55_dedicated_non_admin_kiosk_user'
        payload = {'config_type': 'restricted_login', 'gate_version': 'alpha56', 'source_sha256': sha, 'analysis_scope': 'target_iso_rootfs', 'capability_status': capability, 'rootfs_login_restriction_verified': True, 'operation': operation, 'backend': str(evidence.get('backend') or ''), 'management_tool_path': str(evidence.get('management_tool_path') or ''), 'management_tool_layer': str(evidence.get('management_tool_layer') or ''), 'passwd_layer': str(evidence.get('passwd_layer') or ''), 'group_layer': str(evidence.get('group_layer') or ''), 'existing_regular_users': existing, 'admin_users': admin_users, 'username': username, 'account_dependency': dependency, 'restriction_scope': 'password_authentication_only', 'password_authentication': 'locked', 'credential_secret_read': False, 'credential_secret_staged': False, 'shadow_read': False, 'host_login_state_accessed': False, 'pam_contents_read': False, 'ssh_config_read': False, 'preserve_autologin': True, 'preserve_session_policy': True, 'preserve_ssh_configuration': True, 'preserve_pam_configuration': True, 'require_account_dependency_reverification_before_apply': True, 'source_read_only': True, 'preserve_unrelated': True, 'stage_only': True}
        if dependency == 'verified_existing_target_user':
            detail = f"Lock password authentication for existing non-admin target user '{username}' using verified target tool {payload['management_tool_path']}; preserve autologin/session/SSH/PAM policy."
        else:
            detail = f"Lock password authentication for planned dedicated kiosk user '{username}' after explicit Alpha 55 account-creation dependency; preserve autologin/session/SSH/PAM policy."
        change = ChangeItem('Restricted login plan', ChangeKind.CONFIG, detail, payload)
        self.stage_requested.emit(change)
        self.restricted_login_plan_status.setText(tr('Staged — review/Test/Undo in Changes.'))
        QMessageBox.information(self, tr('STAGED: Restricted login plan'), tr('Restricted-login intent is source-hash locked, target-rootfs-tool bound, password-lock scoped and staging-only; no password/secret or source-ISO byte was changed.'))

    def _stage_restricted_session_plan(self) -> None:
        sha = str(self._analysis.get('sha256') or '').strip().casefold()
        evidence = dict(self._analysis.get('system_restricted_session_evidence') or {})
        if not re.fullmatch('[0-9a-f]{64}', sha):
            QMessageBox.information(self, tr('Restricted session blocked'), tr('BLOCKED — analyze a source ISO before staging restricted-session changes.'))
            return
        capability = str(evidence.get('capability_status') or 'UNKNOWN')
        if evidence.get('verified') is not True or capability not in {'SUPPORTED', 'SUPPORTED_WITH_REQUIREMENTS'}:
            QMessageBox.information(self, tr('Restricted session blocked'), tr(f'{capability} — target restricted-session capability is not verified. Nothing has been staged.'))
            self.restricted_session_plan_status.setText(tr(f'{capability} — restricted-session staging blocked fail-closed.'))
            return
        operation = str(self.restricted_session_operation.currentData() or 'preserve')
        if operation != 'bind_kiosk_autologin_session':
            QMessageBox.information(self, tr('Restricted session'), tr('No restricted-session change is selected. Existing session policy remains preserved.'))
            return
        username = self.restricted_session_username.text().strip().casefold()
        if not re.fullmatch('[a-z_][a-z0-9_-]{0,31}', username):
            QMessageBox.warning(self, tr('Restricted session blocked'), tr('BLOCKED — kiosk username is not a safe Linux account name.'))
            return
        existing = [str(x) for x in evidence.get('existing_regular_users') or []]
        admin_users = [str(x) for x in evidence.get('admin_users') or []]
        if username == 'root' or username in admin_users:
            QMessageBox.warning(self, tr('Restricted session blocked'), tr('BLOCKED — root or a verified administrative user cannot be targeted by the restricted-session gate.'))
            return
        session_name = str(self.restricted_session_choice.currentData() or '')
        sessions = [x for x in evidence.get('verified_sessions') or [] if isinstance(x, dict)]
        selected = next((x for x in sessions if str(x.get('name') or '') == session_name), None)
        if not selected:
            QMessageBox.warning(self, tr('Restricted session blocked'), tr('BLOCKED — choose a session descriptor verified in the target ISO.'))
            return
        dependency = 'verified_existing_target_user' if username in existing else 'alpha55_dedicated_non_admin_kiosk_user'
        payload = {'config_type': 'restricted_session', 'gate_version': 'alpha57', 'source_sha256': sha, 'analysis_scope': 'target_iso_rootfs', 'capability_status': capability, 'rootfs_restricted_session_verified': True, 'operation': operation, 'backend': str(evidence.get('backend') or ''), 'display_manager': str(evidence.get('display_manager') or ''), 'display_manager_layer': str(evidence.get('display_manager_layer') or ''), 'target_config_directory': str(evidence.get('target_config_directory') or ''), 'target_config_directory_layer': str(evidence.get('target_config_directory_layer') or ''), 'managed_target_path': str(evidence.get('managed_target_path') or ''), 'managed_target_present': evidence.get('managed_target_present') is True, 'verified_sessions': sessions, 'existing_regular_users': existing, 'admin_users': admin_users, 'username': username, 'account_dependency': dependency, 'session_name': session_name, 'session_kind': str(selected.get('kind') or ''), 'restriction_scope': 'fixed_autologin_session_selection_only', 'sddm_section': 'Autologin', 'sddm_key': 'Session', 'restricted_login_dependency': 'alpha56_restricted_login_required', 'autologin_dependency': 'alpha39_autologin_same_user_required', 'session_file_contents_read': False, 'display_manager_config_contents_read': False, 'credential_secret_read': False, 'credential_secret_staged': False, 'host_session_state_accessed': False, 'pam_contents_read': False, 'ssh_config_read': False, 'preserve_existing_session_descriptors': True, 'preserve_existing_display_manager_config': True, 'preserve_other_users_sessions': True, 'preserve_pam_configuration': True, 'preserve_ssh_configuration': True, 'require_managed_target_absence_reverification_before_apply': True, 'require_dependencies_reverification_before_apply': True, 'source_read_only': True, 'preserve_unrelated': True, 'stage_only': True}
        detail = f"Bind kiosk user '{username}' to verified {payload['session_kind']} session '{session_name}' through a managed SDDM Autologin/Session drop-in; require Alpha 56 restricted login and same-user Alpha 39 autologin before apply; preserve existing sessions and display-manager configuration."
        change = ChangeItem('Restricted session plan', ChangeKind.CONFIG, detail, payload)
        self.stage_requested.emit(change)
        self.restricted_session_plan_status.setText(tr('Staged — review/Test/Undo in Changes.'))
        QMessageBox.information(self, tr('STAGED: Restricted session plan'), tr('Restricted-session intent is source-hash locked, target-session/SDDM-evidence bound, dependency-explicit and staging-only; source-ISO bytes remain untouched.'))

    def _stage_service_lockdown_plan(self) -> None:
        sha = str(self._analysis.get('sha256') or '').strip().casefold()
        evidence = dict(self._analysis.get('system_service_lockdown_evidence') or {})
        if not re.fullmatch('[0-9a-f]{64}', sha):
            QMessageBox.information(self, tr('Service lockdown blocked'), tr('BLOCKED — analyze a source ISO before staging service-lockdown changes.'))
            return
        capability = str(evidence.get('capability_status') or 'UNKNOWN')
        if evidence.get('verified') is not True or capability not in {'SUPPORTED', 'SUPPORTED_WITH_REQUIREMENTS'}:
            QMessageBox.information(self, tr('Service lockdown blocked'), tr(f'{capability} — target service-lockdown capability is not verified. Nothing has been staged.'))
            self.service_lockdown_plan_status.setText(tr(f'{capability} — service-lockdown staging blocked fail-closed.'))
            return
        operation = str(self.service_lockdown_operation.currentData() or 'preserve')
        if operation != 'disable_and_mask_verified_service':
            QMessageBox.information(self, tr('Service lockdown'), tr('No service-lockdown change is selected. Existing service policy remains preserved.'))
            return
        unit = str(self.service_lockdown_choice.currentData() or '')
        available = [x for x in evidence.get('available_lockdown_units') or [] if isinstance(x, dict)]
        selected = next((x for x in available if str(x.get('name') or '') == unit), None)
        if not selected:
            QMessageBox.warning(self, tr('Service lockdown blocked'), tr('BLOCKED — choose a non-protected .service unit verified in the target ISO.'))
            return
        protected = [str(x) for x in evidence.get('protected_service_units') or []]
        if unit in protected:
            QMessageBox.warning(self, tr('Service lockdown blocked'), tr('BLOCKED — the selected unit is protected by ChromaPress safety policy.'))
            return
        payload = {'config_type': 'service_lockdown', 'gate_version': 'alpha58', 'source_sha256': sha, 'analysis_scope': 'target_iso_rootfs', 'capability_status': capability, 'rootfs_service_lockdown_verified': True, 'operation': operation, 'backend': str(evidence.get('backend') or ''), 'init_system': str(evidence.get('init_system') or ''), 'vendor_unit_path': str(evidence.get('vendor_unit_path') or ''), 'vendor_unit_layer': str(evidence.get('vendor_unit_layer') or ''), 'local_unit_path': str(evidence.get('local_unit_path') or ''), 'local_unit_layer': str(evidence.get('local_unit_layer') or ''), 'verified_service_units': list(evidence.get('verified_service_units') or []), 'available_lockdown_units': available, 'protected_service_units': protected, 'service_unit': unit, 'service_unit_directory': str(selected.get('directory') or ''), 'service_unit_layer': str(selected.get('layer') or ''), 'lockdown_scope': 'single_verified_noncritical_systemd_service', 'unit_contents_read': False, 'enablement_links_read': False, 'enablement_link_targets_read': False, 'environment_files_read': False, 'service_secrets_read': False, 'credential_secret_read': False, 'host_service_state_accessed': False, 'preserve_unit_file_contents': True, 'preserve_timer_socket_units': True, 'preserve_unrelated_services': True, 'require_target_unit_reverification_before_apply': True, 'require_systemd_apply_verification': True, 'source_read_only': True, 'preserve_unrelated': True, 'stage_only': True}
        detail = f"Disable and mask verified non-protected target service '{unit}'; preserve unit contents, timers/sockets and unrelated service policy; re-verify target/systemd semantics before apply."
        change = ChangeItem('Service lockdown plan', ChangeKind.CONFIG, detail, payload)
        self.stage_requested.emit(change)
        self.service_lockdown_plan_status.setText(tr('Staged — review/Test/Undo in Changes.'))
        QMessageBox.information(self, tr('STAGED: Service lockdown plan'), tr('Service-lockdown intent is source-hash locked, verified-target-unit bound, protected-unit filtered and staging-only; source-ISO bytes and host service state remain untouched.'))

    def _stage_network_restriction_plan(self) -> None:
        sha = str(self._analysis.get('sha256') or '').strip().casefold()
        evidence = dict(self._analysis.get('system_network_restriction_evidence') or {})
        if not re.fullmatch('[0-9a-f]{64}', sha):
            QMessageBox.information(self, tr('Network restrictions blocked'), tr('BLOCKED — analyze a source ISO before staging network restrictions.'))
            return
        capability = str(evidence.get('capability_status') or 'UNKNOWN')
        if evidence.get('verified') is not True or capability not in {'SUPPORTED', 'SUPPORTED_WITH_REQUIREMENTS'}:
            QMessageBox.information(self, tr('Network restrictions blocked'), tr(f'{capability} — target network-restriction capability is not verified. Nothing has been staged.'))
            self.network_restriction_plan_status.setText(tr(f'{capability} — network-restriction staging blocked fail-closed.'))
            return
        operation = str(self.network_restriction_operation.currentData() or 'preserve')
        if operation != 'restrict_kiosk_networkmanager_control':
            QMessageBox.information(self, tr('Network restrictions'), tr('No network-restriction change is selected. Existing network-control policy remains preserved.'))
            return
        username = self.network_restriction_username.text().strip()
        if not re.fullmatch('[a-z_][a-z0-9_-]{0,31}', username):
            QMessageBox.warning(self, tr('Network restrictions blocked'), tr('BLOCKED — enter a safe Linux kiosk username.'))
            return
        if evidence.get('managed_target_present') is True:
            QMessageBox.warning(self, tr('Network restrictions blocked'), tr('BLOCKED — the managed Alpha 59 polkit rule already exists; preservation-first policy forbids overwrite.'))
            return
        payload = {'config_type': 'network_restriction', 'gate_version': 'alpha59', 'source_sha256': sha, 'analysis_scope': 'target_iso_rootfs', 'capability_status': capability, 'rootfs_network_restriction_verified': True, 'operation': operation, 'backend': str(evidence.get('backend') or ''), 'network_backend': str(evidence.get('network_backend') or ''), 'polkit_rules_directory': str(evidence.get('polkit_rules_directory') or ''), 'polkit_rules_directory_layer': str(evidence.get('polkit_rules_directory_layer') or ''), 'networkmanager_policy_path': str(evidence.get('networkmanager_policy_path') or ''), 'networkmanager_policy_layer': str(evidence.get('networkmanager_policy_layer') or ''), 'managed_rule_name': str(evidence.get('managed_rule_name') or ''), 'managed_rule_path': str(evidence.get('managed_rule_path') or ''), 'managed_target_present': False, 'existing_rule_names': list(evidence.get('existing_rule_names') or []), 'restricted_actions': list(evidence.get('restricted_actions') or []), 'username': username, 'restriction_scope': 'kiosk_networkmanager_control_only', 'kiosk_user_dependency': 'alpha55_dedicated_non_admin_kiosk_user_required', 'traffic_blocking_claimed': False, 'firewall_rules_read': False, 'firewall_rules_staged': False, 'networkmanager_profile_contents_read': False, 'polkit_policy_contents_read': False, 'existing_rule_contents_read': False, 'credential_secret_read': False, 'host_network_accessed': False, 'preserve_existing_network_profiles': True, 'preserve_existing_polkit_rules': True, 'preserve_firewall_policy': True, 'preserve_other_users_network_control': True, 'require_managed_target_absence_reverification_before_apply': True, 'require_networkmanager_polkit_reverification_before_apply': True, 'require_kiosk_user_dependency_reverification_before_apply': True, 'source_read_only': True, 'preserve_unrelated': True, 'stage_only': True}
        detail = f"Restrict kiosk user '{username}' from changing verified NetworkManager system/network-control state via a managed polkit rule; preserve profiles/firewall/other polkit rules and re-verify target mechanism/dependency before apply."
        change = ChangeItem('Network restrictions plan', ChangeKind.CONFIG, detail, payload)
        self.stage_requested.emit(change)
        self.network_restriction_plan_status.setText(tr('Staged — review/Test/Undo in Changes.'))
        QMessageBox.information(self, tr('STAGED: Network restrictions plan'), tr('Network-control restriction intent is source-hash locked, target NetworkManager/polkit bound, non-traffic-blocking and staging-only; source-ISO bytes and host networking remain untouched.'))

    def _stage_firewall_rules_plan(self) -> None:
        sha = str(self._analysis.get('sha256') or '').strip().casefold()
        evidence = dict(self._analysis.get('system_firewall_rules_evidence') or {})
        if not re.fullmatch('[0-9a-f]{64}', sha):
            QMessageBox.information(self, tr('Firewall rules blocked'), tr('BLOCKED — analyze a source ISO before staging firewall rules.'))
            return
        capability = str(evidence.get('capability_status') or 'UNKNOWN')
        if evidence.get('verified') is not True or capability not in {'SUPPORTED', 'SUPPORTED_WITH_REQUIREMENTS'}:
            QMessageBox.information(self, tr('Firewall rules blocked'), tr(f'{capability} — target firewall-rule capability is not verified. Nothing has been staged.'))
            self.firewall_rules_plan_status.setText(tr(f'{capability} — firewall-rule staging blocked fail-closed.'))
            return
        operation = str(self.firewall_rules_operation.currentData() or 'preserve')
        if operation != 'deny_inbound_tcp_port':
            QMessageBox.information(self, tr('Firewall rules'), tr('No firewall-rule change is selected. Existing firewall policy remains preserved.'))
            return
        raw_port = self.firewall_rules_port.text().strip()
        try:
            port = int(raw_port)
        except ValueError:
            port = 0
        if not 1 <= port <= 65535 or str(port) != raw_port:
            QMessageBox.warning(self, tr('Firewall rules blocked'), tr('BLOCKED — enter one TCP port as an integer from 1 through 65535.'))
            return
        payload = {'config_type': 'firewall_rule', 'gate_version': 'alpha60', 'source_sha256': sha, 'analysis_scope': 'target_iso_rootfs', 'capability_status': capability, 'rootfs_firewall_rules_verified': True, 'operation': operation, 'firewall_backend': str(evidence.get('firewall_backend') or ''), 'backend_evidence_path': str(evidence.get('backend_evidence_path') or ''), 'backend_evidence_layer': str(evidence.get('backend_evidence_layer') or ''), 'rule_adapter': str(evidence.get('rule_adapter') or ''), 'rule_command_path': str(evidence.get('rule_command_path') or ''), 'rule_command_layer': str(evidence.get('rule_command_layer') or ''), 'tcp_port': port, 'protocol': 'tcp', 'direction': 'in', 'action': 'deny', 'rule_scope': 'single_inbound_tcp_port_deny', 'existing_rule_contents_read': False, 'ports_services_policy_read': False, 'application_profiles_read': False, 'firewall_secrets_read': False, 'host_firewall_accessed': False, 'preserve_existing_rules': True, 'preserve_default_policy': True, 'preserve_unrelated_firewall_policy': True, 'requires_apply_time_conflict_check': True, 'requires_backend_state_reverification': True, 'require_rule_command_reverification_before_apply': True, 'source_read_only': True, 'preserve_unrelated': True, 'stage_only': True}
        detail = f"Deny inbound TCP port {port} through verified target {payload['firewall_backend']} additive adapter; preserve existing/default/unrelated firewall policy and re-verify duplicate/conflict/backend state before apply."
        change = ChangeItem('Firewall rules plan', ChangeKind.CONFIG, detail, payload)
        self.stage_requested.emit(change)
        self.firewall_rules_plan_status.setText(tr('Staged — review/Test/Undo in Changes.'))
        QMessageBox.information(self, tr('STAGED: Firewall rules plan'), tr('Firewall-rule intent is source-hash locked, target-adapter bound, single-port scoped and staging-only; existing rules and host firewall state remain untouched.'))

    def _stage_persistence_policy_plan(self) -> None:
        sha = str(self._analysis.get('sha256') or '').strip().casefold()
        evidence = dict(self._analysis.get('system_persistence_policy_evidence') or {})
        if not re.fullmatch('[0-9a-f]{64}', sha):
            QMessageBox.information(self, tr('Persistence policy blocked'), tr('BLOCKED — analyze a source ISO before staging persistence policy.'))
            return
        capability = str(evidence.get('capability_status') or 'UNKNOWN')
        if evidence.get('verified') is not True or capability not in {'SUPPORTED', 'SUPPORTED_WITH_REQUIREMENTS'}:
            QMessageBox.information(self, tr('Persistence policy blocked'), tr(f'{capability} — target persistence-policy capability is not verified. Nothing has been staged.'))
            self.persistence_policy_plan_status.setText(tr(f'{capability} — persistence-policy staging blocked fail-closed.'))
            return
        operation = str(self.persistence_policy_operation.currentData() or 'preserve')
        if operation == 'preserve':
            QMessageBox.information(self, tr('Persistence policy'), tr('No persistence-policy change is selected. Existing policy remains preserved.'))
            return
        if operation not in {'require_volatile_kiosk_runtime', 'require_controlled_kiosk_persistence'}:
            QMessageBox.warning(self, tr('Persistence policy blocked'), tr('BLOCKED — unsupported persistence-policy operation.'))
            return
        username = self.persistence_policy_username.text().strip().casefold()
        if not re.fullmatch('[a-z_][a-z0-9_-]{0,31}', username):
            QMessageBox.warning(self, tr('Persistence policy blocked'), tr('BLOCKED — enter a safe Linux kiosk username.'))
            return
        kiosk = dict(self._analysis.get('system_kiosk_user_evidence') or {})
        admin_users = {str(x).casefold() for x in kiosk.get('admin_users') or []}
        if username == 'root' or username in admin_users:
            QMessageBox.warning(self, tr('Persistence policy blocked'), tr('BLOCKED — persistence policy cannot target root or a verified administrative user.'))
            return
        existing = {str(x).casefold() for x in kiosk.get('existing_regular_users') or []}
        account_dependency = 'verified_existing_target_user' if username in existing else 'alpha55_dedicated_non_admin_kiosk_user'
        directories: list[str] = []
        if operation == 'require_controlled_kiosk_persistence':
            try:
                directories = self._parse_kiosk_persistence_directories(username, self.persistence_policy_directories.text())
            except ValueError as exc:
                QMessageBox.warning(self, tr('Persistence policy blocked'), tr(f'BLOCKED — {exc}'))
                return
        elif self.persistence_policy_directories.text().strip():
            QMessageBox.warning(self, tr('Persistence policy blocked'), tr('BLOCKED — volatile policy must not include persistent directories.'))
            return
        part3_dependency = 'controlled_persistence' if operation == 'require_controlled_kiosk_persistence' else 'immutable_runtime'
        payload = {'config_type': 'persistence_policy', 'gate_version': 'alpha61', 'source_sha256': sha, 'analysis_scope': 'target_iso_metadata', 'capability_status': capability, 'rootfs_persistence_policy_verified': True, 'operation': operation, 'username': username, 'account_dependency': account_dependency, 'existing_regular_users': sorted(existing), 'admin_users': sorted(admin_users), 'policy_scope': 'kiosk_session_runtime_only', 'persistence_policy': 'selected_directories' if directories else 'volatile', 'persistent_directories': directories, 'runtime_changes_survive_reboot': False, 'selected_directories_survive_reboot': bool(directories), 'unlisted_runtime_changes_survive_reboot': False, 'part3_dependency': part3_dependency, 'rootfs_layers': list(evidence.get('rootfs_layers') or []), 'boot_config_files': list(evidence.get('boot_config_files') or []), 'initramfs_mechanism': str(evidence.get('initramfs_mechanism') or ''), 'existing_persistence_policy_read': False, 'persistent_data_contents_read': False, 'mount_configuration_contents_read': False, 'host_storage_accessed': False, 'host_mount_state_accessed': False, 'require_part3_dependency_before_apply': True, 'require_part3_dependency_reverification_before_apply': True, 'require_account_dependency_reverification_before_apply': True, 'preserve_existing_persistence_configuration': True, 'preserve_unselected_user_data': True, 'do_not_stage_mount_or_volume_changes': True, 'source_read_only': True, 'preserve_unrelated': True, 'stage_only': True}
        detail = f"Set kiosk persistence policy for '{username}' to {payload['persistence_policy']}; delegate runtime mechanics to Part 3 {part3_dependency}, preserve existing persistence/data, and re-verify dependencies before apply."
        change = ChangeItem('Persistence policy plan', ChangeKind.CONFIG, detail, payload)
        self.stage_requested.emit(change)
        self.persistence_policy_plan_status.setText(tr('Staged — review/Test/Undo in Changes.'))
        QMessageBox.information(self, tr('STAGED: Persistence policy plan'), tr('Persistence policy is source-hash locked, target-metadata bound, Part-3 delegated and staging-only; no mount, volume, initramfs or persistent-data changes were made.'))

    def _stage_admin_recovery_policy_plan(self) -> None:
        sha = str(self._analysis.get('sha256') or '').strip().casefold()
        evidence = dict(self._analysis.get('system_admin_recovery_policy_evidence') or {})
        if not re.fullmatch('[0-9a-f]{64}', sha):
            QMessageBox.information(self, tr('Administrator/recovery policy blocked'), tr('BLOCKED — analyze a source ISO before staging administrator/recovery policy.'))
            return
        capability = str(evidence.get('capability_status') or 'UNKNOWN')
        if evidence.get('verified') is not True or capability not in {'SUPPORTED', 'SUPPORTED_WITH_REQUIREMENTS'}:
            QMessageBox.information(self, tr('Administrator/recovery policy blocked'), tr(f'{capability} — target administrator/recovery capability is not verified. Nothing has been staged.'))
            self.admin_recovery_plan_status.setText(tr(f'{capability} — administrator/recovery staging blocked fail-closed.'))
            return
        operation = str(self.admin_recovery_operation.currentData() or 'preserve')
        if operation == 'preserve':
            QMessageBox.information(self, tr('Administrator/recovery policy'), tr('No administrator/recovery policy change is selected. Existing policy remains preserved.'))
            return
        if operation != 'require_dedicated_recovery_administrator':
            QMessageBox.warning(self, tr('Administrator/recovery policy blocked'), tr('BLOCKED — unsupported administrator/recovery operation.'))
            return
        username = self.admin_recovery_username.text().strip().casefold()
        if not re.fullmatch('[a-z_][a-z0-9_-]{0,31}', username) or username == 'root':
            QMessageBox.warning(self, tr('Administrator/recovery policy blocked'), tr('BLOCKED — enter a safe non-root Linux recovery-administrator username.'))
            return
        admin_groups = [str(x) for x in evidence.get('admin_groups') or []]
        admin_group = str(self.admin_recovery_admin_group.currentData() or '')
        if admin_group not in admin_groups or admin_group not in {'sudo', 'wheel'}:
            QMessageBox.warning(self, tr('Administrator/recovery policy blocked'), tr('BLOCKED — select a verified target administrator group.'))
            return
        autologin_user = str(evidence.get('autologin_user') or '').strip().casefold()
        if autologin_user and username == autologin_user:
            QMessageBox.warning(self, tr('Administrator/recovery policy blocked'), tr('BLOCKED — the explicit autologin account cannot also be the recovery administrator.'))
            return
        existing = {str(x).casefold() for x in evidence.get('existing_regular_users') or []}
        admins = {str(x).casefold() for x in evidence.get('existing_admin_users') or []}
        if username in existing and username not in admins:
            QMessageBox.warning(self, tr('Administrator/recovery policy blocked'), tr('BLOCKED — an existing non-admin user cannot be silently promoted by the recovery-policy gate; use the verified account gate first.'))
            return
        account_dependency = 'verified_existing_admin_user' if username in admins else 'alpha50_create_administrator'
        payload = {'config_type': 'administrator_recovery_policy', 'gate_version': 'alpha62', 'source_sha256': sha, 'analysis_scope': 'target_iso_rootfs', 'capability_status': capability, 'rootfs_admin_recovery_verified': True, 'operation': operation, 'policy_scope': 'separate_non_autologin_recovery_administrator', 'username': username, 'admin_group': admin_group, 'account_dependency': account_dependency, 'existing_regular_users': sorted(existing), 'existing_admin_users': sorted(admins), 'verified_admin_groups': admin_groups, 'current_autologin_user': autologin_user, 'recovery_account_must_be_distinct_from_kiosk': True, 'recovery_account_must_not_autologin': True, 'allow_root_as_recovery_administrator': False, 'credential_policy': 'deferred_secure_verified_apply', 'authentication_factor_policy': 'deferred_to_fido2_webauthn_security_key_tpm_gates', 'shadow_read': False, 'credential_secret_read': False, 'credential_secret_staged': False, 'recovery_secret_read': False, 'recovery_secret_staged': False, 'pam_contents_read': False, 'ssh_config_read': False, 'rescue_boot_config_read': False, 'root_account_policy_read': False, 'host_accounts_touched': False, 'host_login_state_accessed': False, 'preserve_existing_administrators': True, 'preserve_root_account_policy': True, 'preserve_rescue_boot_configuration': True, 'preserve_pam_configuration': True, 'preserve_ssh_configuration': True, 'do_not_stage_authenticator_changes': True, 'require_admin_membership_reverification_before_apply': True, 'require_autologin_reverification_before_apply': True, 'require_recovery_kiosk_separation_reverification_before_apply': True, 'require_account_dependency_before_apply': True, 'require_account_dependency_reverification_before_apply': True, 'source_read_only': True, 'preserve_unrelated': True, 'stage_only': True}
        detail = f"Require recovery administrator '{username}' via {account_dependency} and verified admin group '{admin_group}'; keep it separate from root/kiosk/autologin roles, preserve existing recovery/login policy, and defer credentials/authenticators to verified later gates."
        change = ChangeItem('Administrator/recovery policy plan', ChangeKind.CONFIG, detail, payload)
        self.stage_requested.emit(change)
        self.admin_recovery_plan_status.setText(tr('Staged — review/Test/Undo in Changes.'))
        QMessageBox.information(self, tr('STAGED: Administrator/recovery policy'), tr('Administrator/recovery policy is source-hash locked, target-account/autologin-evidence bound, recovery-role separated, secret-free and staging-only.'))

    def _stage_fido2_policy_plan(self) -> None:
        sha = str(self._analysis.get('sha256') or '').strip().casefold()
        evidence = dict(self._analysis.get('system_fido2_policy_evidence') or {})
        admin_recovery = dict(self._analysis.get('system_admin_recovery_policy_evidence') or {})
        if not re.fullmatch('[0-9a-f]{64}', sha):
            QMessageBox.information(self, tr('FIDO2 policy blocked'), tr('BLOCKED — analyze a source ISO before staging FIDO2 policy.'))
            return
        capability = str(evidence.get('capability_status') or 'UNKNOWN')
        if evidence.get('verified') is not True or capability not in {'SUPPORTED', 'SUPPORTED_WITH_REQUIREMENTS'}:
            QMessageBox.information(self, tr('FIDO2 policy blocked'), tr(f'{capability} — target FIDO2 policy capability is not verified. Nothing has been staged.'))
            self.fido2_plan_status.setText(tr(f'{capability} — FIDO2 staging blocked fail-closed.'))
            return
        operation = str(self.fido2_operation.currentData() or 'preserve')
        if operation == 'preserve':
            QMessageBox.information(self, tr('FIDO2 policy'), tr('No FIDO2 policy change is selected. Existing authentication policy remains preserved.'))
            return
        if operation != 'require_fido2_second_factor_for_recovery_admin':
            QMessageBox.warning(self, tr('FIDO2 policy blocked'), tr('BLOCKED — unsupported FIDO2 operation.'))
            return
        username = self.fido2_username.text().strip().casefold()
        if not re.fullmatch('[a-z_][a-z0-9_-]{0,31}', username) or username == 'root':
            QMessageBox.warning(self, tr('FIDO2 policy blocked'), tr('BLOCKED — enter the safe non-root recovery-administrator username from the Alpha 62 policy.'))
            return
        autologin_user = str(admin_recovery.get('autologin_user') or '').strip().casefold()
        if autologin_user and username == autologin_user:
            QMessageBox.warning(self, tr('FIDO2 policy blocked'), tr('BLOCKED — the explicit autologin user cannot be used as the FIDO2 recovery administrator.'))
            return
        pam_packages = [str(x) for x in evidence.get('pam_fido2_packages') or [] if str(x).strip()]
        lib_packages = [str(x) for x in evidence.get('libfido2_packages') or [] if str(x).strip()]
        if not pam_packages or not lib_packages or evidence.get('alpha62_dependency_verified') is not True:
            QMessageBox.warning(self, tr('FIDO2 policy blocked'), tr('BLOCKED — required target PAM-FIDO2/libfido2 evidence or Alpha 62 dependency is missing.'))
            return
        payload = {'config_type': 'fido2_policy', 'gate_version': 'alpha63', 'source_sha256': sha, 'analysis_scope': 'target_iso_package_manifest', 'capability_status': capability, 'fido2_policy_verified': True, 'operation': operation, 'policy_scope': 'recovery_administrator_fido2_second_factor', 'username': username, 'current_autologin_user': autologin_user, 'administrator_recovery_dependency': 'alpha62_administrator_recovery_policy', 'alpha62_dependency_verified': True, 'pam_fido2_packages': pam_packages, 'libfido2_packages': lib_packages, 'fido2_tool_packages': [str(x) for x in evidence.get('fido2_tool_packages') or []], 'authentication_composition': 'existing_primary_plus_fido2_second_factor', 'pam_contents_read': False, 'pam_contents_modified_during_analysis': False, 'authenticator_devices_enumerated': False, 'usb_hid_state_accessed': False, 'credential_ids_read': False, 'credential_secret_read': False, 'credential_secret_staged': False, 'authenticator_enrollment_performed': False, 'webauthn_capability_claimed': False, 'security_key_presence_claimed': False, 'yubikey_capability_claimed': False, 'platform_authenticator_claimed': False, 'tpm_capability_claimed': False, 'host_authenticator_state_accessed': False, 'preserve_existing_primary_authentication': True, 'preserve_pam_contents_during_analysis_and_staging': True, 'require_pam_integration_verification_before_apply': True, 'require_alpha62_dependency_before_apply': True, 'require_alpha62_dependency_reverification_before_apply': True, 'require_target_package_reverification_before_apply': True, 'require_recovery_username_reverification_before_apply': True, 'source_read_only': True, 'preserve_unrelated': True, 'stage_only': True}
        detail = f"Require FIDO2 as an additional second factor for recovery administrator '{username}' after Alpha 62; preserve existing primary authentication and defer PAM integration/device enrollment to verified apply/later gates."
        change = ChangeItem('FIDO2 policy plan', ChangeKind.CONFIG, detail, payload)
        self.stage_requested.emit(change)
        self.fido2_plan_status.setText(tr('Staged — review/Test/Undo in Changes.'))
        QMessageBox.information(self, tr('STAGED: FIDO2 policy'), tr('FIDO2 policy is source-hash locked, target package-evidence bound, Alpha 62 recovery-role dependent, authenticator/credential isolated and staging-only.'))

    def _stage_webauthn_policy_plan(self) -> None:
        sha = str(self._analysis.get('sha256') or '').strip().casefold()
        evidence = dict(self._analysis.get('system_webauthn_policy_evidence') or {})
        admin_recovery = dict(self._analysis.get('system_admin_recovery_policy_evidence') or {})
        if not re.fullmatch('[0-9a-f]{64}', sha):
            QMessageBox.information(self, tr('WebAuthn policy blocked'), tr('BLOCKED — analyze a source ISO before staging WebAuthn policy.'))
            return
        capability = str(evidence.get('capability_status') or 'UNKNOWN')
        if evidence.get('verified') is not True or capability not in {'SUPPORTED', 'SUPPORTED_WITH_REQUIREMENTS'}:
            QMessageBox.information(self, tr('WebAuthn policy blocked'), tr(f'{capability} — target WebAuthn policy capability is not verified. Nothing has been staged.'))
            self.webauthn_plan_status.setText(tr(f'{capability} — WebAuthn staging blocked fail-closed.'))
            return
        operation = str(self.webauthn_operation.currentData() or 'preserve')
        if operation == 'preserve':
            QMessageBox.information(self, tr('WebAuthn policy'), tr('No WebAuthn policy change is selected. Existing browser authentication policy remains preserved.'))
            return
        if operation != 'allow_webauthn_for_recovery_web_workflows':
            QMessageBox.warning(self, tr('WebAuthn policy blocked'), tr('BLOCKED — unsupported WebAuthn operation.'))
            return
        username = self.webauthn_username.text().strip().casefold()
        if not re.fullmatch('[a-z_][a-z0-9_-]{0,31}', username) or username == 'root':
            QMessageBox.warning(self, tr('WebAuthn policy blocked'), tr('BLOCKED — enter the safe non-root recovery-administrator username from the Alpha 62 policy.'))
            return
        autologin_user = str(admin_recovery.get('autologin_user') or '').strip().casefold()
        if autologin_user and username == autologin_user:
            QMessageBox.warning(self, tr('WebAuthn policy blocked'), tr('BLOCKED — the explicit autologin user cannot be used as the WebAuthn recovery administrator.'))
            return
        browser_packages = [str(x) for x in evidence.get('browser_packages') or [] if str(x).strip()]
        browser_package = str(self.webauthn_browser.currentData() or '').strip()
        if not browser_package or browser_package not in browser_packages or evidence.get('alpha62_dependency_verified') is not True:
            QMessageBox.warning(self, tr('WebAuthn policy blocked'), tr('BLOCKED — required target browser-package evidence or Alpha 62 dependency is missing.'))
            return
        payload = {'config_type': 'webauthn_policy', 'gate_version': 'alpha64', 'source_sha256': sha, 'analysis_scope': 'target_iso_package_manifest', 'capability_status': capability, 'webauthn_policy_verified': True, 'operation': operation, 'policy_scope': 'recovery_administrator_browser_webauthn', 'username': username, 'current_autologin_user': autologin_user, 'administrator_recovery_dependency': 'alpha62_administrator_recovery_policy', 'alpha62_dependency_verified': True, 'alpha63_evidence_observed': evidence.get('alpha63_evidence_observed') is True, 'browser_package': browser_package, 'browser_packages': browser_packages, 'libfido2_packages': [str(x) for x in evidence.get('libfido2_packages') or []], 'browser_config_contents_read': False, 'webauthn_runtime_verified': False, 'relying_party_config_read': False, 'relying_party_verified': False, 'origin_config_read': False, 'origin_verified': False, 'authenticator_devices_enumerated': False, 'usb_hid_state_accessed': False, 'credential_ids_read': False, 'credential_secret_read': False, 'credential_secret_staged': False, 'authenticator_enrollment_performed': False, 'security_key_presence_claimed': False, 'yubikey_capability_claimed': False, 'platform_authenticator_claimed': False, 'tpm_capability_claimed': False, 'host_browser_state_accessed': False, 'host_authenticator_state_accessed': False, 'preserve_existing_primary_authentication': True, 'preserve_browser_configuration_during_analysis_and_staging': True, 'require_browser_runtime_verification_before_apply': True, 'require_relying_party_and_origin_verification_before_use': True, 'require_alpha62_dependency_before_apply': True, 'require_alpha62_dependency_reverification_before_apply': True, 'require_target_package_reverification_before_apply': True, 'require_recovery_username_reverification_before_apply': True, 'source_read_only': True, 'preserve_unrelated': True, 'stage_only': True}
        detail = f"Allow browser-mediated WebAuthn recovery workflows for administrator '{username}' using verified target browser package '{browser_package}'; preserve existing authentication and defer runtime/RP/origin/authenticator verification to verified apply/use."
        change = ChangeItem('WebAuthn policy plan', ChangeKind.CONFIG, detail, payload)
        self.stage_requested.emit(change)
        self.webauthn_plan_status.setText(tr('Staged — review/Test/Undo in Changes.'))
        QMessageBox.information(self, tr('STAGED: WebAuthn policy'), tr('WebAuthn policy is source-hash locked, target browser-package evidence bound, Alpha 62 recovery-role dependent, runtime/RP/origin/authenticator claims deferred and staging-only.'))

    @staticmethod
    def _safe_recovery_username(username: str, admin_recovery: dict) -> tuple[bool, str]:
        value = str(username or '').strip().casefold()
        if not re.fullmatch('[a-z_][a-z0-9_-]{0,31}', value) or value == 'root':
            return (False, value)
        autologin_user = str(admin_recovery.get('autologin_user') or '').strip().casefold()
        if autologin_user and value == autologin_user:
            return (False, value)
        return (True, value)

    def _stage_security_key_policy_plan(self) -> None:
        sha = str(self._analysis.get('sha256') or '').strip().casefold()
        evidence = dict(self._analysis.get('system_security_key_policy_evidence') or {})
        admin = dict(self._analysis.get('system_admin_recovery_policy_evidence') or {})
        capability = str(evidence.get('capability_status') or 'UNKNOWN')
        if not re.fullmatch('[0-9a-f]{64}', sha) or evidence.get('verified') is not True or capability not in {'SUPPORTED', 'SUPPORTED_WITH_REQUIREMENTS'}:
            self.security_key_plan_status.setText(tr(f'{capability} — security-key staging blocked fail-closed.'))
            QMessageBox.information(self, tr('Security-key policy blocked'), tr(f'{capability} — verified target security-key capability is required. Nothing has been staged.'))
            return
        operation = str(self.security_key_operation.currentData() or 'preserve')
        if operation == 'preserve':
            return
        ok, username = self._safe_recovery_username(self.security_key_username.text(), admin)
        if not ok:
            QMessageBox.warning(self, tr('Security-key policy blocked'), tr('BLOCKED — enter a safe non-root, non-autologin recovery administrator username.'))
            return
        tools = [str(x) for x in evidence.get('security_key_tool_packages') or []]
        libs = [str(x) for x in evidence.get('libfido2_packages') or []]
        payload = {'config_type': 'security_key_policy', 'gate_version': 'alpha65', 'source_sha256': sha, 'analysis_scope': 'target_iso_package_manifest', 'capability_status': capability, 'security_key_policy_verified': True, 'operation': operation, 'policy_scope': 'recovery_administrator_external_security_key', 'username': username, 'current_autologin_user': str(admin.get('autologin_user') or '').strip().casefold(), 'administrator_recovery_dependency': 'alpha62_administrator_recovery_policy', 'fido2_dependency': 'alpha63_fido2_policy', 'alpha62_dependency_verified': True, 'alpha63_dependency_verified': evidence.get('alpha63_dependency_verified') is True, 'security_key_tool_packages': tools, 'libfido2_packages': libs, 'physical_security_key_enumerated': False, 'security_key_presence_claimed': False, 'security_key_compatibility_claimed': False, 'credential_ids_read': False, 'credential_secret_read': False, 'credential_secret_staged': False, 'authenticator_enrollment_performed': False, 'usb_hid_state_accessed': False, 'yubikey_capability_claimed': False, 'platform_authenticator_claimed': False, 'tpm_capability_claimed': False, 'host_authenticator_state_accessed': False, 'preserve_existing_primary_authentication': True, 'require_physical_key_verification_before_apply': True, 'require_key_compatibility_verification_before_apply': True, 'require_explicit_enrollment_before_use': True, 'require_recovery_username_reverification_before_apply': True, 'require_target_package_reverification_before_apply': True, 'source_read_only': True, 'preserve_unrelated': True, 'stage_only': True}
        self.stage_requested.emit(ChangeItem('Security-key policy plan', ChangeKind.CONFIG, f"Allow a verified external FIDO2 security key for recovery administrator '{username}' after apply-time device verification/enrollment.", payload))
        self.security_key_plan_status.setText(tr('Staged — review/Test/Undo in Changes.'))

    def _stage_yubikey_policy_plan(self) -> None:
        sha = str(self._analysis.get('sha256') or '').strip().casefold()
        evidence = dict(self._analysis.get('system_yubikey_policy_evidence') or {})
        admin = dict(self._analysis.get('system_admin_recovery_policy_evidence') or {})
        capability = str(evidence.get('capability_status') or 'UNKNOWN')
        if not re.fullmatch('[0-9a-f]{64}', sha) or evidence.get('verified') is not True or capability not in {'SUPPORTED', 'SUPPORTED_WITH_REQUIREMENTS'}:
            self.yubikey_plan_status.setText(tr(f'{capability} — YubiKey-class staging blocked fail-closed.'))
            QMessageBox.information(self, tr('YubiKey-class policy blocked'), tr(f'{capability} — verified target YubiKey-class package evidence is required. Nothing has been staged.'))
            return
        operation = str(self.yubikey_operation.currentData() or 'preserve')
        if operation == 'preserve':
            return
        ok, username = self._safe_recovery_username(self.yubikey_username.text(), admin)
        if not ok:
            QMessageBox.warning(self, tr('YubiKey-class policy blocked'), tr('BLOCKED — enter a safe non-root, non-autologin recovery administrator username.'))
            return
        packages = [str(x) for x in evidence.get('yubikey_packages') or []]
        payload = {'config_type': 'yubikey_policy', 'gate_version': 'alpha66', 'source_sha256': sha, 'analysis_scope': 'target_iso_package_manifest', 'capability_status': capability, 'yubikey_policy_verified': True, 'operation': operation, 'policy_scope': 'recovery_administrator_yubikey_class', 'username': username, 'current_autologin_user': str(admin.get('autologin_user') or '').strip().casefold(), 'administrator_recovery_dependency': 'alpha62_administrator_recovery_policy', 'alpha62_dependency_verified': True, 'alpha65_evidence_observed': evidence.get('alpha65_evidence_observed') is True, 'yubikey_packages': packages, 'physical_yubikey_enumerated': False, 'yubikey_presence_claimed': False, 'serial_number_read': False, 'otp_secret_read': False, 'pin_secret_read': False, 'credential_ids_read': False, 'credential_secret_read': False, 'credential_secret_staged': False, 'authenticator_enrollment_performed': False, 'usb_hid_state_accessed': False, 'platform_authenticator_claimed': False, 'tpm_capability_claimed': False, 'host_authenticator_state_accessed': False, 'preserve_existing_primary_authentication': True, 'require_physical_yubikey_verification_before_apply': True, 'require_vendor_mode_compatibility_verification_before_apply': True, 'require_explicit_enrollment_before_use': True, 'require_recovery_username_reverification_before_apply': True, 'require_target_package_reverification_before_apply': True, 'source_read_only': True, 'preserve_unrelated': True, 'stage_only': True}
        self.stage_requested.emit(ChangeItem('YubiKey-class policy plan', ChangeKind.CONFIG, f"Allow a verified YubiKey-class authenticator for recovery administrator '{username}' after apply-time device/mode verification and enrollment.", payload))
        self.yubikey_plan_status.setText(tr('Staged — review/Test/Undo in Changes.'))

    def _stage_platform_authenticator_policy_plan(self) -> None:
        sha = str(self._analysis.get('sha256') or '').strip().casefold()
        evidence = dict(self._analysis.get('system_platform_authenticator_policy_evidence') or {})
        admin = dict(self._analysis.get('system_admin_recovery_policy_evidence') or {})
        capability = str(evidence.get('capability_status') or 'UNKNOWN')
        if not re.fullmatch('[0-9a-f]{64}', sha) or evidence.get('verified') is not True or capability not in {'SUPPORTED', 'SUPPORTED_WITH_REQUIREMENTS'}:
            self.platform_auth_plan_status.setText(tr(f'{capability} — platform-authenticator staging blocked fail-closed.'))
            QMessageBox.information(self, tr('Platform authenticator blocked'), tr(f'{capability} — static ISO evidence does not verify runtime platform-authenticator hardware/integration. Nothing has been staged.'))
            return
        operation = str(self.platform_auth_operation.currentData() or 'preserve')
        if operation == 'preserve':
            return
        ok, username = self._safe_recovery_username(self.platform_auth_username.text(), admin)
        if not ok:
            QMessageBox.warning(self, tr('Platform authenticator blocked'), tr('BLOCKED — enter a safe recovery administrator username.'))
            return
        payload = {'config_type': 'platform_authenticator_policy', 'gate_version': 'alpha67', 'source_sha256': sha, 'analysis_scope': 'verified_target_runtime_and_hardware', 'capability_status': capability, 'platform_authenticator_policy_verified': True, 'operation': operation, 'policy_scope': 'recovery_administrator_platform_authenticator', 'username': username, 'current_autologin_user': str(admin.get('autologin_user') or '').strip().casefold(), 'administrator_recovery_dependency': 'alpha62_administrator_recovery_policy', 'alpha62_dependency_verified': True, 'alpha64_dependency_verified': True, 'platform_authenticator_runtime_verified': True, 'platform_authenticator_hardware_verified': True, 'biometric_capability_claimed': False, 'tpm_capability_claimed': False, 'credential_ids_read': False, 'credential_secret_read': False, 'credential_secret_staged': False, 'authenticator_enrollment_performed': False, 'host_authenticator_state_accessed': False, 'preserve_existing_primary_authentication': True, 'require_runtime_reverification_before_apply': True, 'require_hardware_reverification_before_apply': True, 'require_explicit_enrollment_before_use': True, 'source_read_only': True, 'preserve_unrelated': True, 'stage_only': True}
        self.stage_requested.emit(ChangeItem('Platform-authenticator policy plan', ChangeKind.CONFIG, f"Allow a separately runtime/hardware-verified platform authenticator for recovery administrator '{username}'.", payload))
        self.platform_auth_plan_status.setText(tr('Staged — review/Test/Undo in Changes.'))

    def _stage_tpm_key_protection_plan(self) -> None:
        sha = str(self._analysis.get('sha256') or '').strip().casefold()
        evidence = dict(self._analysis.get('system_tpm_key_protection_evidence') or {})
        admin = dict(self._analysis.get('system_admin_recovery_policy_evidence') or {})
        capability = str(evidence.get('capability_status') or 'UNKNOWN')
        if not re.fullmatch('[0-9a-f]{64}', sha) or evidence.get('verified') is not True or capability not in {'SUPPORTED', 'SUPPORTED_WITH_REQUIREMENTS'}:
            self.tpm_plan_status.setText(tr(f'{capability} — TPM key-protection staging blocked fail-closed.'))
            QMessageBox.information(self, tr('TPM key protection blocked'), tr(f'{capability} — verified target TPM2/TSS2 package support is required. Nothing has been staged.'))
            return
        operation = str(self.tpm_operation.currentData() or 'preserve')
        if operation == 'preserve':
            return
        ok, username = self._safe_recovery_username(self.tpm_username.text(), admin)
        if not ok:
            QMessageBox.warning(self, tr('TPM key protection blocked'), tr('BLOCKED — enter a safe non-root, non-autologin recovery administrator username.'))
            return
        payload = {'config_type': 'tpm_key_protection', 'gate_version': 'alpha68', 'source_sha256': sha, 'analysis_scope': 'target_iso_package_manifest', 'capability_status': capability, 'tpm_key_protection_verified': True, 'operation': operation, 'policy_scope': 'recovery_administrator_tpm_backed_key_protection', 'username': username, 'current_autologin_user': str(admin.get('autologin_user') or '').strip().casefold(), 'administrator_recovery_dependency': 'alpha62_administrator_recovery_policy', 'alpha62_dependency_verified': True, 'tpm_tool_packages': [str(x) for x in evidence.get('tpm_tool_packages') or []], 'tss_packages': [str(x) for x in evidence.get('tss_packages') or []], 'tpm_hardware_enumerated': False, 'tpm_hardware_verified': False, 'tpm_presence_claimed': False, 'tpm_ownership_state_read': False, 'pcr_values_read': False, 'key_material_generated': False, 'key_material_read': False, 'key_material_staged': False, 'key_material_sealed': False, 'credential_secret_read': False, 'credential_secret_staged': False, 'biometric_capability_claimed': False, 'platform_authenticator_claimed': False, 'host_tpm_state_accessed': False, 'preserve_existing_primary_authentication': True, 'require_tpm_hardware_verification_before_apply': True, 'require_tpm_ownership_verification_before_apply': True, 'require_pcr_policy_review_before_sealing': True, 'require_key_generation_and_sealing_only_at_verified_apply': True, 'require_recovery_username_reverification_before_apply': True, 'require_target_package_reverification_before_apply': True, 'source_read_only': True, 'preserve_unrelated': True, 'stage_only': True}
        self.stage_requested.emit(ChangeItem('TPM-backed key-protection plan', ChangeKind.CONFIG, f"Require TPM-backed protection for future recovery key material for administrator '{username}', with hardware/ownership/PCR/key operations deferred to verified apply.", payload))
        self.tpm_plan_status.setText(tr('Staged — review/Test/Undo in Changes.'))

    def _stage_targets_plan(self) -> None:
        sha = str(self._analysis.get('sha256') or '').strip().casefold()
        evidence = dict(self._analysis.get('system_targets_evidence') or {})
        if not re.fullmatch('[0-9a-f]{64}', sha):
            QMessageBox.information(self, tr('Targets/startup plan blocked'), tr('BLOCKED — analyze a source ISO before staging default-target changes.'))
            return
        if evidence.get('verified') is not True:
            QMessageBox.information(self, tr('Targets/startup plan blocked'), tr('BLOCKED — supported systemd target staging evidence has not been verified read-only inside the selected rootfs. Nothing has been staged.'))
            self.targets_plan_status.setText(tr('Blocked — rootfs targets/systemd evidence is not verified.'))
            return
        operation = str(self.targets_operation.currentData() or '')
        if operation != 'set_default_target':
            QMessageBox.information(self, tr('Targets/startup plan'), tr('No default startup-target change is selected. Existing target policy remains preserved.'))
            return
        unit = self.targets_target.text().strip()
        if not re.fullmatch('[A-Za-z0-9_.@:-]{1,120}\\.target', unit) or '/' in unit:
            QMessageBox.warning(self, tr('Targets/startup plan blocked'), tr('Target must be a safe systemd .target unit name, for example graphical.target.'))
            return
        payload = {'config_type': 'system_targets', 'source_sha256': sha, 'operation': operation, 'target_unit': unit, 'init_system': str(evidence.get('init_system') or ''), 'vendor_unit_path': str(evidence.get('vendor_unit_path') or ''), 'vendor_unit_layer': str(evidence.get('vendor_unit_layer') or ''), 'local_unit_path': str(evidence.get('local_unit_path') or ''), 'local_unit_layer': str(evidence.get('local_unit_layer') or ''), 'rootfs_targets_verified': True, 'require_target_unit_verification_before_apply': True, 'preserve_services_timers': True, 'preserve_unit_file_contents': True, 'target_contents_read': False, 'default_target_symlink_read': False, 'service_secrets_read': False, 'secret_read': False, 'secret_staged': False, 'source_read_only': True, 'preserve_unrelated': True, 'stage_only': True}
        detail = f"Set target-system default startup target to '{unit}'; preserve services, timers, unit contents and unrelated startup policy; target unit must be re-verified before apply."
        change = ChangeItem('Targets / startup plan', ChangeKind.CONFIG, detail, payload)
        self.stage_requested.emit(change)
        self.targets_plan_status.setText(tr('Staged — review/Test in Changes.'))
        QMessageBox.information(self, tr('STAGED: Targets / startup plan'), tr('Default-target intent is source-hash locked and staging-only. Target contents, service credentials and source-ISO bytes remain untouched.'))
