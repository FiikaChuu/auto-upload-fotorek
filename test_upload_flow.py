import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import upload_flow as flow


class FlowTests(unittest.TestCase):
    def test_multiple_folders_and_duplicate_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in ['11','13','other']:(root/name).mkdir()
            selected=flow.add_source([],root)
            self.assertEqual([p.name for p in selected],['11','13'])
            self.assertEqual(flow.add_source(selected,root/'11'),selected)

    def test_empty_selection_and_missing_tab_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'Pilih folder'):
            flow.prepare((Mock(),Mock()),[],'id','id','NOV')
        with self.assertRaisesRegex(ValueError,'tab'):
            flow.prepare((Mock(),Mock()),[Path('11')],'id','id','')

    def prepare(self, root):
        folder=root/'11';folder.mkdir()
        drive,sheets=Mock(),Mock()
        drive.files.return_value.get.return_value.execute.return_value={'mimeType':'application/vnd.google-apps.folder','capabilities':{'canAddChildren':True}}
        drive.about.return_value.get.return_value.execute.return_value={'user':{'permissionId':'account'}}
        rows=[['No.','Reference','Location','PIC','','','Link Drive']]+[[] for _ in range(10)]+[['11','','','afzal']]
        cols={'no':0,'pic':3,'link':6}
        with patch.object(flow.core,'read_sheet',return_value=("'FEEDS-OKT'",rows,0,cols)):
            prepared=flow.prepare((drive,sheets),[folder],'sheet','drive','FEEDS-OKT')
        return (drive,sheets),prepared,rows,cols

    def test_preview_maps_folder_11_to_g12(self):
        with tempfile.TemporaryDirectory() as temp:
            _,prepared,_,_=self.prepare(Path(temp))
            self.assertEqual(prepared['jobs'][0]['row'],12)
            self.assertEqual(prepared['cols']['link'],6)
            self.assertFalse(prepared['jobs'][0]['error'])

    def test_execute_uses_checked_plan(self):
        with tempfile.TemporaryDirectory() as temp:
            clients,prepared,rows,cols=self.prepare(Path(temp))
            with patch.object(flow.core,'read_sheet',return_value=("'FEEDS-OKT'",rows,0,cols)),patch.object(flow.core,'upload_job') as upload:
                self.assertEqual(flow.execute(clients,prepared),1)
                self.assertEqual(upload.call_args.args[5]['row'],12)

    def test_changed_pic_stops_upload(self):
        with tempfile.TemporaryDirectory() as temp:
            clients,prepared,rows,cols=self.prepare(Path(temp))
            rows[11][3]='kayla'
            with patch.object(flow.core,'read_sheet',return_value=("'FEEDS-OKT'",rows,0,cols)),patch.object(flow.core,'upload_job') as upload:
                with self.assertRaisesRegex(ValueError,'Sheets berubah'):
                    flow.execute(clients,prepared)
                upload.assert_not_called()

    def test_existing_link_is_skipped(self):
        with tempfile.TemporaryDirectory() as temp:
            clients,prepared,_,_=self.prepare(Path(temp))
            prepared['jobs'][0]['error']='Link sudah terisi'
            with patch.object(flow.core,'upload_job') as upload:
                self.assertEqual(flow.execute(clients,prepared),0)
                upload.assert_not_called()


if __name__=='__main__':
    unittest.main()
