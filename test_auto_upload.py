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

    def test_select_individual_and_multiple_parent_folders(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'Edited';root.mkdir()
            for name in ['11','13','15','other']:(root/name).mkdir()
            with patch.object(app,'pick_directory',return_value=str(root/'11')),patch.object(app,'ask',return_value='t'):
                self.assertEqual(app.select_local_folders(),[root/'11'])
            with patch.object(app,'pick_directory',return_value=str(root)),patch.object(app,'ask',return_value='t'):
                self.assertEqual({p.name for p in app.select_local_folders()},{'11','13','15'})

    def test_local_folder_11_uploads_then_writes_g12(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);folder=root/'11';folder.mkdir();(folder/'edited.jpg').write_bytes(b'edited')
            drive,sheets=Mock(),Mock()
            drive.files.return_value.get.return_value.execute.return_value={'mimeType':'application/vnd.google-apps.folder','capabilities':{'canAddChildren':True}}
            drive.about.return_value.get.return_value.execute.return_value={'user':{'permissionId':'account'}}
            drive.files.return_value.create.return_value.execute.return_value={'id':'uploaded-11'}
            order=[]
            drive.files.return_value.create.return_value.next_chunk.side_effect=lambda **kw:(order.append('upload') or (None,{'id':'photo'}))
            sheets.spreadsheets.return_value.values.return_value.update.return_value.execute.side_effect=lambda:order.append('write')
            rows=[['No.','Reference','Location','PIC','','','Link Drive']]+[[] for _ in range(10)]+[['11','','','afzal']]
            cols={'no':0,'pic':3,'link':6}
            with patch.object(app,'STATE',root/'state'),patch.object(app,'select_local_folders',return_value=[folder]),patch.object(app,'tabs',return_value=['FEEDS-OKT']),patch.object(app,'ask',side_effect=['sheet-id','1','drive-id','UPLOAD']),patch.object(app,'read_sheet',return_value=("'FEEDS-OKT'",rows,0,cols)):
                app.configure_and_upload((drive,sheets))
            self.assertEqual(order,['upload','write'])
            write=sheets.spreadsheets.return_value.values.return_value.update.call_args.kwargs
            self.assertEqual(write['range'],"'FEEDS-OKT'!G12")
            self.assertEqual(write['body']['values'],[['https://drive.google.com/drive/folders/uploaded-11']])

    def test_drive_folder_pagination(self):
        drive=Mock()
        drive.files.return_value.list.return_value.execute.side_effect=[
            {'files':[{'id':'one','name':'11'},{'id':'skip','name':'other'}],'nextPageToken':'next'},
            {'files':[{'id':'two','name':'24'}]}]
        self.assertEqual([f['name'] for f in app.drive_folders(drive,'parent')],['11','24'])
        self.assertEqual(drive.files.return_value.list.call_args.kwargs['pageToken'],'next')

    def test_one_click_defaults_to_wizard(self):
        with patch('sys.argv',['auto_upload.py']),patch.object(app,'wizard') as wizard:
            app.main()
            wizard.assert_called_once_with(None)

    def test_wizard_first_login_then_local_upload(self):
        with tempfile.TemporaryDirectory() as temp:
            drive,sheets=Mock(),Mock()
            drive.about.return_value.get.return_value.execute.return_value={'user':{'emailAddress':'user@example.test'}}
            order=[]
            with patch.object(app,'STATE',Path(temp)),patch.object(app,'client_file',return_value=Path('oauth.json')),patch.object(app,'login',side_effect=lambda *_:order.append('login')),patch.object(app,'services',return_value=(drive,sheets)),patch.object(app,'ask',return_value='1'),patch.object(app,'configure_and_upload',side_effect=lambda *_:order.append('upload')) as upload:
                app.wizard()
                self.assertEqual(order,['login','upload'])
                upload.assert_called_once_with((drive,sheets))

    def test_wizard_reuses_login_then_local_upload(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'token.json').write_text('{}')
            drive,sheets=Mock(),Mock()
            drive.about.return_value.get.return_value.execute.return_value={'user':{'emailAddress':'user@example.test'}}
            with patch.object(app,'STATE',root),patch.object(app,'services',return_value=(drive,sheets)),patch.object(app,'login') as login,patch.object(app,'ask',side_effect=['bad','2']),patch.object(app,'configure_and_upload') as upload:
                app.wizard()
                login.assert_not_called()
                upload.assert_called_once_with((drive,sheets))

    def test_wizard_expired_session_reauthenticates(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'token.json').write_text('{}')
            drive,sheets=Mock(),Mock()
            drive.about.return_value.get.return_value.execute.return_value={'user':{}}
            with patch.object(app,'STATE',root),patch.object(app,'services',side_effect=[ValueError('expired'),(drive,sheets)]),patch.object(app,'client_file',return_value=Path('oauth.json')),patch.object(app,'login') as login,patch.object(app,'ask',return_value='1'),patch.object(app,'configure_and_upload'):
                app.wizard()
                login.assert_called_once_with('oauth.json')

    def test_sync_drive_nonconsecutive_numbers_without_upload(self):
        with tempfile.TemporaryDirectory() as temp:
            drive,sheets=Mock(),Mock()
            folders=[{'name':str(n),'id':'folder-'+str(n)} for n in [11,13,15,17,19,21,24]]
            rows=[['No.','PIC','Link Drive']]+[[f['name'],'afzal'] for f in folders]
            cols={'no':0,'pic':1,'link':2}
            with patch.object(app,'STATE',Path(temp)),patch.object(app,'services',return_value=(drive,sheets)),patch.object(app,'tabs',return_value=['NOV']),patch.object(app,'ask',side_effect=['sheet-id','1','drive-id','ISI']),patch.object(app,'drive_folders',return_value=folders),patch.object(app,'read_sheet',return_value=("'NOV'",rows,0,cols)):
                app.sync_drive()
            writes=sheets.spreadsheets.return_value.values.return_value.update.call_args_list
            self.assertEqual(len(writes),7)
            self.assertEqual(writes[-1].kwargs['body']['values'],[['https://drive.google.com/drive/folders/folder-24']])
            drive.files.return_value.create.assert_not_called()

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
