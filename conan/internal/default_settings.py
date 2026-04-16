import os
import sys


def _load_settings_yml():
    if getattr(sys, 'frozen', False):
        # PyInstaller frozen executable: data files are extracted to sys._MEIPASS
        path = os.path.join(sys._MEIPASS, "conan", "internal", "settings.yml")
    else:
        path = os.path.join(os.path.dirname(__file__), "settings.yml")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


default_settings_yml = _load_settings_yml()


def migrate_settings_file(cache_folder):
    from conan.internal.api.migrations import update_file

    settings_path = os.path.join(cache_folder, "settings.yml")
    update_file(settings_path, default_settings_yml)
