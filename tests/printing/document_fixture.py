import base64
import hashlib
from pathlib import Path
import struct
import zlib


def markup(webkit_source: Path):
    font = (webkit_source / 'Tools/TestWebKitAPI/Resources/cocoa/Ahem.ttf').read_bytes()
    assert hashlib.sha256(font).hexdigest() == '63d2abd0041c3e3b4b52ad8d382353b53c51c6785e76ce56ed9dacad2d2e31c4'

    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))

    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 4, 4, 8, 2, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress((b'\x00' + b'\x00\x00\xff' * 4) * 4)) + chunk(b'IEND', b'')
    font_url = 'data:font/ttf;base64,' + base64.b64encode(font).decode()
    image_url = 'data:image/png;base64,' + base64.b64encode(png).decode()
    pages = ''.join(f'<article><h1>PRINT177 PAGE {n}</h1><p>Invoice document {n}: text stays text.</p>'
                    '<svg width="180" height="35"><rect width="96" height="10" fill="#f00"/>'
                    '<rect x="120" width="30" height="30" fill="#008000"/></svg>'
                    f'<img width="32" height="32" src="{image_url}">'
                    '<p class="font">XXXX</p><p class="screen-only">SCREEN ONLY</p></article>' for n in (1, 2, 3))
    return ('<!doctype html><meta charset="utf-8"><style>'
            f'@font-face{{font-family:PrintAhem;src:url({font_url})}}'
            'html,body{margin:0}article{height:450px;padding:12px;font:16px Arial,sans-serif}'
            '.font{font:20px PrintAhem}h1{font-size:24px}'
            '@media print{article{height:220px;padding:0;break-before:page}article:first-child{break-before:auto}'
            '.screen-only{display:none}}</style><body>' + pages + '</body>')
