"""Permisos de archivos: evidencias privadas y estáticos públicos (CP-CFG-001 y 002)."""

from django.conf import settings
from django.core.files.storage import default_storage, storages
from django.test import SimpleTestCase


class PruebasPermisosArchivos(SimpleTestCase):

    def test_CP_CFG_001_estaticos_legibles_por_nginx(self):
        """CP-CFG-001: collectstatic deja CSS e imágenes en 644/755 (si no, Nginx da 403)."""
        estaticos = storages["staticfiles"]
        self.assertEqual(estaticos.file_permissions_mode, 0o644)
        self.assertEqual(estaticos.directory_permissions_mode, 0o755)

    def test_CP_CFG_002_evidencias_siguen_privadas(self):
        """CP-CFG-002 (seguridad): las evidencias subidas siguen en 640/750."""
        self.assertEqual(settings.FILE_UPLOAD_PERMISSIONS, 0o640)
        self.assertEqual(default_storage.file_permissions_mode, 0o640)
        self.assertEqual(default_storage.directory_permissions_mode, 0o750)
