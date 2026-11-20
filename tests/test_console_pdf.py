import base64
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from console_import import Imports
from console_pdf import pdf


def fixture():
    # Minimal two-page parser fixture; not a delivered document.
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [4 0 R 6 0 R] /Count 2 >>',
             b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
             b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Resources << /Font << /F1 3 0 R >> >> /Contents 5 0 R >>']
    stream=b'BT /F1 12 Tf 20 250 Td (PDF_IMPORT_OK) Tj ET'
    objects.extend([b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream',
                    b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Contents 7 0 R >>',
                    b'<< /Length 0 >>\nstream\n\nendstream'])
    raw=b'%PDF-1.4\n';offsets=[0]
    for i,obj in enumerate(objects,1):
        offsets.append(len(raw));raw+=str(i).encode()+b' 0 obj\n'+obj+b'\nendobj\n'
    start=len(raw);raw+=b'xref\n0 8\n0000000000 65535 f \n'
    raw+=b''.join(('%010d 00000 n \n'%offset).encode() for offset in offsets[1:])
    return raw+b'trailer\n<< /Size 8 /Root 1 0 R >>\nstartxref\n'+str(start).encode()+b'\n%%EOF\n'


class PdfTests(unittest.TestCase):
    def test_read_pages_and_missing_text_warning_preserve_original(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Imports(folder);raw=fixture()
            item=store.add({'name':'sample.pdf','data':base64.b64encode(raw).decode()})
            page=store.preview(item['id'])
            self.assertIn('PDF_IMPORT_OK',page['content']);self.assertIn('【第2页】',page['content'])
            self.assertEqual(2,item['summary']['pages']);self.assertEqual([2],item['summary']['empty_pages'])
            self.assertIn('OCR',''.join(item['summary']['notes']))
            self.assertEqual(raw,(store.path(item['id'])/'original').read_bytes())

    def test_invalid_timeout_and_failure_are_explicit(self):
        with self.assertRaisesRegex(ValueError,'文件头'):pdf(b'bad')
        with self.assertRaisesRegex(ValueError,'无法读取'):pdf(b'%PDF-1.4\nbroken')
        with patch('console_pdf.subprocess.run',side_effect=subprocess.TimeoutExpired('parser',12)):
            with self.assertRaisesRegex(ValueError,'12秒'):pdf(fixture())


if __name__=='__main__':unittest.main()
