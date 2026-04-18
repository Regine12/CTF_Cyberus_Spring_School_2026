# Analyzing Extracted Firmware in Ghidra

> A quick guide to loading and analyzing the RISC-V firmware binaries extracted from these FPGA challenges.

---

## 1. Setup

1. Download [Ghidra](https://ghidra-sre.org/) (10.x+, which has built-in RISC-V support)
2. No extra plugins needed — Ghidra supports RV32I out of the box

## 2. Import the Firmware

1. **File → Import File** → select the extracted `firmware.bin` (or `firmware_extracted.bin`)
2. When prompted for format, choose **Raw Binary**
3. Set the language:
   - **Processor**: `RISCV`
   - **Variant**: `RV32IC` (or `RV32I` — the VexRiscv in these challenges uses RV32I with compressed extensions)
   - **Endian**: `little`
   - **Size**: `32`
4. Click **Options...** and set:
   - **Base Address**: `0x40000000` (this is the SRAM base from `regions.ld` / `mem.h`)

## 3. Memory Map Reference

From the challenge `software/` headers:

| Region | Base Address | Size | Description |
|--------|-------------|------|-------------|
| SRAM | `0x40000000` | 64 KB | Main RAM (firmware loads here) |
| CSR Base | `0xf0000000` | — | Control/Status Registers |
| UART CSR | `0xf0001000` | — | UART TX/RX |
| Timer CSR | `0xf0002800` | — | Timer |
| LEDs CSR | `0xf0003000` | — | GPIO LEDs |

You can add these as memory blocks in **Window → Memory Map → Add** to help Ghidra resolve CSR accesses.

## 4. Initial Analysis

1. Click **Yes** when Ghidra asks to auto-analyze
2. Enable all default analyzers — the important ones are:
   - **Disassembly** — converts raw bytes to RISC-V instructions
   - **Function Creation** — identifies function boundaries
   - **ASCII Strings** — finds plaintext in the binary
   - **Scalar Operand References** — resolves memory addresses

## 5. Finding Interesting Code

### Entry Point
The firmware entry point is at offset `0x0` (address `0x40000000`). Go there first — you'll see the reset vector which sets up the stack pointer and jumps to `main`.

### Strings
**Window → Defined Strings** shows all ASCII strings. Look for:
- `"Lock Admin Tool"` / `"Secure Lock Administration Panel"` — the main menu
- `"challenge"`, `"status"`, `"leds"`, `"reboot"` — command handlers
- `"Good job"` / `"Uh oh"` — challenge response strings
- `"JTAG"` — JTAG enable/disable logic
- `"TOP-SECRET"` — restricted memory range checks

### XOR-Encrypted Flags
The flags are stored XOR'd with a single byte. In Ghidra, look for functions that:
1. Load a byte sequence from a data section
2. XOR each byte with a constant in a loop
3. Call a print/UART function

You can spot these by searching for `xori` instructions with immediate operands like `0x65`, `0x0A`, `0x5D`, `0x8E`, or `0xAC`.

### Command Dispatch
The admin console typically has a dispatch table or `strcmp` chain:
```
if (strcmp(input, "challenge") == 0) { ... }
else if (strcmp(input, "status") == 0) { ... }
```
Find the `strcmp`-like function and cross-reference it to map all commands.

## 6. Challenge-Specific Tips

### Print Paradox — `DVS{m@ster_of_printf}`
- XOR key: `0x65`
- The `printf` in the flag name hints at a **format string vulnerability**
- Look for calls where user input is passed directly as a format string: `printf(user_input)` instead of `printf("%s", user_input)`

### String Symphony — `DVS{form@t_on$}`
- XOR key: `0x8E`
- Another format string challenge — the challenge name "String Symphony" is the hint
- The admin panel has commands that echo user input unsafely

### String Symphony — `DVS{@dmIniStr4t10N-p@ne1-UNlOcK3d}`
- XOR key: `0x0A`
- Look for authentication bypass or hidden commands in the admin panel

### ByteStorm — `DVS{st@ck_on$}`
- XOR key: `0x5D`
- The flag name hints at a **stack overflow / buffer overflow**
- Look for fixed-size stack buffers with unbounded input (e.g., `gets()` or `scanf("%s", buf)`)
- The admin console likely has a command that reads input into a small buffer without length checking

## 7. Useful Ghidra Shortcuts

| Shortcut | Action |
|----------|--------|
| `G` | Go to address |
| `L` | Rename label/function |
| `T` | Set data type |
| `D` | Disassemble at cursor |
| `;` | Add comment |
| `Ctrl+Shift+E` | Search for strings |
| `X` | Show cross-references (xrefs) |
| `F` | Create function at cursor |

## 8. Decompiler

Ghidra's decompiler (**Window → Decompiler**) works well with RISC-V. It will show you pseudo-C for each function, making it much easier to understand the control flow, XOR decryption loops, and vulnerability patterns.

**Tip**: Right-click variables in the decompiler to rename them and retype them — this dramatically improves readability.

---

*For the full extraction methodology, see [WALKTHROUGH.md](WALKTHROUGH.md).*
