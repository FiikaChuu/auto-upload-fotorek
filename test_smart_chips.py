import json
import unittest
from unittest.mock import Mock
from googleapiclient.errors import HttpError
from httplib2 import Response
import auto_upload as core


class SmartChipTests(unittest.TestCase):
    def api(self,title='FEEDS-OKT',sheet_id=0):
        sheets=Mock()
        sheets.spreadsheets.return_value.get.return_value.execute.return_value={'sheets':[{'properties':{'title':title,'sheetId':sheet_id}}]}
        return sheets

    def test_native_chip_at_g12_preserves_formatting(self):
        sheets=self.api()
        core.write_drive_chip(sheets,'sid','FEEDS-OKT',12,6,'https://drive.google.com/drive/folders/folder11')
        update=sheets.spreadsheets.return_value.batchUpdate.call_args.kwargs['body']['requests'][0]['updateCells']
        self.assertEqual(update['start'],{'sheetId':0,'rowIndex':11,'columnIndex':6})
        self.assertEqual(update['fields'],'userEnteredValue,chipRuns')
        self.assertEqual(update['rows'],[{'values':[{'userEnteredValue':{'stringValue':'@'},'chipRuns':[{'startIndex':0,'chip':{'richLinkProperties':{'uri':'https://drive.google.com/drive/folders/folder11'}}}]}]}])
        self.assertNotIn('userEnteredFormat',update['rows'][0]['values'][0])
        sheets.spreadsheets.return_value.values.return_value.update.assert_not_called()

    def test_sheet_identity_is_resolved_from_exact_title(self):
        sheets=self.api("Nov'26",91)
        core.write_drive_chip(sheets,'sid',"Nov'26",15,6,'https://drive.google.com/drive/folders/folder15')
        start=sheets.spreadsheets.return_value.batchUpdate.call_args.kwargs['body']['requests'][0]['updateCells']['start']
        self.assertEqual(start,{'sheetId':91,'rowIndex':14,'columnIndex':6})

    def test_missing_sheet_stops_before_writing(self):
        sheets=self.api()
        with self.assertRaisesRegex(ValueError,'Tab tujuan chip'):
            core.write_drive_chip(sheets,'sid','NOV',12,6,'https://drive.google.com/drive/folders/id')
        sheets.spreadsheets.return_value.batchUpdate.assert_not_called()

    def test_chip_failure_keeps_error_and_never_falls_back_to_plain_url(self):
        sheets=self.api()
        failure=HttpError(Response({'status':'400','reason':'Bad Request'}),b'{"error":{"message":"Invalid chip"}}')
        sheets.spreadsheets.return_value.batchUpdate.return_value.execute.side_effect=failure
        with self.assertRaises(HttpError):
            core.write_drive_chip(sheets,'sid','FEEDS-OKT',12,6,'https://drive.google.com/drive/folders/id')
        self.assertIn('Menulis chip folder Drive',failure.upload_operation)
        sheets.spreadsheets.return_value.values.return_value.update.assert_not_called()

    def test_sdk_supports_chip_schema_and_serializes_request(self):
        from googleapiclient.discovery import build
        from google.auth.credentials import AnonymousCredentials
        api=build('sheets','v4',credentials=AnonymousCredentials())
        self.assertIn('chipRuns',api._rootDesc['schemas']['CellData']['properties'])
        sheets=self.api()
        core.write_drive_chip(sheets,'sid','FEEDS-OKT',12,6,'https://drive.google.com/drive/folders/id')
        body=sheets.spreadsheets.return_value.batchUpdate.call_args.kwargs['body']
        request=api.spreadsheets().batchUpdate(spreadsheetId='sid',body=body)
        self.assertEqual(json.loads(request.body),body)


if __name__=='__main__':
    unittest.main()
