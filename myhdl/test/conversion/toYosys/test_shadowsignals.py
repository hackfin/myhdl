import myhdl
from myhdl import *
from .cosim_common import *
from .lfsr8 import lfsr8
import pytest

from .test_simple import up_counter

@block
def concat1(clk, ce, reset, dout, debug):
	"Working test case"
	counter = Signal(modbv(0)[8:])
	cr = ResetSignal(0, 1, isasync = False)
	ctr = up_counter(clk, ce, cr, counter)

	part_a = Signal(modbv()[4:])
	part_b = Signal(modbv()[4:])

	data = ConcatSignal(part_b, part_a)

	# This is internally created as a memory object (future: array)
	chain = [ Signal(intbv(0)[32:]) for i in range(2) ]

	@always(clk.posedge)
	def worker():
		index = counter[2:]

		chain[1].next = chain[0]
		chain[0].next = counter

		if ce:
			part_a.next = chain[1][4:]
		else:
			part_b.next = counter[2:].signed()

		debug.next = True

	@always_comb
	def assign():
		cr.next = reset
		dout.next = data

	return instances()


@block
def bitflip(clk, ce, reset, dout, debug):
	"Bit flipping of signal"
	counter = Signal(modbv(0)[8:])
	ctr = up_counter(clk, ce, reset, counter)

	cbits = [ counter(i) for i in range(len(counter)) ]

	data = ConcatSignal(*cbits)

	@always_comb
	def assign():
		dout.next = data
		debug.next = False

	return instances()

UUT_LIST = [ concat1, bitflip ]


@pytest.mark.parametrize("uut", UUT_LIST)
def test_mapped_uut(uut):
	arst = False
	run_conversion(uut, arst, None, False) # No wrapper, no display
	run_tb(tb_unit(uut, mapped_uut, arst), 20000)

