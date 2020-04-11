from myhdl import *

from .cosim_common import *
from .lfsr8 import lfsr8
from myhdl.conversion import yshelper

# New `blackbox` entity test cases
#

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
		c = module.addCell(yshelper.ID(name + "_cell"), yshelper.PID("user_xor"))

		in_a = interface.addWire(a)
		in_b = interface.addWire(b)
		out_q = interface.addWire(q, True)
		w = module.addWire(None, out_q.size())

		c.setPort(yshelper.PID("A"), in_a)
		c.setPort(yshelper.PID("B"), in_b)
		c.setPort(yshelper.PID("Y"), out_q)

		print("PORT OUT", out_q.as_wire().port_output)

	return simulation, implementation

@block
def blackbox_simple(clk, ce, reset, dout, debug):
	a, b = [ Signal(modbv(0)[8:]) for i in range(2) ]
	inst_lfsr1 = lfsr8(clk, 1, reset, 5, a)
	inst_lfsr2 = lfsr8(clk, 1, reset, 0, b)
	inst_xor = xor(a, b, dout)

	return instances()

@block
def blackbox_ext(clk, ce, reset, dout, debug):
	a, b = [ Signal(modbv(0)[8:]) for i in range(2) ]
	inst_lfsr1 = lfsr8(clk, 1, reset, 5, a)
	inst_lfsr2 = lfsr8(clk, 1, reset, 0, b)
	inst_xor = ext_xor(a, b, dout)

	return instances()

def test_blackbox_simple():
	UNIT = blackbox_simple
	arst = False
	design = design_from_entity(UNIT, arst)

	design.write_verilog("blackbox_simple", True)
	# design.display_rtl("$xor_8_8_8", fmt='ps')

	run_tb(tb_unit(UNIT, mapped_uut, arst), 20000)

def test_blackbox_ext():
	UNIT = blackbox_ext
	arst = False
	design = design_from_entity(UNIT, arst)
 
	a, b, q = [ Signal(modbv(0)[8:]) for i in range(3) ]
	inst_user_xor = user_xor(a, b, q)
	inst_user_xor.convert("verilog", name_prefix="\\", no_testbench=True)
	# Import the used defined module to resolve:
	design.import_verilog("user_xor.v")
 
	design.write_verilog("blackbox_ext", True)
	design.display_rtl("$ext_xor_8_8_8", fmt='ps')
 
	run_tb(tb_unit(UNIT, mapped_uut, arst), 20000)

