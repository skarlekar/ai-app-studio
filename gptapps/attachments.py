"""Bounded chat file inputs; no filesystem paths, URLs, or hosted file IDs accepted."""
import base64
import binascii
from pathlib import PurePosixPath
import re

MAX_FILES = 5
MAX_FILE_BYTES = 10 * 1024**2
MAX_TOTAL_BYTES = 20 * 1024**2
MAX_REQUEST_BYTES = 29 * 1024**2  # JSON/base64 overhead plus the bounded setup reply.
DOCUMENT_TYPES = {
    '.pdf':'application/pdf', '.txt':'text/plain', '.md':'text/markdown', '.json':'application/json',
    '.csv':'text/csv', '.tsv':'text/tab-separated-values', '.xml':'application/xml', '.html':'text/html',
    '.doc':'application/msword', '.docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.rtf':'application/rtf', '.odt':'application/vnd.oasis.opendocument.text',
    '.ppt':'application/vnd.ms-powerpoint', '.pptx':'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    '.xls':'application/vnd.ms-excel', '.xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
}
for extension in ('.c','.cpp','.cs','.css','.go','.java','.js','.php','.py','.rb','.sh','.tex','.ts','.yaml','.yml'):
    DOCUMENT_TYPES[extension]='text/plain'
IMAGE_TYPES={'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp'}
EXTENSIONS=tuple(sorted(DOCUMENT_TYPES | IMAGE_TYPES))
TEXT_EXTENSIONS=set(DOCUMENT_TYPES)-{'.pdf','.doc','.docx','.rtf','.odt','.ppt','.pptx','.xls','.xlsx'}


def validate_attachments(value):
    if value is None:
        return []
    if not isinstance(value,list) or len(value)>MAX_FILES:
        raise ValueError('Attach up to 5 files per message')
    result=[];total=0
    for item in value:
        if not isinstance(item,dict) or set(item)!={'name','data'}:
            raise ValueError('Each attachment requires a filename and base64 data')
        name,data=item['name'],item['data']
        if (not isinstance(name,str) or not 1<=len(name)<=200 or name.strip()!=name
                or '/' in name or '\\' in name or re.search(r'[\x00-\x1f\x7f]',name)):
            raise ValueError('Invalid attachment filename')
        extension=PurePosixPath(name).suffix.lower()
        if extension not in EXTENSIONS:
            raise ValueError('Unsupported attachment type; use a supported document, text, spreadsheet or PNG/JPEG/WebP image')
        if not isinstance(data,str) or len(data)>4*((MAX_FILE_BYTES+2)//3):
            raise ValueError('Each attachment must be at most 10 MiB')
        try:
            raw=base64.b64decode(data,validate=True)
        except (ValueError,binascii.Error):
            raise ValueError('Invalid attachment encoding') from None
        if not 0<len(raw)<=MAX_FILE_BYTES:
            raise ValueError('Attachments must be nonempty and at most 10 MiB each')
        total+=len(raw)
        if total>MAX_TOTAL_BYTES:
            raise ValueError('Attachments must total at most 20 MiB')
        if extension in IMAGE_TYPES:
            valid=(raw.startswith(b'\x89PNG\r\n\x1a\n') if extension=='.png' else
                   raw.startswith(b'\xff\xd8\xff') if extension in ('.jpg','.jpeg') else
                   raw.startswith(b'RIFF') and raw[8:12]==b'WEBP')
            if not valid:
                raise ValueError('Attachment image bytes do not match its filename type')
        result.append({'name':name,'mime_type':(DOCUMENT_TYPES | IMAGE_TYPES)[extension],
                       'size':len(raw),'data':base64.b64encode(raw).decode('ascii')})
    return result


def public_attachments(files):
    return [{key:item[key] for key in ('name','mime_type','size')} for item in files]


def input_content(text,files):
    if not files:
        return text  # Preserve text-only clients and saved conversations.
    parts=[{'type':'input_text','text':text}] if text else []
    for item in files:
        data_url=f"data:{item['mime_type']};base64,{item['data']}"
        if item['mime_type'].startswith('image/'):
            parts.extend([{'type':'input_text','text':'Attached image: '+item['name']},
                          {'type':'input_image','image_url':data_url}])
        else:
            parts.append({'type':'input_file','filename':item['name'],'file_data':data_url})
    return parts


def exact_text(files):
    texts=[]
    for item in files:
        if PurePosixPath(item['name']).suffix.lower() not in TEXT_EXTENSIONS:
            raise ValueError('For exact instructions or Action schemas, attach UTF-8 text/Markdown/JSON files, or paste the text')
        try:
            texts.append(base64.b64decode(item['data']).decode('utf-8-sig'))
        except UnicodeError:
            raise ValueError('Setup instructions and Action schemas require UTF-8 text files') from None
    return '\n\n'.join(texts)
