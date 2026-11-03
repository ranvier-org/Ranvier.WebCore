using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;

var expected = args.Single();
var path = Path.Combine(AppContext.BaseDirectory, "libRanvierWebCoreAtspi.so");
if (!File.Exists(path) || !Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).Equals(expected, StringComparison.OrdinalIgnoreCase))
    throw new InvalidOperationException("Ordinary SDK publish did not preserve the reviewed provider asset.");
var module = NativeLibrary.Load("RanvierWebCoreAtspi", Assembly.GetExecutingAssembly(), null);
try
{
    foreach (var name in new[] { "rv_atspi_bridge_create", "rv_atspi_bridge_set_geometry", "rv_atspi_bridge_bus_name", "rv_atspi_bridge_release" })
        NativeLibrary.GetExport(module, name);
    Console.WriteLine(JsonSerializer.Serialize(new { scope = "SDK asset discovery and dynamic load only", providerSha256 = expected, loaded = true }));
}
finally
{
    NativeLibrary.Free(module);
}
