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

#	ce_d = [ Signal(bool(0)) for i in range(2) ]
	ce_d0, ce_d1 = [ Signal(bool(0)) for i in range(2) ]

	ctr = up_counter(clk, ce, reset, counter)
	inst_mem0 = simple_lut(clk, mem0)
	inst_mem1 = simple_lut(clk, mem1)

	@always_seq(clk.posedge, reset)
	def delay():
		ce_d0.next = ce
		ce_d1.next = ce_d0

	@always_comb
	def assign():
		if ce_d1 == True:
			dout.next = mem0.data ^ mem1.data
		else:
			dout.next = 0
		debug.next = 0
		mem0.en.next = ce
		mem1.en.next = ce_d0
		mem0.addr.next = counter
		mem1.addr.next = counter

	return instances()

@block
def sig_classes1(clk, ce, reset, dout, debug):
	"Case: Signals are wired explicitely"
	mem0, mem1 = [ Bus(8, 8) for i in range(2) ]
	counter = Signal(modbv(0)[8:])

	ce_d = [ Signal(bool(0)) for i in range(2) ]

	ctr = up_counter(clk, ce, reset, counter)
	inst_mem0 = simple_lut(clk, mem0)
	inst_mem1 = simple_lut(clk, mem1)

	@always_seq(clk.posedge, reset)
	def delay():
		ce_d[0].next = ce
		ce_d[1].next = ce_d[0]

	@always_comb
	def assign():
		if ce_d[1] == True:
			dout.next = mem0.data ^ mem1.data
		else:
			dout.next = 0
		debug.next = 0
		mem0.en.next = ce
		mem1.en.next = ce_d[0]
		mem0.addr.next = counter
		mem1.addr.next = counter

	return instances()

@block
def sig_array(clk, ce, reset, dout, debug):
	"Signal array wiring"
	counter = Signal(modbv(0)[8:])
	lq = [ Signal(modbv(0)[8:]) for i in range(2) ]

	for i in range(2):
		inst_lfsr1 = lfsr8(clk, ce, reset, i, lq[i])
	# inst_lfsr2 = lfsr8(clk, ce, reset, 2, lq[1])

	@always_comb
	def assign():
		dout.next = lq[0] ^ lq[1]

	return instances()

@block
def unit(clk, ce, reset, ia, ib, q):

	@always_seq(clk.posedge, reset)
	def assign():
		q.next = ia ^ ib

	return instances()
	

@block
def unit_array(clk, ce, reset, dout, debug):
	"""Procedural instancing and signal arrays"""

	val = [ Signal(bool(0)) for i in range(3) ]

	o = Signal(modbv()[8:])
	inst_lfsr1 = lfsr8(clk, ce, reset, 0, o)

	inst = [ unit(clk, 1, reset, o(i*2), o(i*2 + 1), val[i]) for i in range(3) ]

	@always_comb
	def assign():
		debug.next = val[0] ^ val[1] ^ val[2]
		dout.next = o

	return instances()


@block
def sig_classes_hier(clk, ce, reset, dout, debug):
	"Case: submodule is driver"
	b = Bus(8, 8)
	
	q = Signal(intbv()[8:])

	inst_lfsr2 = lfsr8(clk, ce, reset, 2, b.data)
	inst_lfsr1 = lfsr8(clk, True, reset, 0, b.addr)
	# BUG: b.data/b.addr not resolved, falls back to parent 'dout'
	inst_logic = simple_logic_comb(b.data, b.addr, dout)

	return instances()

@block
def sig_classes_hier_namespace(clk, ce, reset, dout, debug):
	"Submodule is driver to bus class"
	b = Bus(8, 8)

	valid0, valid1 = [ Signal(bool(0)) for i in range(2) ]
	data = Signal(intbv()[8:])

	inst_lfsr2 = lfsr8(clk, ce, reset, 2, b.addr)
	inst_lfsr1 = lfsr8(clk, ce, reset, 0, b.data)

	inst_logic = simple_logic(clk, b.addr, b.data, data)

	@always(clk.posedge)
	def worker():
		valid1.next = valid0
		valid0.next = ce

	@always_comb
	def assign():
		if valid1:
			dout.next = data
		else:
			dout.next = 0

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
	"""This one may simulate correctly, but create warnings
in synthesis check due to incorrect in/out mapping"""
	a, b = [ Signal(modbv(0)[DWIDTH:]) for i in range(2) ]

	inst_lfsr2 = wrapper(clk, ce, reset, 2, a)

	inst_lfsr1 = lfsr8(clk, 1, reset, 0, b)

	@always_comb
	def assign():
		dout.next = a ^ b

	return instances()


UUT_LIST = [ lfsr8_multi, sig_classes ]
UUT_LIST += [ sig_classes_hier, sig_classes_hier_namespace ]
UUT_LIST += [ sig_classes1 ]
UUT_LIST += [ nested_hier, unit_array  ]
# Unresolved cases
UUT_LIST_UNRESOLVED = [ ]


@pytest.mark.parametrize("uut", UUT_LIST)
def test_mapped_uut(uut):
	arst = False
	# No wrapper, no display
	# 'check' command can crash in current yosys versions. Disabled for now
	run_conversion(uut, arst, None, False, run_check = False)
	run_tb(tb_unit(uut, mapped_uut, arst), 20000)

@pytest.mark.xfail
@pytest.mark.parametrize("uut", UUT_LIST_UNRESOLVED)
def test_unresolved(uut):
	arst = False
	run_conversion(uut, arst, None, False) # No wrapper, no display
	run_tb(tb_unit(uut, mapped_uut, arst), 20000)

