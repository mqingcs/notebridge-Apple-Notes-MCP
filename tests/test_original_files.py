import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from apple_notes_mcp import server as m
from apple_notes_mcp.attachments import MAX_BYTES

ROOT=Path(__file__).resolve().parents[1]

class Originals(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.b=m.Backend(ROOT/'fixtures/synthetic.json',folders=['folder-demo'],write_enabled=True,experimental_attachments=True,backup_dir=Path(self.tmp.name)/'backup')
        self.s=m.Service(self.b); self.id='notes://fixture/a'
        self.note=self.b.fixture['notes'][0]

    def put(self, name, data, ident='a'):
        self.note.setdefault('attachments',[]).append({'id':ident,'name':name,'data_base64':base64.b64encode(data).decode(),'shared':False})
        return {'id':self.id,'attachment_id':ident}

    def get(self,args): return self.s.call('apple_notes_get_attachment',args)

    def test_original_formats_and_duplicate_names_reassemble_exactly(self):
        for idx,(name,head,mime) in enumerate([
            ('long.png',b'\x89PNG\r\n\x1a\n','image/png'),
            ('same.jpg',b'\xff\xd8\xff','image/jpeg'),
            ('same.jpg',b'\xff\xd8\xffdifferent','image/jpeg'),
            ('image.heic',b'\x00\x00\x00\x18ftypheic','image/heic'),
            ('secret.gpg',b'\x85opaque encrypted bytes','application/pgp-encrypted'),
            ('multipage.pdf',b'%PDF-1.7\n','application/pdf'),
            ('unknown.custom',b'\x00\x01\x02','application/octet-stream')]):
            with self.subTest(name=name,idx=idx):
                data=head+bytes(range(256))*1100
                args=self.put(name,data,str(idx)); out=self.get(args)
                self.assertEqual(out['mime_type'],mime); self.assertFalse(out['complete'])
                got=base64.b64decode(out['data_base64']); sha=out['sha256']
                while out['next_offset'] is not None:
                    out=self.get(dict(args,offset=out['next_offset'],expected_sha256=sha))
                    got+=base64.b64decode(out['data_base64'])
                self.assertEqual(got,data); self.assertEqual(sha,hashlib.sha256(data).hexdigest())
                self.assertFalse(out['original_transformed'])

    def test_changed_original_refuses_mixed_chunks_and_resource(self):
        args=self.put('a.bin',b'one'); first=self.get(args)
        self.note['attachments'][0]['data_base64']=base64.b64encode(b'two').decode()
        with self.assertRaisesRegex(m.NotesError,'changed'): self.get(dict(args,expected_sha256=first['sha256']))
        with self.assertRaisesRegex(m.NotesError,'changed'): self.s.attachments.resource(first['resource_uri'])

    def test_empty_files_and_offset_bound(self):
        args=self.put('empty',b''); out=self.get(args)
        self.assertTrue(out['complete']); self.assertEqual(out['bytes'],0)
        with self.assertRaises(m.NotesError): self.get(dict(args,offset=1))

    def test_resource_exact_bytes_scope_and_protocol_content(self):
        data=b'file'*100000; args=self.put('file.bin',data)
        self.s.state='ready'
        reply=self.s.handle({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'apple_notes_get_attachment','arguments':args}})['result']
        self.assertFalse(reply['isError']); self.assertEqual(reply['content'][1]['type'],'resource_link')
        self.assertNotIn('data_base64',reply['content'][0]['text'])
        uri=reply['structuredContent']['resource_uri']
        r=self.s.handle({'jsonrpc':'2.0','id':2,'method':'resources/read','params':{'uri':uri}})
        self.assertEqual(base64.b64decode(r['result']['contents'][0]['blob']),data)
        self.b.folders=[]
        with self.assertRaises(m.NotesError): self.s.attachments.resource(uri)
        with self.assertRaises(m.NotesError): self.s.attachments.resource('file:///etc/passwd')

    def test_note_html_preserved_and_maps_cid_without_binary(self):
        self.put('a.png',b'fake image')
        self.note['attachments'][0]['content_identifier']='cid:one'
        html='<div><b>Title</b><img src="cid:one"></div>'
        self.note['body_html']=html
        out=self.s.call('apple_notes_get',{'id':self.id,'format':'html'})
        self.assertEqual(out['body_html'],html)
        self.assertEqual(out['attachments'][0]['content_identifier'],'cid:one')
        self.assertNotIn('data_base64',json.dumps(out))
        with self.assertRaises(m.NotesError): self.s.call('apple_notes_get',{'id':self.id,'format':'nope'})

    def test_large_inline_image_externalized_by_exact_hash(self):
        data=b'\x89PNG\r\n\x1a\n'+b'x'*300000
        args=self.put('image.png',data)
        encoded=base64.b64encode(data).decode()
        self.note['body_html']='<div><b>title</b><img style="width:100%" src="data:image/png;base64,'+encoded+'"></div>'
        row=self.s.call('apple_notes_get',{'id':self.id,'format':'html'})
        out=self.get(args)
        self.assertEqual(row['inline_media'][0]['sha256'],out['sha256'])
        ref=row['inline_media'][0]['reference']
        self.assertIn('style="width:100%"',row['body_html'])
        self.assertEqual(row['body_html'].replace(ref,'data:image/png;base64,'+encoded),self.note['body_html'])

if __name__=='__main__': unittest.main()
