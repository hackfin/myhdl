from myhdl import *

from .cosim_common import *
from .lfsr8 import lfsr8
from myhdl.conversion import yshelper

# New `blackbox` entity test cases
#

############################################################################
# Blackbox implementations

@block
def user_xor(A, B, Y):
	"User defined blackbox module implementation to resolve cosimulation"
	@always_comb
	def simulation():
		Y.next = A ^ B

	return instances()

@blackbox
def xor(a, b, q):
	"XOR black box cell"
	@always(a, b)
	def simulation():
		"Simulation model, must match the synthesis result below"
		q.next = a ^ b

	@synthesis(yshelper.yosys)
	def implementation(module, interface):
		"This implementation just adds a simple native XOR cell"
		name = interface.name

		in_a = interface.addWire(a)
		in_b = interface.addWire(b)
		out_q = interface.addWire(q, True)

		xor_inst = module.addXor(yshelper.ID(name + "_xor"), in_a, in_b, out_q)

	return simulation, implementation

@blackbox
def ext_xor(a, b, q):
	"XOR black box cell, external wrapping"
	@always(a, b)
	def simulation():
		q.next = a ^ b

	@synthesis(yshelper.yosys)
	def implementation(module, interface):
		"Create cell for above user_xor module"
		name = interface.name
		c = module.addCell(name + "_cell", "user_xor")

		in_a = interface.addWire(a)
		in_b = interface.addWire(b)
		out_q = interface.addWire(q, True)
		w = module.addWire(None, out_q.size())

		c.setPort("A", in_a)
		c.setPort("B", in_b)
		c.setPort("Y", out_q)

		module.fixup_ports()

	return simulation, implementation


@blackbox
def bb_ext_logic_parameter(a, b, q, WHICH=1):
	"XOR black box cell, external wrapping"
	@always(a, b)
	def simulation():
		if WHICH == 1:
			q.next = a ^ b
		elif WHICH == 2:
			q.next = a & b
		else:
			raise ValueError("undefined selection")

	@synthesis(yshelper.yosys)
	def implementation(module, interface):
		"Create cell for above user_xor module"
		name = interface.name
		c = module.addCell(name + "_cell", "user_logic")

		in_a = interface.addWire(a)
		in_b = interface.addWire(b)
		out_q = interface.addWire(q, True)
		w = module.addWire(None, out_q.size())

		c.setPort("A", in_a)
		c.setPort("B", in_b)
		c.setPort("Y", out_q)

		c.setParam('WHICH', WHICH)

	return simulation, implementation

@blackbox
def _TRELLIS_DPR16X4(clk1, a1addr, a1data, b1addr, b1data, b1en, CLKPOL2, INIT):
	"TRELLIS primitive for testing"

	mem = [ intbv()[3:] for i in range(64) ]

	@always(clk1.posedge)
	def simulation():
		if b1en:
			mem[b1addr] = b1data

		a1data.next = mem[a1addr]


	@synthesis(yshelper.yosys)
	def implementation(module, interface):
		"Create cell for built-in primitive"
		name = interface.name
		c = module.addCell(name + "_dpr16x4", "__TRELLIS_DPR16X4")
		port_clk = interface.addWire(clk1)
		port_a1addr = interface.addWire(a1addr)
		port_a1data = interface.addWire(a1data, True)
		port_b1addr = interface.addWire(b1addr)
		port_b1data = interface.addWire(b1data)
		port_b1en = interface.addWire(b1en)

		# port_read = module.addSignal(yshelper.PID("a1read"), 4)
		# port_read.as_wire().port_input = True 
		# port_read.as_wire().port_output = False 
		c.setPort("A1DATA", port_a1data)

		c.setPort("CLK1", port_clk)
		c.setPort("A1ADDR", port_a1addr)
		c.setPort("B1EN", port_b1en)
		c.setPort("B1ADDR", port_b1addr)
		c.setPort("B1DATA", port_b1data)

		c.setParam('CLKPOL2', CLKPOL2)
		if len(INIT) != 64:
			raise AssertionError("Bad INIT vector length")
		c.setParam('INIT', INIT)
		module.fixup_ports()

	return simulation, implementation


############################################################################
# Instances / UUTs

@block
def inst_simple_blackbox(clk, ce, reset, dout, debug):
	a, b = [ Signal(modbv(0)[8:]) for i in range(2) ]
	inst_lfsr1 = lfsr8(clk, 1, reset, 5, a)
	inst_lfsr2 = lfsr8(clk, 1, reset, 0, b)
	inst_xor = xor(a, b, dout)

	return instances()

@block
def inst_ext_blackbox(clk, ce, reset, dout, debug):
	a, b = [ Signal(modbv(0)[8:]) for i in range(2) ]
	inst_lfsr1 = lfsr8(clk, ce, reset, 5, a)
	inst_lfsr2 = lfsr8(clk, 1, reset, 0, b)
	inst_xor = ext_xor(a, b, dout)

	return instances()

@block
def inst_ext_parameter_blackbox(clk, ce, reset, dout, debug):
	a, b = [ Signal(modbv(0)[8:]) for i in range(2) ]
	inst_lfsr1 = lfsr8(clk, ce, reset, 5, a)
	inst_lfsr2 = lfsr8(clk, ce, reset, 0, b)

	da, aa, db, ab = [ Signal(modbv(0)[4:]) for i in range(4) ]

	INIT = intbv(0xdeadbeeff00dface)[64:]

	@always_comb
	def wire():
		aa.next = a[4:]
		ab.next = b[4:]
		db.next = b[8:4]
		dout.next = da

	inst = _TRELLIS_DPR16X4(clk, aa, da, ab, db, ce, 1, INIT)

	return instances()


############################################################################
# TESTS

def test_blackbox_simple():
	UNIT = inst_simple_blackbox
	arst = False
	design = design_from_entity(UNIT, arst)

	design.write_verilog("inst_simple_blackbox", True)
	design.display_rtl("$xor_8_8_8", fmt='ps')

	run_tb(tb_unit(UNIT, mapped_uut, arst), 20000)

def test_blackbox_ext():
	UNIT = inst_ext_blackbox
	arst = False
	design = design_from_entity(UNIT, arst)
 
	a, b, q = [ Signal(modbv(0)[8:]) for i in range(3) ]
	inst_user_xor = user_xor(a, b, q)
	inst_user_xor.convert("verilog", name_prefix="\\$", no_testbench=True)
	# Import the used defined module to resolve:
	design.import_verilog("user_xor.v")
 
	design.write_verilog("inst_ext_blackbox", True)
	design.display_rtl("$ext_xor_8_8_8", fmt='ps')
	design.write_ilang("ext_xor")
 
	run_tb(tb_unit(UNIT, mapped_uut, arst), 20000)

def test_blackbox_ext_parameter():
	UNIT = inst_ext_parameter_blackbox
	arst = False
	design = design_from_entity(UNIT, arst)
 
#	a, b, q = [ Signal(modbv(0)[8:]) for i in range(3) ]
#	inst_user_xor = user_xor(a, b, q)
#	inst_user_xor.convert("verilog", name_prefix="\\", no_testbench=True)
#	# Import the used defined module to resolve:
#	design.import_verilog("user_xor.v")
 
	design.test_synth()
	design.display_rtl("$_TRELLIS_DPR16X4_1_4_4_4_4_1_c1_64", fmt='ps', full=False)

	design.import_verilog("techmap/lutrams_map.v")
	design.write_verilog("inst_ext_parameter_blackbox", True)
	# Simulation yet flaky:
	# run_tb(tb_unit(UNIT, mapped_uut, arst), 20000)

