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
			init = module.addCell(interface.name + "_init", "meminit")
			init.setParam("MEMID", interface.name)
			init.setParam("ABITS", abits)
			init.setParam("WIDTH", dbits)
			init.setParam("WORDS", len(INIT_DATA))

			# Note: When INIT_DATA array is long, the
			# RTL display will barf.
			init.setPort("DATA", interface.toInitData(INIT_DATA, dbits))
			module.memories[interface.name] = user


		readport = module.addCell(interface.name + "_read%d" % user, "memrd")
		readport.setPort("ADDR", in_addr)
		readport.setPort("DATA", out_data)

		readport.setParam("MEMID", interface.name)
		readport.setParam("CLK_ENABLE", False) # We're totally async


	return simulation, implementation
