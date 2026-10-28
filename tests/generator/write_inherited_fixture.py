"""Generate a focused contract for concrete F# inherited-overload implementations."""

from pathlib import Path
import shutil
import sys

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / 'gen'))
import domgen

output = Path(sys.argv[1]).resolve()
source = output / 'webkit/Source/WebCore/dom'
source.mkdir(parents=True, exist_ok=True)
(source / 'Fixture.idl').write_text('''
interface EventTarget {};
interface Node : EventTarget {};
interface mixin ChildNode { undefined remove(); };
interface Element : Node {};
Element includes ChildNode;
interface HTMLElement : Element {};
interface HTMLSelectElement : HTMLElement { undefined remove(); undefined remove(long index); };
''')
config = dict(interfaces=['Node', 'Element', 'HTMLElement', 'HTMLSelectElement'],
              skipDirectories=[], exclude=[], atomArguments=[], contract=dict(mixins={'ChildNode': 'ChildNode'}))
generator = domgen.Generator(domgen.World(output / 'webkit', config))
generator.lock = {}
generator.lock_structs = {}
generator.run()
(output / 'Dom.fs').write_text(generator.interfaces())
shutil.copy2(Path(__file__).parent / 'InheritedFixture.fs', output / 'Program.fs')
(output / 'Fixture.fsproj').write_text('''<Project Sdk="Microsoft.NET.Sdk">
<PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><FSharpCoreImplicitPackageVersion>8.0.100</FSharpCoreImplicitPackageVersion></PropertyGroup>
<ItemGroup><Compile Include="Dom.fs"/><Compile Include="Program.fs"/></ItemGroup>
</Project>''')
print('Wrote inherited implementation fixture to', output)
