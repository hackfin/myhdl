from myhdl import *
from myhdl import CosimulationError
from .cosim_common import *
from .lfsr8 import lfsr8
from myhdl.conversion import yshelper
import pytest

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
def user_assert(a, b, EN):
	"User defined assert"

	q = Signal(intbv()[len(a):])

	@always_comb
	def dummy():
		"Dummy simulation to satisfy myhdl"
		q.next = a == b

	@synthesis(yshelper.yosys)
	def implementation(module, interface):
		"Adds an assert cell for a == b"
		name = interface.name

		in_a = interface.addPort('a')
		in_b = interface.addPort('b')
		q = module.addSignal(yshelper.PID("eq"), 1)

		en = yshelper.ConstSignal(EN, 1)

		assert_inst = module.addEq(yshelper.ID(name + "_eq"), in_a, in_b, q)

		c = module.addCell(name + "_cell", "user_assert", True)
		c.setPort("COND", q)

	return dummy, implementation

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

		in_a = interface.addPort('a')
		in_b = interface.addPort('b')
		out_q = interface.addPort('q', True)

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

		in_a = interface.addPort('a')
		in_b = interface.addPort('b')
		out_q = interface.addPort('q', True)
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

		in_a = interface.addPort('a')
		in_b = interface.addPort('b')
		out_q = interface.addPort('q', True)
		w = module.addWire(None, out_q.size())

		c.setPort("A", in_a)
		c.setPort("B", in_b)
		c.setPort("Y", out_q)

		c.setParam('WHICH', WHICH)

	return simulation, implementation

@blackbox
def ext_xor_cls(a, b, q):
	"XOR black box cell, class parameters"
	@always_comb
	def simulation():
		q.data.next = a.data ^ b.data
		q.en.next = a.en & b.en

	@synthesis(yshelper.yosys)
	def implementation(module, interface):
		"This implementation just adds a simple native XOR cell"
		name = interface.name

		in_a = interface.addPort('a_data')
		in_b = interface.addPort('b_data')
		out_q = interface.addPort('q_data', True)

		xor_inst = module.addXor(yshelper.ID(name + "_xor"), in_a, in_b, out_q)

		in_a = interface.addPort('a_en')
		in_b = interface.addPort('b_en')
		out_q = interface.addPort('q_en', True)

		and_inst = module.addAnd(yshelper.ID(name + "_and"), in_a, in_b, out_q)

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
		port_clk = interface.addPort(clk1)
		port_a1addr = interface.addPort('a1addr')
		port_a1data = interface.addPort('a1data', True)
		port_b1addr = interface.addPort('b1addr')
		port_b1data = interface.addPort('b1data')
		port_b1en = interface.addPort('b1en')

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
def my_assert_success(clk, ce, reset, dout, debug):
	a, b = [ Signal(modbv(0)[8:]) for i in range(2) ]
	inst_lfsr1 = lfsr8(clk, 1, reset, 0, a)
	inst_lfsr2 = lfsr8(clk, 1, reset, 0, b)

	# Need a dummy instance to drive dout
	inst_xor = xor(a, b, dout)

	inst_assert = user_assert(a, b, 1)

	return instances()

@block
def my_assert_failure(clk, ce, reset, dout, debug):
	a, b = [ Signal(modbv(0)[8:]) for i in range(2) ]
	inst_lfsr1 = lfsr8(clk, ce, reset, 0, a)
	inst_lfsr2 = lfsr8(clk, 1, reset, 0, b)

	# Need a dummy instance to drive dout
	inst_xor = xor(a, b, dout)

	inst_assert = user_assert(a, b, 1)

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

class Record:
	def __init__(self):
		self.data = Signal(intbv(0)[8:])
		self.en = Signal(bool(0))

@block
def inst_classarg_blackbox(clk, ce, reset, dout, debug):
	a, b, q = [ Record() for i in range(3) ]
	inst_lfsr1 = lfsr8(clk, ce, reset, 5, a.data)
	inst_lfsr2 = lfsr8(clk, ce, reset, 0, b.data)

	inst_xor = ext_xor_cls(a, b, q)

	@always_comb
	def assign():
		dout.next = q.data
		debug.next = q.en

	return instances()

############################################################################
# TESTS

def test_blackbox_simple():
	UNIT = inst_simple_blackbox
	arst = False
	design = design_from_entity(UNIT, arst)

	design.write_verilog("inst_simple_blackbox", True)
	# design.display_rtl("$xor_8_8_8", fmt='ps')

	# design.import_verilog("aux/assert.v")

	run_tb(tb_unit(UNIT, mapped_uut, arst), 20000)

def test_blackbox_assert_fail():
	"We expect a cosim error to happen, if not, assertion is flaky"
	UNIT = my_assert_failure
	arst = False
	design = design_from_entity(UNIT, arst)

	design.write_verilog("my_assert_failure", True)
	try:
		run_tb(tb_unit(UNIT, mapped_uut_assert, arst), 2000)
	except CosimulationError:
		pass

def test_blackbox_assert():
	UNIT = my_assert_success
	arst = False
	design = design_from_entity(UNIT, arst)

	design.write_verilog("my_assert_success", True)

	run_tb(tb_unit(UNIT, mapped_uut_assert, arst), 2000)

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

def test_blackbox_classarg():
	UNIT = inst_classarg_blackbox
	arst = False
	design = design_from_entity(UNIT, arst)

	design.write_verilog("inst_classarg_blackbox", True)

	run_tb(tb_unit(UNIT, mapped_uut, arst), 2000)

def _test_blackbox_ext_parameter():
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

