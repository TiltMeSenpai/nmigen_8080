from nmigen import *

class I8080_ROM(Elaboratable):
    @property
    def rom(self):
        with open("test.com", "rb") as f:
            return f.read()

    def __init__(self, data_in, data_out, addr, hold, sync):
        self._data_in  = data_in
        self._data_out = data_out
        self._addr = addr
        self._hold = hold
        self._sync = sync
        self._rom  = Memory(width=8, depth=len(self.rom) + 0xFF, init=((b"\x00" * 0xFF) + self.rom), name="rom")
        self._rom_r = self._rom.read_port(transparent=False)
        self._rom_w = self._rom.write_port()
        self._stack = Memory(width=8, depth=256, name="ram")
        self._ram_r = self._stack.read_port(transparent=False)
        self._ram_w = self._stack.write_port()

    def elaborate(self, platform):
        m = Module()
        m.submodules.rom_r = self._rom_r
        m.submodules.rom_w = self._rom_w
        m.submodules.ram_r = self._ram_r
        m.submodules.ram_w = self._ram_w

        is_int   = Signal()
        is_read  = Signal()
        is_stack = Signal()
        is_halt  = Signal()
        is_out   = Signal()
        is_code  = Signal()
        is_in    = Signal()
        is_mem   = Signal()
        status   = Cat(is_int, is_read, is_stack, is_halt, is_out, is_code, is_in, is_mem)

        output_port = Signal(8)

        m.d.comb += [
            self._rom_r.addr.eq(self._addr),
            self._rom_w.addr.eq(self._addr),
            self._ram_r.addr.eq(self._addr[0:8]),
            self._ram_w.addr.eq(self._addr[0:8]),
        ]

        m.d.sync += [
            self._rom_w.en.eq(0),
            self._ram_w.en.eq(0)
        ]

        with m.FSM():
            with m.State("START"):
                with m.If(self._sync):
                    m.d.sync += [
                        status.eq(self._data_in),
                        self._hold.eq(1)
                    ]
                    m.next    = "PREP"
            with m.State("PREP"):
                with m.If(is_out):
                    m.next = "OUTPUT"
                with m.Elif(is_stack & is_read):
                    m.next = "READ_STACK"
                with m.Elif(is_stack & ~is_read):
                    m.next = "WRITE_STACK"
                with m.Elif(~is_stack & is_read):
                    m.next = "READ_ROM"
                with m.Elif(~is_stack & ~is_read):
                    m.next = "WRITE_ROM"
            with m.State("WRITE_STACK"):
                m.d.sync += [
                    self._ram_w.data.eq(self._data_in),
                    self._ram_w.en.eq(1)
                ]
                m.next = "RELEASE"
            with m.State("READ_STACK"):
                m.d.sync += self._data_out.eq(self._ram_r.data)
                m.next = "RELEASE"
            with m.State("READ_ROM"):
                m.d.sync += self._data_out.eq(self._rom_r.data)
                m.next = "RELEASE"
            with m.State("WRITE_ROM"):
                m.d.sync += [
                    self._rom_w.data.eq(self._data_in),
                    self._rom_w.en.eq(1)
                ]
                m.next = "RELEASE"
            with m.State("OUTPUT"):
                m.d.sync += output_port.eq(self._data_in)
                m.next = "RELEASE"
            with m.State("RELEASE"):
                m.d.sync += self._hold.eq(0)
                m.next = "START"
        return m



