from nmigen import *


class I8080_USB(Elaboratable):
    def __init__(self, bus):
        from luna.full_devices import USBSerialDevice

        self.in_ready   = Signal()
        self.tx_empty   = Signal()
        self.parity_err = Signal()
        self.frame_err  = Signal()
        self.overflow   = Signal()
        self.data_avail = Signal()
        self.out_ready  = Signal()
        self.status = Cat(self.in_ready,
                          self.tx_empty,
                          self.parity_err,
                          self.frame_err,
                          self.overflow,
                          self.data_avail,
                          Const(0),
                          self.out_ready
                          )

        self.tx = Signal(8)
        self.tx_ready = Signal()
        self.rx = Signal(8)
        self.rx_ready = Signal()

        self.serial = USBSerialDevice(bus=bus,
                                      idVendor=1337,
                                      idProduct=1337,
                                      manufacturer_string="potatocore",
                                      product_string="intel 8080 serial port"
                                      )

    def elaborate(self, platform):
        m = Module()
        m.submodules.serial = self.serial 
        m.d.comb += [
            self.serial.tx.first.eq(1),
            self.serial.tx.last.eq(1),
            self.serial.connect.eq(1),
        ]
        m.d.sync += [
            self.out_ready.eq(~self.serial.tx.valid),
            self.in_ready.eq(self.serial.rx.valid),
        ]

        with m.If(self.serial.tx.valid & self.serial.tx.ready):
            m.d.sync += self.serial.tx.valid.eq(0)

        with m.If(self.serial.rx.valid & self.serial.rx.ready):
            m.d.sync += self.serial.rx.ready.eq(0)

        return m

    # Input/Output here refer to the perspective of the IN and OUT instructions
    def input_handlers(self, m, bus):
        with m.Switch(bus._addr[:8]):
            with m.Case(0):
                m.d.sync += bus._data_out.eq(self.status)
                m.next = "START"
            with m.Case(1):
                m.d.sync += self.serial.rx.ready.eq(1)
                with m.If(self.serial.rx.valid):
                    m.next = "START"
                    m.d.sync += bus._data_out.eq(self.serial.rx.payload)
            with m.Default():
                m.d.sync += bus._data_out.eq(0)
                m.next = "START"

    def output_handlers(self, m, bus):
        with m.Switch(bus._addr[:8]):
            with m.Case(1):
                with m.If(self.serial.tx.valid == 0):
                    m.next = "START"
                    m.d.sync += [
                        self.serial.tx.payload.eq(bus._data_in),
                        self.serial.tx.valid.eq(1)
                    ]
            with m.Default():
                m.next = "START"

class I8080_TEST(Elaboratable):
    def __init__(self):
        self.out_addr = Signal(8)
        self.out_data = Signal(8)
    def elaborate(self, platform):
        m = Module()
        return m
    
    def input_handlers(self, m, bus):
        m.d.sync += bus._data_out.eq(bus._addr[:8])
        m.next = "START"

    def output_handlers(self, m, bus):
        m.d.sync += [
            self.out_addr.eq(bus._addr[:8]),
            self.out_data.eq(bus._data_in)
        ]
        m.next = "START"

class I8080_ROM(Elaboratable):
    @property
    def rom(self):
        with open("boot.com", "rb") as f:
            return f.read()

    def __init__(self, data_in, data_out, addr, hold, sync):
        self._data_in  = data_in
        self._data_out = data_out
        self._addr = addr
        self._hold = hold
        self._sync = sync
        self._rom  = Memory(width=8, depth=0x4000, init=self.rom, name="rom")
        self._rom_r = self._rom.read_port(transparent=False)
        self._rom_w = self._rom.write_port()
        self.serial_status = Signal(8)

    def elaborate(self, platform):
        m = Module()

        # usb = platform.request("usb")
        # m.submodules.io_bus = io_bus = I8080_USB(usb)
        # m.d.comb += self.serial_status.eq(io_bus.status)

        m.submodules.io_bus = io_bus = I8080_TEST()

        m.submodules.rom_r = self._rom_r
        m.submodules.rom_w = self._rom_w

        status   = Record([
            ("is_int", 1),
            ("is_read", 1),
            ("is_stack", 1),
            ("is_halt", 1),
            ("is_out", 1),
            ("is_code", 1),
            ("is_in", 1),
            ("is_mem", 1)])

        m.d.comb += [
            self._rom_r.addr.eq(self._addr),
            self._rom_w.addr.eq(self._addr),
        ]

        m.d.sync += [
            self._rom_w.en.eq(0),
        ]

        with m.FSM() as fsm:
            m.d.comb += self._hold.eq(~fsm.ongoing("START"))
            with m.State("START"):
                with m.If(self._sync):
                    m.d.comb += status.eq(self._data_in)
                    with m.If(status.is_in):
                        m.next = "INPUT"
                    with m.If(status.is_out):
                        m.next = "OUTPUT"
                    with m.Elif(status.is_mem & status.is_read):
                        m.d.sync += self._data_out.eq(self._rom_r.data)
                    with m.Elif(status.is_mem & ~status.is_read):
                        m.d.sync += [
                            self._rom_w.data.eq(self._data_in),
                            self._rom_w.en.eq(1)
                        ]
            with m.State("INPUT"):
                io_bus.input_handlers(m, self)
            with m.State("OUTPUT"):
                io_bus.output_handlers(m, self)
        return m



