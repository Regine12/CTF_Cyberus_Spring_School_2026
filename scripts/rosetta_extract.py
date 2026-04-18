#!/usr/bin/env python3
"""
Rosetta Stone: Extract firmware from FPGA bitstreams using prjxray.

Uses the Print Paradox firmware.bin as ground truth to discover the BRAM
bit mapping, then applies it to extract firmware from other bitstreams
sharing the same SoC place-and-route.

Requirements:
    pip install numpy fasm
    git clone https://github.com/f4pga/prjxray /tmp/prjxray-repo
    git clone https://github.com/f4pga/prjxray-db /tmp/prjxray-db
"""
import struct, sys, os, json, re
import numpy as np

# ─── Configuration ────────────────────────────────────────────────────

PRJXRAY_REPO = os.environ.get('PRJXRAY_REPO', '/tmp/prjxray-repo')
PRJXRAY_DB   = os.environ.get('PRJXRAY_DB',   '/tmp/prjxray-db')
PART         = 'xc7a35tcpg236-1'
FAMILY       = 'artix7'

sys.path.insert(0, PRJXRAY_REPO)
os.environ['XRAY_DATABASE']     = FAMILY
os.environ['XRAY_PART']         = PART
os.environ['XRAY_DATABASE_DIR'] = PRJXRAY_DB
os.environ['XRAY_PART_YAML']    = f'{PRJXRAY_DB}/{FAMILY}/{PART}/part.yaml'

from prjxray import bitstream, fasm_disassembler
from prjxray.db import Database

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT    = os.path.dirname(SCRIPT_DIR)
CHALLENGES   = os.path.join(REPO_ROOT, 'challenges')
OUTPUT_DIR   = os.path.join(REPO_ROOT, 'output')
FRAME_WORDS  = 101

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ─── Bitstream Parsing ────────────────────────────────────────────────

def bit_to_bitdata(bit_path):
    """Parse a .bit file and return frame data in prjxray format."""
    with open(bit_path, 'rb') as f:
        data = f.read()
    sync = data.find(b'\xaa\x99\x55\x66')
    d = data[sync:]
    pos = 4
    fdri_data = None
    while pos < len(d) - 4:
        h = struct.unpack('>I', d[pos:pos+4])[0]
        pos += 4
        pt = (h >> 29) & 7
        if h == 0x20000000:
            continue
        elif pt == 1:
            op = (h >> 27) & 3
            wc = h & 0x7FF
            if op in (1, 2) and wc > 0:
                pos += wc * 4
        elif pt == 2:
            wc = h & 0x07FFFFFF
            if wc > 0:
                fdri_data = d[pos:pos + wc * 4]
            pos += wc * 4

    part_json = f'{PRJXRAY_DB}/{FAMILY}/{PART}/part.json'
    with open(part_json) as f:
        pj = json.load(f)

    far_sequence = []
    for bus_name in ['CLB_IO_CLK', 'BLOCK_RAM']:
        for region, rev in [('top', True), ('bottom', False)]:
            rows = pj['global_clock_regions'][region]['rows']
            for rs in sorted(rows.keys(), key=int, reverse=rev):
                rd = rows[rs]
                if bus_name not in rd['configuration_buses']:
                    continue
                cols = rd['configuration_buses'][bus_name]['configuration_columns']
                for cs in sorted(cols.keys(), key=int):
                    for minor in range(cols[cs]['frame_count']):
                        far_sequence.append(
                            bitstream.addr_bits2word(bus_name, region, int(rs), int(cs), minor)
                        )

    bitdata = {}
    for idx, far_addr in enumerate(far_sequence):
        off = idx * FRAME_WORDS * 4
        if off + FRAME_WORDS * 4 > len(fdri_data):
            break
        words = struct.unpack(f'>{FRAME_WORDS}I', fdri_data[off:off + FRAME_WORDS * 4])
        if all(w == 0 for w in words):
            continue
        ws = set()
        bs = set()
        for wi, wv in enumerate(words):
            if wv:
                ws.add(wi)
                for b in range(32):
                    if wv & (1 << b):
                        bs.add(wi * 32 + b)
        bitdata[far_addr] = (ws, bs)
    return bitdata


