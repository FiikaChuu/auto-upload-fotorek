import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
import auto_upload as core
import upload_flow as flow
from matching import detect, parse_columns


class HeaderTests(unittest.TestCase):
    def test_partial_decorative_duplicate_row_is_not_header(self):
        self.assertEqual(detect([['PIC','PIC'],['No.','PIC','Link Drive']]),(1,{'no':0,'pic':1,'link':2}))

    def test_duplicate_header_reports_columns_without_requesting_sheet_edits(self):
        with self.assertRaisesRegex(ValueError,'pic: D, E'):
            detect([['No.','Reference','Location','PIC','PIC','','Link Drive']])

    def test_ambiguous_first_table_does_not_select_later_table(self):
        with self.assertRaisesRegex(ValueError,'kandidat kolom'):
            detect([['No.','PIC','PIC','Link Drive'],['No.','PIC','Link Drive']])

    def test_explicit_mapping_ignores_hidden_duplicate_headers(self):
        rows=[['No.','Reference','Location','PIC','PIC','Link Drive','Link Drive']]
        mapping=parse_columns({'no':'a','pic':'d','link':'g'})
        self.assertEqual(detect(rows,mapping),(0,{'no':0,'pic':3,'link':6}))

    def test_mapping_must_match_real_header_and_use_distinct_letters(self):
        with self.assertRaisesRegex(ValueError,'berbeda'):
            parse_columns({'no':'A','pic':'A','link':'G'})
        with self.assertRaisesRegex(ValueError,'huruf'):
            parse_columns({'no':'A1','pic':'D','link':'G'})
        with self.assertRaisesRegex(ValueError,'Judul kolom tidak cocok'):
            detect([['No.','PIC','Link Drive']],{'no':0,'pic':3,'link':6})

    def test_hidden_duplicates_upload_then_write_only_g12(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);folder=root/'11';folder.mkdir();(folder/'edited.jpg').write_bytes(b'edited')
            rows=[['No.','Reference','Location','PIC','PIC','Link Drive','Link Drive']]+[[] for _ in range(10)]+[['11','','','afzal','kayla','existing-hidden-link','']]
            drive,sheets=Mock(),Mock()
            sheets.spreadsheets.return_value.get.return_value.execute.return_value={'sheets':[{'properties':{'title':'FEEDS-OKT','sheetId':0}},{'properties':{'title':'NOV','sheetId':1}}]}
            sheets.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value={'values':rows}
            drive.files.return_value.get.return_value.execute.return_value={'mimeType':'application/vnd.google-apps.folder','capabilities':{'canAddChildren':True}}
            drive.about.return_value.get.return_value.execute.return_value={'user':{'permissionId':'account'}}
            drive.files.return_value.create.return_value.execute.return_value={'id':'folder11'}
            drive.files.return_value.create.return_value.next_chunk.return_value=(None,{'id':'file'})
            with patch.object(core,'STATE',root/'state'):
                prepared=flow.prepare((drive,sheets),[folder],'sid','did','FEEDS-OKT',{'no':0,'pic':3,'link':6})
                self.assertFalse(prepared['jobs'][0]['error'])
                self.assertEqual(flow.execute((drive,sheets),prepared),1)
            writes=sheets.spreadsheets.return_value.batchUpdate.call_args_list
            self.assertEqual(len(writes),1)
            self.assertEqual(writes[0].kwargs['body']['requests'][0]['updateCells']['start'],{'sheetId':0,'rowIndex':11,'columnIndex':6})
            self.assertEqual(writes[0].kwargs['body']['requests'][0]['updateCells']['rows'][0]['values'][0]['chipRuns'][0]['chip']['richLinkProperties']['uri'],'https://drive.google.com/drive/folders/folder11')


if __name__=='__main__':
    unittest.main()
