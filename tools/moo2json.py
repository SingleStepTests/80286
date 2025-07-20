#!/usr/bin/env python3

# MIT License
#
# Copyright (c) 2025 Daniel Balsom
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
import os
import time
import re
import gzip
import json
import struct
import binascii
import argparse
from concurrent.futures import ProcessPoolExecutor

JSON_INDENT = 2

REG_ORDER = [
    'ax', 'bx', 'cx', 'dx', 'cs', 'ss', 'ds', 'es',
    'sp', 'bp', 'si', 'di', 'ip', 'flags'
]
SEGMENT_MAP    = {0: "ES", 1: "SS", 2: "CS", 3: "DS", 4: "--"}
BUS_STATUS_MAP = {0: "INTA", 1: "IOR", 2: "IOW", 3: "MEMR", 4: "MEMW", 5: "HALT", 6: "CODE", 7: "PASV"}
BUS_STATUS_286_MAP = {
    0x0:  'IRQA', 0x1: 'PASV', 0x2: 'PASV', 0x3: 'PASV',
    0x4:  'HALT', 0x5: 'MEMR', 0x6: 'MEMW', 0x7: 'PASV',
    0x8:  'PASV', 0x9: 'IOR',  0xA: 'IOW',  0xB: 'PASV',
    0xC:  'PASV', 0xD: 'CODE', 0xE: 'PASV', 0xF: 'PASV'
}
T_STATE_MAP      = {0: "Ti", 1: "T1", 2: "T2", 3: "T3", 4: "T4"}
T_STATE_286_MAP  = {0: "Ti", 1: "Ts", 2: "Tc"}
QUEUE_OP_MAP     = {0: "-", 1: "F", 2: "E", 3: "S"}
FLAG_CHARS       = ['R', 'A', 'W']

CYCLE_STRUCT = struct.Struct('<B I B B B B H B B B B')
RE_UNQUOTE   = re.compile(r'"(\[\s*[\d,",\s]+\])"')

def decode_bitfield3(bf: int) -> str:
    return ''.join(FLAG_CHARS[i] if (bf >> (2-i)) & 1 else '-' for i in range(3))

def list_to_str(lst) -> str:
    parts = []
    for v in lst:
        parts.append(f'"{v}"' if isinstance(v,str) else str(v))
    return '[' + ', '.join(parts) + ']'

def decode_exception(mv : memoryview, offset: int, length: int) -> tuple[dict,int]:
    """
    Decode an exception from a MOO `EXCP` chunk.
    Returns the exception code and the flag address.
    """
    if length < 5:
        raise ValueError("Exception chunk too short")
    exc_code = struct.unpack_from('<B', mv, offset)[0]
    offset += 1
    flag_addr = struct.unpack_from('<I', mv, offset)[0]
    offset += 4
    return {'number': exc_code, 'flag_address': flag_addr}, offset

def decode_regs(mv: memoryview, offset: int, length: int) -> tuple[dict,int]:
    bitmask = struct.unpack_from('<H', mv, offset)[0]
    offset += 2
    regs = {}
    for i,name in enumerate(REG_ORDER):
        if bitmask & (1<<i):
            val = struct.unpack_from('<H', mv, offset)[0]
            regs[name] = val
            offset += 2
    return regs, offset

def decode_ram(mv: memoryview, offset: int, length: int) -> tuple[list,list[int]]:
    count = struct.unpack_from('<I', mv, offset)[0]
    offset += 4
    ram = []
    for _ in range(count):
        addr, byte = struct.unpack_from('<I B', mv, offset)
        ram.append([addr, byte])
        offset += 5
    return ram, offset

def decode_queue(mv: memoryview, offset: int, length: int) -> tuple[list[int],int]:
    count = struct.unpack_from('<I', mv, offset)[0]
    offset += 4
    q = list(mv[offset:offset+count])
    offset += count
    return q, offset

