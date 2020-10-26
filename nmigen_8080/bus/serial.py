from nmigen import *
from nmigen.lib.fifo import AsyncFIFO

class I8080_USB(Elaboratable):
    def __init__(self, bus):
        from luna.full_devices import USBSerialDevice

        self.serial = USBSerialDevice(bus=bus,
                                      idVendor=1337,
                                      idProduct=1337,
                                      manufacturer_string="potatocore",
                                      product_string="intel 8080 serial port"
                                      )
        
        self.i_fifo = AsyncFIFO(width=8, depth=8, r_domain="usb", w_domain="sync")
        self.o_fifo = AsyncFIFO(width=8, depth=8, r_domain="sync", w_domain="usb")

    def elaborate(self, platform):
        m = Module()

        m.d.usb += [
            self.i_fifo.r_en.eq(0),
            self.o_fifo.w_en.eq(0),
            self.serial.tx.valid.eq(self.o_fifo.r_rdy),
            self.serial.rx.ready.eq(self.i_fifo.w_rdy)
        ]
        with m.If(self.o_fifo.r_rdy & self.serial.tx.valid):
            m.d.usb += [
                self.o_fifo.r_en.eq(1),
                self.serial.tx.payload.eq(self.o_fifo.r_data)
            ]

        with m.If(self.i_fifo.w_rdy & self.serial.rx.valid):
            m.d.usb += [
                self.i_fifo.w_en.eq(1),
                self.i_fifo.w_data.eq(self.serial.rx.payload)
            ]

        return m

    def txn(self, bus, m):
        running = Signal()
        m.d.sync += [
            self.i_fifo.r_en.eq(0),
            self.o_fifo.w_en.eq(0)
        ]
        with m.If(bus.en | running):
            with m.If(bus.rw): # rw high == IN
                with m.If(self.i_fifo.r_rdy):
                    m.d.sync += [
                        bus.data_out.eq(self.i_fifo.r_data),
                        self.i_fifo.r_en.eq(1),
                        bus.done.eq(1),
                        running.eq(0)
                    ]
                with m.Else():
                    m.d.sync += running.eq(1)
            with m.Else(): # rw low = OUT
                with m.If(self.o_fifo.w_rdy):
                    m.d.sync += [
                        self.o_fifo.w_data.eq(bus.data_in),
                        self.o_fifo.w_en.eq(1),
                        bus.done.eq(1),
                        running.eq(0)
                    ]
                with m.Else():
                    m.d.sync += running.eq(1)