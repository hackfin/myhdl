# 'Work' library for ROM entities.
#
# Here you can store ROM blackboxes that are explicitly inferred.
#
# If they are supported by implicit inferral, see myhdl/conversion/yosys_bb.py
#
from myhdl import *

from myhdl.conversion import yshelper

@blackbox
def Rom(addr, data, INIT_DATA):

	@always_comb
	def simulation():
		data.next = INIT_DATA[addr]

	@synthesis(yshelper.yosys)
	def implementation(module, interface):
		in_addr = interface.addPort('addr')
		out_data = interface.addPort('data', True)

		dbits = out_data.size()
		abits = in_addr.size()

		user = 0
		memid = "\\" + interface.name
		
		# Create only once:
		if interface.name in module.memories:
			user = module.memories[interface.name]
			user += 1 # Inc user
		else:
			print("ADDING ROM MEMORY")
			mem = module.addMemory(interface.name)
			mem.width = dbits
			mem.size = 2 ** abits

			init = module.addCell(interface.name + "_init", "meminit")
			init.setParam("ABITS", 32)
			init.setParam("PRIORITY", 48)
			init.setParam("WORDS", len(INIT_DATA))
			init.setParam("MEMID", memid)
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

		readport.setParam("MEMID", memid)
		readport.setParam("CLK_POLARITY", 0)
		readport.setParam("CLK_ENABLE", 0) # We're totally async


	return simulation, implementation


