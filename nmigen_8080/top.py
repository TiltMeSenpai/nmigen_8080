from enum import Enum

from nmigen import *
from nmigen.sim import *

from .rom import I8080_ROM

class OpBlock(Enum):
    # Possible decoder op blocks
    # Drive from core state machine, never read
    # This results in synth optimizing this out
    DECODE = 1
    CARRY_BIT = 2
    INR = 3
    DCR = 4
    CMA = 5
    DAA = 6
    HLT = 7
    MOV_r_M = 8
    MOV_M_r = 9
    MOV_r_r = 10
    STAX = 11
    LDAX = 12
    ALU_REG = 13
    BIT_ROT = 14
    PUSH = 15
    POP = 16
    DAD = 17
    INX = 18
    DCX = 19
    XCHG = 20
    XTHL = 21
    SPHL = 22
    MVI_M_i = 23
    MVI_r_i = 24
    ALU_IMM = 25
    LXI = 26
    DIRECT = 27
    PCHL = 28
    JMP = 29
    JMP_COND = 30
    CALL = 31
    CALL_COND = 32
    RET = 33
    RET_COND = 34
    RST = 35
    EI_DI = 36
    IO = 37
    NOP = 38

class I8080(Elaboratable):
    # Intel 8080-based Softcore
    # Bus Notes:
    # - SYNC denotes a status byte and the start of a memory cycle.
    # - Contents of DATA during SYNC determine direction and usage of memory
    # - 1 stall cycle follows SYNC
    # - If DATA is not ready after this cycle hold HOLD high until DATA is processed
    # Status Bit Notes:
    # - Status Bits are nearly identical to the original 8080
    # - status[0]: INTA (Interrupt Acknowledge)
    # - status[1]: WON  (Write/Output Negate) 0 = Write or Output
    # - status[2]: STACK (Memory belongs to stack)
    # - status[3]: HLTA (Halt Acknowledge)
    # - status[4]: OUT  (Output)
    # - status[5]: CODE (Data is being executed as code)
    # - status[7]: MEMR (Data is memory of some type [Code/RAM/Stack])
    def __init__(self):
        # External signals
        self.data_in  = Signal(8)
        self.data_out = Signal(8)
        self.addr     = Signal(16)
        self.inte     = Signal()
        self.int      = Signal()
        self.hold     = Signal()
        self.wait     = Signal()
        self.sync     = Signal()
        self.rst      = Signal()

        # ALU signals
        self._acc   = Signal(8)
        self._act   = Signal(8)
        self._flags = Signal(8)
        self._tmp   = Signal(8)

        # Registers
        self._w  = Signal(8, reset_less=True)
        self._z  = Signal(8, reset_less=True)
        self._wz = Cat(self._z, self._w)

        self._b  = Signal(8, reset_less=True)
        self._c  = Signal(8, reset_less=True)
        self._bc = Cat(self._c, self._b)

        self._d  = Signal(8, reset_less=True)
        self._e  = Signal(8, reset_less=True)
        self._de = Cat(self._e, self._d)

        self._h  = Signal(8, reset_less=True)
        self._l  = Signal(8, reset_less=True)
        self._hl = Cat(self._l, self._h)

        self._sp = Signal(16, reset_less=True)
        self._pc = Signal(16, reset=0x100)

        self._reg_array = Array([
            self._b,
            self._c,
            self._d,
            self._e,
            self._h,
            self._l,
            Signal(8),
            self._acc,
        ])
        
        self._rp_array = Array([
            self._bc,
            self._de,
            self._hl,
            self._sp
        ])

        self._state = Signal(range(18), reset=1)

    def ALU(self, m, op, i, incoming_state):
        with m.Case(incoming_state):
            with m.Switch(op):
                with m.Case(0b000): # ADD
                    m.d.sync += [
                        Cat(self._tmp, self._flags[0]).eq(self._acc + i),
                        self._state.eq(incoming_state + 1)
                    ]
                with m.Case(0b001): # ADC
                    m.d.sync += [
                        Cat(self._tmp, self._flags[0]).eq(self._acc + i + self._flags[0]),
                        self._state.eq(incoming_state + 1)
                    ]
                with m.Case(0b010): # SUB
                    m.d.sync += [
                        Cat(self._tmp, self._flags[0]).eq(self._acc - i),
                        self._state.eq(incoming_state + 1)
                    ]
                with m.Case(0b011): # SBB
                    m.d.sync += [
                        Cat(self._tmp, self._flags[0]).eq(self._acc - i - self._flags[0]),
                        self._state.eq(incoming_state + 1)
                    ]
                with m.Case(0b100): # ANA
                    m.d.sync += [
                        self._tmp.eq(self._acc & i),
                        self._state.eq(incoming_state + 1)
                    ]
                with m.Case(0b101): # XRA
                    m.d.sync += [
                        self._tmp.eq(self._acc ^ i),
                        self._state.eq(incoming_state + 1)
                    ]
                with m.Case(0b110): # ORA
                    m.d.sync += [
                        self._tmp.eq(self._acc | i),
                        self._state.eq(incoming_state + 1)
                    ]
                with m.Case(0b111): # CMP
                    m.d.sync += [
                        Cat(self._tmp, self._flags[0]).eq(self._acc - i),
                        self._state.eq(incoming_state + 1)
                    ]
        with m.Case(incoming_state + 1):
            m.d.sync += [
                self._flags[7].eq(self._tmp[7]),
                self._flags[6].eq(self._tmp == 0),
                self._flags[2].eq(~self._tmp.xor()),
                self._state.eq(1)
            ]
            with m.If(op != 0b111):
                m.d.sync += self._acc.eq(self._tmp)

    def elaborate(self, platform):
        m = Module()

        m.submodules.rom = I8080_ROM(
            self.data_out,
            self.data_in,
            self.addr,
            self.hold,
            self.sync
        )

        instr = Signal(8)
        instr_op = Signal(OpBlock)

        m.d.sync += [
            self.sync.eq(0)
        ]

        with m.If(self.rst):
            m.d.sync += [
                self._w.eq(0),
                self._z.eq(0),
                self._b.eq(0),
                self._c.eq(0),
                self._d.eq(0),
                self._e.eq(0),
                self._h.eq(0),
                self._l.eq(0),
                self._sp.eq(0),
                self._pc.eq(0),
                self._state.eq(0),
                self.data_out.eq(0),
                self.addr.eq(0)
            ]
        with m.Switch(self._state):
            with m.Case(1):
                m.d.sync += [
                    self.addr.eq(self._pc),
                    self.data_out.eq(Cat(self.int, 0b1100_001)),
                    self.sync.eq(1),
                    self._state.eq(2),
                    instr_op.eq(OpBlock.DECODE),
                ]
                with m.If(self.int):
                    m.d.sync += self.inte.eq(0) # Disable interrupts if we begin processing one
            with m.Case(2):
                m.d.sync += [
                    self._pc.eq(self._pc + 1),
                    self._state.eq(3)
                ]
            with m.Case(3):
                m.d.sync += [
                    instr.eq(self.data_in),
                    self._state.eq(4)
                ]
                with m.If(self.hold):
                    m.d.sync += [
                        self._state.eq(3)
                    ]
            # Instructions are decoded at ths point, continue
            with m.Default():
                with m.Switch(instr):
                    with m.Case("0011-111"): # Carry Bit block
                        m.d.sync += [
                            self._state.eq(1),
                            instr_op.eq(OpBlock.CARRY_BIT)
                        ]
                        with m.If(instr[3]):
                            m.d.sync += self._flags[0].eq(~self._flags[0])
                        with m.Else():
                            m.d.sync += self._flags[0].eq(1)
                    with m.Case("00---100"): # INR
                        d = instr[3:6]
                        m.d.sync += instr_op.eq(OpBlock.INR)
                        with m.If(d == 0b110):
                            with m.Switch(self._state):
                                with m.Case(4):
                                    m.d.sync += [
                                        self.addr.eq(self._rp_array[2]),
                                        self.sync.eq(1),
                                        self.data_out.eq(0b1000_0010),
                                        self._state.eq(5)
                                    ]
                                with m.Case(5):
                                    m.d.sync += [
                                        self._state.eq(6)
                                    ]
                                with m.Case(6):
                                    m.d.sync += [
                                        self._tmp.eq(self.data_in),
                                        self._state.eq(7)
                                    ]
                                    with m.If(self.hold):
                                        m.d.sync += self._state.eq(6)
                                with m.Case(7):
                                    m.d.sync += [
                                        self._tmp.eq(self._tmp + 1),
                                        self._flags[7].eq(self._tmp[7]),
                                        self._flags[6].eq(self._tmp == 0),
                                        self._flags[2].eq(~self._tmp.xor()),
                                        self.addr.eq(self._rp_array[2]),
                                        self.sync.eq(1),
                                        self.data_out.eq(0b1000_0000),
                                        self._state.eq(8),
                                    ]
                                with m.Case(8):
                                    m.d.sync += self._state.eq(9)
                                with m.Case(9):
                                    m.d.sync += [
                                        self.data_out.eq(self._tmp),
                                        self._state.eq(1)
                                    ]
                                    with m.If(self.hold):
                                        m.d.sync += self._state.eq(9)
                        with m.Else():
                            m.d.sync += [
                                self._reg_array[d].eq(self._reg_array[d] + 1),
                                self._flags[7].eq(self._reg_array[d][7]),
                                self._flags[6].eq(self._reg_array[d] == 0),
                                self._flags[2].eq(~self._reg_array[d].xor()),
                                self._state.eq(1)
                            ]
                    with m.Case("00---101"): # DCR
                        d = instr[3:6]
                        m.d.sync += instr_op.eq(OpBlock.DCR)
                        with m.If(d == 0b110):
                            with m.Switch(self._state):
                                with m.Case(4):
                                    m.d.sync += [
                                        self.addr.eq(self._rp_array[2]),
                                        self.sync.eq(1),
                                        self.data_out.eq(0b1000_0010),
                                        self._state.eq(5)
                                    ]
                                with m.Case(5):
                                    m.d.sync += [
                                        self._state.eq(6)
                                    ]
                                with m.Case(6):
                                    m.d.sync += [
                                        self._tmp.eq(self.data_in),
                                        self._state.eq(7)
                                    ]
                                    with m.If(self.hold):
                                        m.d.sync += self._state.eq(6)
                                with m.Case(7):
                                    m.d.sync += [
                                        self._tmp.eq(self._tmp - 1),
                                        self._flags[7].eq(self._tmp[7]),
                                        self._flags[6].eq(self._tmp == 0),
                                        self._flags[2].eq(~self._tmp.xor()),
                                        self.addr.eq(self._rp_array[2]),
                                        self.sync.eq(1),
                                        self.data_out.eq(0b1000_0000),
                                        self._state.eq(8),
                                    ]
                                with m.Case(8):
                                    m.d.sync += self._state.eq(9)
                                with m.Case(9):
                                    m.d.sync += [
                                        self.data_out.eq(self._tmp),
                                        self._state.eq(1)
                                    ]
                                    with m.If(self.hold):
                                        m.d.sync += self._state.eq(9)
                        with m.Else():
                            m.d.sync += [
                                self._reg_array[d].eq(self._reg_array[d] - 1),
                                self._flags[7].eq(self._reg_array[d][7]),
                                self._flags[6].eq(self._reg_array[d] == 0),
                                self._flags[2].eq(~self._reg_array[d].xor()),
                                self._state.eq(1)
                            ]
                    with m.Case("00101111"): # CMA
                        m.d.sync += [
                            self._acc.eq(~self._acc),
                            self._state.eq(1),
                            instr_op.eq(OpBlock.CMA)
                        ]
                    with m.Case("01110110"): # HLT
                        m.d.sync += [
                            self.data_out.eq(0b0000_1000),
                            self.wait.eq(1),
                            instr_op.eq(OpBlock.HLT)
                        ]
                    with m.Case("01---110"): # MOV r, M
                        d = instr[3:6]
                        m.d.sync += instr_op.eq(OpBlock.MOV_r_M)
                        with m.Switch(self._state):
                            with m.Case(4):
                                m.d.sync += [
                                    self.addr.eq(self._rp_array[2]),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1000_0010),
                                    self._state.eq(5)
                                ]
                            with m.Case(5):
                                m.d.sync += [
                                    self._state.eq(6)
                                ]
                            with m.Case(6):
                                m.d.sync += [
                                    self._reg_array[d].eq(self.data_in),
                                    self._state.eq(1)
                                ]
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(6)
                    with m.Case("01110---"): # MOV m, r 
                        s = instr[:3]
                        m.d.sync += instr_op.eq(OpBlock.MOV_M_r)
                        with m.Switch(self._state):
                            with m.Case(4):
                                m.d.sync += [
                                    self.addr.eq(self._rp_array[2]),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1000_0000),
                                    self._state.eq(5)
                                ]
                            with m.Case(5):
                                m.d.sync += [
                                    self._state.eq(6)
                                ]
                            with m.Case(6):
                                m.d.sync += [
                                    self.data_out.eq(self._reg_array[s]),
                                    self._state.eq(1)
                                ]
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(6)
                    with m.Case("01------"): # MOV r, r 
                        s = instr[:3]
                        d = instr[3:6]
                        m.d.sync += instr_op.eq(OpBlock.MOV_r_r)
                        m.d.sync += [
                            self._reg_array[d].eq(self._reg_array[s]),
                            self._state.eq(1)
                        ]
                    with m.Case("000-0010"): # STAX
                        m.d.sync += instr_op.eq(OpBlock.STAX)
                        with m.Switch(self._state):
                            with m.Case(4):
                                m.d.sync += [
                                    self.addr.eq(self._rp_array[instr[4]]),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1000_0000),
                                    self._state.eq(5),
                                ]
                            with m.Case(5):
                                m.d.sync += self._state.eq(6)
                            with m.Case(6):
                                m.d.sync += [
                                    self.data_out.eq(self._acc),
                                    self._state.eq(1)
                                ]
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(6)
                    with m.Case("000-1010"): # LDAX
                        m.d.sync += instr_op.eq(OpBlock.LDAX)
                        with m.Switch(self._state):
                            with m.Case(4):
                                m.d.sync += [
                                    self.addr.eq(self._rp_array[instr[4]]),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1000_0010),
                                    self._state.eq(5),
                                ]
                            with m.Case(5):
                                m.d.sync += self._state.eq(6)
                            with m.Case(6):
                                m.d.sync += [
                                    self._acc.eq(self.data_in),
                                    self._state.eq(1)
                                ]
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(6)
                    with m.Case("10------"): # ALU op block
                        op = instr[3:6]
                        s  = instr[:3]
                        m.d.sync += instr_op.eq(OpBlock.ALU_REG)
                        with m.If(s == 0b110):
                            with m.Switch(self._state):
                                with m.Case(4):
                                    m.d.sync += [
                                        self.addr.eq(self._rp_array[2]),
                                        self.sync.eq(1),
                                        self.data_out.eq(0b1000_0010),
                                        self._state.eq(5),
                                    ]
                                with m.Case(5):
                                    m.d.sync += self._state.eq(6)
                                with m.Case(6):
                                    m.d.sync += [
                                        self._act.eq(self.data_in),
                                        self._state.eq(7)
                                    ]
                                    with m.If(self.hold):
                                        m.d.sync += self._state.eq(6)
                                self.ALU(m, op, self.data_in, 7)
                        with m.Else():
                            with m.Switch(self._state):
                                self.ALU(m, op, self._reg_array[s], 4)
                    with m.Case("000--111"): # Accumulator Bit Rotations
                        op = instr[3:5]
                        m.d.sync += instr_op.eq(OpBlock.BIT_ROT)
                        with m.Switch(op):
                            with m.Case(0b00):
                                m.d.sync += [
                                    self._acc.eq(self._acc.rotate_left(1)),
                                    self._flags[0].eq(self._acc[7]),
                                    self._state.eq(1)
                                ]
                            with m.Case(0b01):
                                m.d.sync += [
                                    self._acc.eq(self._acc.rotate_right(1)),
                                    self._flags[0].eq(self._acc[0]),
                                    self._state.eq(1),
                                ]
                            with m.Case(0b10):
                                m.d.sync += [
                                    Cat(self._acc, self._flags[0]).eq(Cat(self._acc, self._flags[0]).rotate_left(1)),
                                    self._state.eq(1)
                                ]
                            with m.Case(0b11):
                                m.d.sync += [
                                    Cat(self._flags[0], self._acc).eq(Cat(self._flags[0], self._acc).rotate_right(1)),
                                    self._state.eq(1)
                                ]
                    with m.Case("11--0101"): # PUSH
                        rp = instr[4:6]
                        m.d.sync += instr_op.eq(OpBlock.PUSH)
                        with m.Switch(self._state):
                            with m.Case(4):
                                m.d.sync += [
                                    self._sp.eq(self._sp - 1),
                                    self._state.eq(5)
                                ]
                            with m.Case(5):
                                m.d.sync += [
                                    self.addr.eq(self._sp),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1000_0100),
                                    self._state.eq(6)
                                ]
                            with m.Case(6):
                                m.d.sync += [
                                    self._state.eq(7),
                                    self._sp.eq(self._sp - 1)
                                ]
                            with m.Case(7):
                                m.d.sync += self._state.eq(8)
                                with m.Switch(rp):
                                    with m.Case(0b00):
                                        m.d.sync += self.data_out.eq(self._b)
                                    with m.Case(0b01):
                                        m.d.sync += self.data_out.eq(self._d)
                                    with m.Case(0b10):
                                        m.d.sync += self.data_out.eq(self._h)
                                    with m.Case(0b11):
                                        m.d.sync += self.data_out.eq(self._flags)
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(7)
                            with m.Case(8):
                                m.d.sync += [
                                    self.addr.eq(self._sp),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1000_0100),
                                    self._state.eq(9)
                                ]
                            with m.Case(9):
                                m.d.sync += [
                                    self._state.eq(10),
                                ]
                            with m.Case(10):
                                m.d.sync += self._state.eq(1)
                                with m.Switch(rp):
                                    with m.Case(0b00):
                                        m.d.sync += self.data_out.eq(self._c)
                                    with m.Case(0b01):
                                        m.d.sync += self.data_out.eq(self._e)
                                    with m.Case(0b10):
                                        m.d.sync += self.data_out.eq(self._l)
                                    with m.Case(0b11):
                                        m.d.sync += self.data_out.eq(self._acc)
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(10)
                    with m.Case("11--0001"): # POP
                        rp = instr[4:6]
                        m.d.sync += instr_op.eq(OpBlock.POP)
                        with m.Switch(self._state):
                            with m.Case(4):
                                m.d.sync += [
                                    self.addr.eq(self._sp),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1000_0110),
                                    self._state.eq(5)
                                ]
                            with m.Case(5):
                                m.d.sync += [
                                    self._state.eq(6),
                                    self._sp.eq(self._sp + 1)
                                ]
                            with m.Case(6):
                                m.d.sync += self._state.eq(7)
                                with m.Switch(rp):
                                    with m.Case(0b00):
                                        m.d.sync += self._c.eq(self.data_in)
                                    with m.Case(0b01):
                                        m.d.sync += self._e.eq(self.data_in)
                                    with m.Case(0b10):
                                        m.d.sync += self._l.eq(self.data_in)
                                    with m.Case(0b11):
                                        m.d.sync += self._acc.eq(self.data_in)
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(6)
                            with m.Case(7):
                                m.d.sync += [
                                    self.addr.eq(self._sp),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1000_0110),
                                    self._state.eq(8)
                                ]
                            with m.Case(8):
                                m.d.sync += [
                                    self._sp.eq(self._sp + 1),
                                    self._state.eq(9),
                                ]
                            with m.Case(9):
                                m.d.sync += self._state.eq(1)
                                with m.Switch(rp):
                                    with m.Case(0b00):
                                        m.d.sync += self._b.eq(self.data_in)
                                    with m.Case(0b01):
                                        m.d.sync += self._d.eq(self.data_in)
                                    with m.Case(0b10):
                                        m.d.sync += self._h.eq(self.data_in)
                                    with m.Case(0b11):
                                        m.d.sync += self._flags.eq(self.data_in)
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(9)
                    with m.Case("00--1001"): # DAD
                        rp = instr[4:6]
                        m.d.sync += [
                            Cat(self._hl, self._flags[0]).eq(self._hl + self._rp_array[rp]),
                            self._state.eq(1),
                            instr_op.eq(OpBlock.DAD)
                        ]
                    with m.Case("00--0011"): # INX
                        rp = instr[4:6]
                        m.d.sync += [
                            self._rp_array[rp].eq(self._rp_array[rp] + 1),
                            self._state.eq(1),
                            instr_op.eq(OpBlock.INX)
                        ]
                    with m.Case("00--1011"): # DCX
                        rp = instr[4:6]
                        m.d.sync += [
                            self._rp_array[rp].eq(self._rp_array[rp] - 1),
                            self._state.eq(1),
                            instr_op.eq(OpBlock.DCX)
                        ]
                    with m.Case("11101011"): # XCHG
                        m.d.sync += [
                            Cat(self._rp_array[1], self._rp_array[2]).eq(Cat(self._rp_array[2], self._rp_array[1])),
                            self._state.eq(1),
                            instr_op.eq(OpBlock.XCHG)
                        ]
                    with m.Case("11100011"): # XTHL
                        m.d.sync += instr_op.eq(OpBlock.XTHL)
                        with m.Switch(self._state):
                            with m.Case(4):
                                m.d.sync += [
                                    self.addr.eq(self._sp),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1000_0010),
                                    self._state.eq(5)
                                ]
                            with m.Case(5):
                                m.d.sync += [
                                    self._sp.eq(self._sp + 1),
                                    self._state.eq(6)
                                ]
                            with m.Case(6):
                                m.d.sync += [
                                    self._z.eq(self.data_in),
                                    self._state.eq(7)
                                ]
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(6)
                            with m.Case(7):
                                m.d.sync += [
                                    self.addr.eq(self._sp),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1000_0010),
                                    self._state.eq(8)
                                ]
                            with m.Case(8):
                                m.d.sync += [
                                    self._state.eq(9)
                                ]
                            with m.Case(9):
                                m.d.sync += [
                                    self._w.eq(self.data_in),
                                    self._state.eq(10)
                                ]
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(9)
                            with m.Case(10):
                                m.d.sync += [
                                    self.addr.eq(self._sp),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1000_0000),
                                    self._state.eq(11)
                                ]
                            with m.Case(11):
                                m.d.sync += [
                                    self._sp.eq(self._sp - 1),
                                    self._state.eq(12)
                                ]
                            with m.Case(12):
                                m.d.sync += [
                                    self.data_out.eq(self._h),
                                    self._state.eq(13)
                                ]
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(12)
                            with m.Case(13):
                                m.d.sync += [
                                    self.addr.eq(self._sp),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1000_0000),
                                    self._state.eq(14)
                                ]
                            with m.Case(14):
                                m.d.sync += [
                                    self._state.eq(15)
                                ]
                            with m.Case(15):
                                m.d.sync += [
                                    self.data_out.eq(self._l),
                                    self._rp_array[2].eq(self._wz),
                                    self._state.eq(1)
                                ]
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(15)
                    with m.Case("11111001"): # SPHL
                        m.d.sync += [
                            self._sp.eq(self._rp_array[2]),
                            self._state.eq(1),
                            instr_op.eq(OpBlock.SPHL)
                        ]

                    with m.Case("00110110"): # MVI M, data
                        m.d.sync += instr_op.eq(OpBlock.MVI_M_i)
                        with m.Switch(self._state):
                            with m.Case(4):
                                m.d.sync += [
                                    self.addr.eq(self._pc),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1100_0010),
                                    self._state.eq(5)
                                ]
                            with m.Case(5):
                                m.d.sync += [
                                    self._pc.eq(self._pc + 1),
                                    self._state.eq(6)
                                ]
                            with m.Case(6):
                                m.d.sync += [
                                    self._tmp.eq(self.data_in),
                                    self._state.eq(7)
                                ]
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(6)
                            with m.Case(7):
                                m.d.sync += [
                                    self.addr.eq(self._rp_array[2]),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1000_0000),
                                    self._state.eq(8)
                                ]
                            with m.Case(8):
                                m.d.sync += [
                                    self._state.eq(9)
                                ]
                            with m.Case(9):
                                m.d.sync += [
                                    self.data_out.eq(self._tmp),
                                    self._state.eq(1)
                                ]
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(9)
                    with m.Case("00---110"): # MVI r, data
                        d = instr[3:6]
                        m.d.sync += instr_op.eq(OpBlock.MVI_r_i)
                        with m.Switch(self._state):
                            with m.Case(4):
                                m.d.sync += [
                                    self.addr.eq(self._pc),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1100_0010),
                                    self._state.eq(5)
                                ]
                            with m.Case(5):
                                m.d.sync += [
                                    self._pc.eq(self._pc + 1),
                                    self._state.eq(6)
                                ]
                            with m.Case(6):
                                m.d.sync += [
                                    self._reg_array[d].eq(self.data_in),
                                    self._state.eq(1)
                                ]
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(6)
                    with m.Case("11---110"): # Immediate ALU group
                        op = instr[3:6]
                        m.d.sync += instr_op.eq(OpBlock.ALU_IMM)
                        with m.Switch(self._state):
                            with m.Case(4):
                                m.d.sync += [
                                    self.addr.eq(self._pc),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1100_0010),
                                    self._state.eq(5)
                                ]
                            with m.Case(5):
                                m.d.sync += [
                                    self._pc.eq(self._pc + 1),
                                    self._state.eq(6)
                                ]
                            with m.Case(6):
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(6)
                                with m.Else():
                                    m.d.sync += [
                                        self._tmp.eq(self.data_in),
                                        self._state.eq(7)
                                    ]
                            self.ALU(m, op, self.data_in, 7)
                    with m.Case("00--0001"): # LXI
                        rp = instr[4:6]
                        m.d.sync += instr_op.eq(OpBlock.LXI)
                        with m.Switch(self._state):
                            with m.Case(4):
                                m.d.sync += [
                                    self.addr.eq(self._pc),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1100_0010),
                                    self._state.eq(5)
                                ]
                            with m.Case(5):
                                m.d.sync += [
                                    self._pc.eq(self._pc + 1),
                                    self._state.eq(6)
                                ]
                            with m.Case(6):
                                m.d.sync += [
                                    self._z.eq(self.data_in),
                                    self._state.eq(7)
                                ]
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(6)
                            with m.Case(7):
                                m.d.sync += [
                                    self.addr.eq(self._pc),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1100_0010),
                                    self._state.eq(8)
                                ]
                            with m.Case(8):
                                m.d.sync += [
                                    self._pc.eq(self._pc + 1),
                                    self._state.eq(9)
                                ]
                            with m.Case(9):
                                m.d.sync += [
                                    self._w.eq(self.data_in),
                                    self._state.eq(10)
                                ]
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(9)
                            with m.Case(10):
                                m.d.sync += [
                                    self._rp_array[rp].eq(self._wz),
                                    self._state.eq(1)
                                ]
                    with m.Case("001--010"): # Direct Addressing block
                        op = instr[3:5]
                        m.d.sync += instr_op.eq(OpBlock.DIRECT)
                        with m.Switch(self._state):
                            with m.Case(4):
                                m.d.sync += [
                                    self.addr.eq(self._pc),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1100_0010),
                                    self._state.eq(5),
                                ]
                            with m.Case(5):
                                m.d.sync += [
                                    self._pc.eq(self._pc + 1),
                                    self._state.eq(6)
                                ]
                            with m.Case(6):
                                m.d.sync += [
                                    self._z.eq(self.data_in),
                                    self._state.eq(7)
                                ]
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(6)
                            with m.Case(7):
                                m.d.sync += [
                                    self.addr.eq(self._pc),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1100_0010),
                                    self._state.eq(8),
                                ]
                            with m.Case(8):
                                m.d.sync += [
                                    self._pc.eq(self._pc + 1),
                                    self._state.eq(9)
                                ]
                            with m.Case(9):
                                m.d.sync += [
                                    self._w.eq(self.data_in),
                                    self._state.eq(10)
                                ]
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(9)
                            with m.Case(10):
                                m.d.sync += [
                                    self.addr.eq(self._wz),
                                    self.sync.eq(1),
                                    self.data_out.eq(Cat(0, op[0], 0b1000_00)),
                                    self._state.eq(11)
                                ]
                            with m.Case(11):
                                m.d.sync += [
                                    self._state.eq(12),
                                    self._wz.eq(self._wz + 1)
                                ]
                            with m.Case(12):
                                m.d.sync += self._state.eq(1)
                                with m.Switch(op):
                                    with m.Case(0b00):
                                        m.d.sync += [
                                            self.data_out.eq(self._l),
                                            self._state.eq(13),
                                        ]
                                    with m.Case(0b01):
                                        m.d.sync += [
                                            self._l.eq(self.data_in),
                                            self._state.eq(13)
                                        ]
                                    with m.Case(0b10):
                                        m.d.sync += self.data_out.eq(self._acc)
                                    with m.Case(0b11):
                                        m.d.sync += self._acc.eq(self.data_in)
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(12)
                            with m.Case(13):
                                m.d.sync += [
                                    self.addr.eq(self._wz),
                                    self.sync.eq(1),
                                    self.data_out.eq(Cat(0, op[0], 0b1000_00)),
                                    self._state.eq(14)
                                ]
                            with m.Case(14):
                                m.d.sync += self._state.eq(15)
                            with m.Case(15):
                                m.d.sync += self._state.eq(1)
                                with m.Switch(op):
                                    with m.Case(0b00):
                                        m.d.sync += self.data_out.eq(self._h)
                                    with m.Case(0b01):
                                        m.d.sync += self._h.eq(self.data_in)
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(15)


                    with m.Case("11101001"): # PCHL
                        m.d.sync += [
                            self._pc.eq(self._rp_array[2]),
                            self._state.eq(1),
                            instr_op.eq(OpBlock.PCHL)
                        ]
                    with m.Case("11000011"): # JMP
                        m.d.sync += instr_op.eq(OpBlock.JMP)
                        with m.Switch(self._state):
                            with m.Case(4):
                                m.d.sync += [
                                    self.addr.eq(self._pc),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1100_0010),
                                    self._state.eq(5)
                                ]
                            with m.Case(5):
                                m.d.sync += [
                                    self._pc.eq(self._pc + 1),
                                    self._state.eq(6)
                                ]
                            with m.Case(6):
                                m.d.sync += [
                                    self._z.eq(self.data_in),
                                    self._state.eq(7)
                                ]
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(6)
                            with m.Case(7):
                                m.d.sync += [
                                    self.addr.eq(self._pc),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1100_0010),
                                    self._state.eq(8)
                                ]
                            with m.Case(8):
                                m.d.sync += [
                                    self._pc.eq(self._pc + 1),
                                    self._state.eq(9)
                                ]
                            with m.Case(9):
                                m.d.sync += [
                                    self._w.eq(self.data_in),
                                    self._state.eq(10)
                                ]
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(9)
                            with m.Case(10):
                                m.d.sync += [
                                    self._pc.eq(self._wz),
                                    self._state.eq(1)
                                ]
                    with m.Case("11---010"): # Jump Condtitional block
                        cond = instr[3:6]
                        m.d.sync += instr_op.eq(OpBlock.JMP_COND)
                        with m.Switch(self._state):
                            with m.Case(4):
                                m.d.sync += [
                                    self.addr.eq(self._pc),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1100_0010),
                                    self._state.eq(5)
                                ]
                            with m.Case(5):
                                m.d.sync += [
                                    self._pc.eq(self._pc + 1),
                                    self._state.eq(6)
                                ]
                            with m.Case(6):
                                m.d.sync += [
                                    self._z.eq(self.data_in),
                                    self._state.eq(7)
                                ]
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(6)
                            with m.Case(7):
                                m.d.sync += [
                                    self.addr.eq(self._pc),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1100_0010),
                                    self._state.eq(8)
                                ]
                            with m.Case(8):
                                m.d.sync += [
                                    self._pc.eq(self._pc + 1),
                                    self._state.eq(9)
                                ]
                            with m.Case(9):
                                m.d.sync += [
                                    self._w.eq(self.data_in),
                                    self._state.eq(10)
                                ]
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(9)
                            with m.Case(10):
                                m.d.sync += self._state.eq(1)
                                with m.Switch(cond[1:]):
                                    with m.Case(0b00):
                                        with m.If(self._flags[6] == cond[0]):
                                            m.d.sync += self._pc.eq(self._wz)
                                    with m.Case(0b01):
                                        with m.If(self._flags[0] == cond[0]):
                                            m.d.sync += self._pc.eq(self._wz)
                                    with m.Case(0b10):
                                        with m.If(self._flags[2] == cond[0]):
                                            m.d.sync += self._pc.eq(self._wz)
                                    with m.Case(0b11):
                                        with m.If(self._flags[7] == cond[0]):
                                            m.d.sync += self._pc.eq(self._wz)
                    with m.Case("11001101"): # CALL
                        m.d.sync += instr_op.eq(OpBlock.CALL)
                        with m.Switch(self._state):
                            with m.Case(4):
                                m.d.sync += [
                                    self.addr.eq(self._pc),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1100_0010),
                                    self._state.eq(5)
                                ]
                            with m.Case(5):
                                m.d.sync += [
                                    self._pc.eq(self._pc + 1),
                                    self._state.eq(6)
                                ]
                            with m.Case(6):
                                m.d.sync += [
                                    self._z.eq(self.data_in),
                                    self._state.eq(7)
                                ]
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(6)
                            with m.Case(7):
                                m.d.sync += [
                                    self.addr.eq(self._pc),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1100_0010),
                                    self._state.eq(8)
                                ]
                            with m.Case(8):
                                m.d.sync += [
                                    self._pc.eq(self._pc + 1),
                                    self._state.eq(9)
                                ]
                            with m.Case(9):
                                m.d.sync += [
                                    self._w.eq(self.data_in),
                                    self._state.eq(10)
                                ]
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(9)
                            with m.Case(10):
                                m.d.sync += [
                                    self.addr.eq(self._sp),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1000_0100),
                                    self._state.eq(11)
                                ]
                            with m.Case(11):
                                m.d.sync += [
                                    self._sp.eq(self._sp - 1),
                                    self._state.eq(12)
                                ]
                            with m.Case(12):
                                m.d.sync += [
                                    self.data_out.eq(self._pc[8:]),
                                    self._state.eq(13)
                                ]
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(12)
                            with m.Case(13):
                                m.d.sync += [
                                    self.addr.eq(self._sp),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1000_0100),
                                    self._state.eq(14)
                                ]
                            with m.Case(14):
                                m.d.sync += [
                                    self._sp.eq(self._sp - 1),
                                    self._state.eq(15)
                                ]
                            with m.Case(15):
                                m.d.sync += [
                                    self.data_out.eq(self._pc[:8]),
                                    self._pc.eq(self._wz),
                                    self._state.eq(1)
                                ]
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(15)
                    with m.Case("11---100"): # Call conditional block
                        cond = instr[3:6]
                        m.d.sync += instr_op.eq(OpBlock.CALL_COND)
                        with m.Switch(self._state):
                            with m.Case(4):
                                m.d.sync += [
                                    self.addr.eq(self._pc),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1100_0010),
                                    self._state.eq(5)
                                ]
                            with m.Case(5):
                                m.d.sync += [
                                    self._pc.eq(self._pc + 1),
                                    self._state.eq(6)
                                ]
                            with m.Case(6):
                                m.d.sync += [
                                    self._z.eq(self.data_in),
                                    self._state.eq(7)
                                ]
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(6)
                            with m.Case(7):
                                m.d.sync += [
                                    self.addr.eq(self._pc),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1100_0010),
                                    self._state.eq(8)
                                ]
                            with m.Case(8):
                                m.d.sync += [
                                    self._pc.eq(self._pc + 1),
                                    self._state.eq(9)
                                ]
                            with m.Case(9):
                                m.d.sync += [
                                    self._w.eq(self.data_in),
                                    self._state.eq(1)
                                ]
                                with m.Switch(cond[1:]):
                                    m.d.sync += self._state.eq(1)
                                    with m.Case(0b00):
                                        with m.If(self._flags[6] == cond[0]):
                                            m.d.sync += self._state.eq(10)
                                    with m.Case(0b01):
                                        with m.If(self._flags[0] == cond[0]):
                                            m.d.sync += self._state.eq(10)
                                    with m.Case(0b10):
                                        with m.If(self._flags[2] == cond[0]):
                                            m.d.sync += self._state.eq(10)
                                    with m.Case(0b11):
                                        with m.If(self._flags[7] == cond[0]):
                                            m.d.sync += self._state.eq(10)
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(9)
                            with m.Case(10):
                                m.d.sync += [
                                    self.addr.eq(self._sp),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1000_0100),
                                    self._state.eq(11)
                                ]
                            with m.Case(11):
                                m.d.sync += [
                                    self._sp.eq(self._sp - 1),
                                    self._state.eq(12)
                                ]
                            with m.Case(12):
                                m.d.sync += [
                                    self.data_out.eq(self._pc[8:]),
                                    self._state.eq(13)
                                ]
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(12)
                            with m.Case(13):
                                m.d.sync += [
                                    self.addr.eq(self._sp),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1000_0100),
                                    self._state.eq(14)
                                ]
                            with m.Case(14):
                                m.d.sync += [
                                    self._sp.eq(self._sp - 1),
                                    self._state.eq(15)
                                ]
                            with m.Case(15):
                                m.d.sync += [
                                    self.data_out.eq(self._pc[:8]),
                                    self._pc.eq(self._wz),
                                    self._state.eq(1)
                                ]
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(15)
                    with m.Case("11001001"): # RET
                        m.d.sync += instr_op.eq(OpBlock.RET)
                        with m.Switch(self._state):
                            with m.Case(4):
                                m.d.sync += [
                                    self._sp.eq(self._sp + 1),
                                    self.addr.eq(self._sp + 1),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1000_0110),
                                    self._state.eq(5)
                                ]
                            with m.Case(5):
                                m.d.sync += [
                                    self._state.eq(6)
                                ]
                            with m.Case(6):
                                m.d.sync += [
                                    self._z.eq(self.data_in),
                                    self._state.eq(7)
                                ]
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(6)
                            with m.Case(7):
                                m.d.sync += [
                                    self._sp.eq(self._sp + 1),
                                    self.addr.eq(self._sp + 1),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1000_0110),
                                    self._state.eq(8)
                                ]
                            with m.Case(8):
                                m.d.sync += [
                                    self._state.eq(9)
                                ]
                            with m.Case(9):
                                m.d.sync += [
                                    self._w.eq(self.data_in),
                                    self._state.eq(10)
                                ]
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(9)
                            with m.Case(10):
                                m.d.sync += [
                                    self._pc.eq(self._wz),
                                    self._state.eq(1)
                                ]
                    with m.Case("11---00-"): # Return Block
                        cond = instr[3:6]
                        m.d.sync += instr_op.eq(OpBlock.RET_COND)
                        with m.Switch(self._state):
                            with m.Case(4):
                                with m.Switch(cond[1:]):
                                    m.d.sync += self._state.eq(1)
                                    with m.Case(0b00):
                                        with m.If(self._flags[6] == cond[0]):
                                            m.d.sync += [
                                                self._sp.eq(self._sp + 1),
                                                self._state.eq(5)
                                            ]
                                    with m.Case(0b01):
                                        with m.If(self._flags[0] == cond[0]):
                                            m.d.sync += [
                                                self._sp.eq(self._sp + 1),
                                                self._state.eq(5)
                                            ]
                                    with m.Case(0b10):
                                        with m.If(self._flags[2] == cond[0]):
                                            m.d.sync += [
                                                self._sp.eq(self._sp + 1),
                                                self._state.eq(5)
                                            ]
                                    with m.Case(0b11):
                                        with m.If(self._flags[7] == cond[0]):
                                            m.d.sync += [
                                                self._sp.eq(self._sp + 1),
                                                self._state.eq(5)
                                            ]
                            with m.Case(5):
                                m.d.sync += [
                                    self.addr.eq(self._sp),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1000_0110),
                                    self._state.eq(6)
                                ]
                            with m.Case(6):
                                m.d.sync += [
                                    self._state.eq(7)
                                ]
                            with m.Case(7):
                                m.d.sync += [
                                    self._z.eq(self.data_in),
                                    self._state.eq(8)
                                ]
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(7)
                            with m.Case(8):
                                m.d.sync += [
                                    self._sp.eq(self._sp + 1),
                                    self.addr.eq(self._sp + 1),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1000_0110),
                                    self._state.eq(9)
                                ]
                            with m.Case(9):
                                m.d.sync += [
                                    self._state.eq(10)
                                ]
                            with m.Case(10):
                                m.d.sync += [
                                    self._w.eq(self.data_in),
                                    self._state.eq(11)
                                ]
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(10)
                            with m.Case(11):
                                m.d.sync += [
                                    self._pc.eq(self._wz),
                                    self._state.eq(1)
                                ]
                    with m.Case("11---111"): # RST
                        exp = instr[3:6]
                        m.d.sync += instr_op.eq(OpBlock.RST)
                        with m.Switch(self._state):
                            with m.Case(4):
                                m.d.sync += [
                                    self.addr.eq(self._sp),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1000_0000),
                                    self._state.eq(5)
                                ]
                            with m.Case(5):
                                m.d.sync += [
                                    self._sp.eq(self._sp - 1),
                                    self._state.eq(6)
                                ]
                            with m.Case(6):
                                m.d.sync += [
                                    self.data_out.eq(self._pc[4:]),
                                    self._state.eq(7)
                                ]
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(6)
                            with m.Case(7):
                                m.d.sync += [
                                    self.addr.eq(self._sp),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1000_0000),
                                    self._state.eq(8)
                                ]
                            with m.Case(8):
                                m.d.sync += [
                                    self._sp.eq(self._sp - 1),
                                    self._state.eq(9)
                                ]
                            with m.Case(9):
                                m.d.sync += [
                                    self.data_out.eq(self._pc[:4]),
                                    self._pc.eq(exp << 3),
                                    self._state.eq(1)
                                ]
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(9)
                    with m.Case("1111-011"): # EI/DI
                        m.d.sync += [
                            self.inte.eq(instr[3]),
                            self._state.eq(1),
                            instr_op.eq(OpBlock.EI_DI)
                        ]
                    with m.Case("1101-011"): # IN/OUT
                        io = instr[3]
                        m.d.sync += instr_op.eq(OpBlock.IO)
                        with m.Switch(self._state):
                            with m.Case(4):
                                m.d.sync += [
                                    self.addr.eq(self._pc),
                                    self.sync.eq(1),
                                    self.data_out.eq(0b1010_0010),
                                    self._state.eq(5),
                                ]
                            with m.Case(5):
                                m.d.sync += [
                                    self._pc.eq(self._pc + 1),
                                    self._state.eq(6)
                                ]
                            with m.Case(6):
                                m.d.sync += [
                                    self._w.eq(self.data_in),
                                    self._state.eq(7)
                                ]
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(6)
                            with m.Case(7):
                                m.d.sync += [
                                    self.addr.eq(Cat(self._w, self._w)),
                                    self.data_out.eq(Cat(*[0, io, 0, ~io, 0, 0, io, 0][::-1])),
                                    self.sync.eq(1),
                                    self._state.eq(8)
                                ]
                            with m.Case(8):
                                m.d.sync += self._state.eq(9)
                            with m.Case(9):
                                m.d.sync += self._state.eq(1)
                                with m.If(io):
                                    m.d.sync += self._acc.eq(self.data_in)
                                with m.Else():
                                    m.d.sync += self.data_out.eq(self._acc)
                                with m.If(self.hold):
                                    m.d.sync += self._state.eq(9)
                    with m.Default(): # NOP
                        m.d.sync += [
                            self._state.eq(1),
                            instr_op.eq(OpBlock.NOP)
                        ]

        return m
        

if __name__ == "__main__":
    import sys
    sys.setrecursionlimit(4096)
    sim = Simulator(I8080())
    sim.add_clock(5e-5)
    with sim.write_vcd("trace.vcd"):
        sim.run_until(1, run_passive=True)
