# Blackboxes implementation for yosys conversion
#
# (c) 2020, <hackfin@section5.ch>
#

from myhdl import *

# Do not import any yshelper stuff in here.
# Use the interface class (`interface` parameter in implementation()

class yosys:
	def __init__(self):
		pass

@blackbox
def Rom(addr, data, INIT_DATA):

	@always_comb
	def simulation():
		data.next = INIT_DATA[addr]

	@synthesis(yosys)
	def implementation(module, interface):
		in_addr = interface.addWire(addr)
		out_data = interface.addWire(data, True)

		dbits = out_data.size()
		abits = in_addr.size()

		user = 0
		
		# Create only once:
		if interface.name in module.memories:
			user = module.memories[interface.name]
			user += 1 # Inc user
			module.memories[interface.name] = user
		else:
			mem = module.addMemory(interface.name)
			mem.width = dbits
			mem.size = 2 ** abits

			init = module.addCell(interface.name + "_init", "meminit")
			init.setParam("ABITS", 32)
			init.setParam("PRIORITY", 48)
			init.setParam("WORDS", len(INIT_DATA))
			init.setParam("MEMID", interface.name)
			init.setParam("WIDTH", dbits)
			init.setPort("ADDR", 0)

			# Note: When INIT_DATA array is long, the
			# RTL display will barf.
			init.setPort("DATA", interface.toInitData(INIT_DATA, dbits))
			module.memories[interface.name] = user

		clk = module.addSignal(None, 1)

		readport = module.addCell(interface.name + "_read%d" % user, "memrd")
		readport.setPort("ADDR", in_addr)
		readport.setPort("DATA", out_data)
		readport.setPort("CLK", clk) # Must connect clock, even if unused
		readport.setPort("EN", True)
		readport.setParam("ABITS", abits)
		readport.setParam("WIDTH", dbits)
		readport.setParam("TRANSPARENT", 0)

		readport.setParam("MEMID", interface.name)
		readport.setParam("CLK_POLARITY", 0)
		readport.setParam("CLK_ENABLE", 0) # We're totally async


	return simulation, implementation
