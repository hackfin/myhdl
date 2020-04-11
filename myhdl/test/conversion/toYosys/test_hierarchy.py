from myhdl import *

from .cosim_common import *
from .lfsr8 import lfsr8

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
		self.en = Signal(bool)
		self.addr = Signal(modbv()[AWIDTH:])
		self.data = Signal(modbv()[DWIDTH:])

@block
def sig_classes(clk, ce, reset, dout, debug):
	"Case: submodule is driver"
	b = Bus(8, 8)

	inst_lfsr2 = lfsr8(clk, ce, reset, 2, b.addr)
	inst_lfsr1 = lfsr8(clk, True, reset, 0, b.data)

	inst_logic = simple_logic(clk, b.addr, b.data, dout)

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

def test_multi_inst():
	UNIT = lfsr8_multi
	arst = False
	run_conversion(UNIT, arst, None, True)
	run_tb(tb_unit(UNIT, mapped_uut, arst), 200)

def test_class_signals():
	UNIT = sig_classes
	arst = False
	run_conversion(UNIT, arst, None, False)
	run_tb(tb_unit(UNIT, mapped_uut, arst), 200)

def test_nested():
	UNIT = nested_hier
	arst = False
	run_conversion(UNIT, arst)
	run_tb(tb_unit(UNIT, mapped_uut, arst), 200)


