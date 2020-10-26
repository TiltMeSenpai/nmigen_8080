from nmigen import *

from .serial import I8080_USB

class I8080_Bus(Elaboratable):
    def __init__(self, rom, peripherals={}, imem_size=0x800):
        self.peripherals = peripherals

        # Signal high means accessing IO bus
        self.io       = Signal()
        # Signal high means read
        self.rw       = Signal()

        # Strobe high initiates transaction
        self.en       = Signal()
        self.addr     = Signal(16, reset_less=True)
        # CPU to Bus
        self.data_in  = Signal(8)
        # Bus to CPU
        self.data_out = Signal(8)

        # Strobe means transaction complete
        self.done     = Signal()

        mem = Memory(width=8, depth=imem_size, init=rom)

        self._r_port = mem.read_port(domain="comb")
        self._w_port = mem.write_port()

    def elaborate(self, platform):
        m = Module()

        m.submodules.r_port = r_port = self._r_port
        m.submodules.w_port = w_port = self._w_port

        m.d.comb += [
            r_port.addr.eq(self.addr),
            w_port.addr.eq(self.addr)
        ]

        m.d.sync += [
            self.done.eq(0),
            w_port.en.eq(0)
        ]
        with m.If(self.io):
            with m.Switch(self.addr[:8]):
                for addr, port in self.peripherals.items():
                    with m.Case(addr):
                        port.txn(self, m)
                with m.Default():
                    m.d.sync += self.done.eq(1)

        with m.Else():
            with m.If(self.en):
                with m.If(self.rw):
                    m.d.sync += [
                        self.data_out.eq(r_port.data),
                        self.done.eq(1)
                    ]
                with m.Else():
                    m.d.sync += [
                        w_port.data.eq(self.data_in),
                        w_port.en.eq(1),
                        self.done.eq(1)
                    ]

        return m