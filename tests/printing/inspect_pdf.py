"""Inspect retained renderer output using separately installed analysis tools."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from PIL import Image
from pypdf import PdfReader


def inspect(path, output):
    output.mkdir(parents=True, exist_ok=True)
    pdf = PdfReader(path, strict=True)
    assert len(pdf.pages) == 3, 'three independently parsed PDF pages'
    rows = []
    assertions = 1
    for index, page in enumerate(pdf.pages):
        box = [float(page.mediabox.width), float(page.mediabox.height)]
        assert box == [576, 720], 'physical point page box'
        text = page.extract_text()
        assert 'PRINT177 PAGE ' + str(index + 1) in text, 'actual DOM text remains text'
        assert 'SCREEN ONLY' not in text, 'print media applied'
        assertions += 3
        descriptors = []
        for font in page['/Resources'].get('/Font', {}).values():
            actual = font.get_object()
            for candidate in [actual] + [item.get_object() for item in actual.get('/DescendantFonts', [])]:
                descriptor = candidate.get('/FontDescriptor')
                if descriptor:
                    descriptors.append(descriptor.get_object())
        embedded = any('Ahem' in str(value.get('/FontName')) and any(
            key in value for key in ['/FontFile', '/FontFile2', '/FontFile3']) for value in descriptors)
        assert embedded, 'actual supplied Ahem font is embedded'
        assertions += 1
        rows.append({'page': index + 1, 'points': box, 'domText': True, 'embeddedAhem': True})
    renderer = shutil.which('pdftoppm')
    assert renderer, 'analysis-only Poppler must be explicitly installed'
    subprocess.run([renderer, '-png', '-r', '72', str(path), str(output / 'page')],
                   check=True, timeout=45, capture_output=True)
    rendered = sorted(output.glob('page-*.png'))
    assert len(rendered) == 3
    assertions += 1
    for row, image_path in zip(rows, rendered):
        image = Image.open(image_path).convert('RGB')
        red = [(x, y) for y in range(image.height) for x in range(image.width)
               if (lambda pixel: pixel[0] > 240 and pixel[1] < 20 and pixel[2] < 20)(image.getpixel((x, y)))]
        span = max(x for x, _ in red) - min(x for x, _ in red) + 1 if red else 0
        blue = any(b > 240 and r < 20 and g < 20 for r, g, b in image.get_flattened_data())
        green = any(g > 100 and r < 20 and b < 20 for r, g, b in image.get_flattened_data())
        assert image.size == (576, 720), 'physical raster page size'
        assert abs(span - 72) <= 1, 'one-inch SVG ruler is 72 PDF points: ' + str(span)
        assert blue and green, 'decoded blue image and green SVG vector survive'
        assertions += 3
        row.update(rasterPixels=image.size, rulerPoints=span, blueImage=blue, greenVector=green)
    result = {'assertions': assertions, 'failures': 0,
              'pdfSha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'pages': rows}
    temporary = output / 'inspection.tmp'
    temporary.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    temporary.replace(output / 'inspection.json')
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    inspect(args.pdf, args.output)