def decode_cpu_state(mv: memoryview, offset: int, length: int) -> tuple[dict,int]:
    end = offset + length
    state = {'regs':{}, 'ram':[], 'queue':[]}
    while offset < end:
        tag = bytes(mv[offset:offset+4]).decode('ascii'); offset +=4
        sublen = struct.unpack_from('<I', mv, offset)[0]; offset+=4
        if tag=='REGS':
            regs, _ = decode_regs(mv, offset, sublen)
            state['regs'] = regs
        elif tag=='RAM ':
            ram, _ = decode_ram(mv, offset, sublen)
            state['ram'] = ram
        elif tag=='QUEU':
            q, _ = decode_queue(mv, offset, sublen)
            state['queue'] = q
        offset += sublen
    return state, offset

def decode_cycles(mv: memoryview, offset: int, length: int, cpu_name: str) -> tuple[list,int]:
    """
    Decode the CYCL chunk from a MOO file.
    Returns a list of cycles and the new offset.
    """
    count = struct.unpack_from('<I', mv, offset)[0]
    offset += 4
    cycles = []
    for _ in range(count):
        fields = CYCLE_STRUCT.unpack_from(mv, offset)
        offset += CYCLE_STRUCT.size
        pin, addr, seg_i, mem_bf, io_bf, bhe, dbus, bus_i, t_i, qop_i, qread = fields
        if '286' in cpu_name:
            bus_status = BUS_STATUS_286_MAP.get(bus_i & 0x0F,'PASV')
            raw_status = bus_i & 0x0F
            t_state    = T_STATE_286_MAP.get(t_i & 0x07,'Ti')
            cycles.append([pin, 
                           addr,
                           mem_bf,
                           io_bf,
                           dbus,
                           bus_status, raw_status,
                           t_state])
        else:
            cycles.append([pin, 
                           addr,
                           SEGMENT_MAP.get(seg_i,'--'),
                           decode_bitfield3(mem_bf),
                           decode_bitfield3(io_bf),
                           bhe, dbus,
                           BUS_STATUS_MAP.get(bus_i,'PASV'),
                           T_STATE_MAP.get(t_i,'Ti'),
                           QUEUE_OP_MAP.get(qop_i,'-'),
                           qread])
    return cycles, offset

def parse_moo_bytes(data: bytes) -> tuple[str,list[dict]]:
    """
    Parse MOO binary data in chunks
    """
    mv = memoryview(data)
    if data[:4] != b'MOO ':
        raise ValueError("Not a MOO file")
    offset = 4
    hlen = struct.unpack_from('<I', mv, offset)[0]; offset +=4
    header = mv[offset:offset+hlen]; offset+=hlen

    version    = header[0]
    test_count = struct.unpack_from('<I', header, 4)[0]
    print(f"   Version: {version}, Test count: {test_count}")
    cpu_name   = bytes(header[8:12]).decode('ascii').rstrip()
    tests = []

    while offset < len(data):
        tag    = bytes(mv[offset:offset+4]).decode('ascii'); offset+=4
        length = struct.unpack_from('<I', mv, offset)[0]; offset+=4

        if tag=='TEST':
            # We have a TEST chunk, decode interior chunks until chunk length exhausted
            tidx = struct.unpack_from('<I', mv, offset)[0]
            poff = offset+4
            test = {'idx':tidx}
            while poff < offset+length:
                subt = bytes(mv[poff:poff+4]).decode('ascii'); poff+=4
                slen = struct.unpack_from('<I', mv, poff)[0]; poff+=4
                if subt=='NAME':
                    nl = struct.unpack_from('<I', mv, poff)[0]
                    test['name'] = bytes(mv[poff+4:poff+4+nl]).decode()
                elif subt=='BYTS':
                    cnt = struct.unpack_from('<I', mv, poff)[0]
                    test['bytes'] = list(mv[poff+4:poff+4+cnt])
                elif subt in ('INIT','FINA'):
                    st, _ = decode_cpu_state(mv, poff, slen)
                    test['initial' if subt=='INIT' else 'final'] = st
                elif subt=='CYCL':
                    cycs, _ = decode_cycles(mv, poff, slen, cpu_name)
                    test['cycles'] = cycs
                elif subt=='HASH':
                    raw = mv[poff:poff+slen].tobytes()
                    test['hash'] = binascii.hexlify(raw).decode('ascii')
                elif subt=='EXCP':
                    exc, _ = decode_exception(mv, poff, slen)
                    test['exception'] = exc
                poff += slen
            tests.append(test)
        offset += length
    return cpu_name, tests

