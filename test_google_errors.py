import json
import unittest
from types import SimpleNamespace
from google_errors import http_message


def failure(status=403,reason=None,service=None,message=''):
    details=[]
    if reason:
        details.append({'reason':reason,'metadata':{'service':service}})
    return SimpleNamespace(resp=SimpleNamespace(status=status),content=json.dumps({'error':{'message':message,'details':details}}).encode())


class ErrorTests(unittest.TestCase):
    def test_sheets_api_disabled_is_identified(self):
        text=http_message(failure(reason='SERVICE_DISABLED',service='sheets.googleapis.com'))
        self.assertIn('Google Sheets API belum aktif',text)
        self.assertIn('Tidak perlu membuat JSON baru',text)

    def test_older_disabled_response(self):
        error=failure(message='Google Drive API has not been used in project 123 before or it is disabled.')
        error.content=json.dumps({'error':{'message':'Google Drive API has not been used in project 123 before or it is disabled.','errors':[{'reason':'accessNotConfigured'}]}}).encode()
        self.assertIn('Google Drive API belum aktif',http_message(error))

    def test_missing_scope_requests_reconsent(self):
        self.assertIn('Klik Ganti akun',http_message(failure(reason='ACCESS_TOKEN_SCOPE_INSUFFICIENT')))

    def test_storage_and_quota_are_not_reported_as_login_failure(self):
        self.assertIn('penuh',http_message(failure(reason='storageQuotaExceeded')))
        self.assertIn('Batas pemakaian',http_message(failure(reason='userRateLimitExceeded')))
        self.assertIn('Batas pemakaian',http_message(failure(status=429)))

    def test_file_permission_and_organization(self):
        self.assertIn('akses edit',http_message(failure(reason='insufficientFilePermissions')))
        self.assertIn('admin',http_message(failure(reason='domainPolicy')))

    def test_unknown_error_does_not_echo_sensitive_content(self):
        text=http_message(failure(message='token=DO-NOT-PRINT bearer private value'))
        self.assertNotIn('DO-NOT-PRINT',text)
        self.assertIn('Penyebab khusus tidak tersedia',text)

    def test_malformed_response_and_session_expiry(self):
        error=failure();error.content=b'not JSON token=private'
        self.assertIn('HTTP 403',http_message(error))
        error.content=b'{"error":{"errors":null,"details":123}}'
        self.assertIn('HTTP 403',http_message(error))
        self.assertIn('Sesi Google',http_message(failure(status=401)))


if __name__=='__main__':
    unittest.main()
