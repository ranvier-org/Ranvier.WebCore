"""Reproduce the protocol interface declarations from the pinned WebKit source."""
from pathlib import Path
import argparse
import subprocess
import xml.etree.ElementTree as ET

parser = argparse.ArgumentParser()
parser.add_argument('--webkit', type=Path, required=True)
args = parser.parse_args()
pin = 'b95c91b1c0ee43cc86d25ff7af73038f67a88e04'
names = ['Accessible', 'Application', 'Component', 'Action', 'Value', 'Text', 'EditableText']
interfaces = []
for name in names:
    data = subprocess.check_output(['rtk', 'proxy', 'git', 'show', pin + ':Source/WebCore/accessibility/atspi/xml/' + name + '.xml'], cwd=args.webkit)
    interfaces.append(ET.tostring(ET.fromstring(data).find('interface'), encoding='unicode'))
output = '// AT-SPI protocol declarations from WebKit ' + pin + '.\n'
output += 'static constexpr const char interfaceXml[] = R"ATSPI(<node>\n' + '\n'.join(interfaces) + '\n</node>)ATSPI";\n'
Path(__file__).with_name('AtspiInterfaces.inc').write_text(output, encoding='utf-8', newline='\n')
