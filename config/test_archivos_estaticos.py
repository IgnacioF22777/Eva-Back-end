"""Permisos de archivos: evidencias privadas y estáticos públicos (CP-EST-001 a 003)."""

from django.conf import settings
from django.core.files.storage import default_storage, storages
from django.test import SimpleTestCase


class PruebasPermisosArchivos(SimpleTestCase):

    def test_CP_EST_001_estaticos_legibles_por_nginx(self):
        """CP-EST-001: collectstatic deja CSS e imágenes en 644/755 (si no, Nginx da 403)."""
        estaticos = storages["staticfiles"]
        self.assertEqual(estaticos.file_permissions_mode, 0o644)
        self.assertEqual(estaticos.directory_permissions_mode, 0o755)

    def test_CP_EST_002_evidencias_siguen_privadas(self):
        """CP-EST-002 (seguridad): las evidencias subidas siguen en 640/750."""
        self.assertEqual(settings.FILE_UPLOAD_PERMISSIONS, 0o640)
        self.assertEqual(default_storage.file_permissions_mode, 0o640)
        self.assertEqual(default_storage.directory_permissions_mode, 0o750)


class PruebasVersionEstaticos(SimpleTestCase):

    def test_CP_EST_003_css_con_version(self):
        """CP-EST-003: el enlace a custom.css lleva ?v= para no usar un CSS antiguo en caché."""
        from django.template.loader import render_to_string
        from django.test import RequestFactory
        from django.contrib.auth.models import AnonymousUser

        request = RequestFactory().get("/")
        request.user = AnonymousUser()
        html = render_to_string("base.html", request=request)
        self.assertRegex(html, r"css/custom\.css\?v=\d+")
