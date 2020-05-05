from myhdl import *

from myhdl.conversion import yshelper

# Once 'standardized', you could move those into the
# yosys_bb.py internal library

class RAMport:
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

	# Force unused port in to be driven for Cosimulation
	a.read._driven = "reg"

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
		in_addr = interface.addWire(b.addr)
		out_data = interface.addWire(b.read, True)

		print("Create yosys implementation of module")

		DBITS = out_data.size()
		ABITS = in_addr.size()

		user = 0
		name = interface.name
		
		# Create only once:
		if name in module.memories:
			user = module.memories[name]
			user += 1 # Inc user
		else:
			mem = module.addMemory(name)
			mem.width = DBITS
			mem.size = 2 ** ABITS

		module.memories[name] = user

		# Write port init:
			
		w = module.addCell(name + "_write%d" % user, "memwr")
		port_clk = interface.addWire(a.clk)
		port_write = interface.addWire(a.write)
		port_addr = interface.addWire(a.addr)
		w.setPort("CLK", port_clk)
		w.setPort("DATA", port_write)
		w.setPort("ADDR", port_addr)
		w.setParam("CLK_ENABLE", 1)
		w.setParam("CLK_POLARITY", 1)
		w.setParam("ABITS", ABITS)
		w.setParam("WIDTH", DBITS)
		w.setParam("TRANSPARENT", 0)
		w.setParam("MEMID", interface.name)
		w.setParam("CLK_POLARITY", 1)
		w.setParam("CLK_ENABLE", 1) # We're synchronous

		if USE_CE:
			port_en = module.addSignal(None, 1)
			in_en = interface.addWire(a.ce)
			in_we = interface.addWire(a.we)
			and_inst = module.addAnd(yshelper.ID(name + "_ce"), \
				in_en, in_we, port_en)
		else:
			port_en = interface.addWire(a.we)

		enable_array = module.addSignal(None, 0)
		for i in range(DBITS):
			enable_array.append(port_en)

		w.setPort("EN", enable_array)

		# Read port initialization:
		port_clk = interface.addWire(b.clk)
		port_read = interface.addWire(b.read, True) # output
		port_addr = interface.addWire(b.addr)

		r = module.addCell(name + "_read%d" % user, "memrd")
		r.setPort("ADDR", port_addr)
		r.setPort("DATA", port_read)
		r.setPort("CLK", port_clk)
		r.setParam("ABITS", ABITS)
		r.setParam("WIDTH", DBITS)
		r.setParam("TRANSPARENT", 0)

		r.setParam("MEMID", interface.name)
		r.setParam("CLK_POLARITY", 1)
		r.setParam("CLK_ENABLE", 1) # We're synchronous
	
		if USE_CE:
			port_en = interface.addWire(b.ce)
		else:
			port_en = yshelper.ConstSignal(True)

		r.setPort("EN", port_en)

		# For Co-Simulation, we must set unused ports:
		# port_a_read_dummy = interface.addWire(a.read, True) # output
		# s = yshelper.ConstSignal(0, DBITS)
		# module.connect(port_a_read_dummy, s)


	return porta_proc, portb_proc, implementation


