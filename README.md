# 80286

This is a set of 80286 CPU tests produced by Daniel Balsom (gloriouscow) using the [ArduinoX86](https://github.com/dbalsom/arduinoX86) CPU controller.

![image](https://github.com/user-attachments/assets/71d0204c-5497-40b3-ae03-2486dcc72722)

## Current Version: 1.0.0

- The ```v1_real_mode``` directory contains real mode opcode tests.
- The ```v1_unreal_mode``` directory will (eventually) contain unreal mode opcode tests.
- The ```v1_protected_mode``` directory will (eventually) contain protected-mode tests.

## About the Tests

These tests were produced using a `Harris N80C286-12 (L4252050) (C)1986` CPU. The copyright date implies this should be
an E-stepping 286, but it is not known for certain.

1,000 - 5,000 tests are provided per opcode. Opcodes that are trivial (`INC reg`, `CLI`, etc.) have fewer tests.

The real mode test suite contains 326 instruction forms, containing nearly 1.5 million instruction executions with over
32 million cycle states captured.

This is fewer tests than the previous 8088 test suite, but test coverage is better overall due to improved instruction 
generation methods.

Each test provides initial and final CPU states including registers and memory. Each test also includes cycle activity
for each instruction, including the values of the address and data busses, bus controller signals, miscellaneous pin 
status and processor T-state.

All tests assume 16MB of RAM is mapped to the processor and writable. 

No wait states are incurred during any of the tests. The interrupt and trap flags are not exercised. 

Due to lack of queue status pins on the 286, and the added complexity of the 286's two-stage prefetch queue, the
prefetch queue is not exercised. All instructions start from a jump to the first opcode or prefix of the instruction, 
which flushes the queue. The 286 takes some time after a jump to fill the prefetch queue, so most tests will begin with 
four code fetches.

## Accuracy

Previous tests leaned on the MartyPC emulator to help validate test output. Tests were not emitted unless ArduinoX86
and MartyPC agreed on bus activity and final register state. In this manner the CPU and emulator helped verify each
other, the CPU showing where MartyPC was inaccurate, and MartyPC catching any errors in hardware test generation. 

The test generator for 286 is a new, standalone implementation that does not tie in to any emulator, relying entirely on
the hardware to produce tests. The rationale for rewriting the test generator is to support CPUs that MartyPC does not 
emulate, such as the 286, and eventually, the 386. 

Errors can potentially creep in due to mis-clocked cycles or serial protocol errors. A mis-clock is where the CPU either
doesn't register a clock edge that the ArduinoX86 delivered, or where noise on the clock line causes the CPU to recognize
a clock edge where one was not intended. This can result in missed bus cycles and the readout of incorrect values, which
will make their way into the tests. This is not acceptable, of course, which means that error-checking is essential.

The test generator has a host of error-checking for invalid conditions, but the primary error detection method is a
simple one: each test is generated at least twice and the results compared.  Two operationally identical tests in a row
must be generated for the test to be accepted. This eliminates the vast majority of transient clocking errors. 

I say operationally identical, because periods where bus lines are floating will be, by the nature of physics, random, 
so these differences are ignored.

In the event that any error slips through and is discovered at a later date, the hexadecimal string of their hashes will
be added to a `revocation_list.txt` file, one per line. 
Since a hash uniquely identifies a test, you can load and compare the hash of each test to the hashes in the revocation
list before executing a test.

This way the test suite can be updated for accuracy without requiring large binary updates. Please open issues for any
suspected bugs you may run across.

## Test Methodology

Each test is actually a sequence of two instructions, the instruction under test, and a `HALT` opcode `0xF4`. The 
initial `ram` state includes the opcode byte for the `HALT` instruction.

If the test is a flow control operation, or otherwise triggers an exception, then this initial `HALT` will not be 
executed. Instead, a `HALT` will be injected at the first code fetch after the jump.

The rationale for injecting `HALT` is to provide a visible signal that an instruction has terminated, since the 286
does not expose queue status pins that allow us to detect instruction boundaries. When the ArduinoX86 CPU server detects
the `HALT` bus cycle, it raises the NMI line to the CPU which begins execution of the NMI handler, where we inject the
`STOREALL` instruction and read out the final register state. We capture the flags, `CS` and `IP` pushed to the stack
when calling the NMI handler and use them to patch the registers dumped by `STOREALL`. Doing so gives us an accurate
readout of the state of the registers at the end of the instruction.

Since each test terminates via `HALT`, the last included cycle state will contain the `HALT` bus status that ended cycle
state recording.

### CPU Shutdown

If the CPU enters the `HALT` state with `SP` < 6, the situation is unrecoverable. When the NMI handler attempts to wake
the CPU, the CPU will fail to push the stack frame and will execute a **CPU shutdown**. This is a special `HALT` cycle
with an address of `0x000000` placed on the bus. 

To avoid this situation, `SP` is not allowed to be initialized to less than `0x0008` for any test - this ensures that
the NMI stack frame can be pushed successfully. If during the course of an instruction `SP` becomes < 6, which it can
due to arbitrary ALU operations, a shutdown is unavoidable and the test will be rejected and omitted from the test suite.
Thus the test suite does not have coverage of this particular scenario - however, it is of questionable utility since
your emulated CPU is essentially freezing at this point, requiring a reset.

## Using the Tests

The general concept of a single step test is to set your emulator state to the initial state provided by each test:
 - Set the register values to the values provided in the initial `regs` state.
 - Write the bytes specified in the initial `ram` state to memory.

Then, begin execution at CS:IP as if you have jumped there.
 - End execution at the `HALT` instruction.
 - Compare your emulator's register state to the final `regs` state. 
 - Confirm the values in memory match the final `ram` state.
 - Optionally, confirm your emulator executed the same cycles and/or bus operations as specified in the `cycles` array.

## Processor Modes and Test Subsets

The 286 supported both real and protected modes, with a third "unreal mode" made possible via the `LOADALL` instruction. 

### Real Mode

Real mode is the CPU's default mode where the CPU's security features are mostly disabled. Typically, only the first 
1MB + 64KB of memory was accessible in this mode. In real mode, segment descriptor bases are initialized directly from
the segment register values. The real mode test set will only include the traditional 8088 register file in the `initial`
state. 

### Unreal Mode

Unreal mode is still real mode, however using the `LOADALL` instruction, the segment descriptor cache can be initialized
to arbitrary values. By setting the segment descriptor base address appropriately, access to the entire 16MB address
space is possible in unreal mode.  Unreal mode tests will include the values of the 286's internal `X0`-`X9` registers as
well as the initial descriptor cache entries in the `initial` state.  

### Protected Mode

Protected mode is a mode in which the 286 enforces security for multitasking system operation, enforcing privilege 
level and segment access checks. A full description of protected mode is beyond the scope of this README.  

Creating tests for protected mode is non-trivial, as memory cannot be randomized (or the vast majority of instructions
would immediately triple-fault).

## Randomization

Previous test suites have blindly randomized register and memory state. There is a minor issue in doing so, in regards 
to exercising edge cases such as operands of 0 or `0xFFFF`.  For example, given a 16-bit `ADD` instruction, there's only
a 0.0015% chance that two random 16-bit numbers sum to 0 and set the zero flag.  For a test set of 5,000 executions,
this only gives us a ~7% chance that any of the instructions will do so.

Therefore, register state is now generated using a beta distribution (α=0.65, β=0.65) that weights 16-bit values toward 
the extremes. Additionally, each register has a small chance to be forced to `0x0000` or `0xFFFF` explicitly.

Memory contents, normally randomized, will be forced to all `0x00` bytes or all `0xFF` bytes at a low probability,
excluding bytes below address `0x1024`.

Immediate 8-bit and 16-bit operands, will also be forced to all-bits-zero or all-bits-one in a similar fashion.

Doing this greatly improves test coverage with fewer instruction runs needed than previous test suites. However, it
isn't perfect - for example, `DEC` would need an operand of `1` to set the zero flag.  This could be addressed in the
future, perhaps.

### Stack Pointer

If randomly generated, the stack pointer will be odd with a 50% probability. This is an unnatural condition, and so the
stack pointer is specifically forced even at a very high probability. In addition, the stack pointer will be set to
`0x0006` at minimum. This is to avoid a processor shutdown when the CPU cannot push the NMI handler stack frame
to the stack.

## Instruction Pointer 

The value of IP is not forced to any specific values, and is not allowed to exceed `0xFFF8` to allow the 286 to fill its 
prefetch queue after a jump.

## Interrupt Vector Table Considerations

In real mode, the Interrupt Vector Table (IVT) exists at address `0`.

Instructions are not allowed to begin below address `0x1024` to avoid writing opcode bytes over the IVT.

The IVT is randomized, thus the corresponding handler address can be anywhere in memory, even at odd alignment.
This will never cause a CPU shutdown, as tests that do so are rejected.

## Segment Override Prefixes

1-5 random segment override prefixes are prepended to a percentage of instructions, even if they may not do anything. 
This isn't completely useless - a few bugs have been found where segment overrides had an effect when they should not
have.
Instructions where segment prefixes are obviously superfluous are excepted from prefix generation.

It is possible for the number of segment prefixes to increase the instruction length beyond the maximum of 10 bytes. 
An exception interrupt #6 will occur in this case. 

## LOCK and LOCK Prefixes

The `LOCK` prefix is rarely prepended to instructions. It may appear before, after, or between segment override prefixes.
This is useful for verifying proper handling of lockable vs unlockable instructions.

The status of the CPU's `LOCK` pin is captured within the included cycle traces. Occasionally, the CPU will assert `LOCK` 
automatically without a `LOCK` prefix.

## String Prefixes

`REP`, `REPE`, and `REPNE` prefixes are randomly prepended to compatible instructions. In this event, CX is masked to 7
bits to produce reasonably sized tests (A string instruction with CX==65535 would be several hundred thousand cycles).

## Instruction Prefetching

Bytes fetched beyond the terminating `HALT` opcode will be random. These random bytes are included in the initial `ram`
state. It is not critical if your emulator does not fetch all of them.

## Test Formats

The 286 test suite is published in a binary format, MOO. This format is a simple and extensible chunked format. 
Traditionally, SingleStepTests have been published in JSON format, but this format is not always easily parsed by some
languages, like C or assembler. 

For information on the MOO format, see the [MOO repository](https://github.com/dbalsom/moo) which contains documentation and Rust and Python code
for manipulating MOO files.

If you prefer the traditional JSON format, a script `moo2json.py` is available with which you can convert the test suite
from MOO to JSON. The JSON format is slightly different for 286, mostly in the cycles array where things have been
simplified and less string parsing is required. See the "Cycle Format" section below.

Example JSON test:

```json
  {
    "idx": 0,
    "name": "add [bx+0Eh],bl",
    "bytes": [0, 95, 14, 244],
    "initial": {
      "regs": {
        "ax": 715,
        "bx": 26659,
        "cx": 49548,
        "dx": 64181,
        "cs": 65535,
        "ss": 41175,
        "ds": 65535,
        "es": 43996,
        "sp": 39769,
        "bp": 65535,
        "si": 35262,
        "di": 34633,
        "ip": 38072,
        "flags": 6291
      },
      "ram": [
        [1086632, 0],
        [1086633, 95],
        [1086634, 14],
        [1086635, 244],
        [1086636, 161],
        [1086637, 214],
        [1086638, 248],
        [1086639, 46],
        [1086640, 107],
        [1086641, 166],
        [1075233, 222]
      ],
      "queue": []
    },
    "final": {
      "regs": {
        "ip": 38076,
        "flags": 19
      },
      "ram": [
        [1075233, 1]
      ],
      "queue": []
    },
    "cycles": [
      [13, 1086632, 0, 0, 65535, "CODE", 13, "Ts"],
      [12, 1086634, 4, 0, 24320, "PASV", 15, "Tc"],
      [13, 1086634, 0, 0, 24320, "CODE", 13, "Ts"],
      [12, 1086636, 4, 0, 62478, "PASV", 15, "Tc"],
      [13, 1086636, 0, 0, 62478, "CODE", 13, "Ts"],
      [12, 1086638, 4, 0, 54945, "PASV", 15, "Tc"],
      [13, 1086638, 0, 0, 54945, "CODE", 13, "Ts"],
      [12, 16777215, 4, 0, 12024, "PASV", 15, "Tc"],
      [14, 1086640, 0, 0, 12024, "PASV", 15, "Ti"],
      [13, 1086640, 0, 0, 12024, "CODE", 13, "Ts"],
      [12, 1075233, 4, 0, 42603, "PASV", 7, "Tc"],
      [13, 1075233, 0, 0, 42603, "MEMR", 5, "Ts"],
      [12, 16777215, 4, 0, 56972, "PASV", 7, "Tc"],
      [14, 16777215, 0, 0, 56939, "PASV", 7, "Ti"],
      [14, 1075233, 0, 0, 56939, "PASV", 7, "Ti"],
      [13, 1075233, 0, 0, 57042, "MEMW", 6, "Ts"],
      [12, 16777215, 1, 0, 256, "PASV", 7, "Tc"],
      [14, 2, 0, 0, 468, "PASV", 7, "Ti"],
      [13, 2, 0, 0, 468, "HALT", 4, "Ts"]
    ],
    "hash": "626be5084b331080eb08256c12a62d24afdf2a03"
  },
```
- `idx`: The numerical index of the test within the test file.
- `name`: A user-readable disassembly of the instruction.
- `bytes`: The raw bytes that make up the instruction.
- `initial`: The register and memory state before instruction execution.
- `final`: Changes to registers and memory after instruction execution.
    - Registers and memory locations that are unchanged from the initial state are not included in the final state.
    - The entire value of `flags` is provided if any flag has changed.
- `exception`: An optional key that contains exception data if an exception occurred. See 'Exception Format' below.
- `hash`: A SHA1 hash of the original `MOO` test chunk data. It should uniquely identify any test in the suite.

### Exception Format

The `exception` key is a convenience feature provided so you do not have to attempt exception detection yourself. 
If an exception occurred during instruction execution, the exception number will be given along with the address of the
flags register pushed to the stack. This can assist in masking undefined flag values that may exist in the flags
register that might otherwise cause memory validation to fail.

```json
    "exception": {
      "number": 13,
      "flag_address": 461420
    },
```

### Cycle Format

If you are not interested in writing a cycle-accurate emulator, you can ignore this section.

 - Pin bitfield
 - Address Bus
 - Memory RW status
 - IO RW status
 - Data Bus
 - Bus Status string
 - Raw Bus Status value
 - T-state string

The first column is a bitfield representing certain chip pin states. 

 - Bit #0 represents the `ALE` (Address Latch Enable) pin output, which is output by the i82288. This signal
 is asserted on `Ts` to instruct the AT's address latches to store the current address. This is necessary since address
 calculations are pipelined, so on `Tc` the address of the next bus transaction may be on the address lines.

 The i82288's `ALE` output is not perfectly synchronized with CPU cycles. In these tests, it is normalized to align such 
 that `ALE` will always read high at `Ts`. 

 - Bit #1 represents the `BHE` pin output, which is active-low. `BHE` is asserted to activate the upper byte of the data
 bus. If a bus cycle begins at an even address with BHE active, it is a 16-bit transfer. If a bus cycle begins at an odd
 address with `BHE` active, it is an 8-bit transfer, where the high (odd) byte of the data bus is active.  If a bus cycle
 begins at an even address with `BHE` inactive, it is an 8-bit transfer where the low (even) byte of the data bus is
 active. It is important to handle this logic correctly - the inactive half of the bus, if any, should be masked/ignored
 when validating against the tests.

 - Bit #2 represents the `READ`Y pin. The ArduinoX86 arbitrates the `READY` line every bus cycle, so you will see it toggle
 on and off quite a bit. There are no wait states in the tests, so this is just a curiosity you can ignore.

 - Bit #3 represents the `LOCK` pin. The 286 will assert `LOCK` for memory transactions when a `LOCK`able instruction is 
 prefeixed with the `LOCK` prefix, or in some cases, on its own. 

The `Address Bus` is the value of the 24 address lines, read from the CPU on each cycle. On some cycles the address
lines may float.

`Memory RW status` is a bitfield where bit 2 is the Read signal and bit 0 is the Write signal. Bit 1 is unused.
`IO RW status` is a bitfield where bit 2 is the Read signal and bit 0 is the Write signal. Bit 1 is unused.

The `Data Bus` is the value of the 16 data bus lines, read from the CPU on each cycle. On some cycles, and given the 
state of BHE, some data bus lines may float.

The `Bus Status string` is a decoded bus status for human-readibility. These will be eight values, INTA, IOR, IOW, MEMR,
MEMW, HALT, CODE, or PASV. 

The `Raw Bus Status Value` is a bitfield containing the raw bus status, which may be of some interest as there are more
possible states than what are decoded as strings.  

 - Bit 0 represents the `S0` pin. 
 - Bit 1 represents the `S1` pin. 
 - Bit 2 represents the `M/IO` pin.
 - Bit 3 represents the `CODE/INTA` pin. 

The `T-state string` is a convenience string that provides the CPU T-state. This is not a status that is provided
directly by the CPU, but is easily calculated based on bus status. The values will be either `Ts`, `Tc`, or `Ti`.

No queue status is provided. The 286 does not make queue status available.

## Undefined Instructions

Unlike the 8088, the 80286 has an UD or Invalid Opcode exception, interrupt #6. Most invalid forms of instructions will
generate this exception. Opcodes that will only generate the UD exception are not included in the test suite.

## Exceptions

On the 286, nearly any instruction can potentially execute an exception. Any 16-bit instruction with a memory operand
will execute an exception if the address of the operand is `0xFFFF`.  When an exception occurs, the test cycle traces
continue through fetching the IVT value for the exception, fetching an injected `HALT` opcode at the ISR address, up
until the final `HALT` bus state. 

The IP pushed to the stack during exception execution is always the IP of the faulting instruction.

Exception execution is noted in both MOO and JSON format tests, with the exception number provided as well as the
address of the flags register pushed to the stack. This is to assist in masking the flag value to handle undefined flags
in instructions such as `DIV`. 

## Specific Instruction Notes

 - **0F**: This is the first byte of the 286's extended opcode range. Extended opcodes will have a four hex-digit filename such as `0F04.MOO`.
    - **`F1 0F 04`**: The `STOREALL` instruction is not included in the real mode test set.
    - **`0F 05`**: The `LOADALL` instruction is not included in real mode test set.
 - **54**: `PUSH SP` has slightly different behavior than earlier Intel CPUs. The value pushed to the stack is the value of SP before the push.
 - **6C-6F, A4-A7, AA-AF**: `CX` is masked to 7 bits. This provides a reasonable test length, as the full 65535 value in `CX` with a `REP` prefix could result in several thousand cycles.
 - **8F, C6, C7**: These forms are only valid for a `reg` field of 0. 5% of tests for these opcodes are allowed to have an invalid `reg` field to help you test your UD exception handling.
 - **D2,D3**: `CL` is not masked. The 286 will internally mask the loop count to 5 bits.
 - **6C, 6D, E4, E5, EC, ED**: All forms of the `IN` instruction should return `0xFF` or `0xFFFF` on IO read.
 - **F0**: The `LOCK` prefix is exercised in this test set, and the status of the `LOCK` pin provided.
 - **F1**: Traditionally an alias for `LOCK`, on the 286 the `F1` opcode relates to the CPU's ICE (In-Circuit Emulation) features. The most practical application of this is the `STOREALL` opcode **`F1 0F 04`**. As such it is not included as a random prefix.
 - **F4**: The `HALT` instruction terminates all instructions in the test suite. The `HALT` instruction is therefore included, and terminates itself.
 - **D4, F6.6, F6.7, F7.6, F7.7** - On the 8088 the return address pushed to the stack on divide exception was the address of the next instruction. On the 286 and later, the address pushed to the stack is the address of the faulting instruction. On the 8088, divisors of `0x80` (for 8-bit division) or `0x8000` (for 16-bit division) generate divide exceptions. On the 286, they do not.

## FAQ
 
### Why not an Intel 286?

Capturing individual cycle states from a CPU running at full speed is non-trivial. To simplify matters, we control
the clock to the CPU via an Arduino and read out the state of the CPU on each clock cycle. 
Deliberatly clocking a CPU via GPIO on a slow microcontroller clocks the CPU at some kilohertz instead of megahertz. 

Intel traditionally manufactured CPUs on an HMOS process, producing chips with dynamic logic gates - these gates 
required minimum cycle times to hold the correct logical state. Clocking them too slowly can cause the CPUs to fail,
making this cycle-by-cycle control scheme infeasible.

To satisfy their customers, primarily IBM, who wanted to guarantee availability of their supply chains, Intel entered
second-source agreements with several manufacturers. These included Siemens, Harris, Oki, Fujitsu, and most famously, AMD.  
These manufacturers were provided masks and were authorized to produce functionally equivalent CPUs.  Some, like
Harris, specialized in CMOS processes. 

A [CMOS process](https://en.wikipedia.org/wiki/CMOS) CPU generally requires less power, but it also can be a fully static
design, meaning that it can be clocked very slowly (or not at all) without losing state or malfunctioning. Therefore, a
CMOS 80C286 was the ideal choice for generating these tests. It just happens that Harris 80C286 CPUs are the most widely
available model. A later model was selected to hopefully be free of the [numerous errata](https://www.pcjs.org/documents/manuals/intel/80286/b2_b3_info/) present in earlier 286 chips.

### Why Are Instructions Longer Than Expected?

The 286 fills its instruction prefetch queue of 6 bytes after a jump. Thus every instruction execution will begin with
several code fetch bus cycles before any opcode is executed. The lack of queue status pins on the 286 prevents the
precise queue status and instruction execution tracking that was possible on the 8088, therefore we use a `HALT`
instruction after the instruction under test to determine when execution has ended. `HALT` is specified to take 
two cycles on the 286, so that also adds to the cycle count.

Some instruction executions may generate interrupts or exceptions. Test cycles in this case continue through fetching
the IVT entry for the exception, jumping there, and then executing a `HALT` at the corresponding ISR.

### How do I handle instructions with undefined flags that generate exceptions?

Instructions that generate exceptions will push the value of the flags register to the stack. If the flags register
contains undefined flag values, this may present a difficulty for emulator authors who have yet to implement undefined
flag behavior.

Exceptions are noted in the test files for you, with the exception number that was executed and the address of the flag
word. You can use this address to mask the undefined flags before comparing your final `ram` state. 

### When will we see protected mode tests?

Creating protected mode tests is non-trivial, as memory cannot simply be randomized - valid descriptor tables must be 
generated in memory to avoid instructions immediately triple-faulting. I cannot say when protected mode tests will 
appear, all I can do is promise that I'll work on it.  Protected mode tests may be generated with the assistance of the 
MartyPC emulator to dump values from real descriptor tables, once MartyPC has 286 support.




