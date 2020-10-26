from nmigen import *
from .bus import I8080_Bus
from .alu import Alu
from .ops import OpBlock

class I8080(Elaboratable):
    def __init__(self, peripherals={}, imem_size = 0x8000):
        self.peripherals = peripherals
        self.imem_size = 0x8000

        self.acc = Signal(8)
        self.flags    = Record([
            ("carry", 1),
            ("0", 1),
            ("parity", 1),
            ("1", 1),
            ("aux_carry", 1),
            ("2", 1),
            ("zero", 1),
            ("sign", 1)
        ])

        self.b = Signal(8)
        self.c = Signal(8)

        self.d = Signal(8)
        self.e = Signal(8)

        self.h = Signal(8)
        self.l = Signal(8)
        
        self.w = Signal(8)
        self.x = Signal(8)

        self.bc = Cat(self.c, self.b)
        self.de = Cat(self.e, self.d)
        self.hl = Cat(self.l, self.h)
        self.wx = Cat(self.x, self.w)

        self.pc = Signal(16)
        self.sp = Signal(16)

        with open("boot.com", "rb") as f:
            self.rom = f.read()

    def elaborate(self, platform):
        m = Module()
        
        m.submodules.bus = bus = I8080_Bus(self.rom, self.peripherals, self.imem_size)
        m.submodules.alu = alu = Alu(self.acc, self.flags[0])

        cycle = Signal(4)
        instr = Record([
            ("b", 3),
            ("a", 3),
            ("op", 2)
        ])
        op = Signal(OpBlock)
        instr_pc = Signal(16)
        instr_data = Signal(8)
        m.d.comb += instr_data.eq(instr)

        reg_array = Array([
            self.b,
            self.c,
            self.d,
            self.e,
            self.h,
            self.l,
            self.flags,
            self.acc,
        ])
        
        rp_array = Array([
            self.bc,
            self.de,
            self.hl,
            self.sp
        ])

        m.d.sync += [
            bus.en.eq(0)
        ]

        branch = Array([
            ~self.flags.zero,
            self.flags.zero,
            ~self.flags.carry,
            self.flags.carry,
            ~self.flags.parity,
            self.flags.parity,
            ~self.flags.sign,
            self.flags.sign
        ])

        with m.FSM():
            with m.State("FETCH"):
                m.d.sync += [
                    bus.addr.eq(self.pc),
                    bus.rw.eq(1),
                    bus.io.eq(0),
                    bus.en.eq(1),
                    instr_pc.eq(self.pc),
                    self.pc.eq(self.pc + 1),
                    cycle.eq(0)
                ]
                m.next = "DECODE"
            with m.State("DECODE"):
                with m.If(bus.done):
                    m.d.sync += instr.eq(bus.data_out) # TODO: Immediate data/addresses could probably be pipelined here
                    m.next = "EXEC"
            with m.State("EXEC"):
                with m.Switch(instr):
                    with m.Case("00 110 100"): # INR M
                        m.d.comb += op.eq(OpBlock.INR)
                        with m.Switch(cycle):
                            with m.Case(0):
                                m.d.sync += [
                                    bus.addr.eq(self.hl),
                                    bus.rw.eq(1),
                                    bus.io.eq(0),
                                    bus.en.eq(1),
                                    cycle.eq(1)
                                ]
                            with m.Case(1):
                                with m.If(bus.done):
                                    m.d.sync += [
                                        bus.data_in.eq(bus.data_out + 1),
                                        bus.rw.eq(0),
                                        bus.en.eq(1),
                                        cycle.eq(2)
                                    ]
                            with m.Case(2):
                                with m.If(bus.done):
                                    m.next = "FETCH"
                    with m.Case("00 --- 100"): # INR r
                        m.d.comb += op.eq(OpBlock.INR)
                        m.d.sync += reg_array[instr.a].eq(reg_array[instr.a] + 1)
                        m.next = "FETCH"
                    with m.Case("00 110 101"): # DCR M
                        m.d.comb += op.eq(OpBlock.DCR)
                        with m.Switch(cycle):
                            with m.Case(0):
                                m.d.sync += [
                                    bus.addr.eq(self.hl),
                                    bus.rw.eq(1),
                                    bus.io.eq(0),
                                    bus.en.eq(1),
                                    cycle.eq(1)
                                ]
                            with m.Case(1):
                                with m.If(bus.done):
                                    m.d.sync += [
                                        bus.data_in.eq(bus.data_out - 1),
                                        bus.rw.eq(0),
                                        bus.en.eq(1),
                                        cycle.eq(2)
                                    ]
                            with m.Case(2):
                                with m.If(bus.done):
                                    m.next = "FETCH"
                    with m.Case("00 --- 101"): # DCR r
                        m.d.comb += op.eq(OpBlock.DCR)
                        m.d.sync += reg_array[instr.a].eq(reg_array[instr.a] - 1)
                        m.next = "FETCH"
                    with m.Case("00 110 110"):  # MVI M, data
                        m.d.comb += op.eq(OpBlock.MVI_M_i)
                        with m.Switch(cycle):
                            with m.Case(0):
                                m.d.sync += [
                                    bus.addr.eq(self.pc),
                                    bus.rw.eq(1),
                                    bus.io.eq(0),
                                    bus.en.eq(1),
                                    self.pc.eq(self.pc + 1),
                                    cycle.eq(1)
                                ]
                            with m.Case(1):
                                with m.If(bus.done):
                                    m.d.sync += [
                                        bus.addr.eq(self.hl),
                                        bus.rw.eq(0),
                                        bus.data_in.eq(bus.data_out),
                                        bus.en.eq(1),
                                        cycle.eq(2)
                                    ]
                            with m.Case(2):
                                with m.If(bus.done):
                                    m.next = "FETCH"
                    with m.Case("00 --- 110"): # MVI R, data
                        m.d.comb += op.eq(OpBlock.MVI_r_i)
                        with m.Switch(cycle):
                            with m.Case(0):
                                m.d.sync += [
                                    bus.addr.eq(self.pc),
                                    bus.rw.eq(1),
                                    bus.io.eq(0),
                                    bus.en.eq(1),
                                    self.pc.eq(self.pc + 1),
                                    cycle.eq(1)
                                ]
                            with m.Case(1):
                                with m.If(bus.done):
                                    m.d.sync += reg_array[instr.a].eq(bus.data_out)
                                    m.next = "FETCH"
                    with m.Case("00 --0 001"): # LXI
                        m.d.comb += op.eq(OpBlock.LXI)
                        with m.Switch(cycle):
                            with m.Case(0):
                                m.d.sync += [
                                    bus.addr.eq(self.pc),
                                    bus.rw.eq(1),
                                    bus.io.eq(0),
                                    bus.en.eq(1),
                                    self.pc.eq(self.pc + 1),
                                    cycle.eq(1)
                                ]
                            with m.Case(1):
                                with m.If(bus.done):
                                    m.d.sync += [
                                        bus.addr.eq(self.pc),
                                        bus.rw.eq(1),
                                        bus.io.eq(0),
                                        bus.en.eq(1),
                                        self.pc.eq(self.pc + 1),
                                        cycle.eq(2),
                                        rp_array[instr.a[1:]][:8].eq(
                                            bus.data_out)
                                    ]
                            with m.Case(2):
                                with m.If(bus.done):
                                    m.d.sync += rp_array[instr.a[1:]][8:].eq(bus.data_out)
                                    m.next = "FETCH"
                    with m.Case("00 --1 001"): # DAD
                        m.d.comb += op.eq(OpBlock.DAD)
                        m.d.sync += Cat(self.hl, self.flags.carry).eq(rp_array[instr.a[1:]] + self.hl)
                        m.next = "FETCH"
                    with m.Case("00 --0 011"): # INX
                        m.d.comb += op.eq(OpBlock.INX)
                        m.d.sync += rp_array[instr.a[1:]].eq(rp_array[instr.a[1:]] + 1)
                        m.next = "FETCH"
                    with m.Case("00 --1 011"): # DCX
                        m.d.comb += op.eq(OpBlock.DCX)
                        m.d.sync += rp_array[instr.a[1:]].eq(rp_array[instr.a[1:]] - 1)
                        m.next = "FETCH"
                    with m.Case("00 0-- 111"): # Accumulator bit rotations
                        m.d.comb += op.eq(OpBlock.BIT_ROT)
                        with m.Switch(instr.a):
                            with m.Case(0b000): # RLC
                                m.d.sync += [
                                    self.acc.eq(self.acc.rotate_left(1)),
                                    self.flags.carry.eq(self.acc[7])
                                ]
                                m.next = "FETCH"
                            with m.Case(0b001): # RRC
                                m.d.sync += [
                                    self.acc.eq(self.acc.rotate_right(1)),
                                    self.flags.carry.eq(self.acc[0])
                                ]
                                m.next = "FETCH"
                            with m.Case(0b010): # RAL
                                m.d.sync += [
                                    self.flags.carry.eq(self.acc[7]),
                                    self.acc.eq(self.acc.rotate_left(1)),
                                    self.acc[0].eq(self.flags.carry)
                                ]
                                m.next = "FETCH"
                            with m.Case(0b011): # RAR
                                m.d.sync += [
                                    self.flags.carry.eq(self.acc[0]),
                                    self.acc.eq(self.acc.rotate_right(1)),
                                    self.acc[7].eq(self.flags.carry)
                                ]
                                m.next = "FETCH"
                    with m.Case("00 0-0 010"): # STAX
                        m.d.comb += op.eq(OpBlock.STAX)
                        with m.Switch(cycle):
                            with m.Case(0):
                                addr = Mux(instr.a[1], self.de, self.bc)
                                m.d.sync += [
                                    bus.rw.eq(0),
                                    bus.io.eq(0),
                                    bus.en.eq(1),
                                    bus.addr.eq(addr),
                                    cycle.eq(1),
                                    bus.data_in.eq(self.acc)
                                ]
                            with m.Case(1):
                                with m.If(bus.done):
                                    m.next = "FETCH"
                    with m.Case("00 0-1 010"): # LDAX
                        m.d.comb += op.eq(OpBlock.LDAX)
                        with m.Switch(cycle):
                            with m.Case(0):
                                addr = Mux(instr.a[1], self.de, self.bc)
                                m.d.sync += [
                                    bus.rw.eq(1),
                                    bus.io.eq(0),
                                    bus.en.eq(1),
                                    bus.addr.eq(addr),
                                    cycle.eq(1),
                                ]
                            with m.Case(1):
                                with m.If(bus.done):
                                    m.d.sync += self.acc.eq(bus.data_out)
                                    m.next = "FETCH"
                    with m.Case("00 11- 010"):  # Direct load/store Accumulator
                        m.d.comb += op.eq(OpBlock.DIRECT)
                        with m.Switch(cycle):
                            with m.Case(0):
                                m.d.sync += [
                                    bus.rw.eq(1),
                                    bus.io.eq(0),
                                    bus.en.eq(1),
                                    bus.addr.eq(self.pc),
                                    self.pc.eq(self.pc + 1),
                                    cycle.eq(1),
                                ]
                            with m.Case(1):
                                with m.If(bus.done):
                                    m.d.sync += [
                                        bus.addr.eq(self.pc),
                                        bus.rw.eq(1),
                                        bus.io.eq(0),
                                        bus.en.eq(1),
                                        self.x.eq(bus.data_out),
                                        self.pc.eq(self.pc + 1),
                                        cycle.eq(2),
                                    ]
                            with m.Case(2):
                                with m.If(bus.done):
                                    m.d.sync += [
                                        bus.addr.eq(Cat(self.x, bus.data_out)),
                                        bus.io.eq(0),
                                        bus.en.eq(1),
                                        cycle.eq(3)
                                    ]
                                    with m.If(instr.a[0]): # LDA
                                        m.d.sync += bus.rw.eq(1)
                                    with m.Else(): # STA
                                        m.d.sync += [
                                            bus.rw.eq(0),
                                            bus.data_in.eq(self.acc)
                                        ]
                            with m.Case(3):
                                with m.If(bus.done):
                                    with m.If(instr.a[0]): # LDA
                                        m.d.sync += self.acc.eq(bus.data_out)
                                    m.next = "FETCH" # Nothing to do for STA
                    with m.Case("00 10- 010"):  # Direct load/store HL
                        m.d.comb += op.eq(OpBlock.DIRECT)
                        with m.Switch(cycle):
                            with m.Case(0):
                                m.d.sync += [
                                    bus.rw.eq(1),
                                    bus.io.eq(0),
                                    bus.en.eq(1),
                                    bus.addr.eq(self.pc),
                                    self.pc.eq(self.pc + 1),
                                    cycle.eq(1),
                                ]
                            with m.Case(1):
                                with m.If(bus.done):
                                    m.d.sync += [
                                        bus.addr.eq(self.pc),
                                        bus.rw.eq(1),
                                        bus.io.eq(0),
                                        bus.en.eq(1),
                                        self.x.eq(bus.data_out),
                                        self.pc.eq(self.pc + 1),
                                        cycle.eq(2),
                                    ]
                            with m.Case(2):
                                with m.If(bus.done):
                                    m.d.sync += [
                                        bus.addr.eq(Cat(self.x, bus.data_out)),
                                        self.w.eq(bus.data_out),
                                        bus.io.eq(0),
                                        bus.en.eq(1),
                                        cycle.eq(3)
                                    ]
                                    with m.If(instr.a[0]): # LHLD
                                        m.d.sync += bus.rw.eq(1)
                                    with m.Else(): # SHLD
                                        m.d.sync += [
                                            bus.rw.eq(0),
                                            bus.data_in.eq(self.l)
                                        ]
                            with m.Case(3):
                                with m.If(bus.done):
                                    m.d.sync += [
                                        bus.addr.eq(self.wx + 1),
                                        bus.en.eq(1),
                                        cycle.eq(4)
                                    ]
                                    with m.If(instr.a[0]): # LHLD
                                        m.d.sync += [
                                            bus.rw.eq(1),
                                            self.l.eq(bus.data_out)
                                        ]
                                    with m.Else(): # SHLD
                                        m.d.sync += [
                                            bus.rw.eq(0),
                                            bus.data_in.eq(self.h)
                                        ]
                            with m.Case(4):
                                with m.If(bus.done):
                                    with m.If(instr.a[0]):
                                        m.d.sync += self.h.eq(bus.data_out)
                                    m.next = "FETCH"
                    with m.Case("00 101 111"): # CMA
                        m.d.comb += op.eq(OpBlock.CMA)
                        m.d.sync += self.acc.eq(~self.acc)
                        m.next = "FETCH"
                    with m.Case("00 11- 111"): # CMC/STC
                        m.d.comb += op.eq(OpBlock.CARRY_BIT)
                        m.next = "FETCH"
                        with m.If(instr.a[0]):
                            m.d.sync += self.flags[0].eq(~self.flags[0])
                        with m.Else():
                            m.d.sync += self.flags[0].eq(1)
                    with m.Case("01 110 110"):
                        m.d.comb += op.eq(OpBlock.HLT)
                        m.next = "HALT"
                    with m.Case("01 110 ---"): # MOV r, M
                        m.d.comb += op.eq(OpBlock.MOV_r_M)
                        with m.Switch(cycle):
                            with m.Case(0):
                                m.d.sync += [
                                    bus.addr.eq(self.hl),
                                    bus.io.eq(0),
                                    bus.rw.eq(0),
                                    bus.en.eq(1),
                                    bus.data_in.eq(reg_array[instr.b]),
                                    cycle.eq(1)
                                ]
                            with m.Case(1):
                                with m.If(bus.done):
                                    m.next = "FETCH"
                    with m.Case("01 --- 110"): # MOV M, r
                        m.d.comb += op.eq(OpBlock.MOV_M_r)
                        with m.Switch(cycle):
                            with m.Case(0):
                                m.d.sync += [
                                    bus.addr.eq(self.hl),
                                    bus.io.eq(0),
                                    bus.rw.eq(1),
                                    bus.en.eq(1),
                                    cycle.eq(1)
                                ]
                            with m.Case(1):
                                with m.If(bus.done):
                                    m.d.sync += reg_array[instr.a].eq(bus.data_out)
                                    m.next = "FETCH"
                    with m.Case("01 --- ---"): # MOV r, r
                        m.d.comb += op.eq(OpBlock.MOV_r_r)
                        m.d.sync += reg_array[instr.a].eq(reg_array[instr.b])
                        m.next = "FETCH"
                    with m.Case("10 --- 110"): # ALU block (Mem)
                        m.d.comb += op.eq(OpBlock.ALU_REG)
                        with m.Switch(cycle):
                            with m.Case(0):
                                m.d.sync += [
                                    bus.addr.eq(self.hl),
                                    bus.io.eq(0),
                                    bus.rw.eq(1),
                                    bus.en.eq(1),
                                    cycle.eq(1)
                                ]
                            with m.Case(1):
                                with m.If(bus.done):
                                    m.d.sync += [
                                        alu.alu_in.eq(bus.data_out),
                                        alu.op.eq(instr.a),
                                        cycle.eq(2)
                                    ]
                            with m.Case(2):
                                m.next = "FETCH"
                                with m.If(instr.a == 0b111):
                                    m.d.sync += self.flags.eq(alu.flags)
                                with m.Else():
                                    m.d.sync += [
                                        self.acc.eq(alu.alu_out),
                                        self.flags.eq(alu.flags)
                                    ]
                    with m.Case("10 --- ---"): # ALU block
                        m.d.comb += op.eq(OpBlock.ALU_REG)
                        with m.Switch(cycle):
                            with m.Case(0):
                                m.d.sync += [
                                    alu.alu_in.eq(reg_array[instr.b]),
                                    alu.op.eq(instr.a),
                                    cycle.eq(1)
                                ]
                            with m.Case(1):
                                m.next = "FETCH"
                                m.d.sync += self.flags.eq(alu.flags)
                                with m.If(instr.a != 0b111):
                                    m.d.sync += self.acc.eq(alu.alu_out)
                    with m.Case("11 011 011"): # IN
                        m.d.comb += op.eq(OpBlock.IO)
                        with m.Switch(cycle):
                            with m.Case(0):
                                m.d.sync += [
                                    self.pc.eq(self.pc + 1),
                                    bus.addr.eq(self.pc),
                                    bus.rw.eq(1),
                                    bus.io.eq(0),
                                    bus.en.eq(1),
                                    cycle.eq(1)
                                ]
                            with m.Case(1):
                                with m.If(bus.done):
                                    m.d.sync += [
                                        bus.addr.eq(Cat(bus.data_out, bus.data_out)),
                                        bus.rw.eq(1),
                                        bus.io.eq(1),
                                        bus.en.eq(1),
                                        cycle.eq(2)
                                    ]
                            with m.Case(2):
                                with m.If(bus.done):
                                    m.d.sync += self.acc.eq(bus.data_out)
                                    m.next = "FETCH"
                    with m.Case("11 010 011"): # OUT
                        m.d.comb += op.eq(OpBlock.IO)
                        with m.Switch(cycle):
                            with m.Case(0):
                                m.d.sync += [
                                    self.pc.eq(self.pc + 1),
                                    bus.addr.eq(self.pc),
                                    bus.rw.eq(1),
                                    bus.io.eq(0),
                                    bus.en.eq(1),
                                    cycle.eq(1)
                                ]
                            with m.Case(1):
                                with m.If(bus.done):
                                    m.d.sync += [
                                        bus.addr.eq(Cat(bus.data_out, bus.data_out)),
                                        bus.rw.eq(0),
                                        bus.io.eq(1),
                                        bus.en.eq(1),
                                        bus.data_in.eq(self.acc),
                                        cycle.eq(2)
                                    ]
                            with m.Case(2):
                                with m.If(bus.done):
                                    m.next = "FETCH"
                    with m.Case("11 100 011"): # XTHL
                        m.d.comb += op.eq(OpBlock.XTHL)
                        with m.Switch(cycle):
                            with m.Case(0):
                                m.d.sync += [
                                    bus.addr.eq(self.sp),
                                    bus.rw.eq(1),
                                    bus.io.eq(0),
                                    bus.en.eq(1),
                                    cycle.eq(1)
                                ]
                            with m.Case(1):
                                with m.If(bus.done):
                                    m.d.sync += [
                                        self.x.eq(bus.data_out),
                                        bus.addr.eq(self.sp + 1),
                                        bus.en.eq(1),
                                        cycle.eq(2)
                                    ]
                            with m.Case(2):
                                with m.If(bus.done):
                                    m.d.sync += [
                                        self.w.eq(bus.data_out),
                                        bus.addr.eq(self.sp),
                                        bus.rw.eq(0),
                                        bus.data_in.eq(self.l),
                                        bus.en.eq(1),
                                        cycle.eq(3)
                                    ]
                            with m.Case(3):
                                with m.If(bus.done):
                                    m.d.sync += [
                                        bus.addr.eq(self.sp + 1),
                                        bus.data_in.eq(self.h),
                                        bus.en.eq(1),
                                        cycle.eq(4)
                                    ]
                            with m.Case(4):
                                with m.If(bus.done):
                                    m.d.sync += self.hl.eq(self.wx)
                                    m.next = "FETCH"
                    with m.Case("11 101 001"): # PCHL
                        m.d.comb += op.eq(OpBlock.PCHL)
                        m.d.sync += self.pc.eq(self.hl)
                        m.next = "FETCH"
                    with m.Case("11 101 011"): # XCHG
                        m.d.comb += op.eq(OpBlock.XCHG)
                        m.d.sync += [
                            self.de.eq(self.hl),
                            self.hl.eq(self.de)
                        ]
                        m.next = "FETCH"
                    with m.Case("11 11- 011"): # EI/DI
                        m.d.comb += op.eq(OpBlock.EI_DI)
                        m.next = "FETCH" # TODO: Implement interrupts
                    with m.Case("11 111 001"): # SPHL
                        m.d.comb += op.eq(OpBlock.SPHL)
                        m.d.sync += self.sp.eq(self.hl)
                        m.next = "FETCH"
                    with m.Case("11 --- 110"): # Immediate ALU group
                        m.d.comb += op.eq(OpBlock.ALU_IMM)
                        with m.Switch(cycle):
                            with m.Case(0):
                                m.d.sync += [
                                    self.pc.eq(self.pc + 1),
                                    bus.addr.eq(self.pc),
                                    bus.rw.eq(1),
                                    bus.io.eq(0),
                                    bus.en.eq(1),
                                    cycle.eq(1)
                                ]
                            with m.Case(1):
                                with m.If(bus.done):
                                    m.d.sync += [
                                        alu.alu_in.eq(bus.data_out),
                                        alu.op.eq(instr.a),
                                        cycle.eq(2)
                                    ]
                            with m.Case(2):
                                m.d.sync += self.flags.eq(alu.flags)
                                m.next = "FETCH"
                                with m.If(instr.a != 0b111):
                                    m.d.sync += self.acc.eq(alu.alu_out)
                    with m.Case("11 --- 111"): # RST
                        m.d.comb += op.eq(OpBlock.RST)
                        with m.Switch(cycle):
                            with m.Case(0):
                                m.d.sync += [
                                    self.sp.eq(self.sp - 2),
                                    bus.data_in.eq(self.pc[8:]),
                                    bus.addr.eq(self.sp - 1),
                                    bus.rw.eq(0),
                                    bus.io.eq(0),
                                    bus.en.eq(1),
                                    cycle.eq(1)
                                ]
                            with m.Case(1):
                                with m.If(bus.done):
                                    m.d.sync += [
                                        bus.data_in.eq(self.pc[:8]),
                                        bus.addr.eq(self.sp),
                                        bus.en.eq(1),
                                        cycle.eq(2)
                                    ]
                            with m.Case(2):
                                with m.If(bus.done):
                                    m.d.sync += self.pc.eq(instr.a << 3)
                                    m.next = "FETCH"
                    with m.Case("11 110 101"): # PUSH PSW
                        m.d.comb += op.eq(OpBlock.PUSH)
                        with m.Switch(cycle):
                            with m.Case(0):
                                m.d.sync += [
                                    self.sp.eq(self.sp - 2),
                                    bus.data_in.eq(self.acc),
                                    bus.addr.eq(self.sp - 1),
                                    bus.rw.eq(0),
                                    bus.io.eq(0),
                                    bus.en.eq(1),
                                    cycle.eq(1)
                                ]
                            with m.Case(1):
                                with m.If(bus.done):
                                    m.d.sync += [
                                        bus.data_in.eq(self.flags),
                                        bus.addr.eq(self.sp),
                                        bus.en.eq(1),
                                        cycle.eq(2)
                                    ]
                            with m.Case(2):
                                with m.If(bus.done):
                                    m.next = "FETCH"
                    with m.Case("11 --0 101"): # PUSH
                        m.d.comb += op.eq(OpBlock.PUSH)
                        rp = rp_array[instr.a[1:]]
                        with m.Switch(cycle):
                            with m.Case(0):
                                m.d.sync += [
                                    self.sp.eq(self.sp - 2),
                                    bus.data_in.eq(rp[8:]),
                                    bus.addr.eq(self.sp - 1),
                                    bus.rw.eq(0),
                                    bus.io.eq(0),
                                    bus.en.eq(1),
                                    cycle.eq(1)
                                ]
                            with m.Case(1):
                                with m.If(bus.done):
                                    m.d.sync += [
                                        bus.data_in.eq(rp[:8]),
                                        bus.addr.eq(self.sp),
                                        bus.en.eq(1),
                                        cycle.eq(2)
                                    ]
                            with m.Case(2):
                                with m.If(bus.done):
                                    m.next = "FETCH"
                    with m.Case("11 110 001"): # POP PSW
                        m.d.comb += op.eq(OpBlock.POP)
                        with m.Switch(cycle):
                            with m.Case(0):
                                m.d.sync += [
                                    self.sp.eq(self.sp + 1),
                                    bus.addr.eq(self.sp),
                                    bus.rw.eq(1),
                                    bus.io.eq(0),
                                    bus.en.eq(1),
                                    cycle.eq(1)
                                ]
                            with m.Case(1):
                                with m.If(bus.done):
                                    m.d.sync += [
                                        self.flags.eq(bus.data_out),
                                        self.sp.eq(self.sp + 1),
                                        bus.addr.eq(self.sp),
                                        bus.rw.eq(1),
                                        bus.io.eq(0),
                                        bus.en.eq(1),
                                        cycle.eq(2)
                                    ]
                            with m.Case(2):
                                with m.If(bus.done):
                                    m.d.sync += self.acc.eq(bus.data_out)
                                    m.next = "FETCH"
                    with m.Case("11 --0 001"): # POP
                        m.d.comb += op.eq(OpBlock.POP)
                        rp = rp_array[instr.a[1:]]
                        with m.Switch(cycle):
                            with m.Case(0):
                                m.d.sync += [
                                    self.sp.eq(self.sp + 1),
                                    bus.addr.eq(self.sp),
                                    bus.rw.eq(1),
                                    bus.io.eq(0),
                                    bus.en.eq(1),
                                    cycle.eq(1)
                                ]
                            with m.Case(1):
                                with m.If(bus.done):
                                    m.d.sync += [
                                        rp[:8].eq(bus.data_out),
                                        self.sp.eq(self.sp + 1),
                                        bus.addr.eq(self.sp),
                                        bus.rw.eq(1),
                                        bus.io.eq(0),
                                        bus.en.eq(1),
                                        cycle.eq(2)
                                    ]
                            with m.Case(2):
                                with m.If(bus.done):
                                    m.d.sync += rp[8:].eq(bus.data_out)
                                    m.next = "FETCH"
                    with m.Case("11 --- 00-"): # Return
                        m.d.comb += op.eq(OpBlock.RET)
                        with m.If(instr.b[0] | branch[instr.a]):
                            with m.Switch(cycle):
                                with m.Case(0):
                                    m.d.sync += [
                                        self.sp.eq(self.sp + 1),
                                        bus.addr.eq(self.sp),
                                        bus.rw.eq(1),
                                        bus.io.eq(0),
                                        bus.en.eq(1),
                                        cycle.eq(1)
                                    ]
                                with m.Case(1):
                                    with m.If(bus.done):
                                        m.d.sync += [
                                            self.pc[:8].eq(bus.data_out),
                                            self.sp.eq(self.sp + 1),
                                            bus.addr.eq(self.sp),
                                            bus.rw.eq(1),
                                            bus.io.eq(0),
                                            bus.en.eq(1),
                                            cycle.eq(2)
                                        ]
                                with m.Case(2):
                                    with m.If(bus.done):
                                        m.d.sync += self.pc[8:].eq(bus.data_out)
                                        m.next = "FETCH"
                        with m.Else():
                            m.next = "FETCH"
                    with m.Case("11 --- 01-"): # Jump
                        m.d.comb += op.eq(OpBlock.JMP)
                        with m.Switch(cycle):
                            with m.Case(0):
                                m.d.sync += [
                                    self.pc.eq(self.pc + 1),
                                    bus.addr.eq(self.pc),
                                    bus.rw.eq(1),
                                    bus.io.eq(0),
                                    bus.en.eq(1),
                                    cycle.eq(1)
                                ]
                            with m.Case(1):
                                with m.If(bus.done):
                                    m.d.sync += [
                                        self.pc.eq(self.pc + 1),
                                        self.x.eq(bus.data_out),
                                        bus.addr.eq(self.pc),
                                        bus.rw.eq(1),
                                        bus.io.eq(0),
                                        bus.en.eq(1),
                                        cycle.eq(2)
                                    ]
                            with m.Case(2):
                                with m.If(bus.done):
                                    with m.If(instr.b[0] | branch[instr.a]):
                                        m.d.sync += self.pc.eq(Cat(self.x, bus.data_out))
                                    m.next = "FETCH"
                    with m.Case("11 --- 10-"): # Call
                        m.d.comb += op.eq(OpBlock.CALL)
                        with m.Switch(cycle):
                            with m.Case(0):
                                m.d.sync += [
                                    self.pc.eq(self.pc + 1),
                                    bus.addr.eq(self.pc),
                                    bus.rw.eq(1),
                                    bus.io.eq(0),
                                    bus.en.eq(1),
                                    cycle.eq(1)
                                ]
                            with m.Case(1):
                                with m.If(bus.done):
                                    m.d.sync += [
                                        self.pc.eq(self.pc + 1),
                                        self.x.eq(bus.data_out),
                                        bus.addr.eq(self.pc),
                                        bus.rw.eq(1),
                                        bus.io.eq(0),
                                        bus.en.eq(1),
                                        cycle.eq(2)
                                    ]
                            with m.Case(2):
                                with m.If(bus.done):
                                    with m.If(instr.b[0] | branch[instr.a]):
                                        m.d.sync += [
                                            self.sp.eq(self.sp - 2),
                                            bus.addr.eq(self.sp - 1),
                                            self.w.eq(bus.data_out),
                                            bus.data_in.eq(self.pc[8:]),
                                            bus.rw.eq(0),
                                            bus.en.eq(1),
                                            cycle.eq(3)
                                        ]
                                    with m.Else():
                                        m.next = "FETCH"
                            with m.Case(3):
                                with m.If(bus.done):
                                    m.d.sync += [
                                        self.pc.eq(self.wx),
                                        bus.addr.eq(self.sp),
                                        bus.data_in.eq(self.pc[:8]),
                                        bus.en.eq(1),
                                        cycle.eq(4)
                                    ]
                            with m.Case(4):
                                with m.If(bus.done):
                                    m.next = "FETCH"
                    with m.Default(): # NOP
                        m.d.comb += op.eq(OpBlock.NOP)
                        m.next = "FETCH"
            with m.State("HALT"):
                pass


        return m

if __name__ == "__main__":
    import sys, os
    from nmigen.sim import Simulator
    sys.setrecursionlimit(8192)
    sim = Simulator(I8080())
    sim.add_clock(1e-4)
    with sim.write_vcd("trace.vcd"):
        sim.run_until(1, run_passive=True)