def get_bram_inits(bit_path):
    """Disassemble a bitstream and return all BRAM INIT values."""
    print(f"  Disassembling {os.path.basename(bit_path)}...")
    bitdata = bit_to_bitdata(bit_path)
    db = Database(f'{PRJXRAY_DB}/{FAMILY}', PART)
    disasm = fasm_disassembler.FasmDisassembler(db)
    features = list(disasm.find_features_in_bitstream(bitdata, verbose=False))

    inits = {}
    for f in features:
        fname = f.set_feature.feature
        bit_idx = f.set_feature.start
        parts = fname.split('.')
        if len(parts) != 3:
            continue
        tile, half, init_name = parts
        if not (init_name.startswith('INIT_') or init_name.startswith('INITP_')):
            continue
        key = (tile, half, init_name)
        if key not in inits:
            inits[key] = 0
        inits[key] |= (1 << bit_idx)
    return inits


def extract_bit_array(inits, tile, half):
    """Extract a flat bit array (numpy) for one RAMB18 half."""
    bits = np.zeros(16384, dtype=np.int8)
    grouped = {}
    for (t, h, init_name), value in inits.items():
        if t == tile and h == half:
            grouped[init_name] = value
    for row in range(0x40):
        val = grouped.get(f'INIT_{row:02X}', 0)
        base = row * 256
        for b in range(256):
            bits[base + b] = (val >> b) & 1
    return bits


# ─── Flag Search ──────────────────────────────────────────────────────

def search_flags(data, label=""):
    """Search firmware bytes for DVS{...} flags (plaintext + XOR brute)."""
    flags_found = []
    for xk in range(256):
        xored = bytes(b ^ xk for b in data)
        idx = xored.find(b'DVS{')
        while idx >= 0:
            end = xored.find(b'}', idx)
            if end > 0 and end - idx < 200:
                flag = xored[idx:end + 1]
                if all(0x20 <= c < 0x7f for c in flag):
                    key_str = f"XOR 0x{xk:02x}" if xk else "plaintext"
                    print(f"  🚩 FLAG ({key_str}): {flag.decode()}")
                    flags_found.append((flag.decode(), xk))
            idx = xored.find(b'DVS{', idx + 1)
    return flags_found


def print_strings(data, min_len=10):
    """Print ASCII strings found in firmware."""
    for m in re.finditer(rb'[\x20-\x7e]{%d,}' % min_len, data):
        print(f"    0x{m.start():04x}: {m.group().decode()[:120]}")


# ─── Main ─────────────────────────────────────────────────────────────

