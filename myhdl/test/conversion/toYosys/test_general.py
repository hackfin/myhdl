# Attempts to integrate parts of the general test suite
#
# - Contains a number of wrappers to drive self containing test benches with
#   parameters
#

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
# yshelper.DebugOutput.debug = True
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
	inst_tb.convert("yosys_module", design, name=name, trace=False, \
		private = True)
	design.write_verilog(name, True)
	design.display_rtl(name, fmt='dot')
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

UUT_LIST_PARAM1 = [ (test_bin2gray.bin2gray, test_bin2gray.bin2grayBench, 8) ]

@pytest.mark.xfail
@pytest.mark.parametrize("uut,bench,param", UUT_LIST_PARAM1)
def test_memory_fail(uut, bench, param):
	run_tb(cosim_bench(uut, bench, param), 2000)

# Those are not supported yet until full sequential (@instance) support is
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
	design.display_rtl(name, fmt='dot')
	wrapper = SelfContainingTb(tb, uut)
	run_tb(cosim_stim(wrapper), 2000)

############################################################################

FRAME_SIZE = 8

@block
def FramerCtrl(clk, SOF, state, syncFlag, reset_n, t_State):

	""" Framing control FSM.

	SOF -- start-of-frame output bit
	state -- FramerState output
	syncFlag -- sync pattern found indication input
	clk -- clock input
	reset_n -- active low reset

	"""

	sof = Signal(bool())
	index = Signal(intbv(0)[8:]) # position in frame

	@always_comb
	def assign():
		SOF.next = sof

	@always_seq(clk.posedge, reset_n)
	def FSM():
		i = (index + 1) % FRAME_SIZE
		index.next = i
		sof.next = 0
		if state == t_State.SEARCH:
			index.next = 1
			if syncFlag:
				state.next = t_State.CONFIRM
		elif state == t_State.CONFIRM:
			if index == 0:
				if syncFlag:
					state.next = t_State.SYNC
				else:
					state.next = t_State.SEARCH
		else:
			if index == 0:
				if not syncFlag:
					state.next = t_State.SEARCH
			# sof.next = (index == FRAME_SIZE-1)

	return FSM

@block
def FSMBench(FramerCtrl, t_State):

	SOF = Signal(bool(0))
	SOF_v = Signal(bool(0))
	syncFlag = Signal(bool(0))
	clk = Signal(bool(0))
	reset_n = ResetSignal(0, 0, isasync = True)
	state = Signal(t_State.SEARCH)
	state_v = Signal(intbv(0)[8:])

	framerctrl_inst = FramerCtrl(clk, SOF, state, syncFlag, reset_n, t_State)

	@instance
	def clkgen():
		clk.next = 0
		reset_n.next = 1
		yield delay(10)
		reset_n.next = 0
		yield delay(30)
		reset_n.next = 1
		yield delay(10)
		for i in range(1000):
			yield delay(10)
			clk.next = not clk

	table = (12, 8, 8, 4, 11, 8, 8, 7, 6, 8, 8)

	@instance
	def stimulus():
		for i in range(3):
			yield clk.posedge
		for i in range(len(table)):
			n = table[i]
			syncFlag.next = 1
			yield clk.posedge
			syncFlag.next = 0
			for j in range(n-1):
				yield clk.posedge
		# raise StopSimulation

	@instance
	def check():
		yield clk.posedge
		while True:
			yield clk.negedge
			print("negedge")
			# in the end, this should work
			# print state

	return framerctrl_inst,  clkgen, stimulus, check


# Local version of FramerCtrl:
UUT_LIST_PARAM2 = [ (FramerCtrl, FSMBench, test_fsm.t_State_b) ]

@block
def cosim_bench_param(uut, bench, param):
	"""Cosimulation run for test benches that take a block as argument
	"""

	clk = Signal(bool())
	debug0, debug1 = [ Signal(bool()) for i in range(2) ]

	wrapper = CosimObjectWrapper(uut, "clk,SOF,state,syncFlag,reset_n,t_State")
	wrapper.trace = True # Trace
	inst_uut1 = bench(wrapper, param)
	inst_uut2 = bench(uut, param)

	return instances()


# Currently not working, could be a cosimulation bug with Enum types
@pytest.mark.xfail
@pytest.mark.parametrize("uut,bench,param", UUT_LIST_PARAM2)
def test_interfaces(uut, bench, param):
	run_tb(cosim_bench_param(uut, bench, param), 3000)

