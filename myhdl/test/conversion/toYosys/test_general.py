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
yshelper.DebugOutput.debug = True
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

	return setupCosimulation(name, True, args)

############################################################################
# Integrate general tests

class SelfContainingTb:
	"Wrapper to emulate a self containing test bench"
	def __init__(self, tb, uut):
		self.func = uut # Emulate block
		self.tb = tb
	def __call__(self, clk, debug):
		return self.tb
		
@block
def self_containing_tb(uut, clk, debug):
	"""Integrates tests that work using the simple assert module
mechanism via yosys"""

	@always(clk.posedge)
	def dummy():
		debug.next = 1

	inst = uut()

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


UUT_LIST = [ (test_intbv_signed.PlainIntbv, self_containing_tb )]
UUT_LIST += [ (test_intbv_signed.SignedConcat, self_containing_tb )]
UUT_LIST += [ (test_intbv_signed.SlicedSigned, self_containing_tb )]

@pytest.mark.parametrize("uut,tb", UUT_LIST )
def test_intbv(uut, tb):
	name = uut.func.__name__
	design = yshelper.Design(name)
	clk = Signal(bool())
	debug = Signal(bool())
	inst_tb = tb(uut, clk, debug)
	inst_tb.convert("yosys_module", design, name=name, trace=False)
	design.write_verilog(name, True, False)
	design.display_rtl("$" + name, fmt='dot')
	wrapper = SelfContainingTb(tb, uut)
	run_tb(cosim_stim(wrapper), 2000)

@block
def cosim_bench(uut, bench, param):
	"""Cosimulation run for test benches that take a block as argument
	"""

	clk = Signal(bool())
	debug0, debug1 = [ Signal(bool()) for i in range(2) ]

	wrapper = CosimObjectWrapper(uut, "width,bin2gray")
	wrapper.trace = True # Trace
	wrapper.synth_pass = True # Run a synthesis pass
	inst_uut1 = bench(param, wrapper)
	inst_uut2 = bench(param, uut)

	return instances()



UUT_LIST_PARAM = [ (test_bin2gray.bin2gray, test_bin2gray.bin2grayBench, 8) ]

@pytest.mark.xfail
@pytest.mark.parametrize("uut,bench,param", UUT_LIST_PARAM)
def test_memory_fail(uut, bench, param):
	run_tb(cosim_bench(uut, bench, param), 2000)

# Those are not supported yet until sequential (@instance) support is
# implemented
UUT_LIST_INST_X = [] 

@pytest.mark.xfail
@pytest.mark.parametrize("uut,tb", UUT_LIST_INST_X )
def test_unsupported_sequential(uut, tb):
	name = uut.func.__name__
	design = yshelper.Design(name)
	clk = Signal(bool())
	debug = Signal(bool())
	inst_tb = tb(uut, clk, debug)
	inst_tb.convert("yosys_module", design, name=name, trace=False)
	design.write_verilog(name, True, False)
	design.display_rtl("$" + name, fmt='dot')
	wrapper = SelfContainingTb(tb, uut)
	run_tb(cosim_stim(wrapper), 2000)

fsm_signals = (Signal(bool(0)), Signal(test_fsm.t_State_b.SEARCH), Signal(bool(0)), Signal(bool(0)), Signal(bool(1)), test_fsm.t_State_b)

# UUT_LIST = [ (test_fsm.FramerCtrl, fsm_signals) ]

UUT_LIST_X = [ (test_toplevel_interfaces.tb_top_level_interfaces, None) ]
UUT_LIST_X += [ (test_interfaces1.c_testbench_one, None) ]
UUT_LIST_X += [ (test_interfaces1.c_testbench_two, None) ]

@pytest.mark.xfail
@pytest.mark.parametrize("uut, args", UUT_LIST)
def _test_general(uut, args):
	arst = False
	name = uut.func.__name__
	design = yshelper.Design(name)
	clk = Signal(bool())
	debug = Signal(bool())
	inst_uut = general(uut, clk, debug, args)
	inst_uut.convert("yosys_module", design, name=name, trace=False)
	design.write_verilog(name, True)
	run_tb(cosim_general(uut, args), 2000)


