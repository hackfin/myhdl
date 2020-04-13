from myhdl import *

from .cosim_common import *
from .lfsr8 import lfsr8
from .test_simple import up_counter
from myhdl import CosimulationError

import pytest

@block
def dummy_driver(clk, dout):
	"Need to insert this to satisfy cosimulation interface"
	@always(clk.posedge)
	def worker():
		dout.next = 1
	return instances()

@block
def stimulus_assert(clk, ce, reset, dout, debug):
	# Dummy to prevent 'optimization' of dout
	dummy = dummy_driver(clk, dout)

	@instance
	def stimulus():
		a = intbv(3)[4:]
		yield delay(10)
		b = intbv(3)[3:]
		assert a == b

	return instances()

@block
def stimulus_assert_fail(clk, ce, reset, dout, debug):
	# Dummy to prevent 'optimization' of dout
	dummy = dummy_driver(clk, dout)

	@instance
	def stimulus():
		a = intbv(3)[4:]
		yield delay(10)
		b = intbv(2)[3:]
		assert a == b

	return instances()

@block
def stimulus_assert(clk, ce, reset, dout, debug):
	# Dummy to prevent 'optimization' of dout
	dummy = dummy_driver(clk, dout)

	@instance
	def stimulus():
		a = intbv(3)[4:]
		yield delay(10)
		b = intbv(3)[3:]
		assert a == b

	return instances()

UUT_LIST_FAIL = [ stimulus_assert_fail ]

# These MUST fail
@pytest.mark.parametrize("uut", UUT_LIST_FAIL)
def test_stimulus_expect_fail(uut):
	arst = False
	run_conversion(uut, arst, None, False) # No wrapper, no display
	try:
		run_tb(tb_unit(uut, mapped_uut_assert, arst), 20000)
		raise AssertionError("Must fail")
	except CosimulationError:
		pass


UUT_LIST = [ stimulus_assert ]

@pytest.mark.parametrize("uut", UUT_LIST)
def test_stimulus(uut):
	arst = False
	run_conversion(uut, arst, None, False) # No wrapper, no display
	run_tb(tb_unit(uut, mapped_uut_assert, arst), 20000)