def main():
    # ── Step 1: Build the mapping from Print Paradox ──────────────────
    print("=" * 60)
    print("STEP 1: Extract Print Paradox BRAM INIT values")
    print("=" * 60)

    pp_dir = os.path.join(CHALLENGES, 'print-paradox')
    pp_inits = get_bram_inits(os.path.join(pp_dir, 'board.bit'))

    with open(os.path.join(pp_dir, 'firmware.bin'), 'rb') as f:
        pp_fw = f.read()

    fw_words = np.array(
        [struct.unpack('<I', pp_fw[i:i+4])[0] for i in range(0, len(pp_fw) - 3, 4)],
        dtype=np.uint32
    )
    n_words = len(fw_words)
    print(f"  PP firmware: {n_words} words ({len(pp_fw)} bytes)")

    # Find significant BRAM tiles (those with substantial INIT data)
    sig_tiles = {}
    for (t, h, _), v in pp_inits.items():
        k = (t, h)
        sig_tiles[k] = sig_tiles.get(k, 0) + bin(v).count('1')
    sig_keys = sorted([k for k, v in sig_tiles.items() if v > 50])
    print(f"  {len(sig_keys)} significant RAMB18 blocks")

    # ── Step 2: Correlate BRAM bits against firmware bits ─────────────
    print("\n" + "=" * 60)
    print("STEP 2: Bit-level correlation (numpy)")
    print("=" * 60)

    fw_bit_vecs = {}
    for bit in range(32):
        fw_bit_vecs[bit] = ((fw_words >> bit) & 1).astype(np.int8)

    mapping = {}

    for (tile, half) in sig_keys:
        bits = extract_bit_array(pp_inits, tile, half)

        for stride in [1, 2, 4]:
            for sub in range(stride):
                sub_arr = bits[sub::stride]
                L = len(sub_arr)

                for start_addr in range(0, min(2000, L - n_words)):
                    chunk = sub_arr[start_addr:start_addr + n_words]

                    for fw_bit in range(32):
                        if fw_bit in mapping:
                            continue
                        matches = np.sum(chunk == fw_bit_vecs[fw_bit])
                        if matches >= n_words - 2:
                            print(f"  fw_bit {fw_bit:2d}: {tile}.{half} "
                                  f"start={start_addr} stride={stride} sub={sub} "
                                  f"({matches}/{n_words})")
                            mapping[fw_bit] = (tile, half, start_addr, stride, sub)

    print(f"\n  Mapped {len(mapping)}/32 firmware bits")

    if len(mapping) < 16:
        print("  ERROR: Not enough bits mapped. Check prjxray setup.")
        sys.exit(1)

    # ── Step 3: Validate on PP, then extract others ───────────────────
    print("\n" + "=" * 60)
    print("STEP 3: Validate and extract firmware")
    print("=" * 60)

    # Reconstruct PP firmware to validate
    recon = np.zeros(n_words, dtype=np.uint32)
    for fw_bit, (tile, half, start, stride, sub) in mapping.items():
        bits = extract_bit_array(pp_inits, tile, half)
        sub_arr = bits[sub::stride]
        chunk = sub_arr[start:start + n_words]
        recon |= (chunk.astype(np.uint32) << fw_bit)

    recon_bytes = b''.join(struct.pack('<I', int(w)) for w in recon)
    match = sum(1 for a, b in zip(recon_bytes, pp_fw) if a == b)
    pct = 100 * match / len(pp_fw)
    print(f"  PP validation: {match}/{len(pp_fw)} bytes ({pct:.1f}%)")

    if pct < 99.0:
        print("  WARNING: Validation below 99%. Results may be unreliable.")

    # Search PP firmware for flags
    print("\n  Print Paradox flags:")
    pp_flags = search_flags(pp_fw, "PP")

    # Extract String Symphony
    print("\n" + "-" * 60)
    targets = [
        ("String Symphony", "string-symphony"),
    ]

    for name, folder in targets:
        bit_path = os.path.join(CHALLENGES, folder, 'board.bit')
        if not os.path.exists(bit_path):
            print(f"\n  {name}: board.bit not found, skipping")
            continue

        print(f"\n  Extracting {name}...")
        other_inits = get_bram_inits(bit_path)

        other_recon = np.zeros(n_words, dtype=np.uint32)
        for fw_bit, (tile, half, start, stride, sub) in mapping.items():
            bits = extract_bit_array(other_inits, tile, half)
            sub_arr = bits[sub::stride]
            chunk = sub_arr[start:start + n_words]
            other_recon |= (chunk.astype(np.uint32) << fw_bit)

        data = b''.join(struct.pack('<I', int(w)) for w in other_recon)
        out_path = os.path.join(OUTPUT_DIR, f'{folder}_firmware.bin')
        with open(out_path, 'wb') as f:
            f.write(data)
        print(f"  Wrote {len(data)} bytes → {os.path.relpath(out_path, REPO_ROOT)}")

        print(f"\n  {name} flags:")
        search_flags(data, name)

        print(f"\n  {name} strings:")
        print_strings(data)

    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)


if __name__ == '__main__':
    main()
