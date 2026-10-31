"""Lists the named exports of a PE DLL."""
import struct, sys


def exports(path):
    data = open(path, 'rb').read()
    pe = struct.unpack_from('<I', data, 0x3C)[0]
    sections = struct.unpack_from('<H', data, pe + 6)[0]
    optional = struct.unpack_from('<H', data, pe + 20)[0]
    base = pe + 24
    magic = struct.unpack_from('<H', data, base)[0]
    directory = base + (112 if magic == 0x20B else 96)
    rva = struct.unpack_from('<I', data, directory)[0]
    table = base + optional
    spans = [struct.unpack_from('<IIII', data, table + i * 40 + 8) for i in range(sections)]

    def offset(address):
        for size, virtual, raw_size, raw in spans:
            if virtual <= address < virtual + max(size, raw_size):
                return address - virtual + raw
        raise ValueError(address)

    start = offset(rva)
    count, names = struct.unpack_from('<II', data, start + 24)[0], struct.unpack_from('<I', data, start + 32)[0]
    result = []
    for i in range(count):
        name = offset(struct.unpack_from('<I', data, offset(names) + 4 * i)[0])
        result.append(data[name:data.index(b'\0', name)].decode())
    return result


if __name__ == '__main__':
    for name in exports(sys.argv[1]):
        print(name)
