import json
import unittest
from types import SimpleNamespace
from google_errors import http_message, api_action


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

    def test_bad_request_shows_google_reason(self):
        text=http_message(failure(status=400,message='Invalid mime type provided'))
        self.assertIn('Invalid mime type provided',text)
        self.assertIn('jenis file',text)
        text=http_message(failure(status=400,message='Unable to parse range: NOV!G12'))
        self.assertIn('Unable to parse range',text)
        self.assertIn('alamat sel',text)

    def test_bad_request_never_echoes_credentials(self):
        for secret in ['access_token=DO-NOT-PRINT','Bearer DO-NOT-PRINT','token: DO-NOT-PRINT','ya29.DO-NOT-PRINT','client_secret=DO-NOT-PRINT']:
            self.assertNotIn('DO-NOT-PRINT',http_message(failure(status=400,message=secret)))
        self.assertNotIn('DO-NOT-PRINT',http_message(failure(status=400,message='Invalid https://example.com/upload?secret=DO-NOT-PRINT')))

    def test_operation_is_attached_without_replacing_error(self):
        from googleapiclient.errors import HttpError
        from httplib2 import Response
        error=HttpError(Response({'status':'400','reason':'Bad Request'}),b'{"error":{"message":"Invalid argument"}}')
        with self.assertRaises(HttpError) as result:
            with api_action('Mengunggah file: edited.jpg'):
                raise error
        self.assertIs(result.exception,error)
        self.assertEqual(error.upload_operation,'Mengunggah file: edited.jpg')

    def test_account_preflight_uses_drive_nested_field_selector(self):
        from unittest.mock import Mock
        import auto_upload
        drive=Mock()
        drive.about.return_value.get.return_value.execute.return_value={'user':{'permissionId':'account'}}
        self.assertEqual(auto_upload.account_key(drive),'account')
        drive.about.return_value.get.assert_called_once_with(fields='user(permissionId)')

    def test_preflight_failure_explains_no_upload_started(self):
        from unittest.mock import Mock
        from googleapiclient.errors import HttpError
        from httplib2 import Response
        import upload_flow
        drive,sheets=Mock(),Mock()
        error=HttpError(Response({'status':'400','reason':'Bad Request'}),b'{"error":{"message":"Invalid field selection user.permissionId"}}')
        drive.about.return_value.get.return_value.execute.side_effect=error
        with self.assertRaises(HttpError):
            upload_flow.execute((drive,sheets),{'jobs':[]})
        self.assertIn('identitas akun',error.upload_operation)
        drive.files.assert_not_called()
        sheets.spreadsheets.assert_not_called()


if __name__=='__main__':
    unittest.main()
