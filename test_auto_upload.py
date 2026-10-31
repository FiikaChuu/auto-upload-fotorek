import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import auto_upload as app


class Tests(unittest.TestCase):
    def setUp(self):
        self.rows = [['Content plan'], ['No.', 'Reference', 'PIC', 'Link Drive'], ['11', '', 'afzal'], ['12', '', 'kayla'], ['13', '', 'afzal', 'existing']]
        self.header, self.cols = app.detect(self.rows)

    def test_number_pic_and_existing_link(self):
        jobs=app.make_plan(self.rows,self.header,self.cols,[Path('11 - VLC'),Path('12'),Path('13')])
        self.assertEqual(jobs[0]['row'],3)
        self.assertFalse(jobs[0]['error'])
        self.assertTrue(jobs[1]['error'])
        self.assertEqual(jobs[2]['error'],'Link sudah terisi')

    def test_duplicates_blocked(self):
        jobs=app.make_plan(self.rows,self.header,self.cols,[Path('11'),Path('011 - other')])
        self.assertTrue(all(j['error'] for j in jobs))
        jobs=app.make_plan(self.rows+[['11','',' AFZAL ']],self.header,self.cols,[Path('11')])
        self.assertIn('ambigu',jobs[0]['error'])

    def test_explicit_month_tab(self):
        sheets=Mock()
        sheets.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value={'values':self.rows}
        quoted,*_=app.read_sheet(sheets,'id',"Nov'26")
        self.assertEqual(quoted,"'Nov''26'")
        self.assertEqual(sheets.spreadsheets.return_value.values.return_value.get.call_args.kwargs['range'],quoted)

    def test_oauth_download_filename(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path=root/'client_secret_download.json'
            app.save(path,{'installed':{k:'example' for k in ('client_id','client_secret','auth_uri','token_uri')}})
            with patch.object(app,'BASE',root):
                self.assertEqual(app.client_file(),path)
                app.save(root/'credentials.json',app.load(path))
                with self.assertRaisesRegex(ValueError,'beberapa'):
                    app.client_file()
            self.assertEqual(app.client_file(str(path)),path)

    def test_web_client_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'web.json';app.save(path,{'web':{'client_id':'example'}})
            with self.assertRaisesRegex(ValueError,'Desktop'):
                app.client_file(str(path))

    def test_login_is_separate_and_stores_local_token(self):
        from google_auth_oauthlib.flow import InstalledAppFlow
        with tempfile.TemporaryDirectory() as temp:
            creds=Mock()
            creds.has_scopes.return_value=True
            creds.to_json.return_value='{"token":"fake-test-token"}'
            flow=Mock()
            flow.run_local_server.return_value=creds
            with patch.object(app,'STATE',Path(temp)),patch.object(app,'client_file',return_value=Path('fake.json')),patch.object(InstalledAppFlow,'from_client_secrets_file',return_value=flow):
                app.login()
                self.assertEqual(app.load(Path(temp)/'token.json'),{'token':'fake-test-token'})
                flow.run_local_server.assert_called_once()

    def test_manifest_nested(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'sub').mkdir();(root/'sub'/'photo').write_bytes(b'123')
            self.assertEqual([(p,s) for p,s,_ in app.manifest(root)],[(str(Path('sub/photo')),3)])

    def test_upload_order_checkpoint_and_changed_sheet(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);folder=root/'11';folder.mkdir();(folder/'photo').write_bytes(b'photo')
            drive,sheets=Mock(),Mock();calls=[]
            drive.files.return_value.create.return_value.execute.return_value={'id':'folder'}
            drive.files.return_value.create.return_value.next_chunk.side_effect=lambda **kw: (calls.append('upload') or (None,{'id':'file'}))
            sheets.spreadsheets.return_value.values.return_value.update.return_value.execute.side_effect=lambda: calls.append('write')
            rows=[['No.','PIC','Link Drive'],['11','afzal']];cols={'no':0,'pic':1,'link':2}
            job={'folder':folder,'no':11,'row':2}
            with patch.object(app,'STATE',root/'state'),patch.object(app,'read_sheet',return_value=("'NOV'",rows,0,cols)):
                app.upload_job(drive,sheets,'sid','did','NOV',job,[folder],'account')
                self.assertEqual(calls,['upload','write'])
                app.upload_job(drive,sheets,'sid','did','NOV',job,[folder],'account')
                self.assertEqual(calls,['upload','write','write'])
                rows[1].append('link-from-someone-else')
                with self.assertRaisesRegex(ValueError,'Sheets berubah'):
                    app.upload_job(drive,sheets,'sid','did','NOV',job,[folder],'account')
                self.assertEqual(calls,['upload','write','write'])


if __name__=='__main__':
    unittest.main()
