# Extracting Firmware from FPGA Bitstreams: A CTF Walkthrough

**CTF Cyberus — "Print Paradox" & "String Symphony" Challenges**

> These two challenges were the most interesting ones at CTF Cyberus for me. They involved extracting firmware from Xilinx FPGA bitstreams — no JTAG, no debug port, just raw `.bit` files and reverse engineering. There were other challenges in the competition too, but I wanted to write this up as a detailed walkthrough because the technique we developed here is reusable and, frankly, I haven't seen it documented elsewhere.
>
> If you want to follow along, the challenge files are in this repo. You'll need Python 3, numpy, and the [Project X-Ray](https://github.com/f4pga/prjxray) toolchain.

---

## Table of Contents

1. [The Setup](#the-setup)
2. [Understanding the Target](#understanding-the-target)
3. [Print Paradox: The Rosetta Stone](#print-paradox-the-rosetta-stone)
   - [Phase 1: FASM Disassembly](#phase-1-fasm-disassembly)
   - [Phase 2: The Correlation Trick](#phase-2-the-correlation-trick)
   - [Phase 3: Extracting Flags](#phase-3-extracting-flags)
   - [The JTAG Flag](#the-jtag-flag)
4. [String Symphony: Applying the Mapping](#string-symphony-applying-the-mapping)
   - [The Lock Admin Panel](#the-lock-admin-panel)
   - [Finding the Hidden Flags](#finding-the-hidden-flags)
5. [ByteStorm: Where We Got Stuck](#bytestorm-where-we-got-stuck)
6. [Flags Summary](#flags-summary)
7. [Key Takeaways](#key-takeaways)

---

## The Setup

Each challenge gave us:
- `board.bit` — A Xilinx 7-series FPGA bitstream
- `board.v` — Partial Verilog source for the SoC
- `software/` — SDK header files (CSR definitions, memory map, linker scripts)

Print Paradox additionally included `firmware.bin` — the actual firmware binary running on the SoC. This turned out to be the key to everything.

## Understanding the Target

From `board.v` and the SDK headers, we identified:
- **FPGA**: Xilinx xc7a35tcpg236-1 (Artix-7, a small FPGA from the Basys 3 / Arty family)
- **SoC**: Built with [LiteX](https://github.com/enjoy-digital/litex), an open-source SoC builder
- **CPU**: VexRiscv (RISC-V RV32I)
- **Firmware storage**: Block RAM (BRAM) — the firmware is baked directly into the FPGA bitstream

The last point is crucial. In a typical LiteX SoC, the BIOS/firmware is stored in FPGA BRAM, which means the firmware bytes are encoded inside the bitstream configuration data. If you can read the BRAM contents from the bitstream, you can extract the firmware without ever powering on the FPGA.

The problem: Xilinx bitstreams are not documented. The BRAM data is scattered across configuration frames in a non-obvious way, and the mapping from "BRAM address" to "bitstream bit position" depends on the specific FPGA part, tile placement, and routing.

## Print Paradox: The Rosetta Stone

This challenge was our breakthrough because it gave us both the bitstream AND the firmware binary. We could use the known firmware as ground truth to reverse-engineer the BRAM encoding.

### Phase 1: FASM Disassembly

[Project X-Ray](https://github.com/f4pga/prjxray) is an open-source project that documents Xilinx 7-series bitstream formats. It includes a **FASM disassembler** that can convert a bitstream back into human-readable FPGA Assembly (FASM) features.

First, we set up the tooling:

```bash
git clone https://github.com/f4pga/prjxray /tmp/prjxray-repo
git clone https://github.com/f4pga/prjxray-db /tmp/prjxray-db
pip install fasm
```

Then we wrote a bitstream parser that:
1. Parses the `.bit` file header to find the FDRI (Frame Data Register Input) payload
2. Reconstructs the FAR (Frame Address Register) sequence using `part.json`
3. Feeds the frame data to prjxray's FASM disassembler

The disassembler outputs features like:

```
BRAM_L_X30Y0.RAMB18_Y0.INIT_05[42] = 1
BRAM_L_X30Y0.RAMB18_Y0.INIT_05[198] = 1
BRAM_R_X37Y10.RAMB18_Y1.INIT_0A[17] = 1
...
```

Each line tells us: in BRAM tile `BRAM_L_X30Y0`, the upper/lower half (`RAMB18_Y0` or `Y1`), initialization row `INIT_05`, bit position 42 is set to 1.

We found **16 significant RAMB18 blocks** (8 tiles × 2 halves) with substantial INIT data — exactly what you'd expect for a 32-bit wide memory using 8 BRAM tiles (each tile provides 4 bits of the word width in 2-bit-wide mode).

### Phase 2: The Correlation Trick

Here's where it gets interesting. We know:
- The firmware binary (`firmware.bin`) — 17,264 bytes = 4,316 32-bit words
- The BRAM INIT data — 16 blocks of initialization values

But we don't know:
- Which BRAM tile provides which firmware bits
- Where in the INIT data the firmware starts (what offset?)
- What stride/interleaving scheme is used

Our solution: **brute-force correlation**.

For each BRAM half, we flatten all INIT values into a single bit array (INIT_00 through INIT_3F, 256 bits each = 16,384 bits total). For each firmware bit position (0–31), we extract the corresponding bit from every firmware word to get a reference vector of 4,316 values (0s and 1s).

Then we slide a window across each BRAM bit array, trying different strides (1, 2, 4) and sub-offsets, correlating against each firmware bit vector using numpy:

```python
for stride in [1, 2, 4]:
    for sub in range(stride):
        sub_arr = bits[sub::stride]
        for start in range(0, 2000):
            chunk = sub_arr[start:start + n_words]
            for fw_bit in range(32):
                matches = np.sum(chunk == fw_bit_vecs[fw_bit])
                if matches >= n_words - 2:  # 4314/4316 match
                    # Found it!
```

The result was stunning: **32/32 firmware bits mapped with 4316/4316 perfect correlation**. Every single bit matched exactly.

The discovered mapping:

| Firmware Bits | BRAM Tile | Half | Start | Stride |
|---------------|-----------|------|-------|--------|
| [1:0] | BRAM_L_X30Y0 | Y0 | 640 | 2 |
| [3:2] | BRAM_L_X30Y0 | Y1 | 640 | 2 |
| [5:4] | BRAM_R_X37Y10 | Y0 | 640 | 2 |
| [7:6] | BRAM_R_X37Y10 | Y1 | 640 | 2 |
| [9:8] | BRAM_R_X37Y5 | Y0 | 640 | 2 |
| [11:10] | BRAM_R_X37Y5 | Y1 | 640 | 2 |
| [13:12] | BRAM_R_X37Y15 | Y0 | 640 | 2 |
| [15:14] | BRAM_R_X37Y15 | Y1 | 640 | 2 |
| [17:16] | BRAM_R_X37Y0 | Y0 | 640 | 2 |
| [19:18] | BRAM_R_X37Y0 | Y1 | 640 | 2 |
| [21:20] | BRAM_L_X6Y5 | Y0 | 640 | 2 |
| [23:22] | BRAM_L_X6Y5 | Y1 | 640 | 2 |
| [25:24] | BRAM_L_X6Y10 | Y0 | 640 | 2 |
| [27:26] | BRAM_L_X6Y10 | Y1 | 640 | 2 |
| [29:28] | BRAM_L_X6Y15 | Y0 | 640 | 2 |
| [31:30] | BRAM_L_X6Y15 | Y1 | 640 | 2 |

Key observations:
- **Start = 640**: Data begins at INIT_05 (640 = 5 × 128 in 2-bit addressing), NOT at INIT_00. The first 5 INIT rows appear to be unused or reserved.
- **Stride = 2**: Each RAMB18 is configured in 2-bit-wide mode. Addresses are interleaved: even positions hold one bit, odd positions hold the other.
- **Y0 = even bits, Y1 = odd bits**: Within each tile, the two RAMB18 halves provide alternating firmware bits.

### Phase 3: Extracting Flags

With the mapping established, we reconstructed the firmware from the bitstream and validated: **17,264/17,264 bytes matched perfectly (100%)**.

Now the flag hunt. The firmware is a LiteX BIOS with a custom "Lock Admin Tool" shell. Plaintext strings revealed commands like `leds`, `reboot`, `challenge`, `status`, and strings like "JTAG is enable/disable", "Good job", and "TOP-SECRET range".

But the actual flags were XOR-encrypted in the binary. We brute-forced all 256 single-byte XOR keys:

```python
for xor_key in range(256):
    xored = bytes(b ^ xor_key for b in firmware)
    if b'DVS{' in xored:
        # Extract the flag
```

This revealed:
- **`DVS{m@ster_of_printf}`** (XOR key 0x65)
- **`DVS{Y0U_arE_An_Ov3rLAP_d3t3cToR}`** (XOR key 0xAC)

### The JTAG Flag

The firmware strings also revealed a JTAG-related challenge built into the admin console:

```
Lock Admin Tool, available commands:
  challenge  - Challenge Command
  status     - Show JTAG status
  leds       - Set Leds value
  reboot     - Reboot the system
  help       - Print this help
```

The `challenge` command appears to check a value and print "Good job : " followed by the flag if JTAG is enabled, or "Uh oh, the value is not correct" if the check fails. The firmware also references the MD5 hash `e208ef11b8997f5e9dc5458481e8c241` and the mysterious encrypted string `N\YqJngCdcY~x>~;:D'zJdo;'_DfEiA9nw` — likely the JTAG challenge's expected input or output.

The flag `DVS{Y0U_arE_An_Ov3rLAP_d3t3cToR}` was found via XOR 0xAC in the same binary, likely the reward for solving the JTAG challenge through the intended interactive path. We got it through static analysis instead.

---

## String Symphony: Applying the Mapping

String Symphony provided the same structure — a `board.bit` for the same FPGA — but **no `firmware.bin`**. This was the whole point: use the mapping discovered from Print Paradox to extract the unknown firmware.

Since these challenges share the "(Overlap)" tag, they use the same LiteX SoC design with the same place-and-route. The BRAM tiles are in the same positions; only their contents differ.

We ran the same extraction pipeline:
1. Disassemble `board.bit` with prjxray → get INIT values for the same 16 RAMB18 blocks
2. Apply the PP-derived mapping → reconstruct 4,316 firmware words
3. Write out 17,264 bytes of firmware

It worked perfectly on the first try.

### The Lock Admin Panel

The extracted firmware contained a "Secure Lock Administration Panel" — a fancier version of the PP admin tool, complete with ASCII art:

```
     ____                           _    __      __         ____    ______   _____       ______
    / __ \____ _____ ___  ____     | |  / /_  __/ /___     /  _/___/_  __/  / ___/____  / ____/
   / / / / __ `/ __ `__ \/ __ \    | | / / / / / / __ \    / // __ \/ /     \__ \/ __ \/ /     
  / /_/ / /_/ / / / / / / / / /    | |/ / /_/ / / / / /  _/ // /_/ / /     ___/ / /_/ / /___   
 /_____/\__,_/_/ /_/ /_/_/ /_/     |___/\__,_/_/_/ /_/  /___/\____/_/     /____/\____/\____/   
                              Secure Lock Administration Panel
```

It had the same command structure — JTAG challenge, memory dump, LED control — plus references to a "TOP-SECRET range" for memory access.

### Finding the Hidden Flags

Same XOR brute-force approach:

- **`DVS{@dmIniStr4t10N-p@ne1-UNlOcK3d}`** (XOR 0x0A) — The admin panel unlock flag
- **`DVS{form@t_on$}`** (XOR 0x8E) — A format string vulnerability flag (the challenge name is a hint!)
- **`DVS{Y0U_arE_An_Ov3rLAP_d3t3cToR}`** (XOR 0xAC) — The shared overlap detection flag

The `form@t_on$` flag name strongly suggests the intended exploitation path involved a **format string vulnerability** in the admin console — the challenge name "String Symphony" is the hint. But since we had the full firmware binary, we could just find the encrypted flags statically.

---

## ByteStorm: Where We Got Stuck

ByteStorm used the same FPGA but — critically — a **different place-and-route**. When we applied the PP-derived BRAM mapping to the ByteStorm bitstream, the extracted firmware was scrambled: word 1 came out as `0x01000003` instead of the expected NOP `0x00000013`.

Analysis showed that the same 8 BRAM tiles were present, but they were connected to different firmware bit positions. The tile-to-nibble assignment had been shuffled by the router.

We attempted:
- **Nibble permutation brute-force** (8! = 40,320 candidates)
- **Intra-nibble bit reordering** (4! per nibble)
- **Greedy optimization** scoring by ASCII string density

We got the NOP pattern correct (`0x00000013`) and partial string fragments, but couldn't resolve the complete 32-bit permutation without a reference binary. The flag for ByteStorm was reportedly obtainable via a **buffer overflow or memory corruption vulnerability** in the firmware's interactive console — a runtime exploit rather than a static extraction. We got this one from another team at the end of the competition.

---

## Flags Summary

| # | Challenge | Flag | XOR Key | Method |
|---|-----------|------|---------|--------|
| 1 | Print Paradox | `DVS{m@ster_of_printf}` | 0x65 | Static firmware extraction |
| 2 | Print Paradox | `DVS{Y0U_arE_An_Ov3rLAP_d3t3cToR}` | 0xAC | Static firmware extraction |
| 3 | String Symphony | `DVS{@dmIniStr4t10N-p@ne1-UNlOcK3d}` | 0x0A | Static firmware extraction |
| 4 | String Symphony | `DVS{form@t_on$}` | 0x8E | Static firmware extraction |
| 5 | String Symphony | `DVS{Y0U_arE_An_Ov3rLAP_d3t3cToR}` | 0xAC | Static firmware extraction |

---

## Key Takeaways

### For CTF Players
1. **If you have a reference binary, use it.** The Print Paradox `firmware.bin` was the Rosetta Stone that unlocked everything else. Without it, we'd have been stuck doing much harder manual reverse engineering.
2. **XOR brute-force is always worth trying.** Single-byte XOR is trivially breakable, but challenge designers use it anyway because the point is the extraction, not the crypto.
3. **"Overlap" is a hint.** The challenges sharing the "(Overlap)" tag use the same FPGA design. Solving one gives you the tools to solve the others.

### For FPGA Security
1. **BRAM contents are extractable from bitstreams.** If your firmware is in BRAM and you distribute the bitstream, the firmware is recoverable. Use bitstream encryption (AES) if confidentiality matters.
2. **The BRAM bit ordering is complex but deterministic.** The stride-2 interleaving, the INIT_05 start offset, the Y0/Y1 half assignment — these are all determined by the FPGA architecture and the place-and-route. With the right tooling (prjxray), it's fully reversible.
3. **Different P&R runs produce different mappings.** ByteStorm showed that re-running place-and-route changes the tile-to-bit assignment, acting as a weak form of obfuscation — but not real security.

### Tools Used
- **[Project X-Ray](https://github.com/f4pga/prjxray)** — Xilinx 7-series bitstream documentation
- **[FASM](https://github.com/chipsalliance/fasm)** — FPGA Assembly format
- **numpy** — Vectorized bit-level correlation (turned a potentially hours-long brute force into seconds)
- **Python 3** — Everything glued together with `rosetta_extract.py`

---

*Written after CTF Cyberus. Thanks to the organizers for creative challenges and to the other teams for the ByteStorm flag. The full extraction script (`rosetta_extract.py`) and challenge files are in this repository.*
