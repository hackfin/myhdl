# Signal arrays and other signal tests
#
#
from myhdl import *
import pytest

from .cosim_common import *
from .test_simple import up_counter, up_counter_reg


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
def sig_array(clk, ce, reset, dout, debug):
	"""Procedural instances/arrays, alternate variant, explicit register"""

	counter = [ Signal(modbv(0)[8:]) for i in range(3) ]

	ctr = [ up_counter(clk, ce, reset, counter[i]) for i in range(3) ]

	@always_comb
	def assign():
		dout.next = counter[0] ^ counter[1] ^ counter[2]


	return instances()


@block
def flipflop_chain(clk, ce, reset, dout, debug):
	"""The delay `chain` tuple is pre-detected as memory, but is in fact
treated as an array of registers, because addressing is static"""
	counter = Signal(modbv(0)[8:])
	cr = ResetSignal(0, 1, isasync = False)
	ctr = up_counter(clk, ce, cr, counter)

	# This is internally created as a memory object (future: array)
	chain = [ Signal(intbv(0)[8:]) for i in range(2) ]

	@always(clk.posedge)
	def worker():
		index = counter[2:]

		if ce:
			chain[1].next = chain[0]
			chain[0].next = counter

		debug.next = True

	@always_comb
	def assign():
		cr.next = reset
		dout.next = chain[1]

	return instances()


@block
def class_arrays(clk, ce, reset, dout, debug):
	"Array of class objects"
	mem = [ Bus(8, 8) for i in range(2) ]
	counter = Signal(modbv(0)[8:])

#	ce_d = [ Signal(bool(0)) for i in range(2) ]
	ce_d0, ce_d1 = [ Signal(bool(0)) for i in range(2) ]

	ctr = up_counter(clk, ce, reset, counter)
	inst_mem = [ simple_lut(clk, mem[i]) for i in range(2) ]

	@always_seq(clk.posedge, reset)
	def delay():
		ce_d0.next = ce
		ce_d1.next = ce_d0

	@always_comb
	def assign():
		if ce_d1 == True:
			dout.next = mem[0].data ^ mem[1].data
		else:
			dout.next = 0
		debug.next = 0
		mem0.en.next = ce
		mem1.en.next = ce_d0
		mem0.addr.next = counter
		mem1.addr.next = counter

	return instances()

@block
def class_array_workaround(clk, ce, reset, dout, debug):
	"Case: Signals are wired explicitely"
	mem0, mem1 = [ Bus(8, 8) for i in range(2) ]
	counter = Signal(modbv(0)[8:])

#	ce_d = [ Signal(bool(0)) for i in range(2) ]
	ce_d0, ce_d1 = [ Signal(bool(0)) for i in range(2) ]

	m = [ mem0, mem1 ]

	ctr = up_counter(clk, ce, reset, counter)
	inst_mem = [ simple_lut(clk, m[i]) for i in range(2) ]

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

UUT_LIST = [ flipflop_chain, class_array_workaround, sig_array ]

@pytest.mark.parametrize("uut", UUT_LIST)
def test_mapped_uut(uut):
	arst = False
	run_conversion(uut, arst, None, False) # No wrapper, no display
	run_tb(tb_unit(uut, mapped_uut, arst), 2000)

UUT_LIST_UNSUPP = [ class_arrays ]

@pytest.mark.xfail
@pytest.mark.parametrize("uut", UUT_LIST_UNSUPP)
def test_mapped_uut_unsupp(uut):
	arst = False
	run_conversion(uut, arst, None, False) # No wrapper, no display
	run_tb(tb_unit(uut, mapped_uut, arst), 2000)