def write_condensed(tests: list[dict], out_path: str):
    """
    Pretty-print tests without any trailing commas:
      • Fields in the order idx, name, bytes, initial, final, cycles, hash
      • Commas between fields, none after the last field
      • Commas between cycle entries, none after the last entry
      • Commas between test objects, none after the last object
    """

    def fmt_primitive(v):
        # numbers, booleans, null, strings—all via json.dumps
        return json.dumps(v)

    def fmt_list_inline(lst):
        # inline a JSON array of primitives
        inner = ', '.join(fmt_primitive(x) for x in lst)
        return f'[{inner}]'

    FIELD_ORDER = ['idx', 'name', 'bytes', 'initial', 'final', 'cycles', 'exception', 'hash']

    with open(out_path, 'w') as f:
        f.write('[\n')
        for ti, item in enumerate(tests):
            f.write(f'{" " * (JSON_INDENT)}{{\n')
            # select only present fields, in desired order
            present = [k for k in FIELD_ORDER if k in item]
            for fi, key in enumerate(present):
                is_last_field = (fi == len(present) - 1)
                field_comma  = '' if is_last_field else ','

                if key == 'bytes':
                    out = fmt_list_inline(item['bytes'])
                    f.write(f'{" " * (JSON_INDENT * 2)}"bytes": {out}{field_comma}\n')

                elif key in ('initial', 'final'):
                    st = item[key]
                    f.write(f'{" " * (JSON_INDENT * 2)}"{key}": ' + '{\n')
                    # sub-fields in fixed order
                    SUB_ORDER = ['regs', 'ram', 'queue']
                    sub_present = [s for s in SUB_ORDER if s in st]
                    for si, sk in enumerate(sub_present):
                        is_last_sub = (si == len(sub_present) - 1)
                        sub_comma   = '' if is_last_sub else ','
                        val = st[sk]

                        if sk == 'regs':
                            indent_level = JSON_INDENT * 3
                            regs_json = json.dumps(val, indent=JSON_INDENT)
                            indented = regs_json.replace('\n', f'\n{" " * (indent_level)}')
                            f.write(f'{" " * indent_level}"regs": {indented}{sub_comma}\n')

                        elif sk == 'ram':                      
                            f.write(f'{" " * (JSON_INDENT * 3)}"ram": [\n')
                            for ri, r in enumerate(val):
                                is_last_r = (ri == len(val) - 1)
                                rc = '' if is_last_r else ','
                                f.write(f'{" " * (JSON_INDENT * 4)}{fmt_list_inline(r)}{rc}\n')
                            f.write(f'{" " * (JSON_INDENT * 3)}]{sub_comma}\n')

                        elif sk == 'queue':
                            q = fmt_list_inline(val)
                            f.write(f'{" " * (JSON_INDENT * 3)}"queue": {q}\n')

                    f.write(f'{" " * (JSON_INDENT * 2)}}}{field_comma}\n')

                elif key == 'cycles':
                    f.write(f'{" " * (JSON_INDENT * 2)}"cycles": [\n')
                    for ci, cycle in enumerate(item['cycles']):
                        is_last_cycle = (ci == len(item['cycles']) - 1)
                        cycle_comma   = '' if is_last_cycle else ','
                        f.write(f'{" " * (JSON_INDENT * 3)}{fmt_list_inline(cycle)}{cycle_comma}\n')
                    f.write(f'{" " * (JSON_INDENT * 2)}]{field_comma}\n')

                elif key == 'exception':
                    exception_json = json.dumps(item['exception'], indent=JSON_INDENT)
                    # Calculate whitespace based on JSON_INDENT level.
                    field_indent = ' ' * (JSON_INDENT * 2)  # 2 spaces for the key, plus JSON_INDENT
                    exception_block = exception_json.replace('\n', f'\n{field_indent}')          
                    f.write(f'{field_indent}"exception": {exception_block}{field_comma}\n')

                else:
                    # idx, name, hash
                    out = fmt_primitive(item[key])
                    f.write(f'{" " * (JSON_INDENT * 2)}"{key}": {out}{field_comma}\n')

            # close this object, comma if not the last test
            obj_comma = ',' if ti < len(tests) - 1 else ''
            f.write(f'{" " * (JSON_INDENT)}}}{obj_comma}\n')
        f.write(']\n')

