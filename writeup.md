# CTF Cyberus — FPGA Challenges Writeup (Short)

## Overall Achievement

Solved **Print Paradox (Overlap)** and **String Symphony (Overlap)** by building an FPGA firmware extraction pipeline from scratch. Developed a "Rosetta Stone" correlation technique: using a known firmware binary as ground truth, we reverse-engineered the Xilinx 7-series BRAM bit mapping via prjxray FASM disassembly + numpy vectorized correlation, achieving **100% byte-accurate firmware extraction** (17,264/17,264 bytes).

Applied the mapping to String Symphony's bitstream, extracting its firmware on the first try and recovering 3 XOR-encrypted flags through static analysis.

**ByteStorm (Overlap)** used a different place-and-route, breaking our mapping. We partially recovered the nibble permutation but couldn't resolve the full bit ordering without a reference binary. The flag was obtained from another team — reportedly via a buffer overflow / memory corruption exploit in the firmware's admin console.

---

## Flags (5 total)

| Challenge | Flag | XOR Key |
|-----------|------|---------|
| Print Paradox | `DVS{m@ster_of_printf}` | 0x65 |
| Print Paradox | `DVS{Y0U_arE_An_Ov3rLAP_d3t3cToR}` | 0xAC |
| String Symphony | `DVS{@dmIniStr4t10N-p@ne1-UNlOcK3d}` | 0x0A |
| String Symphony | `DVS{form@t_on$}` | 0x8E |
| String Symphony | `DVS{Y0U_arE_An_Ov3rLAP_d3t3cToR}` | 0xAC |

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
