"""设置对话框行为：留空保留 Token、清除、主题与扫描目录保存。"""
from PySide6.QtWidgets import QListWidgetItem

from app.core.settings import SettingsStore, get_github_token, get_theme
from app.ui.dialogs.settings_dialog import SettingsDialog


def test_settings_save_and_keep_token(isolated_db, qapp):
    dlg = SettingsDialog()
    index = dlg.theme_box.findData("dark")
    dlg.theme_box.setCurrentIndex(index)
    dlg.token_edit.setText("ghp_ui_token")
    dlg.roots_list.addItem(QListWidgetItem("C:/demo"))
    dlg._save()
    assert get_theme() == "dark"
    assert get_github_token() == "ghp_ui_token"
    assert SettingsStore.get_scan_roots() == ["C:/demo"]

    # 再次打开：留空 + 保存 → Token 保持不变
    dlg2 = SettingsDialog()
    assert dlg2.token_edit.text() == ""
    assert "留空" in dlg2.token_edit.placeholderText()
    dlg2._save()
    assert get_github_token() == "ghp_ui_token"

    # 清除后保存 → Token 被移除
    dlg3 = SettingsDialog()
    dlg3._clear()
    dlg3._save()
    assert get_github_token() is None