def get_json_basename(fname: str) -> str:
    lc = fname.lower()
    if lc.endswith('.moo.gz'):
        return fname[:-7]
    if lc.endswith('.moo'):
        return fname[:-4]
    return os.path.splitext(fname)[0]

def process_file(args):
    in_path, out_path = args
    # read
    if in_path.lower().endswith('.gz'):
        data = gzip.open(in_path,'rb').read()
    else:
        data = open(in_path,'rb').read()

    try:        
      cpu_name, tests = parse_moo_bytes(data)
    except ValueError as e:
        print(f"Error parsing {in_path}: {e}")
        return
    
    # write condensed JSON
    write_condensed(tests, out_path)
    print(f"[{os.getpid()}] {len(tests)} tests -> {out_path}")

def sort_filenames(filenames):
    """
    Sort names like C0.0.json, C0.1.json, ..., D1.0.json in hex-group order.
    """
    pattern = re.compile(r"(\w{2})(?:\.(\d))?\.(?:json|MOO)(?:\.gz)?$", re.IGNORECASE)
    parsed = []
    for fn in filenames:
        m = pattern.match(fn)
        if not m:
            continue
        group, sub = m.groups()
        sub = sub or '0'
        # convert hex strings to ints so "A" sorts after "9"
        parsed.append((fn, int(group, 16), int(sub, 16)))
    parsed.sort(key=lambda x: (x[1], x[2]))
    return [fn for fn, *_ in parsed]

def update_file_times(directory):
    """
    Touch all files in 'directory' in the order given by sort_filenames,
    bumping their mtime a second apart so that ls -t will list them in hex order.
    """
    names = os.listdir(directory)
    ordered = sort_filenames(names)
    now = time.time()
    for i, fn in enumerate(ordered, start=1):
        full = os.path.join(directory, fn)
        new_t = now + i
        print(f"Touching {fn} -> {new_t}")
        os.utime(full, (new_t, new_t))

def main():
    p = argparse.ArgumentParser(description="MOO->JSON converter")
    p.add_argument('src', help=".MOO/.MOO.gz file or directory")
    p.add_argument('out', help="Output JSON file or directory")
    args = p.parse_args()

    if os.path.isdir(args.src):
        os.makedirs(args.out, exist_ok=True)
        tasks = []
        file_list = os.listdir(args.src)
        if not file_list:
            print(f"No files found in {args.src}")
            return
        for fname in sorted(file_list):
            if not fname.lower().endswith(('.moo','.moo.gz')):
                continue
            base = get_json_basename(fname)
            tasks.append((os.path.join(args.src,fname),
                          os.path.join(args.out, base + '.json')))
        with ProcessPoolExecutor() as pool:
            pool.map(process_file, tasks)
        
        update_file_times(args.out)            
    else:
        os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
        process_file((args.src, args.out))

if __name__=='__main__':
    main()