# Hierarchy checks for toYosys synthesis output
#
from myhdl import *

from .cosim_common import *
from .lfsr8 import lfsr8
from .test_simple import up_counter

import pytest

@block
def simple_logic_comb(a_in, b_in, y_out):
	@always_comb
	def worker():
		y_out.next = a_in ^ b_in

	return instances()

@block
def simple_logic(clk, a_in, b_in, y_out):
	@always(clk.posedge)
	def worker():
		y_out.next = a_in ^ b_in

	return instances()

@block
def lfsr8_multi(clk, ce, reset, dout, debug):
	"Simple multi instance test for modules"
	counter = Signal(modbv(0)[8:])
	lq1, lq2, lq3 = [ Signal(modbv(0)[8:]) for i in range(3) ]

	inst_lfsr2 = lfsr8(clk, 1, reset, 2, lq1)
	inst_lfsr1 = lfsr8(clk, True, reset, 0, lq2)

	inst_lfsr_ce = lfsr8(clk, ce, reset, 0, lq3)

	ctr = up_counter(clk, ce, reset, counter)

	@always_seq(clk.posedge, reset)
	def assign():
		if counter % 3 == 0:
			dout.next = lq1
		elif counter % 3 == 1:
			dout.next = lq2
		else:
			dout.next = lq3

	return instances()

class Bus:
	def __init__(self, AWIDTH = 8, DWIDTH = 8):
		self.en = Signal(bool())
		self.addr = Signal(modbv()[AWIDTH:])
		self.data = Signal(modbv()[DWIDTH:])

@block
def simple_lut(clk, bus):
	@always(clk.posedge)
	def worker():
		if bus.en:
			bus.data.next = bus.addr ^ 0xaa

	return instances()

@block
def sig_classes(clk, ce, reset, dout, debug):
	"Case: Signals are wired explicitely"
	mem0, mem1 = [ Bus(8, 8) for i in range(2) ]
	counter = Signal(modbv(0)[8:])

	ctr = up_counter(clk, ce, reset, counter)
	inst_mem = simple_lut(clk, mem0)

	@always_comb
	def assign():
		dout.next = mem0.data
		mem0.en.next = ce
		mem0.addr.next = counter

	return instances()

@block
def sig_classes_hier(clk, ce, reset, dout, debug):
	"Case: submodule is driver"
	b = Bus(8, 8)
	
	o, p = [ Signal(intbv()[8:]) for i in range(2) ]
	q = Signal(intbv()[8:])

	inst_lfsr2 = lfsr8(clk, ce, reset, 2, b.data)
	inst_lfsr1 = lfsr8(clk, True, reset, 0, b.addr)
	# BUG: b.data/b.addr not resolved, falls back to parent 'dout'
	inst_logic = simple_logic_comb(o, p, dout)

	return instances()

@block
def sig_classes_hier_namespace(clk, ce, reset, dout, debug):
	"Make sure name space does not collide"
	b = Bus(8, 8)

	inst_lfsr2 = lfsr8(clk, ce, reset, 2, b.addr)
	inst_lfsr1 = lfsr8(clk, True, reset, 0, b.data)

	inst_logic = simple_logic(clk, b.addr, b.data, dout)

	return instances()

@block
def complex_logic(clk, a, b, y_out):
	@always(clk.posedge)
	def worker():
		y_out.next = a.addr ^ b.addr ^ a.data ^ b.data

	return instances()

@block
def wrapper(clk, ce, reset, rval, out):
	inst_lfsr = lfsr8(clk, ce, reset, rval, out)

	return instances()

@block
def nested_hier(clk, ce, reset, dout, debug, DWIDTH = 8):
	a, b = [ Signal(modbv(0)[DWIDTH:]) for i in range(2) ]

	inst_lfsr2 = wrapper(clk, ce, reset, 2, a)

	inst_lfsr1 = lfsr8(clk, 1, reset, 0, b)

	@always_comb
	def assign():
		dout.next = a ^ b

	return instances()


UUT_LIST = [ lfsr8_multi, nested_hier, sig_classes, sig_classes_hier ]

# Unresolved cases
UUT_LIST_UNRESOLVED = [ sig_classes_hier_namespace ]


@pytest.mark.parametrize("uut", UUT_LIST)
def test_mapped_uut(uut):
	arst = False
	run_conversion(uut, arst, None, False) # No wrapper, no display
	run_tb(tb_unit(uut, mapped_uut, arst), 20000)

@pytest.mark.xfail
@pytest.mark.parametrize("uut", UUT_LIST_UNRESOLVED)
def test_unresolved(uut):
	arst = False
	run_conversion(uut, arst, None, False) # No wrapper, no display
	run_tb(tb_unit(uut, mapped_uut, arst), 20000)

