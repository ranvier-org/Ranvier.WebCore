using System.Collections.Immutable;
using System.Reflection;
using System.Reflection.Metadata;
using System.Reflection.PortableExecutable;
using System.Security.Cryptography;
using System.Text.Json;

if (args.Length != 3)
    throw new ArgumentException("assembly, expected-signatures JSON and output JSON are required");
var expected = JsonDocument.Parse(File.ReadAllBytes(args[1])).RootElement;
var names = expected.EnumerateObject().Select(row => row.Name).ToHashSet(StringComparer.Ordinal);
if (names.Count != 349)
    throw new InvalidDataException("All 349 canonical signatures are required");
using var stream = File.OpenRead(args[0]);
using var pe = new PEReader(stream);
var reader = pe.GetMetadataReader();
var functions = new SortedDictionary<string, object>(StringComparer.Ordinal);
var types = new SignatureTypes();
foreach (var handle in reader.MethodDefinitions)
{
    var method = reader.GetMethodDefinition(handle);
    if ((method.Attributes & MethodAttributes.PinvokeImpl) == 0)
        continue;
    var import = method.GetImport();
    var name = reader.GetString(import.Name);
    if (!names.Contains(name))
        continue;
    var signature = method.DecodeSignature(types, (object?)null);
    var metadata = method.GetParameters().Select(reader.GetParameter)
        .Where(parameter => parameter.SequenceNumber > 0).ToDictionary(parameter => parameter.SequenceNumber);
    var parameters = signature.ParameterTypes.Select((kind, index) =>
    {
        if (!metadata.TryGetValue(index + 1, out var parameter))
            throw new InvalidDataException("Missing parameter metadata: " + name);
        var descriptor = parameter.GetMarshallingDescriptor();
        return new
        {
            type = kind,
            input = (parameter.Attributes & ParameterAttributes.In) != 0,
            output = (parameter.Attributes & ParameterAttributes.Out) != 0,
            marshal = descriptor.IsNil ? "" : Convert.ToHexString(reader.GetBlobBytes(descriptor)).ToLowerInvariant()
        };
    }).ToArray();
    if (!functions.TryAdd(name, new
    {
        signature = new { returns = signature.ReturnType, parameters },
        library = reader.GetString(reader.GetModuleReference(import.Module).Name),
        convention = (int)import.Attributes & 0x700
    }))
        throw new InvalidDataException("Duplicate canonical P/Invoke entry point: " + name);
}
if (functions.Count != 349)
    throw new InvalidDataException("Compiled assembly does not expose all 349 canonical P/Invokes");
var result = new
{
    assemblySha256 = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(args[0]))).ToLowerInvariant(),
    functions
};
File.WriteAllText(args[2], JsonSerializer.Serialize(result, new JsonSerializerOptions { WriteIndented = true }));
Console.WriteLine("METADATA_349_EXACT_SIGNATURES_RECORDED");

sealed class SignatureTypes : ISignatureTypeProvider<string, object?>
{
    public string GetPrimitiveType(PrimitiveTypeCode code) => code switch
    {
        PrimitiveTypeCode.Void => "void", PrimitiveTypeCode.Int32 => "int", PrimitiveTypeCode.Int64 => "int64",
        PrimitiveTypeCode.UInt32 => "uint32", PrimitiveTypeCode.UInt64 => "uint64", PrimitiveTypeCode.UInt16 => "uint16",
        PrimitiveTypeCode.Byte => "byte", PrimitiveTypeCode.Single => "float32", PrimitiveTypeCode.Double => "float",
        PrimitiveTypeCode.IntPtr => "nativeint", PrimitiveTypeCode.String => "string",
        _ => throw new InvalidDataException("Unqualified primitive signature: " + code)
    };
    public string GetSZArrayType(string elementType) => elementType + "[]";
    public string GetByReferenceType(string elementType) => elementType + "&";
    public string GetPointerType(string elementType) => elementType + "*";
    public string GetArrayType(string elementType, ArrayShape shape) => throw new InvalidDataException("Non-vector array signature");
    public string GetTypeFromDefinition(MetadataReader reader, TypeDefinitionHandle handle, byte kind) => reader.GetString(reader.GetTypeDefinition(handle).Name);
    public string GetTypeFromReference(MetadataReader reader, TypeReferenceHandle handle, byte kind) => reader.GetString(reader.GetTypeReference(handle).Name);
    public string GetTypeFromSpecification(MetadataReader reader, object? context, TypeSpecificationHandle handle, byte kind) => reader.GetTypeSpecification(handle).DecodeSignature(this, context);
    public string GetModifiedType(string modifier, string unmodified, bool required) => throw new InvalidDataException("Modified P/Invoke signature: " + modifier);
    public string GetPinnedType(string elementType) => throw new InvalidDataException("Pinned P/Invoke signature");
    public string GetGenericInstantiation(string genericType, ImmutableArray<string> arguments) => throw new InvalidDataException("Generic P/Invoke signature");
    public string GetGenericMethodParameter(object? context, int index) => throw new InvalidDataException("Generic method signature");
    public string GetGenericTypeParameter(object? context, int index) => throw new InvalidDataException("Generic type signature");
    public string GetFunctionPointerType(MethodSignature<string> signature) => throw new InvalidDataException("Unexpected direct function-pointer signature");
}
