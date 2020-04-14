from myhdl import *

from .cosim_common import *
from .lfsr8 import lfsr8
from .test_simple import up_counter
from myhdl import CosimulationError
from myhdl.conversion import yshelper

from ..general import test_interfaces1
from ..general import test_intbv_signed
from ..general import test_bin2gray
from ..general import test_toplevel_interfaces
from ..general import test_fsm

import pytest

@block
def dummy_driver(clk, dout):
	"Need to insert this to satisfy cosimulation interface"
	@always(clk.posedge)
	def worker():
		dout.next = 1
	return instances()

@block
def mapped_test(which, clk, debug, name = None):
	"Wrapper for simple 'clk, debug' interface"
	args = locals()

	if not name:
		name = which.func.__name__ + "_mapped"
	else:
		name += "_mapped"

	tb = "tb_" + name
	use_assert = True

	return setupCosimulation(**locals())

############################################################################
# Integrate general tests

@block
def plain_intbv(clk, debug):
	"""Integrates tests that work using the simple assert module
mechanism via yosys"""

	@always(clk.posedge)
	def dummy():
		debug.next = 1

	plain_intbv = test_intbv_signed.PlainIntbv()

	return instances()

@block
def general(unit, clk, debug, args):
	"""Integrates tests that work using the simple assert module
mechanism via yosys"""

	@always(clk.posedge)
	def dummy():
		debug.next = 1

	if args:
		inst_unit = unit(*args)
	else:
		inst_unit = unit()

	return instances()

@block
def cosim_stim(uut):
	"""Cosimulation run for general tests

	Runs the myhdl unit and the yosys mapped verilog output unit
	in parallel. Simulation will abort early with a myhdl.CosimulationError
	when a test fails and show as ASSERTION warning of the sort

`ASSERTION FAILED in tb_plain_intbv.dut.$PlainIntbv_0.$assert:test_intbv_signed.py:78
`
	"""

	clk = Signal(bool())
	debug0, debug1 = [ Signal(bool()) for i in range(2) ]

	# Important to have a clock generator, otherwise
	# Cosim fails early without verbosity
	inst_clkgen = clkgen(clk, 20)

	inst_mapped = mapped_test(uut, clk, debug0)
	inst_uut = uut(clk, debug1)

	return instances()

@block
def cosim_general(uut, args):
	"""Cosimulation run for general tests

	Runs the myhdl unit and the yosys mapped verilog output unit
	in parallel. Simulation will abort early with a myhdl.CosimulationError
	when a test fails and show as ASSERTION warning of the sort

`ASSERTION FAILED in tb_plain_intbv.dut.$PlainIntbv_0.$assert:test_intbv_signed.py:78
`
	"""

	clk = Signal(bool())
	debug0, debug1 = [ Signal(bool()) for i in range(2) ]

	# Important to have a clock generator, otherwise
	# Cosim fails early without verbosity
	inst_clkgen = clkgen(clk, 20)

	inst_mapped = mapped_test(general, clk, debug0, uut.__name__)
	inst_uut = general(uut, clk, debug1, args)

	return instances()

@block
def cosim_bench(uut, args):
	"""Cosimulation run for test benches that take a block as argument
	"""

	clk = Signal(bool())
	debug0, debug1 = [ Signal(bool()) for i in range(2) ]

	# Important to have a clock generator, otherwise
	# Cosim fails early without verbosity
	inst_clkgen = clkgen(clk, 20)

	inst_mapped = mapped_test(general, clk, debug0, uut.__name__)
	inst_uut = general(uut, clk, debug1, args)

	return instances()


@pytest.mark.xfail
@pytest.mark.parametrize("uut", [plain_intbv])
def test_general(uut):
	arst = False
	name = uut.func.__name__
	design = yshelper.Design(name)
	clk = Signal(bool())
	debug = Signal(bool())
	inst_uut = uut(clk, debug)
	inst_uut.convert("yosys_module", design, name=name, trace=False)
	design.write_verilog(name, True)
	run_tb(cosim_stim(uut), 2000)


fsm_signals = (Signal(bool(0)), Signal(test_fsm.t_State_b.SEARCH), Signal(bool(0)), Signal(bool(0)), Signal(bool(1)), test_fsm.t_State_b)

# UUT_LIST = [ (test_bin2gray.bin2grayBench, ( 8, test_bin2gray.bin2gray )) ]
# UUT_LIST = [ (test_fsm.FramerCtrl, fsm_signals) ]

UUT_LIST = [ (test_toplevel_interfaces.tb_top_level_interfaces, None) ]
UUT_LIST = [ (test_interfaces1.c_testbench_one, None) ]
UUT_LIST += [ (test_interfaces1.c_testbench_two, None) ]
UUT_LIST += [ (test_intbv_signed.PlainIntbv, None) ]

@pytest.mark.xfail
@pytest.mark.parametrize("uut, args", UUT_LIST)
def test_general(uut, args):
	arst = False
	name = uut.func.__name__
	design = yshelper.Design(name)
	clk = Signal(bool())
	debug = Signal(bool())
	inst_uut = general(uut, clk, debug, args)
	inst_uut.convert("yosys_module", design, name=name, trace=False)
	design.write_verilog(name, True)
	run_tb(cosim_general(uut, args), 2000)


