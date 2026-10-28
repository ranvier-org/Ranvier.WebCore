import pathlib
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from test_domgen import IDL, domgen

output = pathlib.Path(sys.argv[1]).resolve()
source = output / 'webkit/Source/WebCore/dom'
source.mkdir(parents=True, exist_ok=True)
(source / 'Fixture.idl').write_text(IDL)
config = dict(interfaces=['Node', 'Element', 'Document', 'HTMLDocument', 'DOMImplementation', 'Event', 'DOMStringMap'],
              skipDirectories=[], exclude=['AddEventListenerOptions.signal', 'AddEventListenerOptions.webkitTrustedOnly'], atomArguments=[],
              contract=dict(dictionaries=['EventListenerOptions', 'AddEventListenerOptions']))
generator = domgen.Generator(domgen.World(output / 'webkit', config))
generator.lock = {}
generator.lock_structs = {}
generator.run()
(output / 'Dom.fs').write_text(generator.interfaces())
shutil.copy2(pathlib.Path(__file__).parent / 'FableFixture.fs', output / 'Program.fs')
(output / 'Fixture.fsproj').write_text('''<Project Sdk="Microsoft.NET.Sdk">
<PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><FSharpCoreImplicitPackageVersion>8.0.100</FSharpCoreImplicitPackageVersion></PropertyGroup>
<ItemGroup><Compile Include="Dom.fs"/><Compile Include="Program.fs"/></ItemGroup>
<ItemGroup><PackageReference Include="Fable.Core" Version="5.3.0"/></ItemGroup>
</Project>''')
(output / 'package.json').write_text('{"type":"module"}')
print('Wrote browser adapter fixture to', output)
