# FPGA Firmware Extraction — CTF Cyberus Walkthrough

> Extracting firmware from Xilinx 7-series FPGA bitstreams using bit-level correlation.

This repository contains the challenge files and solution for **Print Paradox (Overlap)** and **String Symphony (Overlap)** from CTF Cyberus — two FPGA reverse-engineering challenges where the goal was to extract hidden flags from firmware embedded inside Xilinx bitstreams.

## Quick Start

```bash
# 1. Clone dependencies
git clone https://github.com/f4pga/prjxray /tmp/prjxray-repo
git clone https://github.com/f4pga/prjxray-db /tmp/prjxray-db

# 2. Install Python deps
pip install numpy fasm

# 3. Run the extraction
cd scripts/
python3 rosetta_extract.py
```

## Repository Structure

```
├── README.md                    # This file
├── WALKTHROUGH.md               # Detailed blog-style writeup
├── GHIDRA_GUIDE.md              # Quick guide to analyzing firmware in Ghidra
├── writeup.md                   # Short CTF writeup
│
├── challenges/
│   ├── print-paradox/           # Print Paradox (Overlap) — has known firmware
│   │   ├── board.bit            # FPGA bitstream
│   │   ├── board.v              # Partial Verilog source
│   │   ├── firmware.bin         # Known firmware (Rosetta Stone)
│   │   └── software/            # SDK headers (CSR, memory map, linker)
│   │
│   └── string-symphony/         # String Symphony (Overlap) — firmware unknown
│       ├── board.bit            # FPGA bitstream
│       ├── board.v              # Partial Verilog source
│       └── software/            # SDK headers
│
├── scripts/
│   └── rosetta_extract.py       # Main extraction script
│
└── output/
    └── (generated firmware bins appear here)
```

## Challenges

### Print Paradox (Overlap)
The "Rosetta Stone" — this challenge provides both a bitstream and the firmware binary, allowing us to reverse-engineer the BRAM bit mapping through correlation.

**Flags found:**
- `DVS{m@ster_of_printf}` (XOR 0x65)
- `DVS{Y0U_arE_An_Ov3rLAP_d3t3cToR}` (XOR 0xAC)

### String Symphony (Overlap)
Same SoC design, different firmware. Applied the Print Paradox mapping to extract the unknown firmware — worked on the first try.

**Flags found:**
- `DVS{@dmIniStr4t10N-p@ne1-UNlOcK3d}` (XOR 0x0A)
- `DVS{form@t_on$}` (XOR 0x8E)
- `DVS{Y0U_arE_An_Ov3rLAP_d3t3cToR}` (XOR 0xAC)

### ByteStorm (Overlap)
Different place-and-route broke the PP-derived mapping. After normalizing the BRAM start offset to 635 (vs PP's 640), we successfully extracted the firmware and recovered the flag via XOR brute-force.

**Flags found:**
- `DVS{@dmIniStr4t10N-p@ne1-UNlOcK3d}` (XOR 0x0A — shared with String Symphony)
- `DVS{st@ck_on$}` (XOR 0x5D — ByteStorm-specific)
- `DVS{Y0U_arE_An_Ov3rLAP_d3t3cToR}` (XOR 0xAC — shared overlap flag)

## How It Works

1. **FASM Disassembly** — Project X-Ray converts the bitstream into BRAM INIT values
2. **Bit-Level Correlation** — numpy correlates each of 32 firmware bits against BRAM bit arrays, discovering the stride-2 interleaved mapping starting at INIT_05
3. **Extraction** — The mapping is applied to other bitstreams sharing the same P&R
4. **Flag Recovery** — XOR brute-force (0x00–0xFF) over extracted firmware

See [WALKTHROUGH.md](WALKTHROUGH.md) for the full technical deep-dive, or [GHIDRA_GUIDE.md](GHIDRA_GUIDE.md) for a quick guide to analyzing the extracted firmware in Ghidra.

## Target Hardware

- **FPGA**: Xilinx xc7a35tcpg236-1 (Artix-7)
- **SoC**: LiteX with VexRiscv (RISC-V RV32I)
- **Firmware**: LiteX BIOS + custom "Lock Admin Tool" shell
