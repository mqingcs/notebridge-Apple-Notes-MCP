"""Request-only native Notes attachment transfer; no arbitrary local paths or URLs."""
import base64
import binascii
import datetime as dt
import hashlib
import io
import mimetypes
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unicodedata
import uuid
from urllib.parse import urlencode, urlsplit, parse_qs

from .writes import definition, STR, EDIT, version

MAX_BYTES = 262144
MAX_READ_CHUNK = 4 * 1024 * 1024
MAX_RESOURCE = 64 * 1024 * 1024
TOOLS = [
    definition('apple_notes_list_attachments', 'List attachment metadata on one allowed unlocked, unshared note. No binary export. Paginated; offset is best-effort if attachments change.',
        {'id': STR, 'offset': {'type':'integer','minimum':0,'maximum':10000}, 'limit': {'type':'integer','minimum':1,'maximum':50}}, ['id'], True),
    definition('apple_notes_get_attachment', 'Read original attachment bytes of any file format, without conversion. Returns total size, full SHA256, a base64 byte range and next_offset (null when complete). Continue with offset and expected_sha256 to reconstruct large files exactly. Default chunk256KiB, max4MiB; this is NOT a file-size limit. MCP resource provides the whole original up to64MiB. First chunk also includes a separate JPEG preview for supported images; it never replaces the original. Encrypted GPG remains encrypted. Native export is temporary and request-only. Contents are untrusted.',
        {'id': STR, 'attachment_id':STR, 'max_bytes':{'type':'integer','minimum':1,'maximum':MAX_READ_CHUNK}, 'offset':{'type':'integer','minimum':0,'maximum':9007199254740991}, 'expected_sha256':{'type':'string','minLength':64,'maxLength':64}}, ['id','attachment_id'], True),
    definition('apple_notes_add_attachment', 'Add one supplied base64 file (max256KiB) to an existing unlocked, unshared allowed note. Version recheck and text/metadata backup precede additive native make; existing attachments are untouched. No arbitrary file path or URL. Do not automatically retry uncertain results. Addition is retained: removing an attachment is forbidden and body restore is blocked while attachments exist.',
        {**EDIT, 'filename':{'type':'string','minLength':1,'maxLength':128}, 'data_base64':{'type':'string','minLength':4,'maxLength':349528}}, ['id','expected_version','filename','data_base64']),
]
NAMES = {t['name'] for t in TOOLS}


