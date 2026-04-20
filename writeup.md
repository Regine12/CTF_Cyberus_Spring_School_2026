# CTF Cyberus — Software Challenges Writeup (Short)

## Overall Achievement

Solved all 4 Software category challenges: **Print Paradox**, **String Symphony**, **ByteStorm**, and **Code Catastrophe** (all "Overlap" variants). Built an FPGA firmware extraction pipeline from scratch using a "Rosetta Stone" correlation technique: using known firmware binaries as ground truth, we reverse-engineered the Xilinx 7-series BRAM bit mapping via prjxray FASM disassembly + numpy vectorized correlation, achieving **100% byte-accurate firmware extraction**.

- **Print Paradox** & **Code Catastrophe** — provided firmware.bin, flags extracted directly via XOR brute-force
- **String Symphony** — applied PP-derived BRAM mapping, extracted firmware on first try
- **ByteStorm** — different P&R required discovering a shifted BRAM start offset (635 vs 640)

---

## Flags (11 total, 6 unique)

| Challenge | Flag | XOR Key |
|-----------|------|---------|
| Print Paradox | `DVS{m@ster_of_printf}` | 0x65 |
| Print Paradox | `DVS{Y0U_arE_An_Ov3rLAP_d3t3cToR}` | 0xAC |
| String Symphony | `DVS{@dmIniStr4t10N-p@ne1-UNlOcK3d}` | 0x0A |
| String Symphony | `DVS{form@t_on$}` | 0x8E |
| String Symphony | `DVS{Y0U_arE_An_Ov3rLAP_d3t3cToR}` | 0xAC |
| ByteStorm | `DVS{@dmIniStr4t10N-p@ne1-UNlOcK3d}` | 0x0A |
| ByteStorm | `DVS{st@ck_on$}` | 0x5D |
| ByteStorm | `DVS{Y0U_arE_An_Ov3rLAP_d3t3cToR}` | 0xAC |
| Code Catastrophe | `DVS{@dmIniStr4t10N-p@ne1-UNlOcK3d}` | 0x0A |
| Code Catastrophe | `DVS{m@ster_of_st@ck}` | 0xAF |
| Code Catastrophe | `DVS{Y0U_arE_An_Ov3rLAP_d3t3cToR}` | 0xAC |

---

## Method

1. **FASM Disassembly** — prjxray converts bitstream → BRAM INIT values (16 RAMB18 blocks)
2. **Bit Correlation** — Correlate each of 32 firmware bits against BRAM bit arrays (stride/offset sweep)
3. **Mapping**: 8 tiles × 2 halves, stride-2 mode, data starts at INIT_05 (offset 640)
4. **Extraction** — Apply mapping to other bitstreams → reconstruct firmware
5. **Flag Recovery** — XOR brute-force (0x00–0xFF) searching for `DVS{...}`

**Key insight**: BRAM data starts at INIT_05 (not INIT_00), uses stride-2 interleaving, and the tile-to-bit assignment is determined by place-and-route — discoverable only through correlation against known firmware.

---

## Tools

- `rosetta_extract.py` — Main script
- [Project X-Ray](https://github.com/f4pga/prjxray) + [prjxray-db](https://github.com/f4pga/prjxray-db) — Bitstream database
- numpy — Vectorized correlation

---

*See `BLOG_WALKTHROUGH.md` for the full detailed walkthrough.*
