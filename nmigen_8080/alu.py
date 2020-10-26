from nmigen import *

class Alu(Elaboratable):
    def __init__(self, acc, carry_in):
        self.acc      = acc
        self.alu_in   = Signal(8)
        self.alu_out  = Signal(8)
        self.op       = Signal(3)
        self.carry_in = carry_in
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

    def elaborate(self, platform):
        m = Module()

        out = Cat(self.alu_out, self.flags.carry)
        m.d.comb += [
            self.flags.zero.eq(self.alu_out == 0),
            self.flags.sign.eq(self.alu_out[-1]),
            self.flags.parity.eq(~self.alu_out.xor())
        ]

        with m.Switch(self.op):
            with m.Case(0b000): # Add
                m.d.comb += out.eq(self.acc + self.alu_in)
            with m.Case(0b001): # Add with carry
                m.d.comb += out.eq(self.acc + self.alu_in + self.carry_in)
            with m.Case(0b010): # Sub
                m.d.comb += out.eq(self.acc - self.alu_in)
            with m.Case(0b011): # Sub with carry
                m.d.comb += out.eq(self.acc - self.alu_in - self.carry_in)
            with m.Case(0b100):  # And
                m.d.comb += self.alu_out.eq(self.acc & self.alu_in)
            with m.Case(0b101):
                m.d.comb += self.alu_out.eq(self.acc ^ self.alu_in)
            with m.Case(0b110):
                m.d.comb += self.alu_out.eq(self.acc | self.alu_in)
            with m.Case(0b111):
                m.d.comb += out.eq(self.acc - self.alu_in)

        return m