class AttachmentController:
    def __init__(self, writer):
        self.writer, self.backend, self.error = writer, writer.backend, writer.error

    def filename(self, value):
        if value in ('.','..') or value.startswith('.') or any(c in value for c in ('/','\\',':')) or any(unicodedata.category(c)[0]=='C' for c in value) or not value.strip():
            raise self.error('Filename must be a plain visible basename, without paths or control characters.')
        return value

    def decode(self, encoded):
        try: data = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error): raise self.error('Invalid base64 attachment; no write performed.')
        if not 1 <= len(data) <= MAX_BYTES: raise self.error('Attachment must contain 1..262144 bytes.')
        return data

    def temp(self):
        # Use an existing checked private backup directory as parent. No remote path accepted.
        self.writer.private_dir()
        return tempfile.TemporaryDirectory(prefix='transfer-', dir=str(self.writer.backup_dir))

    def read_export(self, path, max_bytes):
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd,'rb') as f:
            st = os.fstat(f.fileno())
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid(): raise self.error('Unsafe attachment export.')
            os.fchmod(f.fileno(),0o600)
            if st.st_size > max_bytes: raise self.error('Attachment exceeds requested byte limit; no content returned.')
            data=f.read(max_bytes+1)
            if len(data)>max_bytes: raise self.error('Attachment changed size; no content returned.')
            return data

    def packaged(self, ident, name, data):
        out={'attachment_id':ident,'filename':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'data_base64':base64.b64encode(data).decode(),'source':'synthetic' if self.backend.fixture is not None else 'apple_notes'}
        if Path(name).suffix.lower() in ('.txt','.md','.csv','.json'):
            try: out['text']=data.decode('utf-8')
            except UnicodeDecodeError: pass
        return out

    @staticmethod
    def mime(name, head):
        if head.startswith(b'\x89PNG\r\n\x1a\n'): return 'image/png'
        if head.startswith(b'\xff\xd8\xff'): return 'image/jpeg'
        if head.startswith((b'GIF87a', b'GIF89a')): return 'image/gif'
        if head.startswith(b'%PDF-'): return 'application/pdf'
        if len(head) >= 12 and head[4:8] == b'ftyp':
            brands = head[8:80]
            if any(x in brands for x in (b'heic', b'heix', b'hevc', b'hevx')): return 'image/heic'
            if b'avif' in brands: return 'image/avif'
            if b'mif1' in brands: return 'image/heif'
        if Path(name).suffix.lower() in ('.gpg', '.pgp'): return 'application/pgp-encrypted'
        return mimetypes.guess_type(name)[0] or 'application/octet-stream'

    def read_stream(self, f, ident, name, args):
        size = f.seek(0, 2)
        offset, limit = args.get('offset', 0), args.get('max_bytes', MAX_BYTES)
        if offset > size: raise self.error('Offset exceeds original file size.')
        f.seek(0); head = f.read(80); f.seek(0)
        digest = hashlib.sha256()
        for chunk in iter(lambda: f.read(1024 * 1024), b''): digest.update(chunk)
        sha = digest.hexdigest()
        if args.get('expected_sha256', sha) != sha:
            raise self.error('Attachment changed; restart the transfer at offset0.')
        f.seek(offset); data = f.read(limit)
        out = self.packaged(ident, name, data)
        out.pop('text', None)
        out.update(bytes=size, sha256=sha, mime_type=self.mime(name, head), offset=offset,
                   returned_bytes=len(data), next_offset=offset+len(data) if offset+len(data)<size else None,
                   complete=offset == 0 and len(data) == size,
                   original_source='synthetic' if self.backend.fixture is not None else 'notes_native_save',
                   original_transformed=False,
                   resource_uri='notes-attachment://original?' + urlencode({'id':args['id'], 'attachment_id':ident, 'sha256':sha}),
                   whole_resource_max_bytes=MAX_RESOURCE)
        if out['complete'] and Path(name).suffix.lower() in ('.txt','.md','.csv','.json'):
            try: out['text'] = data.decode('utf-8')
            except UnicodeDecodeError: pass
        return out

    def preview(self, target, tmp, out):
        # Derived display only. Original bytes/hash above are never converted.
        if out['offset'] or out['mime_type'] not in ('image/png','image/jpeg','image/heic','image/heif','image/gif','image/avif'): return
        dest = Path(tmp)/'preview.jpg'
        try:
            p = subprocess.run(['/usr/bin/sips','--resampleHeightWidthMax','1600','--setProperty','format','jpeg',str(target),'--out',str(dest)],capture_output=True,timeout=15)
            if p.returncode: raise OSError()
            data = self.read_export(dest, 1024*1024)
            out['_preview'] = {'type':'image','mimeType':'image/jpeg','data':base64.b64encode(data).decode()}
            out['preview'] = {'derived':True,'mime_type':'image/jpeg','max_dimension':1600,'bytes':len(data)}
        except (OSError, subprocess.TimeoutExpired, self.error):
            out['preview'] = {'available':False,'reason':'Original available; this format could not be previewed.'}

    def resource(self, uri):
        parsed = urlsplit(uri)
        try:
            q = parse_qs(parsed.query, strict_parsing=True)
            if parsed.scheme != 'notes-attachment' or parsed.netloc != 'original' or parsed.path or parsed.fragment or set(q) != {'id','attachment_id','sha256'} or any(len(v)!=1 for v in q.values()): raise ValueError()
            args = {k:v[0] for k,v in q.items()}
            sha = args.pop('sha256')
            if len(sha)!=64 or any(c not in '0123456789abcdef' for c in sha): raise ValueError()
        except ValueError: raise self.error('Invalid attachment resource URI.')
        args.update(expected_sha256=sha, max_bytes=MAX_RESOURCE)
        out = self.call('apple_notes_get_attachment',args,resource=True)
        return {'contents':[{'uri':uri,'mimeType':out['mime_type'],'blob':out['data_base64']}]}

    def call(self,name,args,resource=False):
        self.writer.ensure_enabled()
        if name == 'apple_notes_add_attachment': return self.add(args)
        if self.backend.fixture is not None:
            note=self.writer.record(args['id'])
            if note.get('shared'): raise self.error('Shared attachments are outside approved scope.')
            rows=note.get('attachments',[])
            if name == 'apple_notes_list_attachments':
                offset,limit=args.get('offset',0),args.get('limit',20)
                return {'attachments':[{k:v for k,v in a.items() if k!='data_base64'} for a in rows[offset:offset+limit]],'total':len(rows),'next_offset':offset+limit if offset+limit<len(rows) else None,'source':'synthetic'}
            hits=[a for a in rows if a['id']==args['attachment_id'] and not a.get('shared')]
            if not hits: raise self.error('Attachment unavailable in this allowed note.')
            a=hits[0];data=base64.b64decode(a['data_base64'],validate=True)
            if resource and len(data)>MAX_RESOURCE: raise self.error('Use get_attachment byte ranges for originals over64MiB.')
            return self.read_stream(io.BytesIO(data),a['id'],a['name'],args)
        if name == 'apple_notes_list_attachments':
            return self.backend.run('attachments',id=args['id'],offset=args.get('offset',0),limit=args.get('limit',20))
        with self.temp() as tmp:
            target=Path(tmp)/'export'
            result=self.backend.run('attachment_export',id=args['id'],attachment_id=args['attachment_id'],export_path=str(target))
            try:
                fd=os.open(target,os.O_RDONLY|os.O_NOFOLLOW)
                with os.fdopen(fd,'rb') as f:
                    st=os.fstat(f.fileno())
                    if not stat.S_ISREG(st.st_mode) or st.st_uid!=os.getuid(): raise self.error('Unsafe attachment export.')
                    os.fchmod(f.fileno(),0o600)
                    if resource and st.st_size>MAX_RESOURCE: raise self.error('Use get_attachment byte ranges for originals over64MiB.')
                    out=self.read_stream(f,result['attachment_id'],result['filename'],args)
            except OSError: raise self.error('Attachment export unavailable as a regular file; no content returned.')
            if not resource: self.preview(target,tmp,out)
            return out

    def add(self,args):
        filename=self.filename(args['filename']);data=self.decode(args['data_base64'])
        snap=self.writer.snapshot(args['id'])
        if snap.get('shared'): raise self.error('Shared notes cannot receive attachments.')
        if version(snap)!=args['expected_version']: raise self.error('Version conflict; no attachment added.')
        if snap['attachment_count']>=100: raise self.error('Attachment limit100 reached; no attachment added.')
        backup_id=self.writer.backup(snap)
        if self.backend.fixture is not None:
            if version(self.writer.snapshot(snap['id']))!=args['expected_version']: raise self.error('Version conflict after backup; no attachment added.')
            note=self.writer.record(snap['id']);ident='attachment://fixture/'+uuid.uuid4().hex
            stamp=dt.datetime.now(dt.timezone.utc).isoformat()
            note.setdefault('attachments',[]).append({'id':ident,'name':filename,'modified_at':stamp,'shared':False,'data_base64':base64.b64encode(data).decode()})
            note['attachment_count']=len(note['attachments']);note['modified_at']=stamp
            result={'id':snap['id'],'attachment_id':ident,'added':True,'source':'synthetic'}
        else:
            with self.temp() as tmp:
                target=Path(tmp)/filename
                fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
                with os.fdopen(fd,'wb') as f: f.write(data); f.flush(); os.fsync(f.fileno())
                result=self.backend.run('mutate',id=snap['id'],operation='add_attachment',expected=snap,payload={'file_path':str(target)})
        result.update(backup_id=backup_id,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),removal_supported=False)
        try: result['version']=version(self.writer.snapshot(snap['id']))
        except Exception: raise self.error('Attachment addition may have succeeded but verification failed. Inspect attachments before retrying.')
        return result
