from myhdl import *

from myhdl.conversion import yshelper

class DPport:
	def __init__(self, awidth, dwidth):
		self.clk = Signal(bool(0))
		self.we = Signal(bool(0))
		self.ce = Signal(bool(0))
		self.addr = Signal(modbv()[awidth:])
		self.write = Signal(modbv()[dwidth:])
		self.read = Signal(modbv()[dwidth:])
		# Low/high select:
		self.sel = Signal(intbv()[2:])


@blackbox
def dpram_r1w1(a, b, HEXFILE = None, USE_CE = False):
	"Synthesizing one read one write port DPRAM, synchronous read b4 write"
	mem = [Signal(modbv(0)[len(a.read):]) for i in range(2 ** len(a.addr))]

	if HEXFILE:
		init_inst = meminit(mem, HEXFILE)

	if USE_CE:
		@always(a.clk.posedge)
		def porta_proc():
			if a.ce:
				if a.we:
					if __debug__:
						print("Writing to ", a.addr)
					mem[a.addr].next = a.write

		@always(b.clk.posedge)
		def portb_proc():
			if b.ce:
				b.read.next = mem[b.addr]
	else:
		@always(a.clk.posedge)
		def porta_proc():
			if a.we:
				if __debug__:
					print("Writing to ", a.addr)
				mem[a.addr].next = a.write

		@always(b.clk.posedge)
		def portb_proc():
			b.read.next = mem[b.addr]

	@synthesis(yshelper.yosys)
	def implementation(module, interface):
		# Create write port:
		print("Create yosys implementation of module")
		name = interface.name
		c = module.addCell(yshelper.ID(name + "_w"), yshelper.ID("memwr"))
		# port_read = interface.addWire(a.read)
		port_clk = interface.addWire(a.clk)
		port_write = interface.addWire(a.write)
		port_addr = interface.addWire(a.addr)
		data_w = port_write.size() # Number of data bits
		c.setPort(yshelper.PID("CLK"), port_clk)
		c.setPort(yshelper.PID("DATA"), port_write)
		c.setPort(yshelper.PID("ADDR"), port_addr)
		c.parameters[yshelper.PID("CLK_ENABLE")] = 1
		c.parameters[yshelper.PID("CLK_POLARITY")] = 1

		if USE_CE:
			port_en = module.addSignal(None, 1)
			in_en = interface.addWire(a.ce)
			in_we = interface.addWire(a.we)
			and_inst = module.addAnd(yshelper.ID(name + "_ce"), \
				in_en, in_we, port_en)
		else:
			port_en = interface.addWire(a.we)

		c.setPort(yshelper.PID("EN"), port_en)
		# Create read port:
		c = module.addCell(yshelper.ID(name + "_r"), yshelper.ID("memrd"))
	
		port_clk = interface.addWire(b.clk)
		port_read = interface.addWire(b.read, True) # output
		port_addr = interface.addWire(b.addr)
		c.setPort(yshelper.PID("DATA"), port_read)
		c.setPort(yshelper.PID("ADDR"), port_addr)
		if USE_CE:
			port_en = interface.addWire(b.ce)
		else:
			port_en = yshelper.ConstSignal(True)

		c.setPort(yshelper.PID("CLK"), port_clk)
		c.setPort(yshelper.PID("EN"), port_en)

	return porta_proc, portb_proc, implementation


